"""A small, model-free handoff recipe. Its schema is application policy, not core API.

Run from the checkout: python -m examples.context_handoff
All messages are fictional. Candidates never become authoritative state here.
"""
from agent_state_core import Ledger, Record, Transition


def context_note(project, key, text, scope, source, *, audience=None, withdrawn=False):
    """Build an application record; the host supplies and checks its source JSON."""
    return Record("context_note", {
        "project": project, "key": key, "text": text, "scope": scope,
        "status": "withdrawn" if withdrawn else "candidate",
    }, audience, source)


def build_handoff(ledger, participant, project, *, after_revision=0, at_revision=None):
    """Return the latest visible change per key in this project and read interval.

    A full read starts at zero. For a delta, keep previous keys, apply `notes`,
    and remove keys in `withdrawn`. The cursor is a read boundary, not evidence
    that a participant understood or agreed. Keep it only after consuming data.
    """
    view = ledger.view(participant, after_revision=after_revision,
                       at_revision=at_revision, kinds=("context_note",))
    latest = {}
    for record in view.records:
        if record.body["project"] == project:
            key = record.body["key"]
            latest.pop(key, None)
            latest[key] = record
    notes, withdrawn = [], []
    for record in latest.values():
        item = {"id": record.id, **record.body, "source": record.source}
        # Project is carried by the envelope; no timestamps or unrelated history.
        del item["project"]
        (withdrawn if item["status"] == "withdrawn" else notes).append(item)
    return {"project": project, "through_revision": view.revision,
            "notes": notes, "withdrawn": withdrawn}


def run():
    import json

    with Ledger() as ledger:
        first = context_note(
            "guide", "editing", "Pause this draft while its structure is reviewed.",
            "This draft's current review; not a permanent ban on editing.",
            {"message": "demo-1", "quote": "Pause edits while we review the structure."},
            audience=("writer", "reviewer"),
        )
        ledger.commit(Transition(records=(first,
            Record("private_note", "PRIVATE_REVIEW_NOTE", ("reviewer",)),
            context_note("another-project", "editing", "Use a different house style.",
                         "Another project's guide only.", {"message": "demo-other"}),
        )), expected_revision=0)
        before = build_handoff(ledger, "writer", "guide")
        cursor = before["through_revision"]

        revised = context_note(
            "guide", "editing", "Resume from the earlier draft; keep its approved opening.",
            "This revision task. A later instruction ended the temporary pause.",
            {"message": "demo-2", "quote": "Resume from the earlier draft and keep its opening."},
            audience=("writer", "reviewer"),
        )
        accepted = context_note(
            "guide", "reference-quality", "This draft is accepted for today, not an ideal template.",
            "This delivery only; not every future document.",
            {"message": "demo-3", "quote": "Send this version today; it is not our ideal template."},
            audience=("writer", "reviewer"),
        )
        ledger.commit(Transition(records=(revised, accepted)), expected_revision=1)
        delta = build_handoff(ledger, "writer", "guide", after_revision=cursor)
        assert [item["key"] for item in delta["notes"]] == ["editing", "reference-quality"]
        assert build_handoff(ledger, "writer", "guide", at_revision=1) == before

        ledger.commit(Transition(records=(context_note(
            "guide", "editing", "The temporary editing note is no longer needed.",
            "This draft's completed revision.", {"message": "demo-4"},
            audience=("writer", "reviewer"), withdrawn=True,
        ),)), expected_revision=2)
        withdrawal = build_handoff(ledger, "writer", "guide", after_revision=2)
        cached = {item["key"]: item for item in before["notes"]}
        for packet in (delta, withdrawal):
            cached.update({item["key"]: item for item in packet["notes"]})
            for item in packet["withdrawn"]:
                cached.pop(item["key"], None)
        assert list(cached) == ["reference-quality"]
        assert ledger.snapshot().state == {}
        assert "PRIVATE_REVIEW_NOTE" not in json.dumps(delta)
        assert "another-project" not in json.dumps(delta)
        assert build_handoff(ledger, None, "guide")["notes"] == []
        print("Revised candidates, scoped sources, and withdrawal:")
        print(json.dumps({"changes": delta, "later_withdrawal": withdrawal}, indent=2))
        return cached


if __name__ == "__main__":
    run()
