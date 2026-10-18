# Using the core

[中文](GUIDE.zh-CN.md) · [Exact semantics](DESIGN.md) · [Operations](OPERATIONS.md)

## 1. Open a ledger

```python
from agent_state_core import Intent, Ledger, Record, Transition

with Ledger("session.db") as ledger:
    if ledger.revision == 0:
        ledger.commit(Transition(updates={"budget": 100}, records=(
            Record("requirement", {"budget": 100}, None),
        )), expected_revision=0)
```

The parent directory must exist. A path keeps data across restarts; `Ledger()`
alone uses memory. Close the ledger or use the context manager. One instance
belongs to one thread; different connections may use the same file.

## 2. Publish information deliberately

```python
with Ledger("session.db") as ledger:
    base = ledger.snapshot()
    ledger.commit(Transition(records=(
        Record("note", "check accessibility", ("reviewer",)),
        Record("claim", {"budget": 200}, ("planner",),
               {"speaker": "messenger", "verified": False}),
        Record("host-note", "internal reasoning", ()),
    )), expected_revision=base.revision)
```

`None` audience publishes to everyone, including participants added later.
A tuple names recipients; `()` keeps the record in host history only. Kind,
body, and source are application-defined. A visible source is sent as written:
provide an appropriate reference rather than private source text. A `claim`
record has no special power to change state.

## 3. Supply a participant's input

```python
with Ledger("session.db") as ledger:
    point = ledger.snapshot()
    context = ledger.view("planner", at_revision=point.revision,
                          kinds=("requirement", "claim"), last=10).to_context()
    print(context)
```

Pass `context` to your own model adapter, tool, or ordinary Python function.
It excludes the reviewer's private note, the host note, and the global state.
The host can still use `point.state` to check an action. Do not pass privileged
data to a model unless that is the information policy you intend.

`last=10` selects the last ten matching visible records and returns them in
chronological order. It is a context window, not a pagination cursor. An empty
`kinds=()` returns no records. `after_revision=N` excludes complete commits
through N; `at_revision=M` sets the inclusive upper bound. All filters preserve
the audience restriction. With no filters, the original full-view API still works.

## 4. Apply a host-selected result

```python
with Ledger("session.db") as ledger:
    base = ledger.snapshot()
    candidate = {"cost": 80, "plan": "online workshop"}
    accepted = candidate["cost"] <= base.state["budget"]
    result = Transition(
        updates={"selected_plan": candidate} if accepted else {},
        accepted=accepted,
        reason="within budget" if accepted else "over budget",
        records=(Record("decision", {"accepted": accepted}, None),),
    )
    ledger.commit(result, expected_revision=base.revision,
                  intent=Intent("planner", "select-plan", candidate))
```

The application made the decision. Accepted results may replace or delete
top-level JSON keys. Rejected results may publish records but cannot change
state. Intents and the host's reason stay in privileged history; a participant
receives them only if the host also publishes appropriate records.

## 5. Handle changed conditions and retries

Catch `StaleRevision` when someone has committed since the base was read. Obtain
a fresh snapshot and decide whether the result is still appropriate; the core
does not retry a model call or automatically reinterpret a proposal.

For a retry after a lost response, resend the identical transition, intent,
original base revision, and request ID. The original commit is returned even
after later commits. Different content with that ID raises `RequestConflict`.

For replay of an application node, `ledger.get_commit(request_id)` can retrieve
an already completed result before recomputing work. Request IDs belong to one
logical operation and ledger; use a new ID for a new decision. This lookup does
not serialize external effects or prevent a tool from running twice during a race.

## 6. Inspect history or show a public view

```python
with Ledger("session.db") as ledger:
    print(ledger.snapshot(at_revision=1).state)
    print(ledger.view(at_revision=1).to_context())  # Public only.
    print(ledger.history())  # Privileged: includes all audiences and host reasons.
```

Revision 0 is the empty beginning. A future revision is an error. Each result,
including records-only messages and rejected actions, advances the global
revision. Domain time can be carried in application-defined record content.

## Next steps

Use the [context-handoff recipe](CONTEXT_HANDOFF.md) for project-scoped candidate
notes, explicit revision/withdrawal, and incremental context without a fixed
agent workflow. It is a checkout example, not a new core schema or model adapter.

Run the [LangGraph example](LANGGRAPH.md) to see actual pause/resume orchestration.
Use [operations](OPERATIONS.md) for backups, schema upgrades, and troubleshooting.
The core does not impose a conversation recipe or require those integrations.
