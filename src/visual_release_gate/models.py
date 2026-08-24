"""Typed contracts crossing pack, provider, policy, and output boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Summary = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]

Severity = Literal["critical", "major", "minor"]
ProcessingStatus = Literal[
    "completed", "input_error", "provider_error", "budget_stopped"
]
ReleaseDecision = Literal["ship", "reject", "human_review", "unsupported"]
UnknownKind = Literal[
    "external_authority", "visual_ambiguity", "source_conflict", "other"
]
Split = Literal["development", "held_out"]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)


class PackManifest(StrictModel):
    schema_version: Literal["1.0"]
    name: NonEmpty
    version: NonEmpty
    description: NonEmpty
    guide: NonEmpty
    rules: NonEmpty
    references: NonEmpty
    briefs: NonEmpty
    feedback: NonEmpty
    labels: NonEmpty
    review_schema: NonEmpty


class PolicyRule(StrictModel):
    rule_id: NonEmpty
    title: NonEmpty
    text: NonEmpty
    default_severity: Severity


class ApprovedReference(StrictModel):
    reference_id: NonEmpty
    image_path: NonEmpty
    description: NonEmpty
    resolved_image_path: Path | None = None


class ExternalRequirement(StrictModel):
    check_id: NonEmpty
    description: NonEmpty


class AssetBrief(StrictModel):
    asset_id: NonEmpty
    split: Split
    image_path: NonEmpty
    request: NonEmpty
    required_copy: NonEmpty | None = None
    expected_action: NonEmpty | None = None
    qualitative_attributes: list[NonEmpty] = Field(default_factory=list)
    external_requirements: list[ExternalRequirement] = Field(default_factory=list)
    resolved_image_path: Path | None = None
    input_error: NonEmpty | None = None

    @model_validator(mode="after")
    def image_state_is_consistent(self) -> AssetBrief:
        # Raw JSONL rows have neither runtime field. After pack loading, one is
        # populated; the two states may never be populated simultaneously.
        if self.resolved_image_path is not None and self.input_error is not None:
            raise ValueError(
                "resolved_image_path and input_error are mutually exclusive"
            )
        return self


class PolicyFeedback(StrictModel):
    feedback_id: NonEmpty
    comment: NonEmpty
    applies_to_rule_ids: list[NonEmpty] = Field(default_factory=list)
    policy_effect: Literal["example_only", "approved_clarification", "superseded"]
    superseded_by: NonEmpty | None = None

    @property
    def active_clarification(self) -> bool:
        return (
            self.policy_effect == "approved_clarification"
            and self.superseded_by is None
        )


class CandidateIssue(StrictModel):
    severity: Severity
    observation: NonEmpty
    source_ids: list[NonEmpty] = Field(min_length=1)
    why_it_matters: NonEmpty
    suggested_fix: NonEmpty
    visibly_observable: bool = True


class PublicIssue(StrictModel):
    severity: Severity
    observation: NonEmpty
    source_ids: list[NonEmpty] = Field(min_length=1)
    why_it_matters: NonEmpty
    suggested_fix: NonEmpty


class UnverifiableCheck(StrictModel):
    check_id: NonEmpty
    reason: NonEmpty
    source_ids: list[NonEmpty] = Field(default_factory=list)
    kind: UnknownKind
    decision_critical: bool = True


class SourceConflict(StrictModel):
    description: NonEmpty
    source_ids: list[NonEmpty] = Field(min_length=2)
    decision_critical: bool = True


class VisionAssessment(StrictModel):
    summary: Summary
    issues: list[CandidateIssue] = Field(default_factory=list)
    unverifiable_checks: list[UnverifiableCheck] = Field(default_factory=list)
    action_clarity: Literal["not_applicable", "clear", "ambiguous", "mismatch"]
    action_observation: NonEmpty | None = None
    requested_copy_status: Literal[
        "not_requested", "present_correct", "missing", "incorrect", "unreadable"
    ]
    requested_copy_observation: NonEmpty | None = None
    source_conflicts: list[SourceConflict] = Field(default_factory=list)


class ProviderTelemetry(StrictModel):
    provider: NonEmpty
    model: NonEmpty
    prompt_profile: NonEmpty
    attempts: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    task_id: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    finish_reason: str | None = None


class StructuredReview(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)

    asset_id: NonEmpty
    processing_status: ProcessingStatus
    verdict: ReleaseDecision | None
    summary: Summary
    issues: list[PublicIssue] = Field(default_factory=list)
    unverifiable_checks: list[UnverifiableCheck] = Field(default_factory=list)
    blocking_reason: NonEmpty | None = None
    telemetry: ProviderTelemetry | None = None

    @model_validator(mode="after")
    def enforce_release_invariants(self) -> StructuredReview:
        if self.processing_status == "completed" and self.verdict is None:
            raise ValueError("completed reviews require a verdict")
        if self.processing_status != "completed" and self.verdict is not None:
            raise ValueError("failed or stopped reviews require a null verdict")
        if self.processing_status != "completed" and self.blocking_reason is None:
            raise ValueError("failed or stopped reviews require a blocking reason")

        serious = any(issue.severity in {"critical", "major"} for issue in self.issues)
        blocking_unknown = any(c.decision_critical for c in self.unverifiable_checks)
        if self.verdict == "ship" and (serious or blocking_unknown):
            raise ValueError("ship cannot contain a serious issue or blocking unknown")
        if self.verdict == "reject" and not serious:
            raise ValueError("reject requires a critical or major issue")
        if self.verdict == "unsupported" and not any(
            c.kind == "external_authority" and c.decision_critical
            for c in self.unverifiable_checks
        ):
            raise ValueError("unsupported requires an external-authority check")
        if self.verdict == "human_review" and not any(
            c.kind in {"visual_ambiguity", "source_conflict", "other"}
            and c.decision_critical
            for c in self.unverifiable_checks
        ):
            raise ValueError("human_review requires a decision-critical ambiguity")
        if (
            self.verdict in {"human_review", "unsupported"}
            and self.blocking_reason is None
        ):
            raise ValueError(f"{self.verdict} requires a blocking reason")
        if self.verdict in {"ship", "reject"} and self.blocking_reason is not None:
            raise ValueError(f"{self.verdict} cannot use a blocking reason")
        return self


class EvaluationLabel(StrictModel):
    asset_id: NonEmpty
    split: Split
    primary_verdict: ReleaseDecision
    acceptable_verdicts: list[ReleaseDecision] = Field(min_length=1)
    rationale: NonEmpty
    provenance: Literal["provisional_author", "reviewer_a", "reviewer_b", "adjudicated"]


class PolicyPack(StrictModel):
    root: Path
    manifest: PackManifest
    guide_text: NonEmpty
    rules: tuple[PolicyRule, ...]
    references: tuple[ApprovedReference, ...]
    briefs: tuple[AssetBrief, ...]
    feedback: tuple[PolicyFeedback, ...]
    labels: tuple[EvaluationLabel, ...]
    review_schema: dict[str, Any]

    @property
    def rule_by_id(self) -> dict[str, PolicyRule]:
        return {rule.rule_id: rule for rule in self.rules}

    @property
    def brief_by_id(self) -> dict[str, AssetBrief]:
        return {brief.asset_id: brief for brief in self.briefs}

    @property
    def label_by_asset_id(self) -> dict[str, EvaluationLabel]:
        return {label.asset_id: label for label in self.labels}
