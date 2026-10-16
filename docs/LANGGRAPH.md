# LangGraph integration / 接入

This is a runnable integration with **LangGraph 1.2.15**, not an imitation of its
API. Its participant function is deterministic so the example needs no model
key and does not measure model reasoning.

## Install and run

From the checkout, preferably in a virtual environment:

```bash
python -m venv .venv
# Activate the environment using your shell's normal command, then:
python -m pip install ".[langgraph]"
python -m examples.langgraph_collaboration
python -B tools/verify.py --langgraph
```

To reproduce the exact optional dependency set, install
`requirements/langgraph-test.txt`. Core-only users do not need any of it.
The dependency versions and licenses are recorded in [upstream review](UPSTREAM.md).

Expected material output:

```text
LangGraph paused for human review: {'cost': 100, 'plan': 'in-person event'}
Resumed and committed: {'cost': 50, 'plan': 'online event'}
```

## Ownership of data and progress

| Owner | Responsibility |
|---|---|
| LangGraph | Node order, graph state, interrupt/resume, graph checkpoints |
| agent-state-core | Domain state, scoped records, revision checks, committed request results |
| Application | Rules, participants, model/tool calls, request IDs, review decisions |

The example uses real `StateGraph`, `InMemorySaver`, `interrupt`, and `Command`.
It does not replace LangGraph's checkpointer. `InMemorySaver` is suitable here
for testing in-process pause/resume; select a persistent upstream checkpointer
for graph recovery across process restarts. A file-backed ledger alone does
not make an in-memory graph durable.

## What the example verifies

1. A planner receives public requirements, not a reviewer-only requirement with
   a different budget and private marker, even though the record kind is the same.
2. The real graph pauses at `interrupt`; no ledger changes precede that pause.
3. `Command(resume={"budget": 50})` supplies human input to the restarted node.
4. The application records the new requirement and computes the selected plan
   from the updated scoped input.
5. Host request receipts allow a repeated logical review node to return the
   original selected result without committing it again.

The full example is [examples/langgraph_collaboration.py](../examples/langgraph_collaboration.py).
The integration tests also check invalid human input and that the graph ends
without a pending node. The runner blocks network connection/DNS/send attempts.
An upstream HTTP dependency may create and bind a loopback socket to test IPv6
support during import; this is tracked separately from network connection attempts.

## Adapting it

`build_graph(ledger, checkpointer=...)` accepts the host ledger and an optional
LangGraph checkpointer. Replace `propose(context)` with a model or tool adapter
that accepts the same scoped JSON. Keep privileged snapshots with host code,
and use one stable, unique request ID per logical review operation.

LangGraph re-executes an interrupted node on resume. Place model calls and other
effects accordingly; the example puts its interrupt before ledger writes and
checks for a completed host result before repeating them. Two simultaneous
executions can still race, and external calls are not part of the SQLite
transaction. `get_commit` is a lookup, not a distributed lock or exactly-once tool
executor. Further integration designs need their own tests.

## 中文说明

这个例子真正安装并调用 LangGraph，由它负责节点执行和中断恢复。本库保存业务状态、按参与者筛选记录、检查版本以及查询已经提交的结果。应用继续决定规则和模型调用方式。

先按预算 100 提方案，在人工复核处暂停；输入预算 50 后，用新的可见资料重新组织方案并提交。即使复核者的私有记录也叫 requirement，planner 仍读不到它。

示例的图检查点只保存在内存，适合演示和测试；进程退出后恢复图执行需要持久化 checkpointer。文件形式的 Ledger 与图检查点各自保存自己的数据，不构成跨两个系统的原子事务。真实模型调用可以接在 `propose(context)` 位置，但模型质量及远端费用没有在这些确定性测试中验证。
