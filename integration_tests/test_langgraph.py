import unittest

from langgraph.types import Command
from agent_state_core import Ledger, Record, Transition
from examples.langgraph_collaboration import build_graph, run


class LangGraphTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.addCleanup(self.ledger.close)
        self.ledger.commit(Transition(updates={"budget": 100}, records=(
            Record("requirement", {"budget": 100}, None),
            Record("requirement", {"budget": 999, "private": "SECRET"}, ("reviewer",)),)), expected_revision=0)
        self.graph = build_graph(self.ledger)
        self.config = {"configurable": {"thread_id": "test-session"}}

    def test_interrupt_resume_and_private_context_with_real_langgraph(self):
        paused = self.graph.invoke({"request": "test-session"}, self.config)
        self.assertTrue(paused["__interrupt__"])
        self.assertEqual(self.ledger.revision, 1)
        self.assertNotIn("SECRET", str(paused))
        self.assertEqual(paused["proposal"]["cost"], 100)
        resumed = self.graph.invoke(Command(resume={"budget": 40}), self.config)
        self.assertEqual(resumed["selected"]["cost"], 40)
        self.assertEqual(self.ledger.revision, 3)
        self.assertFalse(self.graph.get_state(self.config).next)

    def test_host_receipt_prevents_duplicate_commit_when_node_is_replayed(self):
        self.graph.invoke({"request": "same-request"}, self.config)
        first = self.graph.invoke(Command(resume={"budget": 50}), self.config)
        revision = self.ledger.revision
        second = self.graph.invoke({"request": "same-request"}, self.config)
        self.assertEqual(second["selected"], first["selected"])
        self.assertEqual(self.ledger.revision, revision)

    def test_invalid_human_input_does_not_change_ledger(self):
        self.graph.invoke({"request": "invalid"}, self.config)
        with self.assertRaises(ValueError):
            self.graph.invoke(Command(resume={"budget": True}), self.config)
        self.assertEqual(self.ledger.revision, 1)

    def test_documented_example_runs(self):
        self.assertEqual(run()["cost"], 50)
