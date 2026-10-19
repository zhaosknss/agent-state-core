from concurrent.futures import ThreadPoolExecutor
import json
import unittest
from unittest.mock import patch

from agent_state_core import Ledger, Record, Transition
from examples.langchain_retrieval import build_retriever


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.addCleanup(self.ledger.close)
        self.ledger.commit(Transition(updates={"secret": "HOST_DATA"}, records=(
            Record("note", {"text": "guide public"}, None, {"doc": "public-guide"}),
            Record("note", {"text": "guide operator"}, ("operator",)),
            Record("note", {"text": "guide SECRET"}, ("reviewer",)),
            Record("note", {"text": "guide HOST_NOTE"}, ()),
        )), expected_revision=0)

    def test_participants_get_separate_caches_and_worker_chain_needs_no_ledger_access(self):
        operator = build_retriever(self.ledger.view("operator"))
        reviewer = build_retriever(self.ledger.view("reviewer"))
        # Run on a different thread with network blocked; the values need no SQLite access.
        with ThreadPoolExecutor(max_workers=1) as worker:
            result = worker.submit(operator.invoke, "guide").result()
        self.assertEqual([r["id"] for r in result["matches"]], ["1:0", "1:1"])
        self.assertEqual([r["id"] for r in reviewer.invoke("guide")["matches"]], ["1:0", "1:2"])
        self.assertEqual(result["matches"][0]["source"], {"doc": "public-guide"})
        for secret in ("SECRET", "HOST_DATA", "HOST_NOTE"):
            self.assertNotIn(secret, json.dumps(result))

    def test_rebuild_advances_read_point_without_mutating_old_cache_or_history(self):
        earlier = build_retriever(self.ledger.view("operator"))
        earlier.invoke("public")["matches"][0]["body"]["text"] = "poisoned cache"
        self.assertEqual(len(earlier.invoke("public")["matches"]), 1)
        self.ledger.commit(Transition(records=(Record("note", "new material", None),)),
                           expected_revision=1)
        self.assertEqual(earlier.invoke("new")["through_revision"], 1)
        self.assertEqual(earlier.invoke("new")["matches"], [])
        current = build_retriever(self.ledger.view("operator"))
        self.assertEqual(current.invoke("new")["through_revision"], 2)
        self.assertEqual([r["id"] for r in current.invoke("new")["matches"]], ["2:0"])
        self.assertEqual(len(self.ledger.view(at_revision=1).records), 1)

    def test_external_cache_failure_leaves_committed_ledger_rebuildable(self):
        self.ledger.commit(Transition(records=(Record("note", "new material", None),)),
                           expected_revision=1, request_id="publish")
        with patch("langchain_core.stores.InMemoryStore.mset", side_effect=RuntimeError("cache unavailable")):
            with self.assertRaisesRegex(RuntimeError, "cache unavailable"):
                build_retriever(self.ledger.view("operator"))
        self.assertEqual(self.ledger.revision, 2)
        self.assertIsNotNone(self.ledger.get_commit("publish"))
        rebuilt = build_retriever(self.ledger.view("operator"))
        self.assertEqual([r["id"] for r in rebuilt.invoke("new")["matches"]], ["2:0"])
