# Contributing

## Setup

```console
$ uv sync
$ uv run pre-commit install
```

`pre-commit install` wires `ruff check --fix` and `ruff format` into `git commit` — the same lint
gate CI runs, catching formatting drift before it reaches CI instead of after (issue #49). Run it
once per clone; it stays wired for every commit after that.

To run the hooks on demand, without committing:

```console
$ uv run pre-commit run --all-files
```

## Tests and lint

```console
$ uv run pytest
$ uv run ruff check .
$ uv run ruff format --check .
```

To see coverage, including the `tests/test_cli_*.py` cases that invoke `apiver` as a
subprocess:

```console
$ COVERAGE_PROCESS_START=pyproject.toml uv run coverage run -m pytest
$ uv run coverage combine
$ uv run coverage report -m
```

The subprocess capture is enabled by `sitecustomize.py` at the repo root, which is a
no-op unless `COVERAGE_PROCESS_START` is set — plain `uv run pytest` is unaffected.
