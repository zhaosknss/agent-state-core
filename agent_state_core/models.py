"""Domain-free values exchanged with the ledger."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

JSON: TypeAlias = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]


@dataclass(frozen=True)
class Intent:
    """An attempted action, retained in host history rather than agent context."""

    actor: str
    kind: str
    payload: JSON = None


@dataclass(frozen=True)
class Record:
    """Explicitly published information; None audience is public, () is host-only.

    A source is caller-authored JSON. It is visible with its record, so provide
    a safe reference rather than embedding confidential source material.
    """

    kind: str
    body: JSON
    audience: tuple[str, ...] | None
    source: JSON = None


@dataclass(frozen=True)
class Transition:
    """Application-selected result. Rejected results cannot update state."""

    updates: dict[str, JSON] = field(default_factory=dict)
    deletes: tuple[str, ...] = ()
    records: tuple[Record, ...] = ()
    accepted: bool = True
    reason: str = ""


@dataclass(frozen=True)
class Commit:
    revision: int
    created_at: str
    transition: Transition
    intent: Intent | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class Snapshot:
    revision: int
    state: dict[str, JSON]


@dataclass(frozen=True)
class VisibleRecord:
    id: str
    revision: int
    created_at: str
    kind: str
    body: JSON
    source: JSON


@dataclass(frozen=True)
class View:
    participant: str | None
    revision: int
    records: tuple[VisibleRecord, ...]

    def to_context(self) -> dict[str, JSON]:
        """Make a fresh JSON value for a model, tool, or application function."""
        import copy

        return copy.deepcopy({
            "participant": self.participant,
            "records": [
                {"id": r.id, "revision": r.revision, "created_at": r.created_at,
                 "kind": r.kind, "body": r.body, "source": r.source}
                for r in self.records
            ],
        })


@dataclass(frozen=True)
class RecordCursor:
    """Consumed position in one ledger and a fixed participant/kinds scope.

    An ordinal identifies a record within a revision. None means the complete
    revision has been consumed, including commits without matching records.
    """

    revision: int
    ordinal: int | None = None


@dataclass(frozen=True)
class ViewPage:
    participant: str | None
    revision: int
    records: tuple[VisibleRecord, ...]
    next_cursor: RecordCursor
    has_more: bool

    def to_context(self) -> dict[str, JSON]:
        """Supply only detached scoped records, like View.to_context()."""
        return View(self.participant, self.revision, self.records).to_context()


class StaleRevision(Exception):
    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected revision {expected}, found {actual}")


class RequestConflict(Exception):
    """A request ID was reused for a different base, intent, or transition."""


class SchemaError(Exception):
    """The file is not a supported agent-state-core database."""
