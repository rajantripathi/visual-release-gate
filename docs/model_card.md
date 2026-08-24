# Review model card

## Intended use

Structured visual observation that feeds a deterministic release policy. The
model is a review aid and never the final authority.

## Default configuration

- provider: Runware;
- model: `google-gemini-3-5-flash` (CLI-overridable);
- temperature: 0.1;
- top-p: 0.9;
- seed: 1729;
- media resolution: high;
- thinking level: medium;
- output ceiling: 8192 tokens.

## Inputs and outputs

Input order is target followed by approved references. The model returns a
strict `VisionAssessment`: factual summary, candidate issues, unknown checks,
action/copy state, and source conflicts. It does not return the public verdict.

## Limitations

Visual judgments can vary across provider/model revisions. Structured output
does not guarantee semantic validity; Python validates citations, authority,
uncertainty, and release invariants after every response.
