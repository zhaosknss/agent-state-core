# Composing the core with other components

[中文](COMPOSITION.zh-CN.md) · [README](../README.md)

The core supplies a ledger of state, scoped records, and action outcomes. Your
application supplies meaning and connects other components. State-only,
records-only, and intent/result-only commits work without requiring the other
payloads. Kinds, participant IDs, JSON schemas, rules, and execution order are
application choices. These capabilities share one package and SQLite schema;
they are not separately installable storage engines.

## Two exercised paths

| Composition | Core owns | External component owns | Tested scope |
|---|---|---|---|
| [LangGraph](LANGGRAPH.md) + core | Domain state, scoped records, commit receipts | Graph execution, interrupts, graph checkpoints | Synchronous `invoke`, human resume, replay |
| [LangChain Core retrieval recipe](../examples/langchain_retrieval.py) + core | Source records, audience projection, history | A derived in-memory store and Runnable pipeline | Keyword lookup, separate participant caches, rebuild after a new commit |

Both use real upstream APIs with deterministic functions and fictional data.
They are different composition paths within the LangChain ecosystem, not
evidence of compatibility with every framework or better model reasoning.

## Try the retrieval recipe

From the current checkout in a virtual environment:

```bash
python -m pip install -r requirements/retrieval-test.txt
python -m examples.langchain_retrieval
python -B tools/verify.py --retrieval
```

This installs **langchain-core 1.6.11** and its dependencies; LangGraph itself
is not required. The constraint file reuses the tested version set. No model,
embeddings, vector database, or API key is used. See [upstream review](UPSTREAM.md)
for the fixed source revision, MIT license, and actual dependency use.

`build_retriever(view)` accepts a detached `View`, rather than a privileged
ledger or snapshot. It creates a fresh `InMemoryStore` for that participant and
read point, then composes two `RunnableLambda` steps. The first performs ordinary
case-insensitive substring matching against record bodies; the second returns
the participant, upper read revision, and matching records with IDs and sources.
The lookup rule is an example policy, not semantic search or core API.

The example shows an operator receiving public and addressed runbook notes,
excluding reviewer-only notes and host state. It then commits a new note:
the old cache stays at its original read point, and a rebuilt cache includes
the new record. Tests also exercise invocation on a worker thread, detached
results, and rebuilding after external cache creation fails.

Filter the audience **before** handing records to an external store. Keep caches
separate by participant and read point. The host controls which `View` it supplies;
participant IDs are selectors, not authentication. Records remain historical:
a withdrawn or superseded note needs application policy before retrieval can
represent current understanding. Core commit and external cache writes are not
one transaction; the example treats the cache as a rebuildable projection.

The retrieval and handoff recipes are Unreleased checkout additions, absent
from the existing alpha-2 archives. Recipes stay outside the installed core.

## Reproduce the composition boundaries

```bash
python -B tools/audit_composition.py
```

This standard-library script runs 12 checks against temporary databases.
A successful boundary check means that a restriction was reproduced, not
that every composition is supported.

| Boundary | Observed behavior | Integration consequence |
|---|---|---|
| Global commit revision | A records-only note invalidates a proposal's old revision even when state is unchanged; disjoint key updates also conflict | Re-read and reassess stale work; do not blindly substitute a new revision |
| `last` is a context window | Five records in one commit with `last=2` return only the newest two; advancing to `View.revision` skips the other three | For complete deltas, omit `last` and finish consuming the result before advancing the revision |
| One connection belongs to one thread | Sharing a `Ledger` with a worker fails; opening a separate connection in the worker to the same file works | Own the connection where SQLite work executes; separate in-memory ledgers do not share data |
| Dedicated SQLite schema | A foreign database or an extra application table is refused | Use a dedicated ledger file; there is no shared external transaction/backend interface |
| Strict JSON and whole-value updates | External objects need explicit conversion; nested updates replace the top-level value | Adapt object schemas and compute intended updates in host code |
| Application metadata | Project filtering after `last` can miss older matching records | Read then filter without truncation, choose kinds deliberately, or use separate ledgers |
| Separate ledgers | Revisions are independent | There is no cross-ledger atomic commit |

The existing LangGraph example has an additional observed limit: its synchronous
nodes capture the caller's `Ledger`. Calling that graph with `ainvoke` offloads
those nodes and raises SQLite's thread-affinity error in the tested environment.
The verified path is synchronous `invoke`. An asynchronous adapter needs its own
connection lifecycle and tests; this recipe does not provide one.

## Where the core could improve

Reliable bounded incremental consumption, explicitly managed asynchronous
integration, and more selective stale-work checks are useful next candidates.
A record cursor must account for multiple records within one revision. A more
selective conflict check must preserve dependencies on records as well as state.
These are design candidates, not implemented APIs or a commitment to merge
concurrent decisions automatically. [Validation](VALIDATION.md) records actual
checks and their limits.
