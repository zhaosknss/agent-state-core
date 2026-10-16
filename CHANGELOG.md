# Changelog

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
