# Working on agent-state-core

Read README.md and docs/DESIGN.md before changing behavior. This is an alpha
library with Python 3.11+ and no third-party runtime dependencies.

Preserve the distinction between authoritative application state and the
records supplied to a participant. An observation or claim never silently
changes global state. Examples demonstrate possible policies, not required
roles, schedules, action types, or conversation structures.

Test changes to history, audience projection, transaction boundaries, and
request deduplication with concrete failure cases. Run the examples without
model calls. Record actual checks and limitations; simulated agents do not
establish model quality. Keep private source application data outside this repo.
