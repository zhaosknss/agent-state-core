# 带来源和适用范围的上下文交接

[English](CONTEXT_HANDOFF.md)

这个示例把有用的理解交给另一个对话、工具或文档整理流程：保留来源和范围，修订时留下旧记录，过期时明确撤回。接入方自行选择参与者与执行方式。

## 运行

在当前仓库源码目录中，使用 Python 3.11 以上版本：

```powershell
python -m examples.context_handoff
python -B tools/verify.py
```

消息为虚构，参与者是普通函数，不需要 API key、模型请求或可选依赖。代码在 `examples/context_handoff.py`，没有安装进核心 wheel。这是 Unreleased 源码更新，已发布的 alpha 2 源码包和 wheel 不包含新示例。

## 具体展示什么

先记录“复盘期间暂停修改这份草稿”的候选理解；收到后来明确的要求后，改为“从旧稿继续，保留有效开头”。另一条记录说明“采用本次交付”不等于“以后作为理想模板”。临时要求结束后，宿主可以撤回对应记录。

`build_handoff()` 只取一个项目、一个读取区间内每个 key 最后**可见**的记录，按这些最后变化实际发生的顺序返回。交接包省去被替代的记录与不用的元数据，完整历史仍在底层。只给审查者的新记录，不会替换写作者仍能看见的旧记录。

项目标签、状态和“同 key 取最后可见记录”都是示例的应用约定，核心没有增加强制协议，也不会判断哪份理解正确。项目筛选与受众筛选配合使用，不代替身份认证；宿主需保证此类记录符合示例约定的数据格式。

## 在自己的应用里使用

以下代码可以从源码目录运行：

```python
from agent_state_core import Ledger, Transition
from examples.context_handoff import build_handoff, context_note

with Ledger() as ledger:
    note = context_note(
        "docs", "revision-scope", "保留已经认可的开头。",
        "只适用于本次文档修订。", {"message": "sample-1"},
    )
    ledger.commit(Transition(records=(note,)), expected_revision=0)
    packet = build_handoff(ledger, "new-session", "docs")
    assert packet["notes"][0]["status"] == "candidate"
    assert ledger.snapshot().state == {}
```

可以按 MIT 许可把辅助函数放进自己的应用，并调整字段和组织方式。理解及其来源由宿主提供；如果来自模型，应在需要时与实际原文核对，再选择向谁发布。示例没有自动提取理解。可见的来源 JSON 本身也需适合展示，底层不会替你解引用或隐去其中的原文。

## 修订、撤回和增量

- 同项目、同 key 的新记录，在示例的交接包中替代之前可见的候选。旧记录仍可通过 `view()` 与 `at_revision` 回看，各人的视图可以不同。
- `withdrawn=True` 发布撤回。接收增量的一方应删除缓存里的对应 key，避免继续沿用旧要求。
- 没有匹配记录的增量不会清空其他缓存。版本号仍可能因其他内容更新而前进，因为底层使用全局版本。

先用完整读取初始化缓存，再逐份应用增量：

```python
def apply_packet(cache, packet):
    cache.update({item["key"]: item for item in packet["notes"]})
    for item in packet["withdrawn"]:
        cache.pop(item["key"], None)
```

成功接收后，应用可把 `through_revision` 存为下次的 `after_revision`。它只是读取边界，不证明 AI 已理解，也不代表用户已认可。示例不会自动保存读取位置，或把候选写成宿主事实。

每份缓存和读取位置对应同一个账本、项目与参与者；切换其中任何一个时，从完整读取重新建立缓存。

## 适用范围和边界

项目接续、文档整理和多参与者共享理解可以从这份示例起步。记录可来自人、模型或普通函数；选择相关内容、处理语义冲突、核对来源及安排讨论，仍由上层应用负责。

示例和测试检查受众、历史、顺序及撤回处理，不证明减少了反馈、改善模型推理或节省 token，也没有自动读取聊天或完整接入文档整理插件。交接包仍可能过长，应按实际任务选择内容。
