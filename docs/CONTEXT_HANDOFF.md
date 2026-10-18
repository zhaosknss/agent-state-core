# Scoped context handoff

[中文说明](CONTEXT_HANDOFF.zh-CN.md)

This checkout recipe passes useful context to another conversation, tool, or
documentation workflow. It keeps sources and scope, revises an interpretation
without deleting history, and explicitly withdraws outdated notes.

## Run it

From the repository checkout, with Python 3.11+:

```bash
python -m examples.context_handoff
python -B tools/verify.py
```

It uses fictional messages and ordinary functions, with no API key, model call,
or optional dependency. The helpers are in `examples/context_handoff.py`, not
installed in the core wheel. This Unreleased addition requires a current checkout;
the alpha-2 release archives do not include it.

## Behavior and application policy

A writer first receives a candidate interpretation: pause edits during review.
A later instruction resumes editing while preserving an approved opening. A
separate note distinguishes accepting this delivery from endorsing an ideal
template. When a temporary note expires, the host publishes a withdrawal.

`build_handoff()` takes the last **visible** record per key in one project and
read interval, in the order those final changes occurred. Replaced versions and
unused metadata are omitted from the packet; complete history remains in the
ledger. A private update does not replace someone else's visible old note.

These project tags, statuses and latest-visible-key rules are application
conventions. The core does not interpret them or decide which statement is
right. Project selection does not authenticate a caller or replace audience
filtering. The host must supply the recipe's record schema consistently.

## Use from a checkout

```python
from agent_state_core import Ledger, Transition
from examples.context_handoff import build_handoff, context_note

with Ledger() as ledger:
    note = context_note(
        "docs", "revision-scope", "Keep the approved opening.",
        "This document's revision only.", {"message": "sample-1"},
    )
    ledger.commit(Transition(records=(note,)), expected_revision=0)
    packet = build_handoff(ledger, "new-session", "docs")
    assert packet["notes"][0]["status"] == "candidate"
    assert ledger.snapshot().state == {}
```

Keep and adapt the helper with your application under the MIT license. Your host
provides each candidate and source, verifies model-generated quotes against real
material when applicable, and chooses the audience. This example does not extract
understanding automatically. Source JSON must itself be safe to publish; source
references are not automatically dereferenced.

## Revision, withdrawal, and deltas

- A new record with the same project/key replaces the prior visible candidate
  in this recipe's packet. Old records remain readable using `view()` and
  `at_revision`. Different participants need not agree.
- `withdrawn=True` produces an explicit withdrawal. Delta consumers must
  remove that key instead of retaining the cached old note.
- An empty delta does not clear other keys. Its `through_revision` can still
  advance because ledger revisions are global.

Initialize a cache from a full read, then apply deltas:

```python
def apply_packet(cache, packet):
    cache.update({item["key"]: item for item in packet["notes"]})
    for item in packet["withdrawn"]:
        cache.pop(item["key"], None)
```

After successfully consuming a packet, the application may save its
`through_revision` as the next `after_revision`. This is a reading boundary,
not proof an AI understood or a user confirmed anything. The recipe does not
save cursors or promote candidates to authoritative state automatically.
Keep each cache and cursor bound to the same ledger, project and participant;
start with a full read when switching any of them.

## Limits

This is a starting point for project continuation, documentation cleanup and
scoped understanding records. Humans, models or functions can produce notes.
Relevant-content selection, semantic conflict resolution, source verification,
and conversation coordination remain application work.

The example and tests check visibility, history, order and withdrawal handling.
They do not establish fewer user corrections, better reasoning, smaller token
usage, automatic access to existing chats, or integration with a documentation
plugin. A packet can still be too long; choose content for the actual task.
