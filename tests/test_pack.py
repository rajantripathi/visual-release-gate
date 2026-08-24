from __future__ import annotations

import json
from pathlib import Path

import pytest

from visual_release_gate.pack import PackError, _resolve_inside, load_pack


def test_sample_pack_shape(sample_pack):
    assert len(sample_pack.rules) == 5
    assert len(sample_pack.references) == 4
    assert len(sample_pack.briefs) == 24
    assert len(sample_pack.labels) == 24
    assert sum(b.split == "development" for b in sample_pack.briefs) == 8
    assert sum(b.split == "held_out" for b in sample_pack.briefs) == 16


def test_every_image_is_resolved(sample_pack):
    assert all(b.resolved_image_path and not b.input_error for b in sample_pack.briefs)
    assert all(r.resolved_image_path for r in sample_pack.references)


@pytest.mark.parametrize("value", ["../secret", "/etc/passwd", "C:\\secret", ""])
def test_unsafe_paths_fail(tmp_path: Path, value: str):
    with pytest.raises(PackError):
        _resolve_inside(tmp_path, value)


def test_missing_manifest_fails(tmp_path: Path):
    with pytest.raises(PackError, match="missing"):
        load_pack(tmp_path)


def test_duplicate_rule_ids_fail(project_root: Path, tmp_path: Path):
    source = project_root / "sample_pack"
    # Build only enough of a copied pack to exercise duplicate validation.
    import shutil

    shutil.copytree(source, tmp_path / "pack")
    rules = tmp_path / "pack/policy/rules.jsonl"
    first = rules.read_text(encoding="utf-8").splitlines()[0]
    rules.write_text(rules.read_text(encoding="utf-8") + first + "\n", encoding="utf-8")
    with pytest.raises(PackError, match="duplicate rule"):
        load_pack(tmp_path / "pack")


def test_label_coverage_is_exact(project_root: Path, tmp_path: Path):
    import shutil

    shutil.copytree(project_root / "sample_pack", tmp_path / "pack")
    labels = tmp_path / "pack/data/labels.jsonl"
    rows = [
        row for row in labels.read_text(encoding="utf-8").splitlines() if row.strip()
    ]
    labels.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(PackError, match="cover every brief"):
        load_pack(tmp_path / "pack")


def test_manifest_version_fails_closed(project_root: Path, tmp_path: Path):
    import shutil

    shutil.copytree(project_root / "sample_pack", tmp_path / "pack")
    manifest = tmp_path / "pack/pack.json"
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["schema_version"] = "2.0"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PackError, match="invalid JSON"):
        load_pack(tmp_path / "pack")
