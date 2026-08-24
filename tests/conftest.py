from __future__ import annotations

from pathlib import Path

import pytest

from visual_release_gate.models import PolicyPack
from visual_release_gate.pack import load_pack


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def sample_pack(project_root: Path) -> PolicyPack:
    return load_pack(project_root / "sample_pack")


def assessment_for(verdict: str, *, required_copy: bool = False) -> dict[str, object]:
    assessment: dict[str, object] = {
        "summary": "Fixture observation for deterministic tests.",
        "issues": [],
        "unverifiable_checks": [],
        "action_clarity": "clear",
        "action_observation": "The requested action is visible.",
        "requested_copy_status": "present_correct"
        if required_copy
        else "not_requested",
        "requested_copy_observation": "The requested copy is visible."
        if required_copy
        else None,
        "source_conflicts": [],
    }
    if verdict == "reject":
        assessment["issues"] = [
            {
                "severity": "major",
                "observation": "A visible treatment conflicts with the active policy.",
                "source_ids": ["STYLE-01"],
                "why_it_matters": "The active style rule is release-blocking.",
                "suggested_fix": "Redraw the target with flat fills.",
                "visibly_observable": True,
            }
        ]
    elif verdict == "human_review":
        assessment["action_clarity"] = "ambiguous"
        assessment["action_observation"] = (
            "Multiple important readings remain plausible."
        )
    return assessment
