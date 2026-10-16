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
    Commit, Intent, Record, RequestConflict, SchemaError, Snapshot,
    StaleRevision, Transition, View, VisibleRecord,
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
                self._conn.execute("INSERT INTO asc_meta VALUES (1)")
                self._conn.execute(
                    "CREATE TABLE commits (revision INTEGER PRIMARY KEY CHECK(revision>0),"
                    "created_at TEXT NOT NULL, request_id TEXT UNIQUE,"
                    "request_hash TEXT NOT NULL, payload TEXT NOT NULL)")
            elif names != {"asc_meta", "commits"}:
                raise SchemaError("Not an agent-state-core database")
            else:
                versions = self._conn.execute("SELECT schema_version FROM asc_meta").fetchall()
                if len(versions) != 1 or versions[0][0] != 1:
                    raise SchemaError("Unsupported schema version")

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
        fingerprint = hashlib.sha256(
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
            return _commit(row)

    def history(self, *, at_revision: int | None = None) -> tuple[Commit, ...]:
        """Privileged host history, including private records and action results."""
        if at_revision is not None and (type(at_revision) is not int or at_revision < 0):
            raise ValueError("at_revision must be a nonnegative integer or None")
        # One SELECT fixes the read point even if another connection commits.
        rows = self._conn.execute("SELECT * FROM commits ORDER BY revision").fetchall()
        actual = rows[-1]["revision"] if rows else 0
        if at_revision is not None and at_revision > actual:
            raise ValueError(f"Revision {at_revision} does not exist")
        return tuple(_commit(row) for row in rows
                     if at_revision is None or row["revision"] <= at_revision)

    def snapshot(self, *, at_revision: int | None = None) -> Snapshot:
        """Rebuild global application state, never a participant's knowledge."""
        commits = self.history(at_revision=at_revision)
        state = {}
        for commit in commits:
            state.update(commit.transition.updates)
            for key in commit.transition.deletes:
                state.pop(key, None)
        return Snapshot(commits[-1].revision if commits else 0, state)

    def view(self, participant: str | None = None, *,
             at_revision: int | None = None) -> View:
        """Public records plus explicitly addressed records; no global-state merge.

        None selects the public-only view. Source JSON is supplied explicitly by
        the host and is not expanded by following references to hidden commits.
        """
        if participant is not None:
            _label(participant, "participant")
        commits = self.history(at_revision=at_revision)
        records = []
        for commit in commits:
            for index, record in enumerate(commit.transition.records):
                if record.audience is None or (
                        participant is not None and participant in record.audience):
                    records.append(VisibleRecord(
                        f"{commit.revision}:{index}", commit.revision, commit.created_at,
                        record.kind, record.body, record.source))
        return View(participant, commits[-1].revision if commits else 0, tuple(records))

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
