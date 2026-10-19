"""Drain a fixed scoped history in pages, then resume after a saved checkpoint.

Run from a checkout: python -m examples.paged_records
Only the standard library, temporary storage, and fictional data are used.
"""
from dataclasses import asdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_state_core import Ledger, Record, RecordCursor, Transition


def run():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "records.db"
        with Ledger(path) as ledger:
            ledger.commit(Transition(records=tuple(
                Record("note", {"item": n}, None, {"document": "example-guide"})
                for n in range(5)) + (
                    Record("note", "PRIVATE_REVIEW_NOTE", ("reviewer",)),
                    Record("note", "HOST_ONLY_NOTE", ()),)), expected_revision=0)
            page = ledger.view_page("worker", kinds=("note",), limit=2)
            point = page.revision

            # A new commit arrives while the earlier read point is being drained.
            with Ledger(path) as writer:
                writer.commit(Transition(records=(
                    Record("note", {"item": 5}, ("worker",)),)), expected_revision=1)

            seen = []
            while True:
                # Application processing must succeed before checkpointing.
                seen.extend(record.body["item"] for record in page.records)
                checkpoint = json.dumps(asdict(page.next_cursor))
                assert "PRIVATE_REVIEW_NOTE" not in str(page.to_context())
                assert "HOST_ONLY_NOTE" not in str(page.to_context())
                if not page.has_more:
                    break
                page = ledger.view_page("worker", after=page.next_cursor,
                                        at_revision=point, kinds=("note",), limit=2)
            assert seen == [0, 1, 2, 3, 4]

        with Ledger(path) as reopened:
            cursor = RecordCursor(**json.loads(checkpoint))
            later = reopened.view_page("worker", after=cursor, kinds=("note",), limit=2)
            assert [record.body["item"] for record in later.records] == [5]
            assert not later.has_more
        result = {"pinned_revision": point, "items_in_pages": seen,
                  "resumed_items": [record.body["item"] for record in later.records]}
        print("Paged records with a resumable checkpoint:")
        print(json.dumps(result, indent=2))
        return result


if __name__ == "__main__":
    run()
