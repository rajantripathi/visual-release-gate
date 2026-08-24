"""Ordered, failure-isolated batch execution with a conservative budget gate."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from .io import write_jsonl_atomic
from .models import AssetBrief, PolicyPack, StructuredReview
from .policy import error_review
from .prompts import DEFAULT_PROFILE, PromptProfile
from .provider import ProviderFailure, VisionProvider
from .reviewer import review_asset


@dataclass(frozen=True, slots=True)
class BatchTelemetry:
    prompt_profile: str
    attempted: int
    completed: int
    input_errors: int
    provider_errors: int
    budget_stopped: int
    provider_calls: int
    duration_seconds: float
    total_cost_usd: float
    budget_limit_usd: float | None


@dataclass(frozen=True, slots=True)
class BatchResult:
    records: tuple[StructuredReview, ...]
    telemetry: BatchTelemetry
    output_path: Path


def run_batch(
    pack: PolicyPack,
    provider: VisionProvider,
    output_path: Path,
    *,
    prompt_profile: PromptProfile = DEFAULT_PROFILE,
    briefs: Iterable[AssetBrief] | None = None,
    budget_limit_usd: float | None = None,
    reserve_per_call_usd: float = 0.15,
) -> BatchResult:
    selected = tuple(briefs or pack.briefs)
    records: list[StructuredReview] = []
    total_cost = 0.0
    provider_calls = 0
    systemic_failure: ProviderFailure | None = None
    started = time.monotonic()

    for brief in selected:
        if systemic_failure is not None:
            record = error_review(
                brief.asset_id,
                "provider_error",
                f"Provider circuit open after {systemic_failure.code} failure.",
            )
        elif (
            budget_limit_usd is not None
            and total_cost + reserve_per_call_usd > budget_limit_usd
        ):
            record = error_review(
                brief.asset_id,
                "budget_stopped",
                "Conservative experiment budget reserve was reached before this call.",
            )
        else:
            try:
                record = review_asset(
                    pack, brief, provider, prompt_profile=prompt_profile
                )
                if record.telemetry:
                    provider_calls += record.telemetry.attempts
                    total_cost += record.telemetry.cost_usd or 0.0
            except ProviderFailure as exc:
                provider_calls += max(0, exc.attempts)
                total_cost += exc.cost_usd or 0.0
                record = error_review(
                    brief.asset_id,
                    "provider_error",
                    f"Provider {exc.code}: {exc.safe_message}",
                )
                if exc.code in {
                    "configuration",
                    "auth",
                    "quota",
                    "notFound",
                    "validation",
                }:
                    systemic_failure = exc

        jsonschema.validate(record.model_dump(mode="json"), pack.review_schema)
        records.append(record)

    output = write_jsonl_atomic(output_path, records)
    statuses = [record.processing_status for record in records]
    return BatchResult(
        records=tuple(records),
        telemetry=BatchTelemetry(
            prompt_profile=prompt_profile,
            attempted=len(records),
            completed=statuses.count("completed"),
            input_errors=statuses.count("input_error"),
            provider_errors=statuses.count("provider_error"),
            budget_stopped=statuses.count("budget_stopped"),
            provider_calls=provider_calls,
            duration_seconds=round(time.monotonic() - started, 3),
            total_cost_usd=round(total_cost, 8),
            budget_limit_usd=budget_limit_usd,
        ),
        output_path=output,
    )
