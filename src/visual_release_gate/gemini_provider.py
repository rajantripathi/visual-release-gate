"""Google Gemini structured-vision adapter.

A provider-neutral alternative to :mod:`runware_provider`, targeting the free
Google AI Studio tier. It mirrors the Runware adapter's contract exactly:
bounded application-owned retries, a terminal-failure circuit breaker, and
provider telemetry. Credentials are read only from the environment
(``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``); no key is ever stored on the
instance or written to disk.

The Gemini free tier bills at no cost, so ``cost_usd`` is reported as ``0.0``;
budget accounting therefore never trips and every case runs.
"""

from __future__ import annotations

import copy
import json
import mimetypes
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import ProviderTelemetry
from .provider import ProviderFailure, ProviderRequest, ProviderResult

DEFAULT_MODEL = "gemini-3.6-flash"
_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
_TERMINAL = {"auth", "validation", "notFound", "configuration"}
_RETRYABLE = {"rateLimit", "serverError", "provider", "timeout", "connection"}
# Keys that pydantic's JSON Schema emits but Gemini's structured-output dialect
# rejects (it accepts only an OpenAPI 3.0 subset).
_SCHEMA_DROP = {"additionalProperties", "title", "default", "$defs", "$ref", "$schema"}


class GeminiProvider:
    """Reads credentials only from ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        timeout_ms: int = 90_000,
        max_attempts: int = 5,
        backoff_seconds: float = 0.75,
    ) -> None:
        if timeout_ms <= 0 or not 1 <= max_attempts <= 5 or backoff_seconds < 0:
            raise ValueError("invalid Gemini retry or timeout configuration")
        self.model = model
        self.timeout_ms = timeout_ms
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self._terminal_failure: ProviderFailure | None = None
        self._schema_cache: dict[str, Any] | None = None

    def assess(self, request: ProviderRequest) -> ProviderResult:
        if self._terminal_failure is not None:
            failure = self._terminal_failure
            raise ProviderFailure(
                code=failure.code, message=failure.safe_message, attempts=0
            )
        import os

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self._terminal_failure = ProviderFailure(
                code="configuration",
                message="GEMINI_API_KEY (or GOOGLE_API_KEY) is not set.",
                attempts=0,
            )
            raise self._terminal_failure

        client, types = self._client(api_key)
        contents = [types.Content(role="user", parts=self._parts(request, types))]
        config = types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            temperature=0.1,
            top_p=0.9,
            max_output_tokens=8192,
            response_mime_type="application/json",
            response_schema=self._response_schema(request.response_schema),
        )

        started = time.monotonic()
        last: ProviderFailure | None = None
        for attempt in range(1, self.max_attempts + 1):
            task_id = str(uuid4())
            try:
                response = client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                return self._result(
                    response,
                    request=request,
                    attempts=attempt,
                    latency_ms=round((time.monotonic() - started) * 1000),
                    task_id=task_id,
                )
            except ProviderFailure as exc:
                last = ProviderFailure(
                    code=exc.code,
                    message=exc.safe_message,
                    retryable=exc.retryable,
                    attempts=attempt,
                    request_id=exc.request_id or task_id,
                )
            except Exception as exc:
                last = self._from_exception(exc, task_id, attempt)

            if not last.retryable or attempt == self.max_attempts:
                if last.code in _TERMINAL:
                    self._terminal_failure = last
                raise last
            time.sleep(min(self.backoff_seconds * 2 ** (attempt - 1), 30.0))

        assert last is not None
        raise last

    def _response_schema(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        if self._schema_cache is None:
            defs = raw.get("$defs", {}) if isinstance(raw, Mapping) else {}
            self._schema_cache = _gemini_schema(raw, defs)
        return self._schema_cache

    def _client(self, api_key: str):  # noqa: ANN202 - external SDK types
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderFailure(
                code="configuration",
                message="google-genai is not installed; install the 'gemini' extra.",
                attempts=0,
            ) from exc
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=self.timeout_ms),
        )
        return client, types

    def _parts(self, request: ProviderRequest, types):  # noqa: ANN001,ANN202
        parts = [types.Part.from_text(text=request.user_prompt)]
        images = [request.target_image, *(r.path for r in request.reference_images)]
        for path in images:
            raw, mime = _read_image(path)
            parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
        return parts

    def _result(
        self,
        response,  # noqa: ANN001 - external SDK type
        *,
        request: ProviderRequest,
        attempts: int,
        latency_ms: int,
        task_id: str,
    ) -> ProviderResult:
        candidate = next(iter(getattr(response, "candidates", None) or []), None)
        finish = getattr(candidate, "finish_reason", None)
        finish_s = getattr(finish, "name", None) or (
            str(finish) if finish is not None else None
        )
        if finish_s and any(
            flag in finish_s.upper() for flag in ("SAFETY", "PROHIBITED", "BLOCK")
        ):
            raise ProviderFailure(
                code="safety",
                message="provider safety controls blocked the assessment",
                request_id=task_id,
                cost_usd=0.0,
            )

        text = getattr(response, "text", None)
        if not text:
            raise ProviderFailure(
                code="invalidResponse",
                message="Gemini returned an empty response.",
                retryable=True,
                attempts=attempts,
                request_id=task_id,
            )
        try:
            assessment = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ProviderFailure(
                code="invalidResponse",
                message="Gemini returned invalid structured JSON",
                retryable=True,
                attempts=attempts,
                request_id=task_id,
            ) from exc
        if not isinstance(assessment, Mapping):
            raise ProviderFailure(
                code="invalidResponse",
                message="Gemini did not return a JSON object",
                retryable=True,
                request_id=task_id,
            )

        return ProviderResult(
            assessment=dict(assessment),
            telemetry=ProviderTelemetry(
                provider="google",
                model=self.model,
                prompt_profile=request.prompt_profile,
                attempts=attempts,
                latency_ms=latency_ms,
                cost_usd=0.0,
                task_id=task_id,
                usage=_usage(getattr(response, "usage_metadata", None)),
                finish_reason=finish_s[:40] if finish_s else None,
            ),
        )

    def _from_exception(
        self, exc: Exception, request_id: str, attempts: int
    ) -> ProviderFailure:
        status = next(
            (
                value
                for attr in ("code", "status_code", "status")
                if isinstance(value := getattr(exc, attr, None), int)
            ),
            None,
        )
        if status in {401, 403}:
            code, message = "auth", "Gemini authentication failed."
        elif status == 400:
            code, message = "validation", "Gemini rejected the request shape."
        elif status == 404:
            code, message = "notFound", "Configured Gemini model was not found."
        elif status == 429:
            code, message = "rateLimit", "Gemini rate limit or free-tier quota reached."
        elif status in {500, 502, 503, 504}:
            code, message = "serverError", "Gemini returned a server error."
        else:
            text = str(exc).lower()
            if any(w in text for w in ("api key", "permission", "unauthenticated")):
                code, message = "auth", "Gemini authentication failed."
            elif any(w in text for w in ("quota", "rate", "resource_exhausted")):
                code, message = (
                    "rateLimit",
                    "Gemini rate limit or free-tier quota reached.",
                )
            else:
                code, message = "provider", "The Gemini request failed."
        return ProviderFailure(
            code=code,
            message=message,
            retryable=code in _RETRYABLE,
            attempts=attempts,
            request_id=request_id,
        )


def _gemini_schema(node: Any, defs: Mapping[str, Any]) -> Any:
    """Translate a pydantic JSON Schema into Gemini's structured-output dialect.

    Gemini accepts only an OpenAPI 3.0 subset: it rejects ``additionalProperties``
    and ``$ref``/``$defs``, and expresses "optional" as ``nullable: true`` rather
    than a ``{"type": "null"}`` union member. This inlines refs, drops the
    unsupported keys, and collapses nullable unions.
    """
    if isinstance(node, list):
        return [_gemini_schema(item, defs) for item in node]
    if not isinstance(node, Mapping):
        return node
    if "$ref" in node:
        name = node["$ref"].split("/")[-1]
        return _gemini_schema(copy.deepcopy(defs[name]), defs)
    if "anyOf" in node:
        variants = node["anyOf"]
        non_null = [v for v in variants if v.get("type") != "null"]
        has_null = any(v.get("type") == "null" for v in variants)
        if len(non_null) == 1:
            collapsed = _gemini_schema(non_null[0], defs)
        else:
            collapsed = {"anyOf": [_gemini_schema(v, defs) for v in non_null]}
        if has_null:
            collapsed["nullable"] = True
        if "description" in node:
            collapsed.setdefault("description", node["description"])
        return collapsed
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key in _SCHEMA_DROP:
            continue
        cleaned[key] = _gemini_schema(value, defs)
    return cleaned


def _read_image(path: Path) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProviderFailure(
            code="input", message=f"cannot read image: {path.name}"
        ) from exc
    mime, _ = mimetypes.guess_type(path.name)
    if not raw or mime not in _ALLOWED_MIME:
        raise ProviderFailure(code="input", message=f"unsupported image: {path.name}")
    return raw, mime


def _usage(metadata) -> dict[str, int]:  # noqa: ANN001 - external SDK type
    if metadata is None:
        return {}
    fields = {
        "prompt_tokens": "prompt_token_count",
        "candidates_tokens": "candidates_token_count",
        "total_tokens": "total_token_count",
    }
    usage = {}
    for out_key, attr in fields.items():
        value = getattr(metadata, attr, None)
        if isinstance(value, int):
            usage[out_key] = value
    return usage
