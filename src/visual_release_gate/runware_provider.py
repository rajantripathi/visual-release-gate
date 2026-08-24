"""Runware structured-vision adapter with bounded application-owned retries."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import ProviderTelemetry
from .provider import ProviderFailure, ProviderRequest, ProviderResult

DEFAULT_MODEL = "google-gemini-3-5-flash"
_TRANSIENT = {
    "rateLimit",
    "timeout",
    "provider",
    "serverError",
    "connection",
    "invalidResponse",
}
_TERMINAL = {"validation", "auth", "quota", "notFound", "configuration"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RunwareProvider:
    """Reads credentials only from ``RUNWARE_API_KEY``."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        timeout_ms: int = 90_000,
        max_attempts: int = 3,
        backoff_seconds: float = 0.75,
    ) -> None:
        if timeout_ms <= 0 or not 1 <= max_attempts <= 5 or backoff_seconds < 0:
            raise ValueError("invalid Runware retry or timeout configuration")
        self.model = model
        self.timeout_ms = timeout_ms
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._terminal_failure: ProviderFailure | None = None

    def assess(self, request: ProviderRequest) -> ProviderResult:
        if self._terminal_failure is not None:
            failure = self._terminal_failure
            raise ProviderFailure(
                code=failure.code,
                message=failure.safe_message,
                attempts=0,
                request_id=failure.request_id,
            )
        api_key = os.environ.get("RUNWARE_API_KEY")
        if not api_key:
            self._terminal_failure = ProviderFailure(
                code="configuration", message="RUNWARE_API_KEY is not set.", attempts=0
            )
            raise self._terminal_failure

        images = _encode_images(request)
        accrued_cost = 0.0
        has_cost = False
        started = time.monotonic()
        last: ProviderFailure | None = None
        for attempt in range(1, self.max_attempts + 1):
            task_id = str(uuid4())
            try:
                response = asyncio.run(
                    self._invoke(self._payload(request, images, task_id), api_key)
                )
                result = _parse_response(
                    response,
                    model=self.model,
                    profile=request.prompt_profile,
                    attempts=attempt,
                    latency_ms=round((time.monotonic() - started) * 1000),
                    fallback_task_id=task_id,
                )
                if result.telemetry.cost_usd is not None:
                    accrued_cost += result.telemetry.cost_usd
                    has_cost = True
                if has_cost:
                    result = ProviderResult(
                        assessment=result.assessment,
                        telemetry=result.telemetry.model_copy(
                            update={"cost_usd": round(accrued_cost, 8)}
                        ),
                    )
                return result
            except ProviderFailure as exc:
                if exc.cost_usd is not None:
                    accrued_cost += exc.cost_usd
                    has_cost = True
                last = ProviderFailure(
                    code=exc.code,
                    message=exc.safe_message,
                    retryable=exc.retryable,
                    attempts=attempt,
                    request_id=exc.request_id or task_id,
                    cost_usd=round(accrued_cost, 8) if has_cost else None,
                )
            except Exception as exc:
                last = _from_exception(exc, task_id, attempt)

            if not last.retryable or attempt == self.max_attempts:
                if last.code in _TERMINAL:
                    self._terminal_failure = last
                raise last
            time.sleep(min(self.backoff_seconds * 2 ** (attempt - 1), 4.0))
        assert last is not None
        raise last

    def _payload(
        self, request: ProviderRequest, images: Sequence[str], task_id: str
    ) -> dict[str, Any]:
        return {
            "taskType": "textInference",
            "taskUUID": task_id,
            "model": self.model,
            "deliveryMethod": "sync",
            "numberResults": 1,
            "outputFormat": "JSON",
            "jsonSchema": {
                "name": "visual_release_assessment",
                "strict": True,
                "schema": dict(request.response_schema),
            },
            "includeCost": True,
            "includeUsage": True,
            "seed": 1729,
            "settings": {
                "systemPrompt": request.system_prompt,
                "temperature": 0.1,
                "topP": 0.9,
                "maxTokens": 8192,
                "thinkingLevel": "medium",
            },
            "providerSettings": {"google": {"mediaResolution": "high"}},
            "inputs": {"images": list(images)},
            "messages": [{"role": "user", "content": request.user_prompt}],
        }

    async def _invoke(self, payload: Mapping[str, Any], api_key: str) -> Any:
        try:
            from runware import Runware
        except ImportError as exc:
            raise ProviderFailure(
                code="configuration",
                message="runware-sdk is not installed.",
                attempts=0,
            ) from exc
        async with Runware(
            api_key=api_key,
            transport="rest",
            timeout=self.timeout_ms,
            max_retries=0,
            validate=False,
            debug=False,
        ) as client:
            return await client.run(dict(payload))


