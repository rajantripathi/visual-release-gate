# Contributing

Open an issue before proposing a new verdict meaning, pack schema version, or
provider adapter. Pull requests should include focused tests and must not add
third-party brand assets, undisclosed generated data, credentials, or claims
that cannot be reproduced from committed artifacts.

```bash
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest
```

Model-backed tests do not run in CI. Use fixture providers and record no secrets.
