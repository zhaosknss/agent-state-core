"""Actual optional LangGraph orchestration; participant handlers remain plain functions."""
from agent_state_core import Intent, Ledger, Record, Transition


def propose(context):
    budget = [record["body"]["budget"] for record in context["records"]
              if record["kind"] == "requirement"][-1]
    return {"cost": budget, "plan": "in-person event" if budget >= 100 else "online event"}


def build_graph(ledger, checkpointer=None):
    try:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import interrupt
        from typing_extensions import TypedDict
    except ImportError as exc:
        raise RuntimeError('Install the optional example with: python -m pip install ".[langgraph]"') from exc

    class FlowState(TypedDict, total=False):
        request: str
        proposal: dict
        selected: dict

    def plan(state):
        base = ledger.snapshot()
        scoped = ledger.view("planner", at_revision=base.revision, kinds=("requirement",), last=10)
        return {"proposal": propose(scoped.to_context())}

    def human_review(state):
        key = state["request"]
        completed = ledger.get_commit(key + ":select")
        if completed is not None:
            return {"selected": completed.transition.updates["selected_plan"]}

        # LangGraph restarts this node on resume. No side effects precede interrupt.
        decision = interrupt({"proposal": state["proposal"], "question": "Choose a budget"})
        budget = decision.get("budget") if isinstance(decision, dict) else None
        if type(budget) is not int or budget < 1:
            raise ValueError("budget must be a positive integer")
        if ledger.get_commit(key + ":budget") is None:
            base = ledger.snapshot()
            ledger.commit(Transition(updates={"budget": budget}, records=(
                Record("requirement", {"budget": budget}, None, {"speaker": "human"}),)),
                expected_revision=base.revision, request_id=key + ":budget")
        base = ledger.snapshot()
        scoped = ledger.view("planner", at_revision=base.revision, kinds=("requirement",), last=10)
        selected = propose(scoped.to_context())
        ledger.commit(Transition(updates={"selected_plan": selected}, records=(
            Record("decision", selected, None),)), expected_revision=base.revision,
            intent=Intent("human", "select_plan", selected), request_id=key + ":select")
        return {"selected": selected}

    graph = StateGraph(FlowState)
    graph.add_node("plan", plan)
    graph.add_node("human_review", human_review)
    graph.add_edge(START, "plan")
    graph.add_edge("plan", "human_review")
    graph.add_edge("human_review", END)
    return graph.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


def run():
    from langgraph.types import Command

    with Ledger() as ledger:
        ledger.commit(Transition(updates={"budget": 100}, records=(
            Record("requirement", {"budget": 100}, None),
            Record("requirement", {"budget": 999, "private": "PRIVATE_REVIEWER_NOTE"},
                   ("reviewer",)),)), expected_revision=0)
        graph = build_graph(ledger)
        config = {"configurable": {"thread_id": "example-1"}}
        paused = graph.invoke({"request": "example-1"}, config)
        assert paused["__interrupt__"]
        assert ledger.revision == 1
        assert paused["proposal"]["cost"] == 100
        assert "PRIVATE_REVIEWER_NOTE" not in str(paused)
        print("LangGraph paused for human review:", paused["proposal"])
        resumed = graph.invoke(Command(resume={"budget": 50}), config)
        assert resumed["selected"]["cost"] == 50
        assert ledger.snapshot().state["selected_plan"]["cost"] == 50
        print("Resumed and committed:", resumed["selected"])
        return resumed["selected"]


if __name__ == "__main__":
    run()
