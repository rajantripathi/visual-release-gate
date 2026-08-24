from __future__ import annotations

import os
from pathlib import Path

import pytest

from visual_release_gate.provider import ProviderFailure, ProviderRequest
from visual_release_gate.runware_provider import RunwareProvider, _data_uri


def test_key_is_read_from_environment_only(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("RUNWARE_API_KEY", raising=False)
    provider = RunwareProvider()
    request = ProviderRequest(
        asset_id="x",
        target_image=tmp_path / "x.png",
        reference_images=(),
        system_prompt="system",
        user_prompt="user",
        response_schema={},
        prompt_profile="baseline_v1",
    )
    with pytest.raises(ProviderFailure, match="RUNWARE_API_KEY"):
        provider.assess(request)
    assert "RUNWARE_API_KEY" not in provider.__dict__


def test_data_uri_rejects_unsupported_type(tmp_path: Path):
    path = tmp_path / "file.txt"
    path.write_text("not an image", encoding="utf-8")
    with pytest.raises(ProviderFailure, match="unsupported image"):
        _data_uri(path)


def test_no_secret_value_is_stored_in_source(project_root):
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (project_root / "src").rglob("*.py")
    )
    assert os.environ.get("RUNWARE_API_KEY", "__not_set__") not in source
