# Philosophy

**Messy URL patterns are a symptom, not the disease.** By the time a project has a `views_v2.py`, a
`serializers_v2_actually_final.py`, and three different `if version ==` conditionals guarding the same
queryset, the underlying problem isn't the file layout — it's that nothing in the codebase can say what
changed between versions and what didn't. apiver forces that question to be answered explicitly, once,
at the one place a version's behavior is actually decided: `register()`, `override()`, `remove()`.

**Flexibility is the devil.** DRF and Django are permissive by design, and that permissiveness is
exactly what let messy versioning happen in the first place — there are a dozen ways to branch on
`request.version`, and every one of them is a private, uninspectable decision made inside a method
body. apiver is deliberately narrow instead: three verbs, one direction of inheritance, loud failures
on misuse. `register()` raises on a key that already exists. `override()` raises on a key that doesn't.
Setting a serializer field to `None` — the idiom every Django-forms-trained developer reaches for to
remove a field — raises too, because DRF silently keeps serving it. Nothing about apiver tries to be
flexible enough to accommodate every way a team might want to version an API; it tries to be narrow
enough that there's exactly one obvious way, and it happens to be correct.

**Versioning is a mindset, not a feature you bolt on.** Reaching for `if request.version == "v2":` the
first time a breaking change comes up is a reactive decision, made under deadline pressure, by whoever
happened to touch that view last. apiver asks for the decision up front instead: a version is `Frozen`
or it isn't; it's `Live`, `Deprecated`, `Sunset`, or `Archived`; a route is inherited or it's an
explicit `Delta`. Once that vocabulary exists, versioning stops being a special case scattered through
the codebase and becomes an ordinary fact about the project's structure — visible in `apiver versions`,
committed in `apiver.toml`, reviewable in a diff. It also means the mindset doesn't require a clean
slate to adopt: however your project got here — one hand-rolled version or a dozen, one scheme or
three abandoned ones along the way — apiver only ever needs to know what your *next* version changes.
The version before that stays exactly as messy as it already was.

**apiver enforces where routing is declared, never where the rest of your code lives.** The only file
any version — the base you adopted or a version you author later — is ever required to have is
`registry.py`, the one place its `register()`/`override()`/`remove()` calls happen. Your serializers,
views, and everything else stay wherever your project already organizes them; apiver has no opinion on
your file layout beyond that one file, the same way it has no opinion on your data layer or business
logic — how a field actually changes type in the database, what a request is allowed to do, how a
queryset gets built. apiver's job stops at the HTTP-facing shape of what crosses the wire, once per
version. That boundary is permanent, not a placeholder for tooling that doesn't exist yet: apiver will
never move, rename, or rewrite a file it didn't generate. `apiver init` discovers and imports your
existing code from wherever it already lives — it does not, and will not, relocate it.

**A version's own root is the one place apiver *does* draw a hard line.** `registry.py` may hold only
imports, its `Version(...)`/`.derive()` line, and `register()`/`override()`/`remove()` calls — never a
`class`/`def` of its own — and nothing else may sit in that same directory. This is what makes
[squash](guides/version-lifecycle.md#squashing-a-long-delta-chain) mechanical: a version can never be
folded away and silently take code a later version still needs down with it, because implementation
code was never in that directory to begin with. Enforced as an `apiver check` Error, not a suggestion.
