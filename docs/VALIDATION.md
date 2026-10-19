# Validation evidence

## Unreleased record paging — 2026-10-20

Windows/Python 3.13.3 passed **50 tests and six examples** with both optional
integrations, including ten new paging/migration tests. The runner recorded
zero connection/DNS/send attempts and one local socket capability probe.
Core-only verification passed **43 tests/four examples** with zero sockets.
The existing 12-check composition audit now also verifies that the new paging
path consumes all five records while the original newest-window example still
demonstrates why `last` cannot serve as a queue cursor.

Coverage includes a single commit split across pages; an exactly full final page;
audience/kind projection with varied page sizes; hidden, filtered and state-only
commits; pinned reads while a separate connection writes; JSON checkpoint recovery
after reopening; repeated reads before acknowledgement; detached context; invalid
positions; bounded JSON decoding without reading full commit payloads; and paging
after the existing schema-v1 migration. Core schema remains v2 with no new runtime
dependencies. The original full-view/window behavior remains covered.

Local query-plan inspection confirmed use of the existing public-record and
participant/revision/ordinal indexes. This is not a workload performance claim;
limits bound returned row counts, not record bytes or execution time.

A fresh wheel built offline with setuptools 82.0.1 passed the same 50-test,
six-example run under isolated Python, importing the core from the wheel.
Fifteen Python blocks in the README, usage, and paging guides executed in
temporary directories with network connections blocked; changed documentation
links, Python syntax, workflow structure, and Git whitespace were checked.
The wheel is unpublished and does not replace existing alpha-2 release assets.

The cursor is a position for a fixed ledger/participant/kinds selection; it is
not bound to those identities. Application processing and cursor persistence
are outside the read transaction. Tests do not establish exactly-once side
effects, automated cross-chat synchronization, asynchronous ledger support,
or improved model reasoning. See [paging](PAGING.md) for supported usage.

## Unreleased checkout update — 2026-10-19

### Composition audit and derived retrieval

The composition update passed **40 tests and five examples** locally on
Windows/Python 3.13.3 with real LangGraph 1.2.15 and LangChain Core 1.6.11.
The runner reported zero connection/DNS/send attempts and one local socket
capability probe. Base-only counts remain 33 tests/three examples; retrieval-only
counts are 36/four and LangGraph-only counts are 37/four.

The three new retrieval checks exercise audience-specific caches, execution on
a worker thread without accessing SQLite, detached returned values, stable old
read points, rebuilds, and recovery from an external cache creation failure.
These use real `InMemoryStore`/`RunnableLambda` APIs and keyword matching, not
models, embeddings, automatic extraction, or semantic quality measurements.

`python -B tools/audit_composition.py` reproduced 12 capabilities and boundaries,
including independent payload use, JSON adaptation, global revision conflicts,
whole-value replacement, dedicated schema, thread ownership, context-window
truncation, application project filtering, and independent ledgers. A boundary
check passing means the limitation was observed, not removed.

A separate local probe called the existing LangGraph recipe with `ainvoke` and
reproduced a SQLite thread-affinity error before any new commit (revision stayed
at 1). Its synchronous nodes capture the caller's connection. The probe created
the Windows event loop before enabling its network guard so local loop setup
was not confused with remote traffic; subsequent connection/DNS/send attempts
were zero. This is a known limitation, not a passing asynchronous integration.
The canonical retrieval tests use a worker thread without creating an event loop.

Both optional paths are within the LangChain ecosystem. This does not validate
all frameworks, durable external caches, distributed transactions, bounded queue
consumption, or async ledger access. The base API and SQLite schema were not changed.
See [composition](COMPOSITION.md) for commands and integration decisions.

A fresh unpublished wheel built offline with setuptools 82.0.1 passed the same
40 tests/five examples under isolated Python, with core imports resolved from
the wheel and recipes from the checkout. It does not replace the release files.
The two README Python blocks also executed successfully in temporary directories;
changed documentation links, Python syntax, workflow structure, and Git whitespace
were checked locally.

### Earlier handoff update

On Windows/Python 3.13.3, the updated checkout passed **37 tests and four
examples**, including the optional real LangGraph 1.2.15 integration. Of these,
33 tests and three examples need only the standard library. The runner reported
zero network connection/DNS/send attempts and one local socket capability probe.

