# Visual Release Gate v0.1.0

First public-ready release of an auditable multimodal release-decision layer for
AI-generated creative assets.

## Included

- typed model-observation and public-review contracts;
- deterministic four-outcome policy adjudication;
- source-ID validation and explicit external-authority boundaries;
- Runware-backed vision-provider adapter with application-owned retries;
- budget-aware ordered batches with partial-result preservation and telemetry;
- paired baseline/improved evaluation and reviewer-agreement reporting;
- original fictional 24-case pack with 8 development and 16 held-out cases;
- safe precomputed Streamlit benchmark explorer;
- 52 tests, Ruff gates, locked dependencies, and Python 3.11/3.12 CI;
- Apache-2.0 code and CC-BY-4.0 sample-pack documentation.

## Evidence status

The initial benchmark labels are `provisional_author`. Two independent reviewer
files and live provider runs remain required before performance metrics are
published. This release makes no accuracy or improvement claim.

## Known limitations

- one fictional illustration policy system;
- Runware is the only implemented live provider;
- model revisions may change observations despite fixed application settings;
- the safe demo explores provisional labels and performs no inference.