def _encode_images(request: ProviderRequest) -> tuple[str, ...]:
    paths = [request.target_image, *(r.path for r in request.reference_images)]
    return tuple(_data_uri(path) for path in paths)


def _data_uri(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProviderFailure(
            code="input", message=f"cannot read image: {path.name}"
        ) from exc
    mime, _ = mimetypes.guess_type(path.name)
    if not raw or mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise ProviderFailure(code="input", message=f"unsupported image: {path.name}")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def _parse_response(
    response: Any,
    *,
    model: str,
    profile: str,
    attempts: int,
    latency_ms: int,
    fallback_task_id: str,
) -> ProviderResult:
    items = (
        response.get("data")
        if isinstance(response, Mapping) and "data" in response
        else response
    )
    if (
        not isinstance(items, Sequence)
        or isinstance(items, (str, bytes))
        or len(items) != 1
    ):
        raise ProviderFailure(
            code="invalidResponse",
            message="Runware did not return exactly one result.",
            retryable=True,
            attempts=attempts,
            request_id=fallback_task_id,
        )
    item = items[0]
    if hasattr(item, "model_dump"):
        item = item.model_dump(mode="python")
    if not isinstance(item, Mapping):
        raise ProviderFailure(
            code="invalidResponse", message="malformed Runware result", retryable=True
        )
    task_id = (
        _safe_id(_first(item, "taskUUID", "taskUuid", "task_id")) or fallback_task_id
    )
    finish_reason = _first(item, "finishReason", "finish_reason")
    cost = _cost(item.get("cost"))
    if finish_reason == "content_filter":
        raise ProviderFailure(
            code="safety",
            message="provider safety controls blocked the assessment",
            request_id=task_id,
            cost_usd=cost,
        )
    raw = _first(item, "text", "output")
    try:
        assessment = dict(raw) if isinstance(raw, Mapping) else json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProviderFailure(
            code="invalidResponse",
            message="provider returned invalid structured JSON",
            retryable=True,
            request_id=task_id,
            cost_usd=cost,
        ) from exc
    usage = item.get("usage") if isinstance(item.get("usage"), Mapping) else {}
    return ProviderResult(
        assessment=assessment,
        telemetry=ProviderTelemetry(
            provider="runware",
            model=model,
            prompt_profile=profile,
            attempts=attempts,
            latency_ms=latency_ms,
            cost_usd=cost,
            task_id=task_id,
            usage=dict(usage),
            finish_reason=str(finish_reason)[:40]
            if finish_reason is not None
            else None,
        ),
    )


def _from_exception(exc: Exception, request_id: str, attempts: int) -> ProviderFailure:
    raw_code = getattr(exc, "code", "unknown")
    code = str(getattr(raw_code, "value", raw_code))
    messages = {
        "validation": "Runware rejected the request shape.",
        "auth": "Runware authentication failed.",
        "quota": "Runware quota or credit is unavailable.",
        "rateLimit": "Runware rate limit was reached.",
        "timeout": "Runware request timed out.",
        "notFound": "Configured Runware model was not found.",
        "serverError": "Runware returned a server error.",
        "connection": "Runware could not be reached.",
        "provider": "The upstream model provider failed.",
    }
    if code not in messages:
        code = "unknown"
    return ProviderFailure(
        code=code,
        message=messages.get(code, "Runware request failed."),
        retryable=code in _TRANSIENT,
        attempts=attempts,
        request_id=request_id,
    )


def _first(mapping: Mapping[str, Any], *names: str) -> Any:
    return next((mapping[name] for name in names if name in mapping), None)


def _safe_id(value: Any) -> str | None:
    candidate = "" if value is None else str(value)
    return candidate if _SAFE_ID.fullmatch(candidate) else None


def _cost(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number < 1_000_000 else None
