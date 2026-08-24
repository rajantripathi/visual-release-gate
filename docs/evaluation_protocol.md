# Evaluation protocol

## Dataset

- 24 fictional cases built from eight original target images.
- Eight development cases and sixteen held-out cases.
- Reused pixels under different briefs test whether decisions follow the
  request and authority context rather than image identity alone.

## Human labels

Two reviewers label independently without model output or discussion. Raw
agreement and Cohen's kappa are calculated before disagreements are adjudicated.
Public labels use anonymous reviewer IDs unless reviewers explicitly consent.

## Freeze and run

1. Use development cases to motivate at most one general prompt/policy change.
2. Freeze `baseline_v1` and `ambiguity_v2` at a recorded commit SHA.
3. Run both profiles over all 24 cases before revealing held-out labels.
4. Unblind held-out labels and generate the paired report without hand repair.

## Metrics

- primary and acceptable verdict accuracy;
- macro-F1 and per-class precision/recall/F1;
- serious false approvals and all unsafe approvals;
- per-case outcomes and every regression;
- calls, retries, latency, runtime, usage, and provider-reported cost.

No improvement is assumed. If held-out results regress or remain unchanged,
the report says so.
