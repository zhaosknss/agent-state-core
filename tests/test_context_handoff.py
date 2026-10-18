"""Failure boundaries for the optional checkout recipe, not new kernel policy."""
import json
import unittest

from agent_state_core import Ledger, Record, Transition
from examples.context_handoff import build_handoff, context_note


class ContextHandoffTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.addCleanup(self.ledger.close)

    def note(self, text, *, project="guide", key="editing", audience=("writer",), withdrawn=False):
        return context_note(project, key, text, "This task only.",
                            {"message": text}, audience=audience, withdrawn=withdrawn)

    def commit(self, *records):
        return self.ledger.commit(Transition(records=records),
                                  expected_revision=self.ledger.revision)

    def test_context_excludes_other_projects_host_data_and_private_records(self):
        self.ledger.commit(Transition(updates={"secret": "HOST_STATE"}, records=(
            self.note("visible"), self.note("OTHER_PROJECT", project="elsewhere"),
            self.note("PRIVATE_CANDIDATE", key="review", audience=("reviewer",)),
            Record("context_note", {"project": "guide", "key": "host", "text": "HOST_ONLY"}, ()),
        )), expected_revision=0)
        packet = build_handoff(self.ledger, "writer", "guide")
        self.assertEqual([item["text"] for item in packet["notes"]], ["visible"])
        for hidden in ("HOST_STATE", "OTHER_PROJECT", "PRIVATE_CANDIDATE", "HOST_ONLY"):
            self.assertNotIn(hidden, json.dumps(packet))
        self.assertEqual(build_handoff(self.ledger, None, "guide")["notes"], [])

    def test_revision_keeps_old_context_and_does_not_promote_candidates(self):
        self.commit(self.note("pause"), self.note("old quality", key="quality"))
        old = build_handoff(self.ledger, "writer", "guide")
        self.commit(self.note("accepted", key="quality"), self.note("resume"))
        current = build_handoff(self.ledger, "writer", "guide")
        self.assertEqual([item["text"] for item in current["notes"]], ["accepted", "resume"])
        self.assertEqual(current["notes"][0]["status"], "candidate")
        self.assertEqual(build_handoff(self.ledger, "writer", "guide", at_revision=1), old)
        self.assertEqual(len(self.ledger.view("writer").records), 4)
        self.assertEqual(self.ledger.snapshot().state, {})

    def test_withdrawal_delta_removes_cached_note_but_empty_delta_keeps_others(self):
        self.commit(self.note("pause"), self.note("accepted, not ideal", key="quality"))
        full = build_handoff(self.ledger, "writer", "guide")
        cache = {item["key"]: item for item in full["notes"]}
        self.commit(self.note("pause ended", withdrawn=True))
        delta = build_handoff(self.ledger, "writer", "guide", after_revision=1)
        self.assertEqual(delta["notes"], [])
        self.assertEqual([item["key"] for item in delta["withdrawn"]], ["editing"])
        for item in delta["withdrawn"]:
            cache.pop(item["key"], None)
        self.commit(Record("unrelated", "new activity", None))
        empty = build_handoff(self.ledger, "writer", "guide", after_revision=2)
        self.assertEqual((empty["notes"], empty["withdrawn"]), ([], []))
        self.assertEqual(list(cache), ["quality"])
        self.assertEqual(empty["through_revision"], 3)
        # A resume instruction later reuses the same key without rewriting history.
        self.commit(self.note("resume"))
        self.assertEqual(build_handoff(self.ledger, "writer", "guide")["notes"][0]["text"],
                         "accepted, not ideal")
        self.assertEqual(build_handoff(self.ledger, "writer", "guide")["notes"][1]["text"], "resume")

    def test_invisible_revision_does_not_replace_a_visible_candidate(self):
        self.commit(self.note("writer's old view"))
        self.commit(self.note("reviewer's newer view", audience=("reviewer",)))
        writer = build_handoff(self.ledger, "writer", "guide")
        reviewer = build_handoff(self.ledger, "reviewer", "guide")
        self.assertEqual(writer["notes"][0]["text"], "writer's old view")
        self.assertEqual(reviewer["notes"][0]["text"], "reviewer's newer view")
