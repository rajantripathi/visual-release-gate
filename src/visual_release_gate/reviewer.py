"""One-asset orchestration across prompt, provider, parsing, and policy."""

from __future__ import annotations

from pydantic import ValidationError

from .models import AssetBrief, PolicyPack, StructuredReview, VisionAssessment
from .policy import PolicyError, SourceRegistry, adjudicate, error_review
from .prompts import DEFAULT_PROFILE, PromptProfile, build_prompt
from .provider import ProviderFailure, ProviderRequest, ReferenceImage, VisionProvider


def review_asset(
    policy_pack: PolicyPack,
    brief: AssetBrief,
    provider: VisionProvider,
    *,
    prompt_profile: PromptProfile = DEFAULT_PROFILE,
) -> StructuredReview:
    if brief.input_error or brief.resolved_image_path is None:
        return error_review(
            brief.asset_id,
            "input_error",
            brief.input_error or "target image unavailable",
        )
    prompt = build_prompt(policy_pack, brief, prompt_profile)
    request = ProviderRequest(
        asset_id=brief.asset_id,
        target_image=brief.resolved_image_path,
        reference_images=tuple(
            ReferenceImage(reference.reference_id, reference.resolved_image_path)
            for reference in policy_pack.references
            if reference.resolved_image_path is not None
        ),
        system_prompt=prompt.system_prompt,
        user_prompt=prompt.user_prompt,
        response_schema=prompt.response_schema,
        prompt_profile=prompt.profile,
    )
    try:
        result = provider.assess(request)
        assessment = VisionAssessment.model_validate(result.assessment)
        return adjudicate(
            assessment,
            brief,
            SourceRegistry(policy_pack),
            telemetry=result.telemetry,
        )
    except ProviderFailure:
        raise
    except (ValidationError, PolicyError, ValueError) as exc:
        raise ProviderFailure(
            code="invalid_assessment",
            message="Provider assessment failed semantic validation.",
            retryable=False,
        ) from exc
