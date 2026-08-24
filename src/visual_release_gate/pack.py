"""Versioned policy-pack loading with fail-closed path and schema checks."""

from __future__ import annotations

import json
import warnings
from pathlib import Path, PureWindowsPath
from typing import TypeVar

import jsonschema
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ValidationError

from .models import (
    ApprovedReference,
    AssetBrief,
    EvaluationLabel,
    PackManifest,
    PolicyFeedback,
    PolicyPack,
    PolicyRule,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class PackError(ValueError):
    """The supplied pack is missing, malformed, or unsafe to traverse."""


def _resolve_inside(root: Path, relative_value: str) -> Path:
    relative = Path(relative_value)
    windows = PureWindowsPath(relative_value)
    if not relative_value or "\x00" in relative_value:
        raise PackError("pack path is empty or invalid")
    if relative.is_absolute() or windows.is_absolute() or windows.drive:
        raise PackError(f"pack path must be relative: {relative_value!r}")
    if ".." in relative.parts:
        raise PackError(f"pack path cannot traverse upward: {relative_value!r}")
    try:
        candidate = (root / relative).resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, ValueError) as exc:
        raise PackError(
            f"pack path is missing or escapes the root: {relative_value!r}"
        ) from exc
    return candidate


def _read_json(path: Path, model: type[ModelT]) -> ModelT:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        raise PackError(f"invalid JSON object: {path.name}") from exc


def _read_jsonl(path: Path, model: type[ModelT]) -> list[ModelT]:
    rows: list[ModelT] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise PackError(f"cannot read UTF-8 JSONL: {path.name}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rows.append(model.model_validate_json(line))
        except ValidationError as exc:
            raise PackError(
                f"invalid {path.name} record at line {line_number}"
            ) from exc
    return rows


def _unique(rows: list[BaseModel], field: str, label: str) -> None:
    values = [getattr(row, field) for row in rows]
    if len(values) != len(set(values)):
        raise PackError(f"duplicate {label} identifiers")


def _verify_image(path: Path) -> None:
    if not path.is_file():
        raise PackError(f"image is not a file: {path.name}")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
                if image.width < 1 or image.height < 1:
                    raise PackError(f"image has invalid dimensions: {path.name}")
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise PackError(f"image cannot be decoded safely: {path.name}") from exc


def load_pack(pack_path: str | Path) -> PolicyPack:
    try:
        root = Path(pack_path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PackError("pack root does not exist") from exc
    if not root.is_dir():
        raise PackError("pack root must be a directory")

    manifest = _read_json(_resolve_inside(root, "pack.json"), PackManifest)
    guide_path = _resolve_inside(root, manifest.guide)
    try:
        guide_text = guide_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PackError("guide must be readable UTF-8") from exc
    if not guide_text.strip():
        raise PackError("guide cannot be empty")

    rules = _read_jsonl(_resolve_inside(root, manifest.rules), PolicyRule)
    references = _read_jsonl(
        _resolve_inside(root, manifest.references), ApprovedReference
    )
    brief_rows = _read_jsonl(_resolve_inside(root, manifest.briefs), AssetBrief)
    feedback = _read_jsonl(_resolve_inside(root, manifest.feedback), PolicyFeedback)
    labels = _read_jsonl(_resolve_inside(root, manifest.labels), EvaluationLabel)
    if not rules or not references or not brief_rows:
        raise PackError("rules, references, and briefs cannot be empty")

    _unique(rules, "rule_id", "rule")
    _unique(references, "reference_id", "reference")
    _unique(brief_rows, "asset_id", "brief")
    _unique(feedback, "feedback_id", "feedback")
    _unique(labels, "asset_id", "label")

    resolved_references: list[ApprovedReference] = []
    for reference in references:
        image = _resolve_inside(root, reference.image_path)
        _verify_image(image)
        resolved_references.append(
            reference.model_copy(update={"resolved_image_path": image})
        )

    briefs: list[AssetBrief] = []
    for row in brief_rows:
        try:
            image = _resolve_inside(root, row.image_path)
            _verify_image(image)
            briefs.append(
                row.model_copy(
                    update={"resolved_image_path": image, "input_error": None}
                )
            )
        except PackError as exc:
            briefs.append(
                row.model_copy(
                    update={"resolved_image_path": None, "input_error": str(exc)}
                )
            )

    rule_ids = {rule.rule_id for rule in rules}
    for item in feedback:
        unknown = set(item.applies_to_rule_ids) - rule_ids
        if unknown:
            raise PackError(f"{item.feedback_id} cites unknown rule IDs")
    brief_ids = {brief.asset_id for brief in briefs}
    if {label.asset_id for label in labels} != brief_ids:
        raise PackError("labels must cover every brief exactly once")
    for label in labels:
        if label.split != next(b.split for b in briefs if b.asset_id == label.asset_id):
            raise PackError(f"label split mismatch for {label.asset_id}")

    schema_path = _resolve_inside(root, manifest.review_schema)
    try:
        review_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(review_schema)
    except (OSError, UnicodeError, json.JSONDecodeError, jsonschema.SchemaError) as exc:
        raise PackError("review schema is invalid") from exc

    return PolicyPack(
        root=root,
        manifest=manifest,
        guide_text=guide_text,
        rules=tuple(rules),
        references=tuple(resolved_references),
        briefs=tuple(briefs),
        feedback=tuple(feedback),
        labels=tuple(labels),
        review_schema=review_schema,
    )
