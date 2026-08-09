# Prior Art Research: API Versioning Libraries (for `apiver` build-vs-don't-build)

Research date: 2026-08-09. All figures pulled live from primary sources (GitHub API, PyPI JSON API, pypistats.org API, official docs) on this date; see inline citations.

---

## 1. Bottom line

**There is a real, currently-unserved gap for an inheritance/delta versioning model in the DRF ecosystem specifically — but the gap exists mostly because almost nobody has tried to fill it recently, not because the idea has been tried and rejected.** The only library that ever implemented "delta" versioning for DRF — `django-rest-framework-version-transforms` — is dead (last PyPI release 2015, last commit 2019, Python 2/3.3/3.4-era) (https://pypi.org/pypi/djangorestframework-version-transforms/json, https://github.com/mrhwick/django-rest-framework-version-transforms), and it used runtime transform functions, not Python inheritance/subclassing, so `apiver`'s actual mechanism (V2 = V1 + overrides via class inheritance, router resolves missing resources back to V1) has no direct prior implementation anywhere I found, in any framework. DRF's own official third-party-package list names exactly one versioning-delta package, and it's the dead one (https://www.django-rest-framework.org/community/third-party-packages/). DRF's built-in versioning module explicitly only determines `request.version` and rewrites `reverse()` output — it provides zero machinery for "fall back to the previous version's viewset/serializer automatically" (confirmed against doc text below). The closest modern comparator, Cadwyn, is FastAPI/Pydantic-only by explicit framework classifier and README claim, has no Django/DRF support and no open discussion of adding it that I could find. So: for DRF specifically, the space is not adequately served today. The open risk is not "Cadwyn already solved this for DRF" (it hasn't) but "is the DRF versioning problem big enough that anyone will adopt a new dependency for it" — the graveyard of small, single-digit-star, abandoned DRF/Flask versioning packages (django-api-versioning: 3 stars, one-week release burst then silence; drf-versioning: not even a real package; django-rest-versioning: 4 stars, no activity since 2020) suggests genuine demand has historically been thin, even though the technical gap is real.

---

## 2. Comparison table

| Name | Framework(s) | Model | Maturity | Last Release | Downloads/Stars |
|---|---|---|---|---|---|
| Cadwyn | FastAPI + Pydantic only | Stripe-style: write only latest version; "version change" modules migrate requests backward / responses backward through a chain | Active, well-established for its niche | 7.2.0, 2026-07-29 (https://github.com/zmievsa/cadwyn/releases) | 306 stars, 31 contributors, 24 open issues (https://api.github.com/repos/zmievsa/cadwyn); 17.5M/mo PyPI downloads without-mirrors (https://pypistats.org/api/packages/cadwyn/recent) — see caveat in §3 |
| django-rest-framework-version-transforms | Django REST Framework | Delta **transform functions** (forwards/backwards) per resource, not inheritance; parser upgrades old requests to latest, serializer downgrades responses to requested version | Dead | 0.5.0, 2015-11-02 (https://pypi.org/pypi/djangorestframework-version-transforms/json); last commit 2019-11-15 (https://api.github.com/repos/mrhwick/django-rest-framework-version-transforms) | 75 GitHub stars, 8 forks, 2 open issues; PyPI downloads not separately checked (package effectively unmaintained, Python 2.7/3.3/3.4 classifiers) |
| django-api-versioning | Django + DRF | Decorator-based route registration across a min/max version range with "automatic backward compatibility" for routing only (not resource-level fallback) | Very early / low adoption | 0.1.4, 2025-02-22 (https://pypi.org/pypi/django-api-versioning/json) — all 5 releases published within a single 24-hour window (2025-02-21 to 2025-02-22) | 3 GitHub stars, 0 forks, 0 open issues (https://api.github.com/repos/mojtaba-arvin/django-api-versioning); PyPI downloads not obtained |
| django-rest-versioning (PyPI: `djangorestversioning`) | Django REST Framework | "Lightweight mixin to allow routing DRF endpoints to different classes depending on version" — manual per-version class routing, not delta/inheritance-resolving | Dead | 0.2.3, 2015-11-13 (https://pypi.org/pypi/djangorestversioning/json) | 4 GitHub stars, last push 2020-10-26 (https://api.github.com/repos/craigtweedy/django-rest-versioning) |
| drf-versioning (GitHub: sentyaev/drf-versioning) | Django REST Framework | Not a package — a demo repo showing two hand-rolled patterns (fully duplicated V1/V2 views, or shared view + `SerializerClassMixin`) | Not a real library; teaching example only | Never published to PyPI | 25 stars, 3 forks, last push 2023-04-21 (https://api.github.com/repos/sentyaev/drf-versioning) |
| DRF built-in versioning (`rest_framework.versioning`) | Django REST Framework | Request-version **detection** (URL path / header / hostname / query param / namespace) + `reverse()` URL rewriting only; no automatic viewset/serializer resolution | Actively maintained as core DRF, but scope is intentionally narrow | Ships with DRF itself | N/A (part of DRF core) |
| fastapi-versioning (DeanWay) | FastAPI | URL-prefix version tagging via `@version` decorator (`/v1_0/...`), generates versioned route table; no content transformation, no delta/inheritance resolution | Unmaintained since 2023 | 0.10.0, 2021-08-24 (https://pypi.org/pypi/fastapi-versioning/json) | 847 stars, 37 open issues, last push 2023-07-25 (https://api.github.com/repos/DeanWay/fastapi-versioning) |
| fastapi-versionizer | FastAPI | Similar `@api_version` decorator, route-table generation + OpenAPI grouping; no delta/inheritance model | Actively maintained | 4.0.2, 2025-08-03 (https://pypi.org/pypi/fastapi-versionizer/json) | Not obtained |
| fastapi-versioner, fastapi-easy-versioning, fastapi-vers, fast-version | FastAPI | Variants of header/URL negotiation + deprecation management; none described as delta/inheritance-based content resolution | Mixed / not individually verified beyond PyPI search snippets | Not verified per-package | Not obtained |
| Litestar | Litestar (ASGI) | No dedicated versioning subsystem found in official docs search; general routing/OpenAPI docs only, no versioning-specific page surfaced | N/A | N/A | N/A |
| Flask ecosystem | Flask | No package literally named "Flask-API-Versioning" exists on PyPI; versioning is documented only as a manual URL-prefix / blueprint pattern (e.g. Flask-Rebar docs), not a dedicated delta library | N/A | N/A | N/A |

---

## 3. Per-library detail

### Cadwyn
- Repo: https://github.com/zmievsa/cadwyn — "Production-ready Stripe-like API versioning in FastAPI" (https://github.com/zmievsa/cadwyn)
- Docs: https://docs.cadwyn.dev/
- PyPI: https://pypi.org/project/cadwyn/ ; JSON API confirms current version **7.2.0** and `Framework :: FastAPI` / `Framework :: Pydantic` classifiers, `requires_python >=3.10` (https://pypi.org/pypi/cadwyn/json)
- GitHub API (https://api.github.com/repos/zmievsa/cadwyn, fetched 2026-08-09): 306 stars, 52 forks, 24 open issues, not archived, created 2023-06-12, last push 2026-08-03T09:10:59Z. Contributors endpoint returns **31** distinct contributors (https://api.github.com/repos/zmievsa/cadwyn/contributors). Releases endpoint shows **85+ tagged releases** (paginated at 100; first page alone returns 85 items from v3.6.4 through v7.2.0) (https://api.github.com/repos/zmievsa/cadwyn/releases) — i.e. very high release cadence, effectively continuous shipping since 2023.
- Recent release dates confirm active cadence: 7.2.0 (2026-07-29), 7.1.2 (2026-07-28 per GitHub UI), 7.1.1 (2026-07-22), 7.1.0 (2026-06-15), 7.0.0 (2026-06-06) (https://github.com/zmievsa/cadwyn/releases).
- **Model**: README describes it as letting you "maintain the implementation just for your newest API version and get all the older versions generated automatically," using independent "version change" modules — i.e. write the *latest* version as canonical, and Cadwyn migrates requests/responses backward through a chain of version-change modules to serve older-version clients (https://github.com/zmievsa/cadwyn). This is the inverse direction from `apiver`'s proposal (which is forward: V1 canonical baseline, V2 = delta overrides, unspecified resources fall back to V1) — Cadwyn requires you to write migration/diff code for every breaking change between every adjacent version pair, whereas the apiver thesis is that *unchanged* resources require zero migration code at all, just absence of an override class.
- **Framework scope**: PyPI classifiers and README are FastAPI/Pydantic-specific; no Django/DRF classifier, no Django mentions in README fetch (https://github.com/zmievsa/cadwyn) or docs homepage fetch (https://docs.cadwyn.dev/). A targeted GitHub search for "cadwyn Django support issue" surfaced no open issue specifically requesting Django/DRF support among visible results (search performed 2026-08-09); the closest hit was issue #149 "DOCS: Improve docs around alternative Cadwyn use" (https://github.com/zmievsa/cadwyn/issues/149), which was not confirmed to be about Django specifically without opening it further.
- **Explicit "what it doesn't do"**: the docs homepage fetch did not surface a dedicated limitations/scope section; it focuses on capabilities. No such section was located.
- **Downloads**: pypistats.org API (https://pypistats.org/api/packages/cadwyn/recent, cross-checked via direct `curl`) reports last_day 539,946 / last_week 4,472,734 / last_month 17,544,174 downloads. **Caveat**: this figure is surprisingly large relative to a 306-star repo and could reflect CI/mirror/bot download inflation that PyPI's "without_mirrors" bucket does not fully filter (a known general limitation of pypistats.org for any package); it should not be read at face value as "17M developers use Cadwyn monthly." Treat as directionally "non-trivial install-time traffic," not as a reliable proxy for developer adoption.

### django-rest-framework-version-transforms (PyPI: `djangorestframework-version-transforms`)
- Repo: https://github.com/mrhwick/django-rest-framework-version-transforms
- PyPI: https://pypi.org/project/djangorestframework-version-transforms/ ; JSON API: current version 0.5.0, releases 0.1.0–0.5.0 all published between 2015-10-20 and 2015-11-02, classifiers include `Development Status :: 2 - Pre-Alpha`, `Programming Language :: Python :: 2.7`, `:: 3.3`, `:: 3.4` (https://pypi.org/pypi/djangorestframework-version-transforms/json)
- GitHub API: 75 stars, 8 forks, 2 open issues, last push 2019-11-15T07:21:03Z, default branch `dev` (never merged to a stable-looking main branch name) (https://api.github.com/repos/mrhwick/django-rest-framework-version-transforms)
- **Model**: "Delta transformations" — subclasses of `BaseTransform` implement `forwards`/`backwards` methods per resource; a custom parser upgrades old-version requests to the latest internal representation, a custom serializer downgrades latest responses back to the client's requested version (per WebSearch summary of README, https://github.com/mrhwick/django-rest-framework-version-transforms). This is the same directional approach as Cadwyn/Stripe (latest-canonical + backward transform functions) applied to DRF, **not** apiver's inheritance/subclass-of-viewset approach. It is also long dead.
- Listed as DRF's official (and only) versioning-related third-party package (https://www.django-rest-framework.org/community/third-party-packages/, https://djangopackages.org/packages/p/django-rest-framework-version-transforms/).

### django-api-versioning
- Repo: https://github.com/mojtaba-arvin/django-api-versioning — "API versioning for Django! Automatically register routes, ensure backward compatibility, and manage API versions with a simple decorator. Supports Django Rest Framework (DRF)..." (https://github.com/mojtaba-arvin/django-api-versioning)
- PyPI: https://pypi.org/project/django-api-versioning/ ; JSON API: version 0.1.4, `Development Status :: 3 - Alpha`, `Framework :: Django :: 3.2`, `requires_python >=3.6`. All 5 releases (0.1.0–0.1.4) published within roughly 19 hours on 2025-02-21/22 (https://pypi.org/pypi/django-api-versioning/json) — looks like a rapid initial-publish burst followed by no further releases through the research date (2026-08-09), i.e. roughly 18 months of subsequent silence.
- GitHub API: 3 stars, 0 forks, 0 open issues, last push 2025-02-22T08:20:47Z (https://api.github.com/repos/mojtaba-arvin/django-api-versioning) — matches the PyPI publish burst, i.e. no development activity since the initial release day.
- **Model**: decorator that auto-registers a view across a configured min/max version range with route-level backward compatibility; this addresses *routing/URL registration* convenience, not resource-content delta resolution (per WebSearch summary of README).

### django-rest-versioning (GitHub: craigtweedy/django-rest-versioning, PyPI: `djangorestversioning`)
- Repo: https://github.com/craigtweedy/django-rest-versioning
- PyPI: https://pypi.org/project/djangorestversioning/ ; JSON API: version 0.2.3, releases 0.2.1–0.2.3 all on 2015-11-12/13 (https://pypi.org/pypi/djangorestversioning/json)
- GitHub API: 4 stars, last push 2020-10-26T13:52:14Z, not archived (https://api.github.com/repos/craigtweedy/django-rest-versioning)
- **Model**: "A lightweight mixin to allow routing Django Rest Framework endpoints to different classes depending on version" (PyPI summary, https://pypi.org/pypi/djangorestversioning/json) — manual per-version class mapping, no automatic fallback/inheritance resolution.

### drf-versioning (GitHub: sentyaev/drf-versioning)
- Repo: https://github.com/sentyaev/drf-versioning — 25 stars, 3 forks, 1 open issue, last push 2023-04-21T20:53:56Z (https://api.github.com/repos/sentyaev/drf-versioning)
- **Not a published package** — confirmed directly: `https://pypi.org/pypi/drf-versioning/json` returns HTTP **404** (verified 2026-08-09). The name is unregistered on PyPI; this repo is a GitHub-only demo.
- It's a demo/example repo contrasting two hand-rolled patterns: (a) fully duplicate views+serializers per version, or (b) share the view, swap serializer via a `SerializerClassMixin`. Neither is inheritance-based delta resolution at the router/resource-composition level that apiver proposes.

### DRF built-in versioning
- Official docs: https://www.django-rest-framework.org/api-guide/versioning/
- Confirmed via direct doc fetch: "When API versioning is enabled, the `request.version` attribute will contain a string that corresponds to the version requested in the incoming client request." Versioning is off by default; `request.version` is `None` with no scheme configured.
- Docs show the *only* built-in mechanism for varying behavior is manual conditional code in application logic, e.g.:
  ```python
  def get_serializer_class(self):
      if self.request.version == 'v1':
          return AccountSerializerVersion1
      return AccountSerializer
  ```
  This is written by the developer per-view, per-version — DRF supplies no automatic "resolve to previous version's implementation if this version doesn't override it" behavior. The doc content contains **no** description of any such fallback/inheritance mechanism.
- `reverse()` "applies any URL transformations appropriate to the request version" — this is exclusively about URL string construction (namespace prefixes for `NamespaceVersioning`, query params for `QueryParameterVersioning`), not about resource/viewset resolution.
- The five schemes documented — `AcceptHeaderVersioning`, `URLPathVersioning`, `NamespaceVersioning`, `HostNameVersioning`, `QueryParameterVersioning` — are all purely about **how the version identifier is extracted from the request** (header media-type param, URL path segment, URL namespace, hostname subdomain, query string param respectively). None of them touch how a viewset or serializer is selected beyond what the developer writes by hand via `get_serializer_class()`/`get_queryset()` branching.
- **Conclusion, directly grounded in doc text**: DRF's versioning module is request-version *detection and URL reconstruction* only. It confirms the claim in the task brief precisely — there is no built-in delta/inheritance/fallback mechanism.

### fastapi-versioning (DeanWay)
- Repo: https://github.com/DeanWay/fastapi-versioning
- GitHub API: 847 stars, 37 open issues, not archived, last push 2023-07-25T14:20:52Z, created 2019-12-02 (https://api.github.com/repos/DeanWay/fastapi-versioning)
- PyPI: https://pypi.org/project/fastapi-versioning/ ; JSON API: latest version 0.10.0 published 2021-08-24T17:06:33 (note: uploaded *after* 0.9.1 which was 2021-05-18, so last release is mid-2021) (https://pypi.org/pypi/fastapi-versioning/json) — no release in ~5 years as of this research date (2026-08-09), and no commits in ~3 years.
- **Model**: `@version` decorator tags route functions with `(major, minor)`; the library generates a versioned route table (`/v1_0/...`) and can serve a `/latest` alias. Pure route-tagging/URL-prefix generation — no request/response content transformation, no inheritance/delta resolution (per WebSearch summary of the repo's usage examples).

### fastapi-versionizer
- PyPI: https://pypi.org/project/fastapi-versionizer/ ; JSON API: latest version 4.0.2, published 2025-08-03T00:31:29 (https://pypi.org/pypi/fastapi-versionizer/json) — actively maintained relative to the DeanWay package.
- **Model**: `@api_version` decorator on routes plus OpenAPI-per-version doc generation (per WebSearch summary); same route-tagging category as fastapi-versioning, not delta/inheritance-based.

### Other FastAPI versioning packages surfaced (not deep-dived)
`fastapi-versioner`, `fastapi-easy-versioning`, `fastapi-vers`, `community-of-python/fast-version` (Accept-header based) all appeared in PyPI/GitHub search results (https://pypi.org/project/fastapi-versioner/, https://pypi.org/project/fastapi-easy-versioning/, https://pypi.org/project/fastapi-vers/0.2.0, https://github.com/community-of-python/fast-version) but were not individually fetched for stars/downloads/last-release — flagged here as existing but unverified in depth. None was described anywhere in search results as inheritance/delta-based; they are all negotiation/decorator/tagging tools.

### Litestar
- No dedicated versioning documentation page was surfaced via search of https://docs.litestar.dev/ or the GitHub repo (https://github.com/litestar-org/litestar). Not confirmed whether Litestar has zero versioning support or simply didn't surface in this search pass — flagged as **not fully verified**, treat as "no evidence of a dedicated versioning subsystem found," not as a confirmed absence.

### Flask ecosystem
- No PyPI package literally named "Flask-API-Versioning" exists (WebSearch confirms no such listing; closest name matches are unrelated packages like `Flask-Versioned` (SQLAlchemy row-versioning, not API versioning) and `Flask-Continuum`). Flask-Rebar's docs (https://flask-rebar.readthedocs.io/en/latest/quickstart/api_versioning.html) describe URL-prefix versioning as a manual pattern, not a dedicated delta library.

---

## 4. Stripe's model

- Primary source: Brandur Leach, "APIs as infrastructure: future-proofing Stripe with versioning," Stripe Engineering Blog, published 2017-08-05 (https://stripe.com/blog/api-versioning).
- Model, quoted from the post: version changes are chained "version change modules," each of which "assumes that although newer changes may exist in front of them, the data they receive will look the same as when they were originally written." A request tagged with an old version is "walk[ed] back through time" applying "each version change module that finds along the way until that target version is reached" (https://stripe.com/blog/api-versioning). This is Cadwyn's direct design ancestor — Cadwyn's README explicitly calls itself "Stripe-like" (https://github.com/zmievsa/cadwyn).
- **Maintenance burden is explicitly acknowledged in the primary source**, not something inferred: "Versioning is always a compromise between improving developer experience and the additional burden of maintaining old versions" and unencapsulated version checks would otherwise be "littered throughout the project, making it slower, less readable, and more brittle" — which is precisely the problem the gate/version-change-module abstraction exists to contain, not eliminate (https://stripe.com/blog/api-versioning).
- The post also states Stripe "expect[s] to eventually start retiring our older API versions" (https://stripe.com/blog/api-versioning) — i.e. even Stripe's own post frames the gate chain as something that needs eventual pruning, not a free-standing-forever structure — but current live docs (https://docs.stripe.com/api/versioning, fetched 2026-08-09) show the *current* API version is `2026-07-29.dahlia` and the versioning page still documents SDK-pinned versions going back many major releases (e.g. `stripe-ruby v8` and below vs `v9`+, `stripe-python v5` vs `v6`+, etc.), suggesting that in practice very old versions are still being carried forward operationally almost a decade after the 2017 post, i.e. the "retire old gates" intent has not obviously translated into actually deleting old gates at scale.
- No separate outside engineering critique specifically quantifying the gate-chain maintenance cost was located as a primary source within this search pass (only the Stripe post itself, and general secondary blog retellings which were excluded per instructions); the "risk" framing above is drawn directly from Stripe's own post, not a third party.

---

## 5. PyPI name availability

Checked via PyPI JSON API (`https://pypi.org/pypi/<name>/json`) directly with `curl`, which returns a clean HTTP status without the bot-challenge page that the HTML project pages return under automated fetch. Fetched 2026-08-09.

| Name | PyPI JSON API status | Interpretation |
|---|---|---|
| `apiver` | 404 | Available — no package registered under this exact name |
| `django-apiver` | 404 | Available |
| `drf-apiver` | 404 | Available |
| `deltaver` | 200 (v1.0.2, author Almaz Ilaletdinov, no summary set) | **Taken** — published package, unrelated purpose not confirmed (empty summary) |
| `versionkit` | 200 (v0.1.0, author Edward George, empty summary) | **Taken** — published package, purpose not confirmed (empty summary) |

Note: direct HTML fetches of `https://pypi.org/project/<name>/` returned a Fastly "Client Challenge" interstitial for all five names regardless of real status, so the HTML page alone is not a reliable signal under automated fetch — the JSON API (`/pypi/<name>/json`) was used as the authoritative check instead, since it returns real 404s for genuinely unregistered names (confirmed for `apiver`, `django-apiver`, `drf-apiver`) and real 200s with package metadata for taken names (`deltaver`, `versionkit`).

---

## 6. Risks to the apiver thesis

Concrete, unfavorable findings, stated plainly:

1. **The one prior DRF delta-versioning library that existed is completely dead** (last release 2015, last commit 2019, Python 2.7/3.3/3.4 classifiers) (https://pypi.org/pypi/djangorestframework-version-transforms/json, https://api.github.com/repos/mrhwick/django-rest-framework-version-transforms). It only ever reached 75 GitHub stars at its peak activity. This is weak evidence that demand for solving this exact problem in DRF, even when someone built a solution, was thin enough that it wasn't kept alive — could mean "nobody needed it" as easily as "wrong implementation, or bad timing (2015)."

2. **Every from-scratch attempt at DRF-specific versioning convenience libraries since has attracted essentially no adoption**: `django-api-versioning` (3 stars, all 5 releases within one day, then 18 months of silence as of this research date) (https://api.github.com/repos/mojtaba-arvin/django-api-versioning, https://pypi.org/pypi/django-api-versioning/json); `django-rest-versioning` (4 stars, dead since 2020) (https://api.github.com/repos/craigtweedy/django-rest-versioning); `drf-versioning` was never even published as an installable package, staying a 25-star demo repo (https://api.github.com/repos/sentyaev/drf-versioning). Low star counts alone are weak signal, but the *pattern* of near-zero sustained engagement across four independent attempts over a decade is a real, repeated data point against strong latent demand.

3. **DRF's official third-party package list names only one versioning package, and it's the dead one** (https://www.django-rest-framework.org/community/third-party-packages/) — this could be read as "the gap is real and unaddressed" (bullish for apiver) or as "the DRF community stopped trying because most people just don't need this" (bearish). Both readings are consistent with the same fact; it does not resolve in apiver's favor by itself.

4. **Cadwyn's numbers, if the pypistats.org figures are taken at face value (17.5M downloads/month, https://pypistats.org/api/packages/cadwyn/recent), would suggest real, large-scale demand for API versioning tooling in Python generally** — even though Cadwyn is FastAPI-only, a maintainer or company evaluating "build vs. don't build" for DRF could reasonably ask "why hasn't Cadwyn's success pulled a DRF port into existence, or pulled DRF users to migrate to FastAPI+Cadwyn instead?" No evidence of either was found in this research pass. This is a genuine unresolved question, not dismissed here.

5. **FastAPI's own versioning-package ecosystem is crowded and mostly abandoned or shallow** (`fastapi-versioning`: no commits since 2023, no release since 2021; multiple newer FastAPI packages exist but are mostly route-tagging decorators, not content-transformation or delta tools) (https://api.github.com/repos/DeanWay/fastapi-versioning, https://pypi.org/pypi/fastapi-versioning/json). This suggests that even in a framework where a genuinely popular, well-engineered solution (Cadwyn) exists, most other versioning tooling attempts still fail to sustain adoption — i.e. "we'll be the one that succeeds" is not a safe assumption merely because the *idea* (delta/inheritance) is technically novel for DRF.

6. **The inheritance/delta mechanism itself (V2 subclasses V1, router auto-resolves unoverridden resources) was not found implemented anywhere, in any framework**, including Cadwyn and the dead DRF transform library, both of which use runtime transform-function chains rather than class inheritance. This is either a genuine differentiator (bullish) or a sign that class-inheritance composition for whole-API-surface versioning has a structural problem nobody has solved cleanly yet (e.g. MRO complexity across many versions, difficulty of partial overrides at sub-resource granularity, migration-of-data-shape concerns that pure inheritance doesn't obviously address the way explicit transform functions do) — this research pass did not find primary-source discussion either confirming or ruling out such structural problems, so it remains an open technical risk to validate directly rather than by further literature search.

7. **The Stripe blog post that is Cadwyn's own design ancestor explicitly frames the gate-chain approach as an accumulating maintenance cost that requires active retirement of old versions to stay healthy** (https://stripe.com/blog/api-versioning), and Stripe's current live docs still show version-pinned SDK behavior going back many major versions site (https://docs.stripe.com/api/versioning), suggesting that in practice this "retire old gates" discipline is hard to execute even for the company that invented the pattern. If apiver's inheritance model has an analogous accumulation problem (every V_n potentially needs to know about every override in V_1...V_n-1 through the MRO), that risk should be treated as real and Stripe-precedented, not hypothetical.
