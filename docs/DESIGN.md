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

State effects and published records are stored in a single journal row in one
SQLite transaction. There is no second independently saved state file. Historical
state is rebuilt by applying the recorded updates/deletions in order, without
rerunning models or tools. A database insertion failure must leave the previous
history readable and the request ID available for a later successful attempt.

Model calls and external effects happen outside this transaction. If a tool ran
before a failed commit, it may already have caused effects or incurred cost.
Duplicate commit detection does not provide exactly-once external execution.

## Storage and composition

`Ledger()` uses an in-memory SQLite database. `Ledger(path)` persists in that
file; its parent directory must already exist. The ledger is a context manager
and can also be explicitly closed. One instance belongs to one thread. Multiple
connections to the same file are supported; read-modify-write conflicts are
reported through revisions. A SQLite lock timeout can still raise an SQLite error.

Schema version 1 is checked on open. Unrelated databases and unsupported schema
versions are refused. There is no schema migration, compaction, encryption,
tamper-evidence, authorization server, or untrusted-code boundary in this alpha.
Give the ledger object only to trusted host code; participant IDs are selectors,
not authenticated identities. Do not send `history()` or `snapshot()` to a model
unless you intentionally want that model to receive host data.

The core does not schedule participants. A script, graph framework, game loop,
or server can choose the order and pass the scoped JSON to its own adapters.
No third-party agent framework integration has been exercised yet. The current
implementation scans the journal for reads and suits small exploratory sessions;
large histories will need indexing/checkpoints and measured performance work.
