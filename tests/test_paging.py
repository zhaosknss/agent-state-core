from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from agent_state_core import Intent, Ledger, Record, RecordCursor, Transition, ViewPage


class PagingTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.addCleanup(self.ledger.close)

    def drain(self, participant=None, *, kinds=None, limit=2, after=None, point=None):
        records = []
        while True:
            page = self.ledger.view_page(participant, after=after, at_revision=point,
                                         kinds=kinds, limit=limit)
            point = page.revision
            self.assertLessEqual(len(page.records), limit)
            records.extend(page.records)
            if not page.has_more:
                return tuple(records), page.next_cursor
            self.assertTrue(page.records)
            self.assertNotEqual(after, page.next_cursor)
            after = page.next_cursor

    def test_one_commit_spans_pages_and_exact_multiple_has_no_phantom_page(self):
        for count in (4, 5):
            with self.subTest(count=count), Ledger() as ledger:
                ledger.commit(Transition(records=tuple(Record("note", n, None)
                                                       for n in range(count))), expected_revision=0)
                page = ledger.view_page(limit=2)
                self.assertIsInstance(page, ViewPage)
                self.assertEqual(page.next_cursor, RecordCursor(1, 1))
                actual = list(page.records)
                pages = 1
                while page.has_more:
                    page = ledger.view_page(after=page.next_cursor, at_revision=1, limit=2)
                    actual.extend(page.records)
                    pages += 1
                self.assertEqual([r.id for r in actual], [f"1:{n}" for n in range(count)])
                self.assertEqual(pages, (count + 1) // 2)
                self.assertEqual(page.next_cursor, RecordCursor(1))

    def test_paged_projection_matches_full_view_for_scopes_kinds_and_limits(self):
        for n in range(3):
            self.ledger.commit(Transition(updates={"secret": "HOST_STATE"}, reason="HOST_REASON",
                records=(Record("note", [n, "public"], None),
                         Record("note", [n, "alice"], ("alice", "alice")),
                         Record("other", [n, "bob"], ("bob", "alice")),
                         Record("note", "HOST_NOTE", ()),
                         Record("note", "BOB_ONLY", ("bob",)))), expected_revision=n,
                intent=Intent("host", "private", "HOST_INTENT"))
        for participant in (None, "alice", "bob", "unknown"):
            for kinds in (None, (), ("note",), ("other", "note", "note"), ("missing",)):
                for limit in (1, 3, 20):
                    with self.subTest(participant=participant, kinds=kinds, limit=limit):
                        records, cursor = self.drain(participant, kinds=kinds, limit=limit)
                        self.assertEqual(records, self.ledger.view(participant, kinds=kinds).records)
                        self.assertEqual(cursor, RecordCursor(3))
        context = self.ledger.view_page("alice", limit=20).to_context()
        for hidden in ("HOST_STATE", "HOST_REASON", "HOST_NOTE", "HOST_INTENT", "BOB_ONLY"):
            self.assertNotIn(hidden, json.dumps(context))

    def test_fixed_read_point_excludes_new_commits_then_poll_finds_them(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.db"
            with Ledger(path) as reader, Ledger(path) as writer:
                writer.commit(Transition(records=tuple(Record("note", n, None) for n in range(3))),
                              expected_revision=0)
                first = reader.view_page(limit=1)
                writer.commit(Transition(records=(Record("note", "later", None),)), expected_revision=1)
                rest = reader.view_page(after=first.next_cursor, at_revision=first.revision, limit=2)
                self.assertEqual([r.body for r in rest.records], [1, 2])
                self.assertFalse(rest.has_more)
                self.assertEqual((rest.revision, rest.next_cursor), (1, RecordCursor(1)))
                latest = reader.view_page(after=rest.next_cursor)
                self.assertEqual([r.body for r in latest.records], ["later"])
                self.assertEqual(latest.next_cursor, RecordCursor(2))

    def test_empty_and_hidden_commits_advance_consumed_revision_without_skipping_future(self):
        empty = self.ledger.view_page()
        self.assertEqual((empty.records, empty.next_cursor, empty.has_more), ((), RecordCursor(0), False))
        self.ledger.commit(Transition(updates={"x": 1}), expected_revision=0)
        self.ledger.commit(Transition(records=(Record("note", "hidden", ("other",)),)), expected_revision=1)
        self.ledger.commit(Transition(records=(Record("other-kind", "filtered", None),)), expected_revision=2)
        page = self.ledger.view_page("alice", after=empty.next_cursor, kinds=("note",), limit=1)
        self.assertEqual((page.records, page.next_cursor, page.has_more), ((), RecordCursor(3), False))
        self.ledger.commit(Transition(records=(Record("note", "new", None),)), expected_revision=3)
        latest = self.ledger.view_page("alice", after=page.next_cursor, kinds=("note",))
        self.assertEqual([r.body for r in latest.records], ["new"])
        self.assertEqual(self.ledger.view_page(kinds=()).next_cursor, RecordCursor(4))

    def test_cursor_round_trip_resumes_inside_commit_after_reopen(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.db"
            with Ledger(path) as ledger:
                ledger.commit(Transition(records=tuple(Record("note", n, None) for n in range(5))),
                              expected_revision=0)
                first = ledger.view_page(limit=2)
                checkpoint = json.dumps({"cursor": asdict(first.next_cursor), "point": first.revision})
            saved = json.loads(checkpoint)
            with Ledger(path) as reopened:
                second = reopened.view_page(after=RecordCursor(**saved["cursor"]),
                                            at_revision=saved["point"], limit=3)
                self.assertEqual([r.body for r in second.records], [2, 3, 4])
                self.assertFalse(second.has_more)
                self.assertEqual(reopened.revision, 1)

    def test_retry_same_position_and_detached_context_do_not_change_storage(self):
        self.ledger.commit(Transition(records=(
            Record("note", {"items": [1]}, None, {"refs": ["source"]}),
            Record("note", {"items": [2]}, None),)), expected_revision=0)
        first = self.ledger.view_page(limit=1)
        context = first.to_context()
        context["records"][0]["body"]["items"].append(9)
        context["records"][0]["source"]["refs"].append("changed")
        self.assertEqual(first.records[0].body, {"items": [1]})
        self.assertEqual(first.records[0].source, {"refs": ["source"]})
        # A consumer that failed before saving next_cursor can retry the same position.
        self.assertEqual(self.ledger.view_page(at_revision=first.revision, limit=1), first)
        first.records[0].body["items"].append(8)
        self.assertEqual(self.ledger.view_page(limit=1).records[0].body, {"items": [1]})
        self.assertEqual((self.ledger.revision, len(self.ledger.history())), (1, 1))

    def test_whole_revision_checkpoint_differs_from_position_within_revision(self):
        self.ledger.commit(Transition(records=tuple(Record("note", n, None) for n in range(3))),
                           expected_revision=0)
        self.ledger.commit(Transition(records=(Record("note", 3, None),)), expected_revision=1)
        records, cursor = self.drain(after=RecordCursor(1, 0), limit=1)
        self.assertEqual([r.body for r in records], [1, 2, 3])
        self.assertEqual(cursor, RecordCursor(2))
        records, _ = self.drain(after=RecordCursor(1))
        self.assertEqual([r.body for r in records], [3])

    def test_paging_decodes_only_returned_records_without_full_history(self):
        self.ledger.commit(Transition(records=tuple(Record("note", n, None) for n in range(100))),
                           expected_revision=0)

        def authorizer(action, table, column, *_):
            if action == sqlite3.SQLITE_READ and table == "commits" and column == "payload":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.ledger._conn.set_authorizer(authorizer)
        with patch("agent_state_core.ledger.json.loads", wraps=json.loads) as decode:
            page = self.ledger.view_page(limit=2)
        self.assertEqual([r.body for r in page.records], [0, 1])
        self.assertEqual(decode.call_count, 4)  # Body + source for two returned records.
        self.assertTrue(page.has_more)

    def test_invalid_cursor_limit_and_scope_options_are_rejected(self):
        self.ledger.commit(Transition(), expected_revision=0)
        invalid = ({"limit": 0}, {"limit": True}, {"limit": 1.5},
                   {"after": RecordCursor(True)}, {"after": RecordCursor(-1)},
                   {"after": RecordCursor(1, True)}, {"after": RecordCursor(1, -1)},
                   {"after": RecordCursor(0, 0)}, {"after": RecordCursor(2)},
                   {"after": RecordCursor(1), "at_revision": 0},
                   {"at_revision": True}, {"at_revision": 2},
                   {"participant": ""}, {"kinds": "note"}, {"kinds": ("",)})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.ledger.view_page(**kwargs)
        with self.assertRaises(TypeError):
            self.ledger.view_page(after={"revision": 0})
        self.assertEqual(self.ledger.view_page(after=RecordCursor(1)).records, ())
