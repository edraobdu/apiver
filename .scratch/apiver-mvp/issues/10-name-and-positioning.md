# 10 — Package name, positioning, PyPI reservation

Type: task
Status: resolved
Assignee: claude
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

## Answer

1. **Name: `apiver`**, confirmed by the human. Framework-neutral, coherent with the standing decision to keep public vocabulary portable even though internals stay DRF-only; a `drf` extra covers discoverability.

2. **GitHub check found a collision the PyPI check didn't.** `github.com/apiver` (the exact user/org name) is already taken — an empty, apparently inactive account, 0 repos, but taken nonetheless (verified live 2026-08-09). `github.com/apiver-python` and `github.com/getapiver` were both confirmed free as fallback org names, but weren't needed: the human chose to host under their **personal GitHub account** instead (`github.com/<username>/apiver`), which sidesteps the collision entirely since GitHub repos are namespaced under the owner, not a global project-name registry. No further action needed here.

3. **PyPI reservation is a human-only step — I have no PyPI credentials or `twine`/`.pypirc` in this environment, and package registration requires an interactive account (2FA-gated).** Checklist for the human:
   - Create/sign in to a PyPI account.
   - `pip install build twine` locally.
   - Scaffold a minimal package (`pyproject.toml` with `name = "apiver"`, `version = "0.0.0"`, no real content needed yet).
   - `python -m build && twine upload dist/*` to claim the name before 0.1 development finishes.
   - This is time-sensitive only in the sense that the name is confirmed free *today* (2026-08-09) — it is not guaranteed to stay free.

4. **Positioning line, confirmed by the human:** *"Define API versions as deltas, not duplicates."* Goes in the PyPI description, the README's first sentence, and the GitHub repo description.

5. **Honest one-paragraph Cadwyn positioning:**

   > apiver and Cadwyn solve adjacent but different problems, and neither replaces the other. Cadwyn is FastAPI/Pydantic-only and Stripe-style: you write only the latest version, then author explicit "version change" modules that migrate requests and responses backward through the version chain — migration code has to exist for every breaking change between every adjacent version pair, whether or not the resource behind it actually changed. apiver takes the opposite direction, for DRF: V1 is the canonical baseline, V2 is a set of overrides on V1, and anything V2 doesn't touch is served automatically by V1's existing implementation — zero migration code for unchanged resources. If you're on FastAPI and want Stripe's model done well, Cadwyn is mature (85+ releases, active development) and the right choice. If you're on DRF, Cadwyn doesn't reach you at all, and apiver's bet is that most resources in most version bumps don't change — so most of what looks like "migration work" elsewhere should be free here.

**Feeds forward:** the reservation checklist (item 3) is a standing action item for the human, not blocking any other ticket. [11 — Reference project shape](11-reference-project-shape.md) and [12 — Gating semantics](12-gating-semantics.md) remain the only tickets standing between here and the 0.1 build slices.
