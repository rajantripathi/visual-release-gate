# Threat model

## Protected assets

- provider credentials;
- private images and prompts;
- release-decision integrity;
- source authority and audit telemetry;
- experiment budget.

## Boundaries and mitigations

| Threat | Mitigation |
|---|---|
| Prompt injection in image text or pack prose | System prompt declares all supplied content untrusted; model cannot change tool or policy behavior. |
| Fabricated citations | Unknown, inactive, duplicate, and cross-brief source IDs fail closed. |
| Serious issue silently ships | Typed output and deterministic invariants reject the record. |
| Legal/consent claims inferred from pixels | Explicit external requirements map to `unsupported`. |
| One provider failure loses the batch | Ordered per-record isolation and atomic final output. |
| Retried calls hide cost | SDK retries disabled; application owns attempts and cost accumulation. |
| Anonymous demo abuse or private uploads | Hosted demo contains no live endpoint or upload control. |
| Pack path traversal or malicious image | Root-bounded resolution plus safe image decoding. |

## Out of scope for v0.1

- hostile provider infrastructure;
- multi-tenant hosted inference;
- production authorization workflows;
- legal determination of asset rights;
- guaranteed reproducibility across model revisions.
