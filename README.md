# agent-state-core

[中文说明](README.zh-CN.md)

Composable application state, scoped observations, and action commits for agents.

Keep **what happened**, **what each participant was told**, and **what is shown
publicly** separate. An agent can retain an outdated observation or receive a
false claim without that claim rewriting shared state. Applications choose the
rules, participants, model providers, and interaction order.

This is a local alpha implementation. The working project name is provisional;
there is no published package or hosted service yet.

## Quick start

Requires Python 3.11+; the runtime uses only the standard library.
From this checkout, no installation or API key is needed:

```bash
python -m examples.information_flow
python -m examples.collaboration
python -m unittest discover -s tests -v
```

To use the package from another project, install this checkout with `python -m
pip install /path/to/agent-state-core`. Build dependencies may need to be
available to pip; this is a local path, not a package-index release.

## A small example

```python
from agent_state_core import Intent, Ledger, Record, Transition

with Ledger() as ledger:  # Use a file path to keep data across process restarts.
    ledger.commit(
        Transition(
            updates={"key_holder": "alice"},
            records=(Record("observation", {"key_holder": "alice"}, None),),
        ),
        expected_revision=0,
    )
    ledger.commit(
        Transition(
            updates={"key_holder": "bob"},
            records=(Record("observation", {"key_holder": "bob"}, ("alice", "bob")),),
        ),
        expected_revision=1,
        intent=Intent("alice", "transfer", {"to": "bob"}),
    )

    assert ledger.snapshot().state["key_holder"] == "bob"
    assert ledger.view("carol").records[-1].body["key_holder"] == "alice"
    context_for_carol = ledger.view("carol").to_context()
```

The application decided that the transfer succeeded and who observed it. The
ledger preserves that decision. It does not invent domain rules or certify that
an observation is true. The string `observation` is an application-defined kind.

## What the core provides

- Arbitrary JSON state with historical snapshots reconstructed from commits.
- Records with explicit public, addressed, or host-only audiences and source JSON.
- Intents and accepted/rejected results kept in host history; only explicitly
  published records enter participant context.
- Atomic SQLite commits, optimistic revision checks, and duplicate-commit lookup
  by request ID. A repeated request must have the same base, intent, and result.
- JSON context that ordinary Python functions or model adapters can consume.

There are no required character types, directors, world packs, turn schedules,
voting stages, or model SDKs. A single tool or human participant can use the
same primitives as a multi-agent application.

## Examples and limits

`information_flow` demonstrates a private transfer, an outdated public
observation, a mistaken claim, a rejected action, and reopening a saved ledger.
`collaboration` demonstrates a human changing a budget and preventing an old
proposal from overwriting newer state. Both use deterministic application code;
neither measures real model reasoning.

The alpha has no scheduler, semantic fact checker, automatic belief updater,
speculative branch manager, or tested framework adapters. History reads currently
scan the journal. Audience projection is a host-side context selection tool,
not authentication or a sandbox. External model/tool calls are outside the
transaction and may still run or be billed more than once.

See [API and semantics](docs/DESIGN.md), [source and design origins](PROVENANCE.md),
and [validation evidence](docs/VALIDATION.md).

## License

[MIT](LICENSE). No third-party runtime dependencies.
