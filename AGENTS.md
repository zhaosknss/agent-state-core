# Working on agent-state-core

Read README.md and docs/DESIGN.md before changing behavior. This is an alpha
library with Python 3.11+ and no third-party core runtime dependencies. The
optional integration examples have separately tested dependency sets.

Preserve the distinction between authoritative application state and the
records supplied to a participant. An observation or claim never silently
changes global state. Examples demonstrate possible policies, not required
roles, schedules, action types, or conversation structures.

Test changes to history, audience projection, transaction boundaries, and
request deduplication with concrete failure cases. Run the examples without
model calls. Record actual checks and limitations; simulated agents do not
establish model quality. Keep private source application data outside this repo.

Schema v2 query tables (`state_versions`, `record_projection`, `record_audience`)
are derived from `commits`; write them in the same transaction. Keep schema-v1
migration atomic and preserve old request fingerprints. See docs/DESIGN.md.
For usage read docs/GUIDE.md; for upstream reuse read docs/UPSTREAM.md. Run
`python -B tools/verify.py`; with the extra installed add `--langgraph`.
For the separate LangChain Core recipe use `requirements/retrieval-test.txt`
and `--retrieval`. Reproduce composition boundaries with
`python -B tools/audit_composition.py`; restrictions are deliberate observations,
not assertions of universal compatibility. See docs/COMPOSITION.md.
Record paging uses `RecordCursor`/`ViewPage`; preserve `view(last=...)` semantics
and fixed-scope checkpoints. See docs/PAGING.md before changing continuation.
Offline integration CI disables upstream tracing with `LANGSMITH_TRACING=false`
and `LANGCHAIN_TRACING_V2=false`; these are not core configuration fields.
