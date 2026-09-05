"""Command-line interface for validation, live review, and paired evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .batch import run_batch
from .evaluation import paired_evaluation, read_labels, reviewer_agreement
from .gemini_provider import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from .gemini_provider import GeminiProvider
from .io import write_json_atomic
from .pack import PackError, load_pack
from .prompts import DEFAULT_PROFILE, SUPPORTED_PROFILES
from .provider import VisionProvider
from .runware_provider import DEFAULT_MODEL, RunwareProvider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visual-release-gate",
        description="Auditable multimodal release decisions for creative assets.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate-pack", help="Validate a policy pack without model calls."
    )
    validate.add_argument("--pack", type=Path, required=True)

    review = commands.add_parser("review", help="Review every brief in a policy pack.")
    _provider_args(review)
    review.add_argument("--pack", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument(
        "--prompt-profile", choices=SUPPORTED_PROFILES, default=DEFAULT_PROFILE
    )
    review.add_argument("--budget-usd", type=float)
    review.add_argument("--reserve-per-call-usd", type=float, default=0.08)

    evaluate = commands.add_parser(
        "evaluate", help="Run and score frozen baseline and improved profiles."
    )
    _provider_args(evaluate)
    evaluate.add_argument("--pack", type=Path, required=True)
    evaluate.add_argument("--baseline-output", type=Path, required=True)
    evaluate.add_argument("--improved-output", type=Path, required=True)
    evaluate.add_argument("--evaluation-output", type=Path, required=True)
    evaluate.add_argument("--budget-usd", type=float, default=5.0)
    evaluate.add_argument("--reserve-per-call-usd", type=float, default=0.08)
    evaluate.add_argument("--reviewer-a", type=Path)
    evaluate.add_argument("--reviewer-b", type=Path)
    return parser


def _provider_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=("runware", "gemini"), default="runware")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--max-attempts", type=int, choices=range(1, 6), default=3)


def _provider(args: argparse.Namespace) -> VisionProvider:
    if args.provider == "gemini":
        # Substitute the Gemini default when the user left --model at the
        # Runware default (i.e. did not explicitly choose a Gemini model).
        model = GEMINI_DEFAULT_MODEL if args.model == DEFAULT_MODEL else args.model
        return GeminiProvider(
            model=model,
            timeout_ms=args.timeout_seconds * 1000,
            max_attempts=args.max_attempts,
        )
    return RunwareProvider(
        model=args.model,
        timeout_ms=args.timeout_seconds * 1000,
        max_attempts=args.max_attempts,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-pack":
            pack = load_pack(args.pack)
            print(
                json.dumps(
                    {
                        "name": pack.manifest.name,
                        "version": pack.manifest.version,
                        "rules": len(pack.rules),
                        "references": len(pack.references),
                        "briefs": len(pack.briefs),
                        "development": sum(
                            b.split == "development" for b in pack.briefs
                        ),
                        "held_out": sum(b.split == "held_out" for b in pack.briefs),
                        "input_errors": sum(
                            b.input_error is not None for b in pack.briefs
                        ),
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "review":
            pack = load_pack(args.pack)
            result = run_batch(
                pack,
                _provider(args),
                args.output,
                prompt_profile=args.prompt_profile,
                budget_limit_usd=args.budget_usd,
                reserve_per_call_usd=args.reserve_per_call_usd,
            )
            print(json.dumps(asdict(result.telemetry), indent=2))
            return 0 if result.telemetry.completed == result.telemetry.attempted else 1
        if args.command == "evaluate":
            pack = load_pack(args.pack)
            provider = _provider(args)
            baseline = run_batch(
                pack,
                provider,
                args.baseline_output,
                prompt_profile="baseline_v1",
                budget_limit_usd=args.budget_usd,
                reserve_per_call_usd=args.reserve_per_call_usd,
            )
            remaining = max(0.0, args.budget_usd - baseline.telemetry.total_cost_usd)
            improved = run_batch(
                pack,
                provider,
                args.improved_output,
                prompt_profile="ambiguity_v2",
                budget_limit_usd=remaining,
                reserve_per_call_usd=args.reserve_per_call_usd,
            )
            agreement = None
            if bool(args.reviewer_a) != bool(args.reviewer_b):
                raise ValueError("provide both reviewer files or neither")
            if args.reviewer_a and args.reviewer_b:
                agreement = reviewer_agreement(
                    read_labels(args.reviewer_a), read_labels(args.reviewer_b)
                )
            evaluation = paired_evaluation(
                pack.labels,
                baseline.records,
                improved.records,
                baseline_run=asdict(baseline.telemetry),
                improved_run=asdict(improved.telemetry),
                reviewer_agreement=agreement,
            )
            write_json_atomic(args.evaluation_output, evaluation)
            print(json.dumps(evaluation["held_out"], indent=2))
            errors = (
                baseline.telemetry.input_errors
                + baseline.telemetry.provider_errors
                + baseline.telemetry.budget_stopped
                + improved.telemetry.input_errors
                + improved.telemetry.provider_errors
                + improved.telemetry.budget_stopped
            )
            return 1 if errors else 0
    except (OSError, PackError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")
