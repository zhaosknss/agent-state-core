"""Compose a scoped View with real LangChain storage and Runnable APIs.

Run: python -m examples.langchain_retrieval
Optional dependency: langchain-core==1.6.11. No model, embeddings, or network.
The keyword lookup and cache lifetime below are application policy, not core API.
"""
import copy
import json

from agent_state_core import Ledger, Record, Transition


def build_retriever(view):
    """Build a fresh read-only cache for one participant and read point.

    The host supplies a View, not the privileged Ledger or history. Rebuild to
    incorporate later changes. Historical records are not semantic current truth.
    """
    try:
        from langchain_core.runnables import RunnableLambda
        from langchain_core.stores import InMemoryStore
    except ImportError as exc:
        raise RuntimeError('Install: python -m pip install "langchain-core==1.6.11"') from exc

    context = view.to_context()
    cache = InMemoryStore()
    cache.mset([(record["id"], record) for record in context["records"]])

    def lookup(query):
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a nonempty string")
        query = query.casefold()
        records = cache.mget(list(cache.yield_keys()))
        return copy.deepcopy([
            record for record in records
            if record is not None
            and query in json.dumps(record["body"], ensure_ascii=False).casefold()
        ])

    def envelope(matches):
        return {"participant": view.participant, "through_revision": view.revision,
                "matches": matches}

    return RunnableLambda(lookup) | RunnableLambda(envelope)


def run():
    with Ledger() as ledger:
        ledger.commit(Transition(updates={"secret": "HOST_ONLY"}, records=(
            Record("note", {"text": "runbook: deploy during the approved window"},
                   None, {"document": "release-guide"}),
            Record("note", {"text": "runbook: check staging before deployment"},
                   ("operator",), {"document": "staging-guide"}),
            Record("note", {"text": "runbook: PRIVATE_REVIEW_NOTE"}, ("reviewer",)),
        )), expected_revision=0)
        earlier = build_retriever(ledger.view("operator", kinds=("note",)))
        result = earlier.invoke("runbook")
        assert [record["id"] for record in result["matches"]] == ["1:0", "1:1"]
        assert "HOST_ONLY" not in json.dumps(result)
        assert "PRIVATE_REVIEW_NOTE" not in json.dumps(result)

        ledger.commit(Transition(records=(
            Record("note", {"text": "runbook: confirm rollback plan"}, None),
        )), expected_revision=1)
        assert earlier.invoke("rollback")["matches"] == []
        current = build_retriever(ledger.view("operator", kinds=("note",)))
        latest = current.invoke("rollback")
        assert latest["through_revision"] == 2
        assert [record["id"] for record in latest["matches"]] == ["2:0"]
        assert ledger.snapshot().state == {"secret": "HOST_ONLY"}
        print("LangChain retrieval from scoped records:")
        print(json.dumps(latest, indent=2))
        return latest


if __name__ == "__main__":
    run()
