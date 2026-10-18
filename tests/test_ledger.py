from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from agent_state_core import (
    Intent, Ledger, Record, RequestConflict, SchemaError, StaleRevision, Transition,
)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.addCleanup(self.ledger.close)

    def test_hidden_state_intent_and_reason_do_not_enter_context(self):
        self.ledger.commit(Transition(
            updates={"secret": "STATE_MARKER"}, reason="REASON_MARKER",
            records=(Record("note", "HOST_MARKER", ()),
                     Record("note", "ALICE_MARKER", ("alice",)),
                     Record("message", "PUBLIC_MARKER", None))), expected_revision=0,
            intent=Intent("alice", "secret_plan", {"value": "INTENT_MARKER"}))
        bob = json.dumps(self.ledger.view("bob").to_context())
        for value in ("STATE_MARKER", "REASON_MARKER", "HOST_MARKER", "ALICE_MARKER", "INTENT_MARKER"):
            self.assertNotIn(value, bob)
        self.assertIn("PUBLIC_MARKER", bob)
        self.assertIn("ALICE_MARKER", str(self.ledger.view("alice").to_context()))
        self.assertEqual(len(self.ledger.view().records), 1)
        self.assertEqual(len(self.ledger.history()[0].transition.records), 3)

    def test_claims_do_not_change_state_and_old_observation_survives(self):
        self.ledger.commit(Transition(updates={"holder": "alice"}, records=(
            Record("observation", {"holder": "alice"}, None),)), expected_revision=0)
        self.ledger.commit(Transition(updates={"holder": "bob"}, records=(
            Record("observation", {"holder": "bob"}, ("bob",)),)), expected_revision=1)
        self.ledger.commit(Transition(records=(
            Record("claim", {"holder": "dana"}, ("carol",), {"verified": False}),)), expected_revision=2)
        self.assertEqual(self.ledger.snapshot().state, {"holder": "bob"})
        records = self.ledger.view("carol").records
        self.assertEqual([r.body["holder"] for r in records], ["alice", "dana"])
        self.assertEqual(records[-1].kind, "claim")
        self.assertFalse(records[-1].source["verified"])

    def test_historical_views_and_state_do_not_include_future(self):
        self.ledger.commit(Transition(updates={"value": 1}, records=(
            Record("observation", 1, None),)), expected_revision=0)
        self.ledger.commit(Transition(updates={"value": 2}, records=(
            Record("observation", 2, None),)), expected_revision=1)
        self.assertEqual(self.ledger.snapshot(at_revision=1).state, {"value": 1})
        self.assertEqual([r.body for r in self.ledger.view("a", at_revision=1).records], [1])
        self.assertEqual(self.ledger.snapshot(at_revision=0).state, {})
        self.assertEqual(self.ledger.view(at_revision=0).records, ())
        with self.assertRaises(ValueError):
            self.ledger.snapshot(at_revision=3)

    def test_rejected_action_is_recorded_without_state_change(self):
        self.ledger.commit(Transition(updates={"holder": "bob"}), expected_revision=0)
        intent = Intent("alice", "give", {"to": "carol"})
        self.ledger.commit(Transition(accepted=False, reason="not held", records=(
            Record("action_result", "failed", ("alice",)),)),
            expected_revision=1, intent=intent)
        self.assertEqual(self.ledger.snapshot().state, {"holder": "bob"})
        self.assertFalse(self.ledger.history()[-1].transition.accepted)
        self.assertEqual(self.ledger.history()[-1].intent, intent)
        self.assertEqual(self.ledger.view("bob").records, ())

    def test_rejected_state_changes_are_an_error_not_silently_dropped(self):
        for transition in (Transition(updates={"x": 1}, accepted=False),
                           Transition(deletes=("x",), accepted=False)):
            with self.subTest(transition=transition), self.assertRaises(ValueError):
                self.ledger.commit(transition, expected_revision=0)
        self.assertEqual(self.ledger.revision, 0)

    def test_stale_commit_writes_neither_state_nor_records(self):
        base = self.ledger.snapshot()
        self.ledger.commit(Transition(updates={"budget": 50}), expected_revision=base.revision)
        with self.assertRaises(StaleRevision) as error:
            self.ledger.commit(Transition(updates={"plan": "old"}, records=(
                Record("decision", "old", None),)), expected_revision=base.revision)
        self.assertEqual((error.exception.expected, error.exception.actual), (0, 1))
        self.assertEqual(self.ledger.snapshot().state, {"budget": 50})
        self.assertEqual(self.ledger.view().records, ())

    def test_duplicate_request_returns_original_after_later_commit(self):
        transition = Transition(updates={"x": 1}, records=(Record("fact", 1, None),))
        intent = Intent("a", "set", {"x": 1})
        first = self.ledger.commit(transition, expected_revision=0,
                                   intent=intent, request_id="request")
        self.ledger.commit(Transition(updates={"x": 2}), expected_revision=1)
        again = self.ledger.commit(transition, expected_revision=0,
                                   intent=intent, request_id="request")
        self.assertEqual(first, again)
        self.assertEqual(self.ledger.revision, 2)
        self.assertEqual(self.ledger.snapshot().state, {"x": 2})
        self.assertEqual(len(self.ledger.view().records), 1)

    def test_commit_without_request_id_does_not_compute_deduplication_hash(self):
        with patch("agent_state_core.ledger.hashlib.sha256", side_effect=AssertionError("unused hash")):
            receipt = self.ledger.commit(Transition(updates={"x": [1]}, records=(
                Record("note", {"value": 1}, None),)), expected_revision=0)
        self.assertIsNone(receipt.request_id)
        self.assertEqual(self.ledger.snapshot().state, {"x": [1]})
        self.assertEqual(self.ledger.view().records[0].body, {"value": 1})

    def test_request_id_cannot_be_reused_for_changed_content(self):
        transition = Transition(updates={"x": 1})
        self.ledger.commit(transition, expected_revision=0, request_id="same")
        for kwargs in (
            {"transition": Transition(updates={"x": 2}), "expected_revision": 0},
            {"transition": transition, "expected_revision": 1},
            {"transition": transition, "expected_revision": 0, "intent": Intent("a", "act")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(RequestConflict):
                self.ledger.commit(request_id="same", **kwargs)
        self.assertEqual(self.ledger.revision, 1)

    def test_record_audience_is_explicit_and_order_is_not_significant(self):
        transition = Transition(records=(Record("note", "shared", ("b", "a", "a")),))
        first = self.ledger.commit(transition, expected_revision=0, request_id="shared")
        again = self.ledger.commit(Transition(records=(Record("note", "shared", ("a", "b")),)),
                                   expected_revision=0, request_id="shared")
        self.assertEqual(first, again)
        self.assertEqual(len(self.ledger.view("a").records), 1)
        self.assertEqual(len(self.ledger.view("b").records), 1)
        self.assertEqual(self.ledger.view("c").records, ())

    def test_source_reference_does_not_expand_hidden_material(self):
        self.ledger.commit(Transition(records=(Record("note", "SECRET", ()),)), expected_revision=0)
        source = {"record_id": "1:0", "method": "reported"}
        self.ledger.commit(Transition(records=(Record("claim", "possibly rain", None, source),)),
                           expected_revision=1)
        view = self.ledger.view("a").to_context()
        self.assertNotIn("SECRET", str(view))
        self.assertEqual(view["records"][0]["source"], source)

    def test_mutating_inputs_and_results_does_not_change_persisted_data(self):
        nested = {"items": [1]}
        receipt = self.ledger.commit(Transition(updates={"x": nested}, records=(
            Record("note", nested, None, {"items": [1]}),)), expected_revision=0)
        nested["items"].append(2)
        receipt.transition.updates["x"]["items"].append(3)
        self.ledger.snapshot().state["x"]["items"].append(4)
        view = self.ledger.view("a")
        context = view.to_context()
        context["records"][0]["body"]["items"].append(5)
        self.assertEqual(view.records[0].body, {"items": [1]})
        view.records[0].body["items"].append(6)
        self.assertEqual(self.ledger.snapshot().state["x"], {"items": [1]})
        self.assertEqual(self.ledger.view("a").records[0].body, {"items": [1]})

    def test_invalid_json_aborts_the_whole_result(self):
        cyclic = []
        cyclic.append(cyclic)
        for invalid in (float("nan"), float("inf"), {1: "integer key"}, (1, 2), object(), cyclic):
            with self.subTest(value=type(invalid).__name__), self.assertRaises(ValueError):
                self.ledger.commit(Transition(updates={"valid": 1}, records=(
                    Record("note", invalid, None),)), expected_revision=0)
            self.assertEqual(self.ledger.revision, 0)
            self.assertEqual(self.ledger.snapshot().state, {})

    def test_validation_rejects_ambiguous_labels_and_boolean_revisions(self):
        for value in (True, -1, 1.5, "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.ledger.commit(Transition(), expected_revision=value)
        for transition in (
            Transition(accepted=1), Transition(updates={"": 1}),
            Transition(records=(Record("note", "x", "alice"),)),
            Transition(records=(Record("", "x", None),)),
            Transition(deletes=("x", "x")),
            Transition(updates={"x": 1}, deletes=("x",)),
        ):
            with self.subTest(transition=transition), self.assertRaises(ValueError):
                self.ledger.commit(transition, expected_revision=0)
        self.assertEqual(self.ledger.revision, 0)

    def test_custom_action_names_and_nested_state_need_no_story_schema(self):
        self.ledger.commit(Transition(updates={"ci": {"jobs": ["lint"], "ready": True}},
                                      records=(Record("ci-result", {"exit_code": 0}, ("reviewer",)),)),
                           expected_revision=0, intent=Intent("runner", "verify-build", ["lint"]))
        self.assertTrue(self.ledger.snapshot().state["ci"]["ready"])
        self.assertEqual(self.ledger.view("reviewer").records[0].kind, "ci-result")

    def test_deletion_is_replayable_and_does_not_mutate_past(self):
        self.ledger.commit(Transition(updates={"x": 1, "y": None}), expected_revision=0)
        self.ledger.commit(Transition(deletes=("x",)), expected_revision=1)
        self.assertEqual(self.ledger.snapshot().state, {"y": None})
        self.assertEqual(self.ledger.snapshot(at_revision=1).state, {"x": 1, "y": None})


class FileTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.db"

    def test_reopen_preserves_history_views_and_deduplication(self):
        transition = Transition(updates={"x": 1}, records=(Record("observation", "seen", ("a",)),))
        with Ledger(self.path) as ledger:
            first = ledger.commit(transition, expected_revision=0, request_id="once")
        with Ledger(self.path) as ledger:
            self.assertEqual(ledger.snapshot().state, {"x": 1})
            self.assertEqual(ledger.view("b").records, ())
            self.assertEqual(ledger.view("a").records[0].body, "seen")
            self.assertEqual(ledger.commit(transition, expected_revision=0, request_id="once"), first)

    def test_two_concurrent_writers_cannot_both_commit_the_same_base(self):
        with Ledger(self.path):
            pass
        barrier = Barrier(2)

        def write(value):
            with Ledger(self.path) as ledger:
                base = ledger.snapshot()
                barrier.wait(timeout=5)
                try:
                    ledger.commit(Transition(updates={"winner": value}), expected_revision=base.revision)
                    return "committed", value
                except StaleRevision:
                    return "stale", value

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ("a", "b")))
        self.assertEqual(sorted(status for status, _ in results), ["committed", "stale"])
        winner = next(value for status, value in results if status == "committed")
        with Ledger(self.path) as ledger:
            self.assertEqual(ledger.revision, 1)
            self.assertEqual(ledger.snapshot().state, {"winner": winner})

    def test_database_write_failure_does_not_create_partial_result(self):
        with Ledger(self.path) as ledger:
            ledger.commit(Transition(updates={"x": 1}), expected_revision=0)
            with closing(sqlite3.connect(self.path)) as connection, connection:
                connection.execute("CREATE TRIGGER refuse_insert BEFORE INSERT ON commits "
                                   "BEGIN SELECT RAISE(ABORT, 'simulated disk write failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                ledger.commit(Transition(updates={"x": 2}, records=(Record("note", "new", None),)),
                              expected_revision=1, request_id="retry")
            self.assertEqual(ledger.revision, 1)
            self.assertEqual(ledger.snapshot().state, {"x": 1})
            self.assertEqual(ledger.view().records, ())
            with closing(sqlite3.connect(self.path)) as connection, connection:
                connection.execute("DROP TRIGGER refuse_insert")
            ledger.commit(Transition(updates={"x": 2}), expected_revision=1, request_id="retry")
            self.assertEqual(ledger.revision, 2)

    def test_unrelated_database_is_refused_and_not_modified(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE valuable (value TEXT)")
            connection.execute("INSERT INTO valuable VALUES ('keep')")
        before = self.path.read_bytes()
        with self.assertRaises(SchemaError):
            Ledger(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_future_schema_is_refused(self):
        with Ledger(self.path):
            pass
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE asc_meta SET schema_version=999")
        before = self.path.read_bytes()
        with self.assertRaises(SchemaError):
            Ledger(self.path)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
