# API and semantics

This document is the implementation reference for the alpha. Names and policy
choices can evolve as applications exercise the API.

## The boundaries

The host application owns a `Ledger`. It calls `snapshot()` to read its chosen
authoritative state, applies its rules, and commits a `Transition`. A participant
receives `ledger.view(participant).to_context()`, which contains only its scoped
records. A participant can be a model, ordinary function, tool, or human.

The host decides what counts as an established state change. The ledger does
not verify physical reality, infer truth from text, or make participant beliefs
agree with the current global state.

| Value | Meaning |
|---|---|
| `Intent(actor, kind, payload)` | What was attempted; optional host history |
| `Record(kind, body, audience, source=None)` | Information intentionally made available |
| `Transition(updates={}, deletes=(), records=(), accepted=True, reason="")` | Host-selected result |
| `Commit` | Revision, UTC save time, transition, optional intent and request ID |
| `Snapshot` | Revision and detached global state dictionary |
| `View` | Participant, revision, and visible records |
| `RecordCursor(revision, ordinal=None)` | Consumed record position; None means through the complete revision |
| `ViewPage` | Scoped records, upper read revision, next cursor, and whether more matching records remain |

## Public operations

| Operation | Result |
|---|---|
| `Ledger(path=":memory:")` | Open a dedicated ledger database |
| `revision` | Current global commit revision |
| `commit(transition, expected_revision=..., intent=None, request_id=None)` | Atomic `Commit` receipt |
| `get_commit(request_id)` | Privileged original receipt, or `None` |
| `snapshot(at_revision=None)` | Global state at the selected revision |
| `view(participant=None, at_revision=None, after_revision=0, kinds=None, last=None)` | Scoped and optionally filtered records |
| `view_page(participant=None, after=None, at_revision=None, kinds=None, limit=100)` | Next oldest scoped records and a resumable position; Unreleased |
| `history(at_revision=None)` | Complete privileged history through a revision |
| `close()` / context manager | Close the owned connection |

Parameters following `transition` are keyword-only. The view parameters after
`participant` are also keyword-only, including on `view_page`. The usage guide shows complete examples.

Kinds and JSON content are application-defined. `claim`, `observation`, `note`,
and the example action names are conventions, not registered or special types.
The kernel does not turn any record kind into a state update.

## JSON and state updates

State is a dictionary of nonempty string keys to strict JSON values. An update
replaces an entire top-level value. Nested dictionaries and lists are allowed;
automatic deep merge is not performed. Deleting an absent key is a no-op. The
same key cannot be updated and deleted in one transition. A rejected transition
may publish records but must have no updates or deletes.

JSON means null, booleans, integers, finite floats, strings, lists, and objects
with string keys. Nonfinite numbers, tuples inside content, cycles, and silent
key coercions are rejected before any commit is written. Lists or tuples are
accepted for the explicit `records`, `deletes`, and `audience` parameters.

Input values are serialized at commit time. Returned objects are detached from
stored data; modifying a nested returned dictionary cannot alter the database.
Frozen dataclasses prevent field reassignment, not mutation of nested values.

## Visibility and time

- `audience=None`: public to every participant, including future participants.
- `audience=("alice", "bob")`: addressed to those IDs. Order and duplicate IDs
  have no semantic effect.
- `audience=()`: host-only; visible in privileged history, not in any `View`.
- `view(None)` or `view()`: public-only projection.

View records contain ID, revision, UTC save time, kind, body, and caller-provided
source. They do not contain the audience list, other records, global state,
intent, or the host's result reason. A `source` reference is not dereferenced;
the host must avoid embedding private source text in a visible record. Record
IDs and revisions can reveal gaps and activity; this is not metadata secrecy.

Records are immutable historical publications. Later state updates do not
rewrite old observations. Revisions order commits, not the time of an event in
the application domain. Domain time, provenance details, reliability labels,
belief changes, and selective revelation can be represented in record content
and projected by application code. Publication to an audience is not evidence
that a model read, understood, or believed the record.

`snapshot(at_revision=N)` and `view(..., at_revision=N)` exclude later commits.
Revision 0 is the empty initial state. A nonexistent future revision is an error.
When rules read both state and participant context, use the same explicit
revision for both. This does not recreate a model's earlier hidden reasoning.

View filters do not broaden its audience. `kinds` is a tuple/list of nonempty
strings; an empty collection returns no records. `after_revision` excludes
all records through that revision and must not exceed the read point. A positive
`last` takes the newest matching records and returns them in chronological order.
It is a context window, not a pagination cursor. Records in one commit keep their
original ordinal. `View.revision` is the upper read point even for an empty result.

### Bounded record consumption (Unreleased)

