# Read scoped records in pages

[中文](PAGING.zh-CN.md) · [Usage](GUIDE.md) · [Runnable example](../examples/paged_records.py)

`view_page()` reads the next **oldest** matching records, up to `limit` (default
100). A `RecordCursor` includes the position within a commit, so one commit can
span several pages. Audience and kind filtering happen before the page limit.
This is an Unreleased API in the current checkout; existing alpha-2 release
artifacts do not contain it. Install from the checkout with `python -m pip install .`.

```python
from agent_state_core import Ledger, Record, Transition

with Ledger() as ledger:
    ledger.commit(Transition(records=tuple(
        Record("note", n, None) for n in range(5))), expected_revision=0)
    page = ledger.view_page("worker", kinds=("note",), limit=2)
    point = page.revision
    seen = []
    while True:
        seen.extend(record.body for record in page.records)
        cursor = page.next_cursor  # Save only after processing succeeds.
        if not page.has_more:
            break
        page = ledger.view_page("worker", after=cursor, at_revision=point,
                                kinds=("note",), limit=2)
    assert seen == [0, 1, 2, 3, 4]
```

## Read point, continuation, and checkpoint

`ViewPage` contains `participant`, `revision`, `records`, `next_cursor`, and
`has_more`. Its `to_context()` supplies detached scoped records in the same
format as a View, without host state, intent, or result reason.

- `revision` is the page's inclusive upper read point. Pin subsequent pages to
  the first page's revision to drain a finite history while writers continue.
- `has_more` means more matching records exist **through that read point**.
  A final full page has `has_more=False`; no extra empty page is needed.
- While more records remain, `next_cursor` identifies the last returned record
  by revision and ordinal. At exhaustion it marks the whole read revision
  consumed, including hidden, filtered, or records-free commits.
- To poll later commits, reuse the final cursor and omit `at_revision`. Reusing
  an unchanged cursor/read point returns the same records for the same scope.

Save cursor data in application storage using `dataclasses.asdict(cursor)` and
JSON; restore with `RecordCursor(**saved_dict)`. Persist the read point as well
when restarting midway through a pinned drain. `RecordCursor(N)` means all
records through revision N have been consumed; `RecordCursor(N, ordinal)` means
consumed through that particular record. Omitting `after` starts from revision 0.

Use a separate checkpoint for each **ledger, participant, and kinds selection**.
The cursor is a position, not a database identity or scope-bound credential;
switching scope and reusing it can skip earlier records in the new selection.
Start over when broadening or changing a scope. Page size may change freely.
Choose any project/body filtering in application code and examine every page,
including pages with no application-level matches, before advancing.

## What this guarantees

For an unchanged ledger history and fixed selection, following the cursors
enumerates matching records in commit/ordinal order without omissions or
duplicates. Each read pins its database transaction, uses the existing indexed
record projection, fetches at most `limit + 1` rows, and decodes only returned
bodies/sources. The extra row determines `has_more`. The limit bounds record
count, not bytes, query execution time, or total application memory.

This is not a durable queue or exactly-once external processing. Cursor storage
and effects are owned by the application. A crash after processing but before
checkpointing can cause replay; make effects idempotent where needed. A page
can split one commit's records; inspect privileged history if an application
requires full commit-level processing.

`view(last=N)` still means the **newest context window** and retains its existing
behavior. Its `View.revision` is not a cursor for consuming that window. The new
API adds no database schema, dependency, worker, or automatic synchronization.

Run `python -m examples.paged_records` for a fixed read point, a concurrent writer,
and JSON checkpoint recovery after reopening the ledger.
