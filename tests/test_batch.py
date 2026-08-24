from __future__ import annotations

from pathlib import Path

from conftest import assessment_for

from visual_release_gate.batch import run_batch
from visual_release_gate.provider import MappingProvider, ProviderFailure


class OneFailureProvider(MappingProvider):
    def assess(self, request):
        if request.asset_id == "dev_002":
            raise ProviderFailure(
                code="provider", message="upstream failed", attempts=1
            )
        return super().assess(request)


class TerminalProvider:
    def __init__(self):
        self.calls = 0

    def assess(self, request):
        self.calls += 1
        raise ProviderFailure(code="auth", message="authentication failed", attempts=1)


def _fixtures(pack):
    return {
        brief.asset_id: assessment_for(
            pack.label_by_asset_id[brief.asset_id].primary_verdict,
            required_copy=brief.required_copy is not None,
        )
        for brief in pack.briefs
    }


def test_batch_preserves_order_and_writes_output(sample_pack, tmp_path: Path):
    output = tmp_path / "reviews.jsonl"
    result = run_batch(sample_pack, MappingProvider(_fixtures(sample_pack)), output)
    assert [r.asset_id for r in result.records] == [
        b.asset_id for b in sample_pack.briefs
    ]
    assert len(output.read_text(encoding="utf-8").splitlines()) == 24
    assert result.telemetry.completed == 24


def test_one_failure_does_not_discard_peers(sample_pack, tmp_path: Path):
    result = run_batch(
        sample_pack,
        OneFailureProvider(_fixtures(sample_pack)),
        tmp_path / "reviews.jsonl",
        briefs=sample_pack.briefs[:3],
    )
    assert [r.processing_status for r in result.records] == [
        "completed",
        "provider_error",
        "completed",
    ]


def test_terminal_failure_opens_batch_circuit(sample_pack, tmp_path: Path):
    provider = TerminalProvider()
    result = run_batch(
        sample_pack,
        provider,
        tmp_path / "reviews.jsonl",
        briefs=sample_pack.briefs[:4],
    )
    assert provider.calls == 1
    assert result.telemetry.provider_errors == 4


def test_budget_reserve_stops_before_call(sample_pack, tmp_path: Path):
    result = run_batch(
        sample_pack,
        MappingProvider(_fixtures(sample_pack)),
        tmp_path / "reviews.jsonl",
        briefs=sample_pack.briefs[:3],
        budget_limit_usd=0.10,
        reserve_per_call_usd=0.15,
    )
    assert result.telemetry.budget_stopped == 3
    assert result.telemetry.provider_calls == 0
