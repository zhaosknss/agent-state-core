"""Reproduce small composition checks and deliberate alpha boundaries.

Run from a checkout: python -B tools/audit_composition.py
Only temporary databases and fictional data are used. A passing boundary check
means the restriction was reproduced, not that all compositions are supported.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_state_core import Intent, Ledger, Record, SchemaError, StaleRevision, Transition


def state_only():
    with Ledger() as ledger:
        ledger.commit(Transition(updates={"metrics": {"completed": 1}}), expected_revision=0)
        assert ledger.snapshot().state == {"metrics": {"completed": 1}}
        assert ledger.view().records == ()
        assert ledger.history()[0].intent is None
        return {"records_required": False, "intent_required": False}


def records_only():
    with Ledger() as ledger:
        ledger.commit(Transition(records=(
            Record("acme.review.v7", {"evidence": [1, None, True]}, ("tool/x",)),
        )), expected_revision=0)
        assert ledger.snapshot().state == {}
        assert ledger.view("tool/x").records[0].kind == "acme.review.v7"
        return {"state_required": False, "registered_kinds_or_participants_required": False}


def action_only():
    with Ledger() as ledger:
        intent = Intent("human/x", "custom/transform", {"dry_run": True})
        ledger.commit(Transition(reason="host selected result"), expected_revision=0, intent=intent)
        assert ledger.history()[0].intent == intent
        assert ledger.snapshot().state == {} and ledger.view().records == ()
        return {"state_or_records_required": False, "external_tool_invoked": False}


def json_adapter():
    @dataclass
    class Note:
        text: str
        confidence: float

    with Ledger() as ledger:
        note = Note("fictional source", 0.5)
        try:
            ledger.commit(Transition(records=(Record("memory", note, None),)), expected_revision=0)
        except ValueError:
            pass
        else:
            raise AssertionError("external object accepted without JSON conversion")
        assert ledger.revision == 0
        ledger.commit(Transition(records=(Record("memory", asdict(note), None),)), expected_revision=0)
        assert ledger.view().records[0].body == asdict(note)
        return {"direct_dataclass": "rejected", "explicit_json_adapter": "accepted"}


def message_invalidates_state_based_work():
    with Ledger() as ledger:
        ledger.commit(Transition(updates={"budget": 100}), expected_revision=0)
        base = ledger.snapshot()
        ledger.commit(Transition(records=(Record("scratch", "side note", ()),)), expected_revision=1)
        assert ledger.snapshot().state == base.state
        try:
            ledger.commit(Transition(updates={"selected": True}), expected_revision=base.revision)
        except StaleRevision as error:
            assert (error.expected, error.actual) == (1, 2)
        else:
            raise AssertionError("expected global revision conflict")
        return {"state_unchanged": True, "old_base_commit": "StaleRevision"}


def disjoint_updates_conflict():
    with Ledger() as ledger:
        base = ledger.revision
        ledger.commit(Transition(updates={"component_a": 1}), expected_revision=base)
        try:
            ledger.commit(Transition(updates={"component_b": 2}), expected_revision=base)
        except StaleRevision:
            pass
        else:
            raise AssertionError("expected conservative conflict on disjoint keys")
        assert ledger.snapshot().state == {"component_a": 1}
        return {"automatic_disjoint_merge": False}


def nested_replacement():
    with Ledger() as ledger:
        ledger.commit(Transition(updates={"settings": {"left": 1, "right": 2}}), expected_revision=0)
        ledger.commit(Transition(updates={"settings": {"right": 3}}), expected_revision=1)
        assert ledger.snapshot().state == {"settings": {"right": 3}}
        return {"update_unit": "whole top-level value", "automatic_deep_merge": False}


def dedicated_schema():
    with TemporaryDirectory() as directory:
        foreign = Path(directory) / "application.db"
        with closing(sqlite3.connect(foreign)) as db, db:
            db.execute("CREATE TABLE application_data(value TEXT)")
            db.execute("INSERT INTO application_data VALUES ('preserve')")
        try:
            Ledger(foreign)
        except SchemaError:
            pass
        else:
            raise AssertionError("foreign schema accepted")
        with closing(sqlite3.connect(foreign)) as db:
            assert db.execute("SELECT value FROM application_data").fetchone()[0] == "preserve"
        owned = Path(directory) / "ledger.db"
        with Ledger(owned):
            pass
        # Probe an extra application table only in a disposable database.
        with closing(sqlite3.connect(owned)) as db, db:
            db.execute("CREATE TABLE application_cache(value TEXT)")
        try:
            Ledger(owned)
        except SchemaError:
            pass
        else:
            raise AssertionError("extra table accepted")
        return {"foreign_schema": "refused without data loss", "extra_application_table": "refused"}


def worker_connection():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.db"
        with Ledger(path) as ledger:
            ledger.commit(Transition(updates={"ready": True}), expected_revision=0)

            def read_with_owned_connection():
                with Ledger(path) as worker_ledger:
                    return worker_ledger.snapshot().state

            with ThreadPoolExecutor(max_workers=1) as worker:
                try:
                    worker.submit(ledger.snapshot).result()
                except sqlite3.ProgrammingError:
                    pass
                else:
                    raise AssertionError("shared connection crossed threads")
                assert worker.submit(read_with_owned_connection).result() == {"ready": True}
        return {"shared_instance": "thread-affine", "worker_owned_connection": "works"}


def window_is_not_queue():
    with Ledger() as ledger:
        ledger.commit(Transition(records=tuple(Record("event", n, None) for n in range(5))),
                      expected_revision=0)
        window = ledger.view(after_revision=0, last=2)
        assert [record.body for record in window.records] == [3, 4]
        assert ledger.view(after_revision=window.revision).records == ()
        page = ledger.view_page(limit=2)
        seen = list(page.records)
        while page.has_more:
            page = ledger.view_page(after=page.next_cursor, at_revision=1, limit=2)
            seen.extend(page.records)
        assert [record.body for record in seen] == list(range(5))
        return {"total_records": 5, "window_records": 2,
                "unseen_if_window_revision_used_as_queue_cursor": 3,
                "records_consumed_with_view_page": len(seen)}


def project_filter_is_application_policy():
    with Ledger() as ledger:
        ledger.commit(Transition(records=(Record("note", {"project": "a"}, None),)), expected_revision=0)
        ledger.commit(Transition(records=(Record("note", {"project": "b"}, None),)), expected_revision=1)
        full = [record for record in ledger.view().records if record.body["project"] == "a"]
        limited = [record for record in ledger.view(last=1).records if record.body["project"] == "a"]
        assert len(full) == 1 and not limited
        return {"project_a_full_read_matches": 1, "project_a_after_last_window": 0}


def independent_ledgers():
    with Ledger() as first, Ledger() as second:
        first.commit(Transition(updates={"a": 1}), expected_revision=0)
        second.commit(Transition(records=(Record("note", "other component", None),)), expected_revision=0)
        assert first.revision == second.revision == 1
        assert first.view().records == () and second.snapshot().state == {}
        return {"independent_revision_domains": True, "cross_ledger_atomic_commit": False}


def main():
    checks = (state_only, records_only, action_only, json_adapter,
              message_invalidates_state_based_work, disjoint_updates_conflict,
              nested_replacement, dedicated_schema, worker_connection,
              window_is_not_queue, project_filter_is_application_policy,
              independent_ledgers)
    results = {check.__name__: check() for check in checks}
    print(json.dumps({"checks": len(results), "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
