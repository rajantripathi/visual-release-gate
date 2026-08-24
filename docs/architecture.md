# Architecture

Visual Release Gate separates probabilistic perception from deterministic
release authority.

1. The pack loader validates the manifest, structured records, image decoding,
   unique IDs, label coverage, JSON Schema, and every path boundary.
2. The prompt builder serializes only the current brief, active rules,
   approved references, and active clarifications. Labels never enter requests.
3. A provider adapter returns `VisionAssessment`, not a final verdict.
4. `SourceRegistry` rejects unknown, inactive-feedback, and cross-brief citations.
5. Policy converts observable findings and explicit brief requirements into a
   `StructuredReview` with stable precedence.

Decision precedence:

1. input/provider/budget failure -> null verdict plus blocking reason;
2. visible critical or major issue -> `reject`;
3. absent external authority -> `unsupported`;
4. decision-critical visual or source ambiguity -> `human_review`;
5. otherwise -> `ship`.

This intentionally prevents a fluent model response from granting itself
release authority.
