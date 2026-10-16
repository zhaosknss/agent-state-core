# agent-state-core

[中文说明](README.zh-CN.md)

Composable application state, scoped observations, and action commits for agents.

Keep **what happened**, **what each participant was told**, and **what is shown
publicly** separate. An agent can retain an outdated observation or receive a
false claim without that claim rewriting shared state. Applications choose the
rules, participants, model providers, and interaction order.

This is an early open-source alpha. I extracted these ideas from a project I was
building and would like people to try them in their own applications. Feedback
on real use cases, awkward interfaces, and missing pieces is welcome.

[Try the release](https://github.com/zhaosknss/agent-state-core/releases) ·
[Share feedback](https://github.com/zhaosknss/agent-state-core/discussions) ·
[Report a problem](https://github.com/zhaosknss/agent-state-core/issues)

## Quick start

Requires Python 3.11+; the runtime uses only the standard library.
From this checkout, no installation or API key is needed:

```bash
git clone https://github.com/zhaosknss/agent-state-core.git
cd agent-state-core
python -m examples.information_flow
python -m examples.collaboration
python -m unittest discover -s tests -v
```

To use it from another project, download the wheel from
[Releases](https://github.com/zhaosknss/agent-state-core/releases) and install it:

```bash
python -m pip install ./agent_state_core-0.1.0a1-py3-none-any.whl
```

You can also install a local checkout with `python -m pip install
/path/to/agent-state-core`. Build dependencies may need to be available to pip.
The project is not published on PyPI.

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

## Try it and tell me what you think

I would like to hear where this fits in something you are building, which parts
are useful, and where the API gets in your way. If your use case needs a
different approach, that is useful feedback too.

You can start a [discussion](https://github.com/zhaosknss/agent-state-core/discussions)
with an idea or question. For a bug, an
[issue](https://github.com/zhaosknss/agent-state-core/issues) with a small example,
what you expected, and what happened would help me reproduce it. See
[contributing](CONTRIBUTING.md) if you want to change the code.

## License

[MIT](LICENSE). No third-party runtime dependencies.
