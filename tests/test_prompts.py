from __future__ import annotations

import json

import pytest

from visual_release_gate.prompts import build_prompt


def test_labels_never_enter_prompt(sample_pack):
    prompt = build_prompt(
        sample_pack, sample_pack.brief_by_id["dev_001"], "baseline_v1"
    )
    assert "primary_verdict" not in prompt.user_prompt
    assert "acceptable_verdicts" not in prompt.user_prompt
    assert "provisional_author" not in prompt.user_prompt


def test_only_current_brief_is_exposed(sample_pack):
    prompt = build_prompt(
        sample_pack, sample_pack.brief_by_id["dev_001"], "baseline_v1"
    )
    assert "brief:dev_001" in prompt.user_prompt
    assert "brief:dev_002" not in prompt.user_prompt


def test_image_order_is_target_then_references(sample_pack):
    prompt = build_prompt(
        sample_pack, sample_pack.brief_by_id["dev_001"], "baseline_v1"
    )
    payload = json.loads(prompt.user_prompt.split("\n", 1)[1])
    assert payload["image_order"][0]["role"] == "target"
    assert [row["source_id"] for row in payload["image_order"][1:]] == [
        "ref_001",
        "ref_002",
        "ref_003",
        "ref_004",
    ]


def test_ambiguity_profile_is_the_only_system_delta(sample_pack):
    brief = sample_pack.brief_by_id["dev_003"]
    baseline = build_prompt(sample_pack, brief, "baseline_v1")
    improved = build_prompt(sample_pack, brief, "ambiguity_v2")
    assert baseline.user_prompt == improved.user_prompt
    assert baseline.system_prompt != improved.system_prompt
    assert "qualitative attributes" in improved.system_prompt


def test_unknown_profile_fails(sample_pack):
    with pytest.raises(ValueError, match="unsupported"):
        build_prompt(sample_pack, sample_pack.briefs[0], "invented")  # type: ignore[arg-type]
