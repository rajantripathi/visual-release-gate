from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from visual_release_gate.gemini_provider import (
    GeminiProvider,
    _gemini_schema,
    _read_image,
    _usage,
)
from visual_release_gate.prompts import ASSESSMENT_SCHEMA
from visual_release_gate.provider import ProviderFailure, ProviderRequest

_ASSESSMENT = {
    "summary": "Target matches the brief with no blocking issue.",
    "issues": [],
    "unverifiable_checks": [],
    "action_clarity": "clear",
    "action_observation": None,
    "requested_copy_status": "not_requested",
    "requested_copy_observation": None,
    "source_conflicts": [],
}


def _png(path: Path) -> Path:
    # 1x1 PNG so mimetypes resolves image/png and bytes are non-empty.
    path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae42"
            "6082"
        )
    )
    return path


def _request(tmp_path: Path) -> ProviderRequest:
    return ProviderRequest(
        asset_id="dev_001",
        target_image=_png(tmp_path / "target.png"),
        reference_images=(),
        system_prompt="system",
        user_prompt="user",
        response_schema={},
        prompt_profile="baseline_v1",
    )


class _FakeTypes:
    """Minimal stand-in for google.genai.types used by the adapter."""

    @staticmethod
    def Content(*, role, parts):  # noqa: N802 - mirrors SDK name
        return SimpleNamespace(role=role, parts=parts)

    class Part:
        @staticmethod
        def from_text(*, text):
            return SimpleNamespace(text=text)

        @staticmethod
        def from_bytes(*, data, mime_type):
            return SimpleNamespace(data=data, mime_type=mime_type)

    @staticmethod
    def GenerateContentConfig(**kwargs):  # noqa: N802 - mirrors SDK name
        return SimpleNamespace(**kwargs)

    @staticmethod
    def HttpOptions(**kwargs):  # noqa: N802 - mirrors SDK name
        return SimpleNamespace(**kwargs)


def _fake_client(responses):
    calls = {"n": 0}

    def generate_content(*, model, contents, config):
        i = calls["n"]
        calls["n"] += 1
        outcome = responses[min(i, len(responses) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def _install(provider, monkeypatch, responses):
    monkeypatch.setattr(
        provider, "_client", lambda api_key: (_fake_client(responses), _FakeTypes)
    )


def _response(text, finish="STOP", usage=None):
    candidate = SimpleNamespace(finish_reason=SimpleNamespace(name=finish))
    return SimpleNamespace(text=text, candidates=[candidate], usage_metadata=usage)


def test_key_is_read_from_environment_only(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = GeminiProvider()
    with pytest.raises(ProviderFailure, match="GEMINI_API_KEY"):
        provider.assess(_request(tmp_path))
    assert "GEMINI_API_KEY" not in provider.__dict__
    assert "GOOGLE_API_KEY" not in provider.__dict__


def test_read_image_rejects_unsupported_type(tmp_path: Path):
    path = tmp_path / "file.txt"
    path.write_text("not an image", encoding="utf-8")
    with pytest.raises(ProviderFailure, match="unsupported image"):
        _read_image(path)


def test_successful_assessment_is_parsed(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiProvider()
    import json

    usage = SimpleNamespace(
        prompt_token_count=11, candidates_token_count=22, total_token_count=33
    )
    _install(provider, monkeypatch, [_response(json.dumps(_ASSESSMENT), usage=usage)])
    result = provider.assess(_request(tmp_path))
    assert result.assessment["action_clarity"] == "clear"
    assert result.telemetry.provider == "google"
    assert result.telemetry.cost_usd == 0.0
    assert result.telemetry.usage["total_tokens"] == 33


def test_rate_limit_is_retried_then_succeeds(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("time.sleep", lambda *_: None)
    provider = GeminiProvider(backoff_seconds=0.0)
    import json

    transient = SimpleNamespace(code=429, args=("rate",))
    err = type("APIError", (Exception,), {})()
    err.code = 429
    _install(provider, monkeypatch, [err, _response(json.dumps(_ASSESSMENT))])
    result = provider.assess(_request(tmp_path))
    assert result.telemetry.attempts == 2
    assert transient.code == 429  # sanity: retryable status classified


def test_auth_failure_opens_circuit(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GEMINI_API_KEY", "bad-key")
    provider = GeminiProvider()
    err = Exception("permission denied")
    err.code = 403
    _install(provider, monkeypatch, [err])
    with pytest.raises(ProviderFailure, match="authentication failed"):
        provider.assess(_request(tmp_path))
    # Circuit is now open: a second call fails fast without another attempt.
    with pytest.raises(ProviderFailure, match="authentication failed"):
        provider.assess(_request(tmp_path))


def test_usage_handles_missing_metadata():
    assert _usage(None) == {}


def test_gemini_schema_strips_unsupported_keys_and_inlines_refs():
    defs = ASSESSMENT_SCHEMA.get("$defs", {})
    schema = _gemini_schema(ASSESSMENT_SCHEMA, defs)

    forbidden = {"additionalProperties", "$ref", "$defs", "title", "default"}
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in forbidden:
                    found.append(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    assert found == [], f"forbidden keys leaked into Gemini schema: {found}"
    # Optional string field became nullable rather than a null-union.
    copy_obs = schema["properties"]["requested_copy_observation"]
    assert copy_obs.get("nullable") is True


def test_gemini_schema_collapses_nullable_union():
    node = {"anyOf": [{"type": "string"}, {"type": "null"}], "description": "d"}
    assert _gemini_schema(node, {}) == {
        "type": "string",
        "nullable": True,
        "description": "d",
    }
