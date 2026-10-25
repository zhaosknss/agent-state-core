"""SQLite-backed state history with explicit participant projections."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from .models import (
    Commit, Intent, Record, RecordCursor, RequestConflict, SchemaError, Snapshot,
    StaleRevision, Transition, View, ViewPage, VisibleRecord,
)


def _label(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _check_json(value, active=None):
    """Reject coercions such as integer keys, tuples, nonfinite floats, or cycles."""
    if type(value) in (str, int, bool, type(None)):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return
    if type(value) not in (dict, list):
        raise ValueError(f"Not a JSON value: {type(value).__name__}")
    active = set() if active is None else active
    marker = id(value)
    if marker in active:
        raise ValueError("JSON values cannot contain cycles")
    active.add(marker)
    try:
        if isinstance(value, dict):
            for key, item in value.items():
                if type(key) is not str:
                    raise ValueError("JSON object keys must be strings")
                _check_json(item, active)
        else:
            for item in value:
                _check_json(item, active)
    finally:
        active.remove(marker)


def _encode(value):
    _check_json(value)
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def _labels(values, field):
    if not isinstance(values, (tuple, list)):
        raise ValueError(f"{field} must be a tuple or list of strings")
    return [_label(value, field) for value in values]


def _payload(transition, intent):
    if not isinstance(transition, Transition):
        raise TypeError("transition must be a Transition")
    if type(transition.accepted) is not bool:
        raise ValueError("accepted must be a boolean")
    if not isinstance(transition.reason, str):
        raise ValueError("reason must be a string")
    if type(transition.updates) is not dict:
        raise ValueError("updates must be a JSON object")
    for key in transition.updates:
        _label(key, "state key")
    deletes = _labels(transition.deletes, "deletes")
    if len(set(deletes)) != len(deletes):
        raise ValueError("deletes contains duplicate keys")
    if set(deletes).intersection(transition.updates):
        raise ValueError("A key cannot be updated and deleted in the same transition")
    if not transition.accepted and (transition.updates or deletes):
        raise ValueError("Rejected transitions cannot change state")
    if not isinstance(transition.records, (tuple, list)):
        raise ValueError("records must be a tuple or list of Record values")
    records = []
    for record in transition.records:
        if not isinstance(record, Record):
            raise TypeError("records must contain Record values")
        audience = None if record.audience is None else sorted(set(
            _labels(record.audience, "audience")))
        records.append({"kind": _label(record.kind, "record kind"),
                        "body": record.body, "audience": audience, "source": record.source})
    action = None
    if intent is not None:
        if not isinstance(intent, Intent):
            raise TypeError("intent must be an Intent or None")
        action = {"actor": _label(intent.actor, "actor"),
                  "kind": _label(intent.kind, "intent kind"), "payload": intent.payload}
    return {"updates": transition.updates, "deletes": deletes, "records": records,
            "accepted": transition.accepted, "reason": transition.reason, "intent": action}


def _commit(row):
    data = json.loads(row["payload"])
    records = tuple(Record(item["kind"], item["body"],
                           None if item["audience"] is None else tuple(item["audience"]),
                           item["source"]) for item in data["records"])
    transition = Transition(data["updates"], tuple(data["deletes"]), records,
                            data["accepted"], data["reason"])
    intent = None if data["intent"] is None else Intent(**data["intent"])
    return Commit(row["revision"], row["created_at"], transition, intent, row["request_id"])


def _visible_records(rows):
    return tuple(VisibleRecord(
        f"{row['revision']}:{row['ordinal']}", row["revision"], row["created_at"],
        row["kind"], json.loads(row["body"]), json.loads(row["source"])) for row in rows)


class Ledger:
    """Host-owned journal. Give participants a View, not this object.

    One instance belongs to one thread. Independent instances/connections can
    write the same file; SQLite serializes commits and revisions reject stale work.
    """

    def __init__(self, path: str | Path = ":memory:"):
        if not str(path):
            raise ValueError("path cannot be empty")
        self._conn = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        try:
            self._initialize()
        except BaseException:
            self._conn.close()
            raise

    @contextmanager
    def _write(self):
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise

    def _initialize(self):
        with self._write():
            names = {r[0] for r in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if not names:
                self._conn.execute("CREATE TABLE asc_meta (schema_version INTEGER NOT NULL)")
                self._conn.execute("INSERT INTO asc_meta VALUES (2)")
                self._conn.execute(
                    "CREATE TABLE commits (revision INTEGER PRIMARY KEY CHECK(revision>0),"
                    "created_at TEXT NOT NULL, request_id TEXT UNIQUE,"
                    "request_hash TEXT NOT NULL, payload TEXT NOT NULL)")
                self._create_projections()
                return
            if "asc_meta" not in names:
                raise SchemaError("Not an agent-state-core database")
            versions = self._conn.execute("SELECT schema_version FROM asc_meta").fetchall()
            if len(versions) != 1:
                raise SchemaError("Invalid schema metadata")
            version = versions[0][0]
            if version == 1 and names == {"asc_meta", "commits"}:
                self._create_projections()
                for row in self._conn.execute("SELECT * FROM commits ORDER BY revision").fetchall():
                    self._index_commit(row)
                self._conn.execute("UPDATE asc_meta SET schema_version=2")
            elif version != 2 or names != {
                    "asc_meta", "commits", "state_versions", "record_projection", "record_audience"}:
                raise SchemaError("Unsupported or incomplete schema")

    def _create_projections(self):
        statements = (
            "CREATE TABLE state_versions (key TEXT NOT NULL, revision INTEGER NOT NULL "
            "REFERENCES commits(revision), value TEXT, deleted INTEGER NOT NULL, PRIMARY KEY(key,revision))",
            "CREATE TABLE record_projection (revision INTEGER NOT NULL REFERENCES commits(revision),"
            "ordinal INTEGER NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, source TEXT NOT NULL,"
            "is_public INTEGER NOT NULL, PRIMARY KEY(revision,ordinal))",
            "CREATE INDEX idx_record_public ON record_projection(is_public,revision,ordinal)",
            "CREATE TABLE record_audience (participant TEXT NOT NULL, revision INTEGER NOT NULL,"
            "ordinal INTEGER NOT NULL, PRIMARY KEY(participant,revision,ordinal),"
            "FOREIGN KEY(revision,ordinal) REFERENCES record_projection(revision,ordinal))",
        )
        for statement in statements:
            self._conn.execute(statement)

    def _index_commit(self, row):
        """Derived query tables share the commit's transaction, including during migration."""
        data = json.loads(row["payload"])
        revision = row["revision"]
        for key, value in data["updates"].items():
            self._conn.execute("INSERT INTO state_versions VALUES (?,?,?,0)",
                               (key, revision, _encode(value)))
        for key in data["deletes"]:
            self._conn.execute("INSERT INTO state_versions VALUES (?,?,NULL,1)", (key, revision))
        for ordinal, record in enumerate(data["records"]):
            self._conn.execute("INSERT INTO record_projection VALUES (?,?,?,?,?,?)",
                               (revision, ordinal, record["kind"], _encode(record["body"]),
                                _encode(record["source"]), int(record["audience"] is None)))
            for participant in record["audience"] or ():
                self._conn.execute("INSERT INTO record_audience VALUES (?,?,?)",
                                   (participant, revision, ordinal))

    @contextmanager
    def _read(self):
        self._conn.execute("BEGIN")
        try:
            yield
        finally:
            self._conn.rollback()

    def _read_point(self, at_revision):
        if at_revision is not None and (type(at_revision) is not int or at_revision < 0):
            raise ValueError("at_revision must be a nonnegative integer or None")
        current = self.revision
        if at_revision is not None and at_revision > current:
            raise ValueError(f"Revision {at_revision} does not exist")
        return current if at_revision is None else at_revision

    @property
    def revision(self) -> int:
        return self._conn.execute("SELECT COALESCE(MAX(revision),0) FROM commits").fetchone()[0]

    def commit(self, transition: Transition, *, expected_revision: int,
               intent: Intent | None = None, request_id: str | None = None) -> Commit:
        """Atomically record a result; no model or external tool is invoked.

        Retrying the same ID/base/intent/result returns the original commit,
        even after later commits. Changed content with that ID is an error.
        """
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision must be a nonnegative integer")
        if request_id is not None:
            _label(request_id, "request_id")
        payload = _encode(_payload(transition, intent))
        fingerprint = "" if request_id is None else hashlib.sha256(
            _encode({"base": expected_revision, "payload": json.loads(payload)}).encode("utf-8")
        ).hexdigest()
        with self._write():
            if request_id is not None:
                previous = self._conn.execute(
                    "SELECT * FROM commits WHERE request_id=?", (request_id,)).fetchone()
                if previous is not None:
                    if previous["request_hash"] != fingerprint:
                        raise RequestConflict(f"Different content for request {request_id!r}")
                    return _commit(previous)
            actual = self.revision
            if actual != expected_revision:
                raise StaleRevision(expected_revision, actual)
            revision = actual + 1
            created_at = datetime.now(timezone.utc).isoformat()
            self._conn.execute("INSERT INTO commits VALUES (?,?,?,?,?)",
                               (revision, created_at, request_id, fingerprint, payload))
            row = self._conn.execute("SELECT * FROM commits WHERE revision=?", (revision,)).fetchone()
            self._index_commit(row)
            return _commit(row)

    def history(self, *, at_revision: int | None = None) -> tuple[Commit, ...]:
        """Privileged host history, including private records and action results."""
        with self._read():
            point = self._read_point(at_revision)
            rows = self._conn.execute(
                "SELECT * FROM commits WHERE revision<=? ORDER BY revision", (point,)).fetchall()
        return tuple(_commit(row) for row in rows)

    def get_commit(self, request_id: str) -> Commit | None:
        """Host lookup for a committed request, useful before replaying a graph node."""
        _label(request_id, "request_id")
        row = self._conn.execute("SELECT * FROM commits WHERE request_id=?", (request_id,)).fetchone()
        return None if row is None else _commit(row)

    def snapshot(self, *, at_revision: int | None = None) -> Snapshot:
        """Read global application state at one revision, without decoding action history."""
        with self._read():
            point = self._read_point(at_revision)
            rows = self._conn.execute(
                "SELECT s.key,s.value FROM state_versions s JOIN "
                "(SELECT key,MAX(revision) AS revision FROM state_versions WHERE revision<=? GROUP BY key) "
                "latest ON s.key=latest.key AND s.revision=latest.revision WHERE s.deleted=0", (point,)
            ).fetchall()
        return Snapshot(point, {row["key"]: json.loads(row["value"]) for row in rows})

    def view(self, participant: str | None = None, *,
             at_revision: int | None = None, after_revision: int = 0,
             kinds: tuple[str, ...] | None = None, last: int | None = None) -> View:
        """Public records plus explicitly addressed records; no global-state merge.

        None selects the public-only view. Source JSON is supplied explicitly by
        the host and is not expanded by following references to hidden commits.
        """
        if participant is not None:
            _label(participant, "participant")
        if type(after_revision) is not int or after_revision < 0:
            raise ValueError("after_revision must be a nonnegative integer")
        if last is not None and (type(last) is not int or last < 1):
            raise ValueError("last must be a positive integer or None")
        selected_kinds = None if kinds is None else _labels(kinds, "kinds")
        with self._read():
            point = self._read_point(at_revision)
            if after_revision > point:
                raise ValueError("after_revision exceeds the selected read point")
            if selected_kinds == []:
                return View(participant, point, ())
            rows = self._record_rows(participant, point, selected_kinds,
                                     (after_revision + 1, 0), newest=last is not None, limit=last)
        if last is not None:
            rows.reverse()
        return View(participant, point, _visible_records(rows))

    def view_page(self, participant: str | None = None, *,
                  after: RecordCursor | None = None, at_revision: int | None = None,
                  kinds: tuple[str, ...] | None = None, limit: int = 100) -> ViewPage:
        """Read the next oldest matching records, with a resumable record position.

        Keep ledger/participant/kinds fixed for a consumer. Pin at_revision to
        the first page's revision to drain a finite read point. Save next_cursor
        only after processing succeeds; it is not a durable acknowledgement.
        """
        if participant is not None:
            _label(participant, "participant")
        if after is not None and not isinstance(after, RecordCursor):
            raise TypeError("after must be a RecordCursor or None")
        cursor = RecordCursor(0) if after is None else after
        if type(cursor.revision) is not int or cursor.revision < 0:
            raise ValueError("cursor revision must be a nonnegative integer")
        if cursor.ordinal is not None and (
                type(cursor.ordinal) is not int or cursor.ordinal < 0 or cursor.revision == 0):
            raise ValueError("cursor ordinal requires a positive revision and nonnegative integer")
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        selected_kinds = None if kinds is None else _labels(kinds, "kinds")
        start = ((cursor.revision + 1, 0) if cursor.ordinal is None
                 else (cursor.revision, cursor.ordinal + 1))
        with self._read():
            point = self._read_point(at_revision)
            if cursor.revision > point:
                raise ValueError("cursor exceeds the selected read point")
            rows = [] if selected_kinds == [] else self._record_rows(
                participant, point, selected_kinds, start, limit=limit + 1)
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = (RecordCursor(rows[-1]["revision"], rows[-1]["ordinal"])
                       if has_more else RecordCursor(point))
        return ViewPage(participant, point, _visible_records(rows), next_cursor, has_more)

    def _record_rows(self, participant, point, kinds, start, *, newest=False, limit=None):
        """Shared audience/kind projection; callers hold the pinned read transaction."""
        columns = "r.revision,r.ordinal,c.created_at,r.kind,r.body,r.source"
        lower = "(r.revision,r.ordinal)>=(?,?) AND r.revision<=?"
        query = (f"SELECT {columns} FROM record_projection r JOIN commits c USING(revision) "
                 f"WHERE r.is_public=1 AND {lower}")
        params = [*start, point]
        if participant is not None:
            query += (" UNION ALL SELECT a.revision,a.ordinal,c.created_at,r.kind,r.body,r.source "
                      "FROM record_audience a "
                      "JOIN record_projection r ON r.revision=a.revision AND r.ordinal=a.ordinal "
                      "JOIN commits c ON c.revision=r.revision "
                      "WHERE a.participant=? AND (a.revision,a.ordinal)>=(?,?) AND a.revision<=?")
            params.extend([participant, *start, point])
        query = f"SELECT * FROM ({query})"
        if kinds is not None:
            query += " WHERE kind IN (" + ",".join("?" for _ in kinds) + ")"
            params.extend(kinds)
        direction = "DESC" if newest else "ASC"
        query += f" ORDER BY revision {direction},ordinal {direction}"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return self._conn.execute(query, params).fetchall()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
