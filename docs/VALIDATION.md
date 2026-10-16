# Validation evidence

Checked on 2026-10-17 (Asia/Shanghai). This report describes alpha 2. The original alpha-1 release and its CI remain available from the repository's Releases page.

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
