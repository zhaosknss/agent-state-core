# Changelog

## 0.1.0a3 — 2026-10-21

- Added `RecordCursor`, `ViewPage`, and `Ledger.view_page()` for oldest-first,
  scoped record paging within a commit, pinned read points, and resumable positions.
  Existing `view(last=...)` remains a newest context window. The two APIs share
  indexed audience projection; no database schema or dependency change is needed.
- Added paging behavior tests, migration coverage, a runnable standard-library
  checkpoint example, and bilingual paging guides. Progress storage and external
  effects remain application-owned; this is not exactly-once queue delivery.

- Added a real LangChain Core 1.6.11 storage/Runnable recipe using only a scoped
  View, with participant-specific caches, retained sources, and explicit rebuilds.
  Lookup is keyword matching; no model or vector search is implied. The core
  API, schema, and dependency-free base installation are unchanged.
- Added optional retrieval tests and CI, plus a 12-check composition audit and
  bilingual guide covering actual integration paths and limitations. Documented
  global revision conflicts, context-window truncation, dedicated schema, and
  the existing LangGraph recipe's synchronous-only connection ownership.

- Reworked the English/Chinese landing pages around a composable core, possible
  component combinations, and runnable examples; separated current capabilities
  from exploratory applications. Aligned the package description with that scope.
- Added a runnable context-handoff recipe: project-scoped candidate notes,
  compact source references, explicit revisions and withdrawals, and delta reads.
  It uses existing APIs, fictional messages, and no model calls. The recipe's
  schema and latest-visible-key policy are application choices, not kernel rules.
- Added behavior checks for handoff visibility, historical reads, withdrawal
  handling, and private updates; included the recipe in the verification runner.
- Skip the unused request fingerprint when `commit()` has no `request_id`.
  Requests with an id retain the same deduplication and compatibility checks.

## 0.1.0a2

- Expanded English/Chinese introductions, capability tables, architecture,
  usage guides, integration instructions, and troubleshooting.
- Added indexed participant records and per-key state history. Normal views
  and snapshots no longer deserialize the complete action journal.
- Added `view(..., kinds=..., after_revision=..., last=...)` and
  `get_commit(request_id)` for host replay handling.
- Added an atomic schema-v1 to schema-v2 upgrade, preserving original commits
  and request deduplication. Query projection failures roll back the whole commit.
- Added a real optional LangGraph 1.2.15 example for human pause/resume and
  scoped participant input, plus integration tests and a pinned test environment.
- Documented upstream code/license review and the distinction between a direct
  dependency, design reference, and related project.

## 0.1.0a1

Initial public alpha: JSON state, explicit audience records, intents/results,
atomic SQLite commits, historical reads, version checks, request deduplication,
and two deterministic examples. Core behavior was checked in four OS/Python CI
combinations. No third-party agent framework was integrated in that version.
