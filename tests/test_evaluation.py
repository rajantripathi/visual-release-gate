from __future__ import annotations

from visual_release_gate.evaluation import paired_evaluation, reviewer_agreement, score
from visual_release_gate.models import EvaluationLabel, StructuredReview


def _review(asset_id: str, verdict: str) -> StructuredReview:
    kwargs = {}
    if verdict == "reject":
        kwargs["issues"] = [
            {
                "severity": "major",
                "observation": "Mismatch.",
                "source_ids": ["RULE"],
                "why_it_matters": "Blocks release.",
                "suggested_fix": "Fix it.",
            }
        ]
    elif verdict == "human_review":
        kwargs["unverifiable_checks"] = [
            {
                "check_id": "ambiguous",
                "reason": "Ambiguous.",
                "source_ids": [],
                "kind": "visual_ambiguity",
                "decision_critical": True,
            }
        ]
        kwargs["blocking_reason"] = "Needs a person."
    elif verdict == "unsupported":
        kwargs["unverifiable_checks"] = [
            {
                "check_id": "rights",
                "reason": "Rights absent.",
                "source_ids": [],
                "kind": "external_authority",
                "decision_critical": True,
            }
        ]
        kwargs["blocking_reason"] = "Authority absent."
    return StructuredReview(
        asset_id=asset_id,
        processing_status="completed",
        verdict=verdict,
        summary="Summary",
        **kwargs,
    )


def _labels():
    return [
        EvaluationLabel(
            asset_id=f"case_{index}",
            split="development" if index < 2 else "held_out",
            primary_verdict=verdict,
            acceptable_verdicts=[verdict],
            rationale="Rationale",
            provenance="adjudicated",
        )
        for index, verdict in enumerate(
            ["ship", "reject", "human_review", "unsupported"]
        )
    ]


def test_perfect_score():
    labels = _labels()
    reviews = [_review(label.asset_id, label.primary_verdict) for label in labels]
    result = score(labels, reviews)
    assert result["primary_accuracy"] == 1.0
    assert result["macro_f1"] == 1.0
    assert result["serious_false_approvals"] == 0


def test_serious_false_approval_is_visible():
    labels = _labels()
    reviews = [_review(label.asset_id, label.primary_verdict) for label in labels]
    reviews[1] = _review("case_1", "ship")
    result = score(labels, reviews)
    assert result["serious_false_approvals"] == 1
    assert result["unsafe_approvals"] == 1


def test_reviewer_agreement_perfect():
    labels = _labels()
    result = reviewer_agreement(labels, labels)
    assert result["raw_agreement"] == 1.0
    assert result["cohens_kappa"] == 1.0


def test_reviewer_disagreement_is_listed():
    a = _labels()
    b = _labels()
    b[0] = b[0].model_copy(update={"primary_verdict": "reject"})
    result = reviewer_agreement(a, b)
    assert result["disagreements"][0]["asset_id"] == "case_0"


def test_paired_report_keeps_held_out_separate():
    labels = _labels()
    reviews = [_review(label.asset_id, label.primary_verdict) for label in labels]
    report = paired_evaluation(labels, reviews, reviews)
    assert report["development"]["improved"]["case_count"] == 2
    assert report["held_out"]["improved"]["case_count"] == 2
