from __future__ import annotations

import pytest
from conftest import assessment_for

from visual_release_gate.models import VisionAssessment
from visual_release_gate.policy import PolicyError, SourceRegistry, adjudicate


@pytest.mark.parametrize(
    ("asset_id", "assessment_verdict", "expected"),
    [
        ("dev_001", "ship", "ship"),
        ("dev_006", "reject", "reject"),
        ("dev_003", "human_review", "human_review"),
        ("test_002", "ship", "unsupported"),
    ],
)
def test_all_four_decisions(sample_pack, asset_id, assessment_verdict, expected):
    brief = sample_pack.brief_by_id[asset_id]
    assessment = VisionAssessment.model_validate(
        assessment_for(
            assessment_verdict,
            required_copy=brief.required_copy is not None,
        )
    )
    review = adjudicate(assessment, brief, SourceRegistry(sample_pack))
    assert review.verdict == expected


def test_unknown_citation_fails(sample_pack):
    assessment = assessment_for("reject")
    assessment["issues"][0]["source_ids"] = ["MADE-UP"]
    with pytest.raises(PolicyError, match="unknown source"):
        adjudicate(
            VisionAssessment.model_validate(assessment),
            sample_pack.brief_by_id["dev_006"],
            SourceRegistry(sample_pack),
        )


def test_cross_brief_citation_fails(sample_pack):
    assessment = assessment_for("reject")
    assessment["issues"][0]["source_ids"] = ["brief:dev_001"]
    with pytest.raises(PolicyError, match="cross-brief"):
        adjudicate(
            VisionAssessment.model_validate(assessment),
            sample_pack.brief_by_id["dev_006"],
            SourceRegistry(sample_pack),
        )


def test_reference_only_serious_issue_fails(sample_pack):
    assessment = assessment_for("reject")
    assessment["issues"][0]["source_ids"] = ["ref_001"]
    with pytest.raises(PolicyError, match="serious issues"):
        adjudicate(
            VisionAssessment.model_validate(assessment),
            sample_pack.brief_by_id["dev_006"],
            SourceRegistry(sample_pack),
        )


def test_missing_copy_becomes_reject(sample_pack):
    assessment = assessment_for("ship", required_copy=True)
    assessment["requested_copy_status"] = "missing"
    review = adjudicate(
        VisionAssessment.model_validate(assessment),
        sample_pack.brief_by_id["dev_004"],
        SourceRegistry(sample_pack),
    )
    assert review.verdict == "reject"
    assert any("COPY-01" in issue.source_ids for issue in review.issues)


def test_external_authority_is_not_human_review(sample_pack):
    review = adjudicate(
        VisionAssessment.model_validate(assessment_for("ship")),
        sample_pack.brief_by_id["test_016"],
        SourceRegistry(sample_pack),
    )
    assert review.verdict == "unsupported"
    assert review.unverifiable_checks[0].kind == "external_authority"


def test_serious_issue_precedes_external_authority(sample_pack):
    review = adjudicate(
        VisionAssessment.model_validate(assessment_for("reject")),
        sample_pack.brief_by_id["test_002"],
        SourceRegistry(sample_pack),
    )
    assert review.verdict == "reject"