`view_page` is separate from the newest context window. It reads in ascending
revision/ordinal order, with audience and kinds selected before the SQL limit.
`after` accepts a `RecordCursor` or None (the start). Cursor revisions must be
nonnegative integers not exceeding the read point; a record ordinal must be a
nonnegative integer at a positive revision. Booleans are not integer positions.
`limit` must be a positive integer. Existing databases require no schema change.

The returned `ViewPage` has the same participant/records context as a View, plus
`revision`, `next_cursor`, and `has_more`. The database read transaction fixes
both the reported revision and matching rows. At most `limit + 1` rows are
fetched, and only the returned records' body/source JSON is decoded. The extra
row establishes whether more matching records remain at that read point.

If more remain, `next_cursor` identifies the last returned `(revision, ordinal)`.
Otherwise it is `RecordCursor(page.revision)`, meaning the complete upper revision
has been consumed for this selection, including hidden or records-free commits.
Pin later pages to the first page's revision to drain a finite history; after
completion, omit `at_revision` to poll new commits from the final cursor.

Cursor storage and effects are application-owned. Save progress only after
successful processing. For the same ledger and fixed participant/kinds selection,
continuation covers all matching records without skipping within a commit.
Cursors are positions, not ledger identities or authenticated scope bindings;
changing selection requires a separate checkpoint or a fresh scan. A page can
split a commit. There is no queue claim/ack, worker scheduling, or exactly-once
external processing. See [paging](PAGING.md) for runnable use and JSON recovery.

## Commit, concurrency, and retry

```python
base = ledger.snapshot()
# Host rules compute a result. A model can be called separately with a View.
receipt = ledger.commit(result, expected_revision=base.revision,
                        intent=optional_intent, request_id=optional_request_id)
```

Each committed result, including a rejected action or records-only message,
advances one global revision. `BEGIN IMMEDIATE` serializes writers. The expected
revision must equal the current revision or `StaleRevision` is raised with no
new records or state changes. This conservative check does not detect which
individual fields a proposal actually depends on. The application decides
whether to recompute, discard, or review stale work; there is no automatic retry.

An optional request ID deduplicates the **local commit**. The base revision,
intent, and transition must match the first use after JSON key/audience ordering
is normalized. A match returns the original commit, even if the current revision
has advanced. A mismatch raises `RequestConflict`. The ID is scoped to one ledger.

`get_commit(request_id)` provides a direct host lookup of the original receipt
before replaying application work. A caller should keep IDs unique per logical
operation. This lookup is not a lock around external work or a substitute for
the commit's fingerprint and revision checks.

The authoritative commit payload and its state/record query projections share
one SQLite transaction. There is no independently saved state file. Historical
state reads select the latest value/deletion per key at that revision, without
decoding full action payloads or rerunning models/tools. Projection or journal
insertion failure leaves the previous history and request IDs unchanged.

Model calls and external effects happen outside this transaction. If a tool ran
before a failed commit, it may already have caused effects or incurred cost.
Duplicate commit detection does not provide exactly-once external execution.

## Storage and composition

`Ledger()` uses an in-memory SQLite database. `Ledger(path)` persists in that
file; its parent directory must already exist. The ledger is a context manager
and can also be explicitly closed. One instance belongs to one thread. Multiple
connections to the same file are supported; read-modify-write conflicts are
reported through revisions. A SQLite lock timeout can still raise an SQLite error.

Schema version 2 is checked on open. Version 1 upgrades atomically by indexing
its unchanged journal; a failed upgrade rolls back its new tables and version.
Unrelated or unsupported databases are refused. This alpha has no compaction,
encryption, tamper-evidence, authorization server, or untrusted-code boundary.
Give the ledger object only to trusted host code; participant IDs are selectors,
not authenticated identities. Do not send `history()` or `snapshot()` to a model
unless you intentionally want that model to receive host data.

The core does not schedule participants. A script, graph framework, game loop,
or server can choose the order and pass the scoped JSON to its own adapters.
An optional LangGraph integration is exercised separately; see LANGGRAPH.md.
Normal views read indexed public/addressed records, and snapshots read per-key
state versions. Complete `history()` still reads the journal. Large production
histories and arbitrary speculative branch management remain unvalidated.

## Schema v2

| Table | Purpose / key |
|---|---|
| `asc_meta` | One schema-version row |
| `commits` | Original payload, UTC time, optional unique request ID and fingerprint; revision primary key |
| `state_versions` | Value or deletion per `(key, revision)` |
| `record_projection` | Body/source/kind/public flag per `(revision, ordinal)` |
| `record_audience` | Addressed recipients, keyed by `(participant, revision, ordinal)` |

Public record reads use `(is_public, revision, ordinal)` indexing; addressed reads
use the audience primary key and record primary key. State selection uses its
per-key revision key. Scope filtering happens before record JSON is decoded.
The journal remains the source for projections created during migration.
Application code must not manually edit those tables. Read operations pin one
SQLite read transaction so the reported revision and query result agree.
