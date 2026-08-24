"""Provider-neutral request/response types and deterministic test provider."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .models import ProviderTelemetry


@dataclass(frozen=True, slots=True)
class ReferenceImage:
    source_id: str
    path: Path


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    asset_id: str
    target_image: Path
    reference_images: tuple[ReferenceImage, ...]
    system_prompt: str
    user_prompt: str
    response_schema: Mapping[str, Any]
    prompt_profile: str


@dataclass(frozen=True, slots=True)
class ProviderResult:
    assessment: Mapping[str, Any]
    telemetry: ProviderTelemetry


class VisionProvider(Protocol):
    def assess(self, request: ProviderRequest) -> ProviderResult:
        """Return one structured visual assessment."""


class ProviderFailure(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool = False,
        attempts: int = 1,
        request_id: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable
        self.attempts = attempts
        self.request_id = request_id
        self.cost_usd = cost_usd


class MappingProvider:
    """Offline provider used by tests and documented examples."""

    def __init__(self, assessments: Mapping[str, Mapping[str, Any]]) -> None:
        self.assessments = dict(assessments)

    def assess(self, request: ProviderRequest) -> ProviderResult:
        if request.asset_id not in self.assessments:
            raise ProviderFailure(code="not_found", message="fixture is missing")
        return ProviderResult(
            assessment=self.assessments[request.asset_id],
            telemetry=ProviderTelemetry(
                provider="offline",
                model="fixture",
                prompt_profile=request.prompt_profile,
                attempts=1,
                latency_ms=0,
                cost_usd=0.0,
            ),
        )
