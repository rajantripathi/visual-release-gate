# Security policy

Report credential exposure, pack path traversal, prompt/data boundary failures,
or release-invariant bypasses privately to the repository owner before opening
a public issue.

Supported security expectations for v0.1:

- credentials are read only from `RUNWARE_API_KEY`;
- pack paths cannot escape their root;
- unknown and cross-brief citations fail closed;
- serious issues and blocking unknowns cannot become `ship`;
- live inference is disabled in the public demo;
- provider error messages are sanitized before serialization.