The new context-handoff checks cover cross-project and audience exclusion,
historical reads, latest-visible ordering, withdrawal deltas, unchanged caches
after empty deltas, and candidates remaining separate from authoritative state.
The four Python blocks in both handoff guides were executed in temporary
directories; local links in the changed usage documents were checked.

A fresh, unpublished wheel built offline with setuptools 82.0.1 passed the same
37-test/four-example check using isolated Python and importing the core from the
wheel. Checkout examples remain outside the wheel. This check does not replace
the published alpha-2 artifacts or establish model reasoning, automatic chat
integration, or reduced feedback/token use.

The historical alpha-2 release evidence follows. Its counts and artifacts describe
that release, rather than the new checkout recipe.

## Published alpha-2 evidence — 2026-10-17

Checked on 2026-10-17 (Asia/Shanghai). The original alpha-1 release and its CI remain available from the repository's Releases page.

## Local behavior and actual integration

Environment: Windows, Python 3.13.3. Core build tooling: setuptools 82.0.1. Optional LangGraph version: 1.2.15; its exact tested dependency environment is pinned in requirements/langgraph-test.txt and recorded in langgraph-environment.json.

```bash
python -B tools/verify.py
python -B tools/verify.py --langgraph
```

The core suite has **28 tests** and two examples. With the optional real integration installed, **32 tests** and three examples run. The local integration run passed with **0 network connection/DNS/send attempts**. A dependency creates a socket and probes local IPv6 support during import; the runner tracks socket creation separately. It permits loopback capability probing and blocks network connection, DNS, send, and non-loopback bind attempts. These are checks of trusted test code, not a sandbox for hostile code.

Coverage includes:

- Audience filtering, false claims, outdated observations, historic read points, hidden source references, detached mutable values, and custom JSON schemas.
- Rejected actions, stale results, deduplication, conflicting request IDs, deletion, reopened databases, concurrent writers, and failed writes.
- Filter ordering and windows, targeted state/view reads without access to full commit payloads, request lookup, and atomic projection-write rollback.
- Schema-v1 migration, retained historical state and request identity, and failed migration rollback followed by successful retry.
- Real LangGraph interrupt/resume, a private requirement of the same kind as the public requirement, replay of a logical review, invalid human input, and execution of the documented example.

The LangGraph example uses InMemorySaver for in-process demonstration. It does not validate durable graph recovery, real model reasoning, or exactly-once external effects.

The twelve Python code blocks in both READMEs and both usage guides were executed in temporary working directories. The built wheel also passed the 32-test integration suite and three examples using isolated Python and importing the core from the wheel rather than the source checkout.

## Reproducible read comparison

```bash
python tools/benchmark_reads.py --commits 1000 --repeats 20
```

On the same local in-memory ledger, 1000 private 2-KiB records and state updates were followed by one visible record. The comparison reads both state and participant information. The baseline uses the alpha-1 full-history algorithm; the new path uses query projections. Outputs were equal.

| Measurement | Median |
|---|---:|
| Alpha-1 read algorithm | 10.338 ms |
| Indexed alpha-2 reads | 0.094 ms |

This specific shape favors scope-based selection. The result is not a general performance claim or a measurement of model latency. Projection storage costs extra writes and space; large production histories and disk workloads remain unvalidated.

## Packaging and remote checks

Build the package with `python -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir dist` when build tooling is already installed. Test the resulting artifact from outside the checkout with `python -I -B /path/to/tools/verify.py --wheel /path/to/file.whl`; add `--langgraph` in an environment containing the optional dependency. The runner checks that the core was imported from the wheel.

Release notes and SHA256SUMS.txt identify the exact published artifact and checked CI run. Remote status is available in [Behavior checks](https://github.com/zhaosknss/agent-state-core/actions/workflows/test.yml). Core CI targets Ubuntu/Windows on Python 3.11/3.13; optional integration CI targets Ubuntu/Python 3.11 and Windows/Python 3.13. A configured matrix alone is not evidence of a pass.

No real model quality, additional framework adapters, arbitrary branch manager, semantic consistency judge, multi-tenant authorization, or production-scale workload has been validated.
