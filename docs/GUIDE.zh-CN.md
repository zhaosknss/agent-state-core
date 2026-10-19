# 完整使用指南

[English](GUIDE.md) · [精确接口语义](DESIGN.md) · [运行与排错](OPERATIONS.md)

## 1. 创建与继续保存

```python
from agent_state_core import Intent, Ledger, Record, Transition

with Ledger("session.db") as ledger:
    if ledger.revision == 0:
        ledger.commit(Transition(updates={"budget": 100}, records=(
            Record("requirement", {"budget": 100}, None),
        )), expected_revision=0)
```

指定文件路径即可关闭后继续使用，父目录需要存在；不指定路径的 `Ledger()` 只保存在内存中。`with` 退出时关闭连接，也可以主动 `close()`。一个实例供一个线程使用，不同连接可以访问同一文件。

## 2. 明确信息发给谁

```python
with Ledger("session.db") as ledger:
    base = ledger.snapshot()
    ledger.commit(Transition(records=(
        Record("note", "check accessibility", ("reviewer",)),
        Record("claim", {"budget": 200}, ("planner",),
               {"speaker": "messenger", "verified": False}),
        Record("host-note", "internal reasoning", ()),
    )), expected_revision=base.revision)
```

`None` 表示公开，之后加入的参与者也能读到；元组明确接收者；`()` 只供宿主保留。内容种类、正文、来源都由应用定义。来源 JSON 会随这条记录一起给接收者，适合只放该范围可以看到的来源信息或引用。

这里 planner 收到预算 200 的说法，实际预算状态仍然是 100。库保留这一区别，怎么判断消息可信、是否相信它，由应用或参与者处理。

## 3. 给参与者组织输入

```python
with Ledger("session.db") as ledger:
    point = ledger.snapshot()
    context = ledger.view("planner", at_revision=point.revision,
                          kinds=("requirement", "claim"), last=10).to_context()
    print(context)
```

可以把 `context` 传给自己选择的模型、工具或普通函数。里面没有 reviewer 的私有记录、宿主记录，也不会自动混入全局状态。宿主则可以使用 `point.state` 判断动作是否成立。

`last=10` 取最后十条匹配记录，返回时仍按时间顺序排列，用于控制本次上下文，不是翻页游标。`kinds=()` 返回空记录。`after_revision=N` 排除版本 N 及以前的提交，`at_revision=M` 包含版本 M、排除之后的内容。所有筛选都会保留接收范围检查。不传这些参数时仍可读取完整可见记录。

要逐批读全匹配记录，使用独立的 [`view_page()` 与 `RecordCursor`](PAGING.zh-CN.md)：
支持从同一次提交内部续读，并在新增提交到来时固定本轮读取上界。
`last` 保持上下文窗口的原义；分页接口目前在 Unreleased 源码中提供。

## 4. 提交应用判定的结果

```python
with Ledger("session.db") as ledger:
    base = ledger.snapshot()
    candidate = {"cost": 80, "plan": "online workshop"}
    accepted = candidate["cost"] <= base.state["budget"]
    result = Transition(
        updates={"selected_plan": candidate} if accepted else {},
        accepted=accepted,
        reason="within budget" if accepted else "over budget",
        records=(Record("decision", {"accepted": accepted}, None),),
    )
    ledger.commit(result, expected_revision=base.revision,
                  intent=Intent("planner", "select-plan", candidate))
```

这个例子由宿主按预算规则判断。应用也可以选择其他规则、工具或人工决定。接受的结果可以更新或删除顶层状态字段；拒绝的结果可以留下记录，但不能同时改变状态。行动意图和宿主原因保留在完整历史中；想向参与者披露时，需要另外发布适当记录。

## 5. 条件变了怎样处理

如果从读取基础版本到提交期间有人做了新提交，会抛出 `StaleRevision`。应用取得新状态后，决定重算、丢弃、复核还是以新版本提交，不会自动重发模型请求。

如果只是没有收到上一次提交的响应，可以用同一请求 ID、原基础版本、原意图和原结果重试，直接取回原提交。同一 ID 对应的内容不同会抛出 `RequestConflict`。

节点重新执行时，也可先用 `get_commit(request_id)` 查是否已经完成。请求 ID 对应一份确定操作；新决定应使用新 ID。这种去重只覆盖本地提交，不会把远端工具调用变成“保证只执行一次”。

## 6. 历史回看与公开展示

```python
with Ledger("session.db") as ledger:
    print(ledger.snapshot(at_revision=1).state)
    print(ledger.view(at_revision=1).to_context())
    print(ledger.history())
```

不指定参与者的 `view()` 只取公开记录；`history()` 包含所有范围和宿主原因，属于有权限的宿主数据。版本 0 是空初始状态，不存在的未来版本会报错。每次提交都会推进一个全局版本，包括纯消息和失败行动；业务里的事件时间可以放进记录内容中。

跨对话接续可参考[理解交接与修订示例](CONTEXT_HANDOFF.zh-CN.md)：按项目和可见范围提取候选理解，保留来源，并处理后来的修订与撤回。这是应用示例，不是新的核心规则。

接下来可运行 [LangGraph 示例](LANGGRAPH.md)，查看实际编排中的暂停与恢复。数据库升级、备份和报错处理见 [运行说明](OPERATIONS.md)。这些接入方式和应用规则都可以按项目需要替换。
