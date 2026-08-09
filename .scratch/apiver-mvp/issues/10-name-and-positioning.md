# 10 — Package name, positioning, PyPI reservation

Type: task
Status: open
Blocked by: —

## Question

Cheap, takeable now, and it unblocks publishing. Partly HITL (the naming call is yours), partly AFK (the reservation is mechanical).

1. **Pick the name.** `apiver`, `django-apiver`, and `drf-apiver` are all verified free on PyPI (see [research/01-prior-art.md](../research/01-prior-art.md)). Trade-off: `apiver` is clean and keeps the door open for a future FastAPI adapter without a rename; `django-apiver` / `drf-apiver` are discoverable by people searching the DRF ecosystem, which is where the users are. Given the standing decision to keep the public vocabulary framework-neutral, `apiver` with a `drf` extra is the coherent choice — confirm or overrule.

2. **Check GitHub org/repo availability** for the chosen name.

3. **Reserve it on PyPI** — register the project with a placeholder 0.0.0 so the name can't be taken during the months of 0.1 development. Mechanical, do it as soon as the name is picked.

4. **Settle the positioning line.** This goes in the PyPI description, the README's first sentence, and the GitHub repo description, so it's worth ten minutes. Candidates:
   - *"Define API versions as deltas, not duplicates."*
   - *"API versioning by inheritance for Python web frameworks."*
   - *"A system for evolving APIs safely without duplicating them."*

   The first is the sharpest and most concrete. The third describes where the project is heading once `diff`/`check` exist but overpromises for 0.1.

5. **Write the honest one-paragraph positioning** against Cadwyn, since it's the one mature comparator and people will ask. It is FastAPI-only and takes the *inverse* architecture (latest-canonical, transform backwards). apiver is DRF-first and forward-delta. Neither replaces the other — say so plainly rather than claiming superiority.

## Context

- [research/01-prior-art.md](../research/01-prior-art.md) — name availability verified via the PyPI JSON API (the HTML pages serve a bot challenge and give misleading results).
- Standing decision: build it for yourself first; PyPI is a side effect. Reserving the name is still worth doing now.
