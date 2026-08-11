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
