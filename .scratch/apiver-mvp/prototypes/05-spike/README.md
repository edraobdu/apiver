# PROTOTYPE — throwaway, wipe me

Spike for wayfinder ticket [05 — Prove the mechanism](../../issues/05-prove-the-mechanism.md).
Not part of the `apiver` library. Do not import from real package code.

## Run it

```
cd .scratch/apiver-mvp/prototypes/05-spike
.venv/bin/pytest -v
```

Everything (Django, DRF, drf-spectacular, pytest) is already installed in `.venv` (created with `uv venv`).
Database is in-memory sqlite, created fresh per test run — no persistence.

## What's here

- `spike/apiver_core.py` — the throwaway composition mechanism being tested: a `Version` that
  registers viewsets/views, overrides, and removes, and can build a resolution table and
  Django `urlpatterns` from it. **This is spike plumbing, not the real library's design** — the
  real public API surface is a separate open decision (ticket 07).
- `spike/v1/` — base version: `users`, `payments`, `orders` ViewSets + one APIView (`payments/summary/`).
- `spike/v2/` — authored version: overrides `payments` (decimal field type), removes `orders`.
  Everything else (`users`, `payments/summary/`) is inherited for free — zero lines in `v2/registry.py`.
- `tests/test_mechanism.py` — the ticket's 7 verification items, plus the 50-endpoint acceptance test.
