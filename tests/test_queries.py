from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_state_core import Ledger, Record, Transition


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.addCleanup(self.ledger.close)

    def test_filters_keep_scope_order_and_historical_boundary(self):
        for n in range(1, 5):
            self.ledger.commit(Transition(records=(
                Record("claim", n, ("alice",)), Record("observation", n, None),
                Record("claim", f"private-{n}", ("bob",)))), expected_revision=n-1)
        view = self.ledger.view("alice", at_revision=3, after_revision=1,
                                kinds=("claim", "observation"), last=3)
        self.assertEqual([(r.kind, r.body) for r in view.records],
                         [("observation", 2), ("claim", 3), ("observation", 3)])
        self.assertEqual(view.revision, 3)
        self.assertEqual([r.body for r in self.ledger.view(kinds=("claim",)).records], [])
        self.assertEqual(self.ledger.view("alice", kinds=()).records, ())

    def test_two_records_in_one_commit_keep_order_with_last_window(self):
        self.ledger.commit(Transition(records=tuple(Record("note", n, None) for n in range(5))),
                           expected_revision=0)
        self.assertEqual([r.body for r in self.ledger.view(last=2).records], [3, 4])
        self.assertEqual(self.ledger.view(after_revision=1).records, ())

    def test_invalid_query_options(self):
        for kwargs in ({"last": 0}, {"last": True}, {"after_revision": True},
                       {"after_revision": 1}, {"kinds": "claim"}, {"kinds": ("",)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.ledger.view(**kwargs)

    def test_state_and_views_do_not_read_full_commit_payloads(self):
        for n in range(30):
            self.ledger.commit(Transition(updates={"counter": n}, records=(
                Record("note", "large private history" * 100, ("other",)),)), expected_revision=n)
        self.ledger.commit(Transition(records=(Record("note", "visible", ("alice",)),)),
                           expected_revision=30)

        def authorizer(action, table, column, *_):
            if action == sqlite3.SQLITE_READ and table == "commits" and column == "payload":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.ledger._conn.set_authorizer(authorizer)
        self.assertEqual(self.ledger.snapshot().state, {"counter": 29})
        self.assertEqual([r.body for r in self.ledger.view("alice").records], ["visible"])

    def test_request_lookup_is_detached_and_can_prevent_repeated_host_work(self):
        self.assertIsNone(self.ledger.get_commit("missing"))
        self.ledger.commit(Transition(updates={"x": [1]}), expected_revision=0, request_id="done")
        result = self.ledger.get_commit("done")
        result.transition.updates["x"].append(2)
        self.assertEqual(self.ledger.get_commit("done").transition.updates, {"x": [1]})

    def test_projection_failure_rolls_back_journal_and_all_query_tables(self):
        self.ledger.commit(Transition(updates={"x": 1}), expected_revision=0)
        self.ledger._conn.execute(
            "CREATE TRIGGER refuse_scope BEFORE INSERT ON record_audience "
            "BEGIN SELECT RAISE(ABORT, 'projection failed'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.commit(Transition(updates={"x": 2}, records=(Record("note", "x", ("a",)),)),
                               expected_revision=1, request_id="retry")
        self.assertEqual(self.ledger.revision, 1)
        self.assertEqual(self.ledger.snapshot().state, {"x": 1})
        self.assertEqual(self.ledger.view("a").records, ())
        self.assertIsNone(self.ledger.get_commit("retry"))


def make_v1(path):
    data = {"updates": {"holder": "alice"}, "deletes": [], "records": [
        {"kind": "observation", "body": {"holder": "alice"}, "audience": ["alice"], "source": None}],
        "accepted": True, "reason": "", "intent": None}
    encode = lambda value: json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encode({"base": 0, "payload": data}).encode()).hexdigest()
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE asc_meta (schema_version INTEGER NOT NULL)")
        connection.execute("INSERT INTO asc_meta VALUES (1)")
        connection.execute("CREATE TABLE commits (revision INTEGER PRIMARY KEY CHECK(revision>0),"
                           "created_at TEXT NOT NULL, request_id TEXT UNIQUE,"
                           "request_hash TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("INSERT INTO commits VALUES (1,?,?,?,?)",
                           ("2026-10-17T00:00:00+00:00", "legacy", digest, encode(data)))


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "legacy.db"
        make_v1(self.path)

    def test_v1_is_upgraded_without_changing_history_or_request_identity(self):
        with Ledger(self.path) as ledger:
            original = ledger.history()[0]
            self.assertEqual(ledger.snapshot().state, {"holder": "alice"})
            self.assertEqual(ledger.view("bob").records, ())
            self.assertEqual(ledger.view("alice").records[0].body, {"holder": "alice"})
            self.assertEqual(ledger.commit(original.transition, expected_revision=0,
                                          request_id="legacy"), original)
            ledger.commit(Transition(updates={"holder": "bob"}), expected_revision=1)
        with Ledger(self.path) as reopened:
            self.assertEqual(reopened.snapshot().state["holder"], "bob")
            self.assertEqual(reopened.snapshot(at_revision=1).state["holder"], "alice")

    def test_failed_migration_leaves_v1_readable_and_retryable(self):
        with patch.object(Ledger, "_index_commit", side_effect=sqlite3.OperationalError("failure")):
            with self.assertRaises(sqlite3.OperationalError):
                Ledger(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT schema_version FROM asc_meta").fetchone()[0], 1)
            names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(names, {"asc_meta", "commits"})
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM commits").fetchone()[0], 1)
        with Ledger(self.path) as ledger:
            self.assertEqual(ledger.snapshot().state, {"holder": "alice"})
