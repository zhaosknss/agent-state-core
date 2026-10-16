"""Ordinary functions stand in for model calls; no mandatory debate recipe."""
from agent_state_core import Intent, Ledger, Record, StaleRevision, Transition


def propose(context):
    # A real adapter can pass this same scoped JSON to a model.
    budget = [r["body"]["budget"] for r in context["records"]
              if r["kind"] == "requirement"][-1]
    return {"cost": budget, "plan": "host an event" if budget >= 100 else "online event"}


def run():
    with Ledger() as ledger:
        ledger.commit(Transition(updates={"budget": 100}, records=(
            Record("requirement", {"budget": 100}, None),
            Record("note", "check accessibility", ("reviewer",)),)), expected_revision=0)
        base = ledger.snapshot()
        old_plan = propose(ledger.view("planner").to_context())
        assert "check accessibility" not in str(ledger.view("planner").to_context())

        # Human input changes a real constraint, rather than only appending prose.
        ledger.commit(Transition(updates={"budget": 50}, records=(
            Record("requirement", {"budget": 50}, None, {"speaker": "human"}),)),
            expected_revision=base.revision)
        try:
            ledger.commit(Transition(updates={"selected_plan": old_plan}),
                          expected_revision=base.revision)
        except StaleRevision:
            print("Old proposal rejected after the budget changed.")
        else:
            raise AssertionError("A stale proposal was committed")

        fresh = ledger.snapshot()
        new_plan = propose(ledger.view("planner", at_revision=fresh.revision).to_context())
        receipt = ledger.commit(Transition(updates={"selected_plan": new_plan}, records=(
            Record("decision", new_plan, None),)), expected_revision=fresh.revision,
            intent=Intent("human", "select_plan", new_plan), request_id="select-plan-1")
        assert ledger.snapshot().state["selected_plan"]["cost"] == 50
        print("Selected plan:", new_plan)
        print("Committed revision:", receipt.revision)


if __name__ == "__main__":
    run()
