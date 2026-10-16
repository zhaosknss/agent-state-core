"""Compare the alpha-1 read algorithm and indexed reads on the same synthetic journal."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_state_core import Ledger, Record, Transition


def old_read(ledger):
    state, records = {}, []
    for commit in ledger.history():
        state.update(commit.transition.updates)
        for key in commit.transition.deletes:
            state.pop(key, None)
        for record in commit.transition.records:
            if record.audience is None or "alice" in record.audience:
                records.append((record.kind, record.body))
    return state, records


def indexed_read(ledger):
    return ledger.snapshot().state, [(r.kind, r.body) for r in ledger.view("alice").records]


def measure(fn, ledger, repeats):
    times = []
    for _ in range(repeats):
        started = perf_counter()
        fn(ledger)
        times.append((perf_counter() - started) * 1000)
    return median(times)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commits", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    if args.commits < 1 or args.repeats < 1:
        parser.error("commits and repeats must be positive")
    with Ledger() as ledger:
        for n in range(args.commits):
            ledger.commit(Transition(updates={"counter": n}, records=(
                Record("note", "x" * 2048, ("other",)),)), expected_revision=n)
        ledger.commit(Transition(records=(Record("note", "visible", ("alice",)),)),
                      expected_revision=args.commits)
        assert old_read(ledger) == indexed_read(ledger)
        old_read(ledger)
        indexed_read(ledger)
        print(json.dumps({
            "commits": args.commits + 1, "visible_records": 1, "repeats": args.repeats,
            "alpha1_median_ms": round(measure(old_read, ledger, args.repeats), 3),
            "indexed_median_ms": round(measure(indexed_read, ledger, args.repeats), 3),
            "outputs_equal": True, "python": sys.version.split()[0],
        }, sort_keys=True))


if __name__ == "__main__":
    main()
