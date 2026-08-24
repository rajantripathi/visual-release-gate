"""Transparent verdict metrics, paired comparisons, and reviewer agreement."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path

from pydantic import ValidationError

from .models import EvaluationLabel, ReleaseDecision, StructuredReview

VERDICTS: tuple[ReleaseDecision, ...] = (
    "ship",
    "reject",
    "human_review",
    "unsupported",
)


def read_reviews(path: Path) -> tuple[StructuredReview, ...]:
    records: list[StructuredReview] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            records.append(StructuredReview.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"invalid review at line {line_number}") from exc
    return tuple(records)


def read_labels(path: Path) -> tuple[EvaluationLabel, ...]:
    labels: list[EvaluationLabel] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            labels.append(EvaluationLabel.model_validate_json(line))
        except ValidationError as exc:
            raise ValueError(f"invalid label at line {line_number}") from exc
    return tuple(labels)


def score(
    labels: Iterable[EvaluationLabel], reviews: Iterable[StructuredReview]
) -> dict[str, object]:
    label_map = {label.asset_id: label for label in labels}
    review_map = {review.asset_id: review for review in reviews}
    if label_map.keys() != review_map.keys():
        missing_reviews = sorted(label_map.keys() - review_map.keys())
        unknown_reviews = sorted(review_map.keys() - label_map.keys())
        raise ValueError(
            "label/review mismatch; "
            f"missing={missing_reviews}, unknown={unknown_reviews}"
        )

    per_case: list[dict[str, object]] = []
    primary_correct = acceptable_correct = serious_false_approvals = 0
    unsafe_approvals = completed = 0
    confusion: Counter[tuple[str, str]] = Counter()

    for asset_id, label in label_map.items():
        review = review_map[asset_id]
        predicted = review.verdict
        if predicted is not None:
            completed += 1
            confusion[(label.primary_verdict, predicted)] += 1
        primary_match = predicted == label.primary_verdict
        acceptable_match = predicted in label.acceptable_verdicts
        primary_correct += int(primary_match)
        acceptable_correct += int(acceptable_match)
        if label.primary_verdict == "reject" and predicted == "ship":
            serious_false_approvals += 1
        if label.primary_verdict != "ship" and predicted == "ship":
            unsafe_approvals += 1
        per_case.append(
            {
                "asset_id": asset_id,
                "split": label.split,
                "expected": label.primary_verdict,
                "acceptable": list(label.acceptable_verdicts),
                "predicted": predicted,
                "processing_status": review.processing_status,
                "primary_match": primary_match,
                "acceptable_match": acceptable_match,
            }
        )

    class_metrics: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    for verdict in VERDICTS:
        tp = confusion[(verdict, verdict)]
        fp = sum(
            confusion[(actual, verdict)] for actual in VERDICTS if actual != verdict
        )
        fn = sum(
            confusion[(verdict, predicted)]
            for predicted in VERDICTS
            if predicted != verdict
        )
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        f1_values.append(f1)
        class_metrics[verdict] = {
            "support": sum(confusion[(verdict, p)] for p in VERDICTS),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    count = len(label_map)
    return {
        "case_count": count,
        "completed": completed,
        "primary_accuracy": round(primary_correct / count, 4) if count else 0.0,
        "acceptable_accuracy": round(acceptable_correct / count, 4) if count else 0.0,
        "macro_f1": round(sum(f1_values) / len(f1_values), 4),
        "serious_false_approvals": serious_false_approvals,
        "unsafe_approvals": unsafe_approvals,
        "class_metrics": class_metrics,
        "confusion": {
            actual: {
                predicted: confusion[(actual, predicted)] for predicted in VERDICTS
            }
            for actual in VERDICTS
        },
        "per_case": per_case,
    }


def paired_evaluation(
    labels: Iterable[EvaluationLabel],
    baseline: Iterable[StructuredReview],
    improved: Iterable[StructuredReview],
    *,
    baseline_run: Mapping[str, object] | None = None,
    improved_run: Mapping[str, object] | None = None,
    reviewer_agreement: Mapping[str, object] | None = None,
    status: str = "live_model_results",
) -> dict[str, object]:
    labels = tuple(labels)
    baseline_score = score(labels, baseline)
    improved_score = score(labels, improved)
    development = tuple(label for label in labels if label.split == "development")
    held_out = tuple(label for label in labels if label.split == "held_out")
    baseline_by_id = {r.asset_id: r for r in baseline}
    improved_by_id = {r.asset_id: r for r in improved}
    return {
        "status": status,
        "label_provenance": sorted({label.provenance for label in labels}),
        "reviewer_agreement": reviewer_agreement,
        "all_cases": {"baseline": baseline_score, "improved": improved_score},
        "development": {
            "baseline": score(
                development,
                (baseline_by_id[label.asset_id] for label in development),
            ),
            "improved": score(
                development,
                (improved_by_id[label.asset_id] for label in development),
            ),
        },
        "held_out": {
            "baseline": score(
                held_out,
                (baseline_by_id[label.asset_id] for label in held_out),
            ),
            "improved": score(
                held_out,
                (improved_by_id[label.asset_id] for label in held_out),
            ),
        },
        "run_telemetry": {
            "baseline": dict(baseline_run or {}),
            "improved": dict(improved_run or {}),
        },
        "interpretation_rule": (
            "Report every regression and incomplete case; do not claim improvement "
            "unless held-out results support it."
        ),
    }


def reviewer_agreement(
    reviewer_a: Iterable[EvaluationLabel], reviewer_b: Iterable[EvaluationLabel]
) -> dict[str, object]:
    a = {label.asset_id: label.primary_verdict for label in reviewer_a}
    b = {label.asset_id: label.primary_verdict for label in reviewer_b}
    if a.keys() != b.keys() or not a:
        raise ValueError("reviewer label files must cover the same non-empty asset set")
    total = len(a)
    observed = sum(a[key] == b[key] for key in a) / total
    a_counts = Counter(a.values())
    b_counts = Counter(b.values())
    expected = sum((a_counts[v] / total) * (b_counts[v] / total) for v in VERDICTS)
    kappa = (observed - expected) / (1 - expected) if expected < 1 else 1.0
    disagreements = [
        {"asset_id": key, "reviewer_a": a[key], "reviewer_b": b[key]}
        for key in a
        if a[key] != b[key]
    ]
    return {
        "case_count": total,
        "raw_agreement": round(observed, 4),
        "cohens_kappa": round(kappa, 4),
        "disagreements": disagreements,
    }


def dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
