from __future__ import annotations

import json

from visual_release_gate.cli import main


def test_validate_pack_cli(project_root, capsys):
    code = main(["validate-pack", "--pack", str(project_root / "sample_pack")])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["briefs"] == 24
    assert output["input_errors"] == 0


def test_missing_pack_cli_returns_two(tmp_path, capsys):
    code = main(["validate-pack", "--pack", str(tmp_path / "missing")])
    assert code == 2
    assert "does not exist" in capsys.readouterr().err
