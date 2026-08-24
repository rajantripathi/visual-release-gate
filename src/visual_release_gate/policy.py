"""Deterministic source validation and release adjudication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import (
    AssetBrief,
    CandidateIssue,
    PolicyPack,
    PublicIssue,
    SourceConflict,
    StructuredReview,
    UnverifiableCheck,
    VisionAssessment,
)

SourceKind = Literal["rule", "reference", "brief", "feedback"]


class PolicyError(ValueError):
    """Provider output violates source or release-safety policy."""


@dataclass(frozen=True, slots=True)
class Source:
    source_id: str
    kind: SourceKind
    asset_id: str | None = None
    active_clarification: bool = False


class SourceRegistry:
    def __init__(self, pack: PolicyPack) -> None:
        sources: dict[str, Source] = {}

        def add(source: Source) -> None:
            if source.source_id in sources:
                raise PolicyError(f"duplicate source ID: {source.source_id}")
            sources[source.source_id] = source

        for rule in pack.rules:
            add(Source(rule.rule_id, "rule"))
        for reference in pack.references:
            add(Source(reference.reference_id, "reference"))
        for brief in pack.briefs:
            add(Source(f"brief:{brief.asset_id}", "brief", asset_id=brief.asset_id))
        for feedback in pack.feedback:
            add(
                Source(
                    feedback.feedback_id,
                    "feedback",
                    active_clarification=feedback.active_clarification,
                )
            )
        self.sources = sources

    def validate(self, source_ids: list[str], asset_id: str) -> list[Source]:
        if len(source_ids) != len(set(source_ids)):
            raise PolicyError("source IDs must be unique")
        resolved: list[Source] = []
        for source_id in source_ids:
            source = self.sources.get(source_id)
            if source is None:
                raise PolicyError(f"unknown source ID: {source_id}")
            if source.kind == "brief" and source.asset_id != asset_id:
                raise PolicyError(f"cross-brief citation: {source_id}")
            if source.kind == "feedback" and not source.active_clarification:
                raise PolicyError(f"inactive feedback cannot be normative: {source_id}")
            resolved.append(source)
        return resolved

    def validate_issue(self, issue: CandidateIssue, asset_id: str) -> None:
        sources = self.validate(issue.source_ids, asset_id)
        if issue.severity in {"critical", "major"} and not any(
            source.kind in {"rule", "brief"} for source in sources
        ):
            raise PolicyError("serious issues require a rule or current brief")

    def validate_conflict(self, conflict: SourceConflict, asset_id: str) -> None:
        sources = self.validate(conflict.source_ids, asset_id)
        authoritative = [
            source
            for source in sources
            if source.kind == "rule" or source.active_clarification
        ]
        if len(authoritative) < 2:
            raise PolicyError("source conflict needs two active policy sources")


def adjudicate(
    assessment: VisionAssessment,
    brief: AssetBrief,
    registry: SourceRegistry,
    *,
    telemetry=None,
) -> StructuredReview:
    if brief.input_error:
        return error_review(brief.asset_id, "input_error", brief.input_error)

    issues: list[PublicIssue] = []
    checks: list[UnverifiableCheck] = []
    for candidate in assessment.issues:
        registry.validate_issue(candidate, brief.asset_id)
        if candidate.visibly_observable:
            issues.append(
                PublicIssue(
                    severity=candidate.severity,
                    observation=candidate.observation,
                    source_ids=candidate.source_ids,
                    why_it_matters=candidate.why_it_matters,
                    suggested_fix=candidate.suggested_fix,
                )
            )
        else:
            checks.append(
                UnverifiableCheck(
                    check_id=f"observation:{candidate.source_ids[0]}",
                    reason=(
                        f"Visible evidence did not establish: {candidate.observation}"
                    ),
                    source_ids=candidate.source_ids,
                    kind="visual_ambiguity",
                    decision_critical=candidate.severity in {"critical", "major"},
                )
            )

    for check in assessment.unverifiable_checks:
        registry.validate(check.source_ids, brief.asset_id)
        checks.append(check)

    if brief.expected_action and assessment.action_clarity == "mismatch":
        sources = [f"brief:{brief.asset_id}"]
        if "POSE-01" in registry.sources:
            sources.insert(0, "POSE-01")
        issues.append(
            PublicIssue(
                severity="major",
                observation=assessment.action_observation
                or "The requested action is not visibly established.",
                source_ids=sources,
                why_it_matters="The current brief requires the action to read clearly.",
                suggested_fix=(
                    "Redraw body, hand, gaze, and prop relationships so the action "
                    "is unambiguous."
                ),
            )
        )
    elif brief.expected_action and assessment.action_clarity == "ambiguous":
        checks.append(
            UnverifiableCheck(
                check_id="action_clarity",
                reason=assessment.action_observation
                or "The requested action has multiple plausible visual readings.",
                source_ids=[f"brief:{brief.asset_id}"],
                kind="visual_ambiguity",
                decision_critical=True,
            )
        )

    if brief.required_copy and assessment.requested_copy_status in {
        "missing",
        "incorrect",
        "unreadable",
    }:
        sources = [f"brief:{brief.asset_id}"]
        if "COPY-01" in registry.sources:
            sources.insert(0, "COPY-01")
        issues.append(
            PublicIssue(
                severity="major",
                observation=assessment.requested_copy_observation
                or f'The required copy "{brief.required_copy}" is not visibly correct.',
                source_ids=sources,
                why_it_matters="Release copy must match the explicit brief exactly.",
                suggested_fix=f'Render "{brief.required_copy}" clearly and verbatim.',
            )
        )

    for requirement in brief.external_requirements:
        checks.append(
            UnverifiableCheck(
                check_id=requirement.check_id,
                reason=requirement.description,
                source_ids=[f"brief:{brief.asset_id}"],
                kind="external_authority",
                decision_critical=True,
            )
        )

    for conflict in assessment.source_conflicts:
        registry.validate_conflict(conflict, brief.asset_id)
        checks.append(
            UnverifiableCheck(
                check_id="source_conflict",
                reason=conflict.description,
                source_ids=conflict.source_ids,
                kind="source_conflict",
                decision_critical=conflict.decision_critical,
            )
        )

    issues = _deduplicate_issues(issues)
    checks = _deduplicate_checks(checks)
    serious = any(issue.severity in {"critical", "major"} for issue in issues)
    external = any(
        check.kind == "external_authority" and check.decision_critical
        for check in checks
    )
    ambiguous = any(
        check.kind != "external_authority" and check.decision_critical
        for check in checks
    )

    if serious:
        verdict = "reject"
        blocking = None
    elif external:
        verdict = "unsupported"
        blocking = (
            "Release depends on authority or evidence absent from the policy pack."
        )
    elif ambiguous:
        verdict = "human_review"
        blocking = "Decision-critical visual or policy ambiguity requires a person."
    else:
        verdict = "ship"
        blocking = None

    return StructuredReview(
        asset_id=brief.asset_id,
        processing_status="completed",
        verdict=verdict,
        summary=assessment.summary,
        issues=issues,
        unverifiable_checks=checks,
        blocking_reason=blocking,
        telemetry=telemetry,
    )


def error_review(asset_id: str, status: str, reason: str) -> StructuredReview:
    safe_reason = reason[:500].strip() or "Review could not be completed."
    return StructuredReview(
        asset_id=asset_id,
        processing_status=status,
        verdict=None,
        summary="Review could not be completed safely.",
        blocking_reason=safe_reason,
    )


def _deduplicate_issues(issues: list[PublicIssue]) -> list[PublicIssue]:
    seen: set[tuple[str, str]] = set()
    unique: list[PublicIssue] = []
    for issue in issues:
        key = (issue.severity, issue.observation)
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


def _deduplicate_checks(checks: list[UnverifiableCheck]) -> list[UnverifiableCheck]:
    seen: set[tuple[str, str, bool]] = set()
    unique: list[UnverifiableCheck] = []
    for check in checks:
        key = (check.check_id, check.kind, check.decision_critical)
        if key not in seen:
            seen.add(key)
            unique.append(check)
    return unique
