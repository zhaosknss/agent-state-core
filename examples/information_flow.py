"""Deterministic illustration of state, observations, and a mistaken claim."""
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_state_core import Intent, Ledger, Record, Transition


def run(path):
    with Ledger(path) as ledger:
        ledger.commit(Transition(
            updates={"key_holder": "alice"},
            records=(Record("observation", {"key_holder": "alice"}, None,
                            {"method": "direct", "time": 0}),)), expected_revision=0)
        ledger.commit(Transition(
            updates={"key_holder": "bob"},
            records=(Record("observation", {"key_holder": "bob"}, ("alice", "bob"),
                            {"method": "direct", "time": 1}),)),
            expected_revision=1, intent=Intent("alice", "transfer", {"to": "bob"}))
        ledger.commit(Transition(records=(
            Record("claim", {"key_holder": "alice"}, ("carol",),
                   {"speaker": "messenger", "verified": False}),)), expected_revision=2)

        # Rules belong to the application; the ledger imposes no action vocabulary.
        attempt = Intent("carol", "transfer", {"to": "dana"})
        base = ledger.snapshot()
        if base.state["key_holder"] != attempt.actor:
            result = Transition(accepted=False, reason="actor does not hold key", records=(
                Record("action_result", {"accepted": False}, (attempt.actor,)),))
        else:
            result = Transition(updates={"key_holder": attempt.payload["to"]})
        ledger.commit(result, expected_revision=base.revision, intent=attempt)
        assert ledger.snapshot().state["key_holder"] == "bob"
        assert ledger.view("carol").records[-2].kind == "claim"
        assert all(r.body != {"key_holder": "bob"} for r in ledger.view("carol").records)
        assert ledger.snapshot(at_revision=1).state["key_holder"] == "alice"
        print("Global state:", ledger.snapshot().state)
        print("Bob observations:", [r.body for r in ledger.view("bob").records])
        print("Carol records:", [(r.kind, r.body) for r in ledger.view("carol").records])
        print("Public records:", [r.body for r in ledger.view().records])

    with Ledger(path) as reopened:
        assert reopened.revision == 4
        assert reopened.snapshot().state["key_holder"] == "bob"
        print("Reopened revision:", reopened.revision)


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        run(Path(directory) / "example.db")
