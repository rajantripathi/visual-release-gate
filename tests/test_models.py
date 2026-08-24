from __future__ import annotations

import pytest
from pydantic import ValidationError

from visual_release_gate.models import PublicIssue, StructuredReview, UnverifiableCheck


def _issue():
    return PublicIssue(
        severity="major",
        observation="Visible mismatch.",
        source_ids=["RULE-01"],
        why_it_matters="It blocks release.",
        suggested_fix="Correct the visible mismatch.",
    )


def _check(kind="visual_ambiguity"):
    return UnverifiableCheck(
        check_id="check",
        reason="Evidence is incomplete.",
        kind=kind,
        decision_critical=True,
    )


def test_ship_cannot_contain_serious_issue():
    with pytest.raises(ValidationError, match="ship"):
        StructuredReview(
            asset_id="x",
            processing_status="completed",
            verdict="ship",
            summary="Summary",
            issues=[_issue()],
        )


def test_reject_requires_serious_issue():
    with pytest.raises(ValidationError, match="reject"):
        StructuredReview(
            asset_id="x",
            processing_status="completed",
            verdict="reject",
            summary="Summary",
        )


def test_human_review_requires_ambiguity():
    with pytest.raises(ValidationError, match="human_review"):
        StructuredReview(
            asset_id="x",
            processing_status="completed",
            verdict="human_review",
            summary="Summary",
            blocking_reason="Needs a person.",
        )


def test_unsupported_requires_external_authority():
    with pytest.raises(ValidationError, match="unsupported"):
        StructuredReview(
            asset_id="x",
            processing_status="completed",
            verdict="unsupported",
            summary="Summary",
            unverifiable_checks=[_check()],
            blocking_reason="Evidence missing.",
        )


def test_provider_error_requires_null_verdict_and_reason():
    record = StructuredReview(
        asset_id="x",
        processing_status="provider_error",
        verdict=None,
        summary="Failed safely.",
        blocking_reason="Provider unavailable.",
    )
    assert record.verdict is None
