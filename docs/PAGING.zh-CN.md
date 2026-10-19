# 分页读取可见记录

[English](PAGING.md) · [使用指南](GUIDE.zh-CN.md) · [可运行示例](../examples/paged_records.py)

`view_page()` 按从旧到新的顺序读取下一批匹配记录，每页不超过 `limit` 条，默认 100。
`RecordCursor` 包含同一次提交内的记录位置，因此一个提交可以跨多页读取。
接收范围和种类筛选先于条数限制。这是当前源码中的 Unreleased 接口，现有 alpha 2
发布附件不包含它；可在源码目录用 `python -m pip install .` 安装。

```python
from agent_state_core import Ledger, Record, Transition

with Ledger() as ledger:
    ledger.commit(Transition(records=tuple(
        Record("note", n, None) for n in range(5))), expected_revision=0)
    page = ledger.view_page("worker", kinds=("note",), limit=2)
    point = page.revision
    seen = []
    while True:
        seen.extend(record.body for record in page.records)
        cursor = page.next_cursor  # 处理成功后，再保存这个位置。
        if not page.has_more:
            break
        page = ledger.view_page("worker", after=cursor, at_revision=point,
                                kinds=("note",), limit=2)
    assert seen == [0, 1, 2, 3, 4]
```

## 读取上界、续读位置和保存

`ViewPage` 提供 `participant`、`revision`、`records`、`next_cursor`、`has_more`。
其 `to_context()` 与 View 一样，只提供脱离存储的可见记录，不混入宿主状态、意图或结果理由。

- `revision` 是这一页的读取上界。后续页固定为第一页的版本，可以在写入继续发生时，
  先完整读完一个有限范围。
- `has_more` 表示这个上界以内还有匹配记录。最后一页即使正好填满，也会返回 False，
  不需要额外读一个空页才能确定结束。
- 还有后续记录时，`next_cursor` 指向最后返回记录的版本及序号；读完时标记整个读取
  版本已消费，包括隐藏、被筛掉或没有记录的提交。
- 接收后来提交的内容时，沿用最终游标，不传 `at_revision`。在范围不变时，沿用旧游标
  和同一读取上界可以重新读取同一页。

应用可以用 `dataclasses.asdict(cursor)` 转成 JSON 保存，再用 `RecordCursor(**saved_dict)`
恢复。如果在一轮读取中途退出，还应保存上界版本，重启后继续固定该版本。
`RecordCursor(N)` 表示已读完整个版本 N；`RecordCursor(N, ordinal)` 表示读到其中
某条记录。省略 `after` 就从版本 0 开始。

**每个数据库、参与者和种类选择分别保存进度。** 游标只表示位置，不校验数据库身份，
也不绑定接收范围或承担身份认证。改变范围后复用旧游标，可能跳过新范围中较早的记录；
扩大或改变范围时应重新读取。每页大小可以调整。
项目等正文条件仍由应用判断：应逐页检查，即使这一页没有符合应用条件的内容，也要在
检查完成后推进，而不能把它当成底层已无后续记录。

## 保证和边界

在同一份未改写的历史、同一接收范围及种类选择下，沿游标读取会按提交和序号顺序
枚举匹配记录，不遗漏、不重复。每次读取固定数据库事务，使用已有记录索引，最多
取回 `limit + 1` 行，只解析实际返回记录的正文与来源；多取的一行用于判断是否还有下一页。
条数限制不等于字节数、查询耗时或应用总内存限制。

它不提供持久化队列或外部处理恰好一次的保证。处理动作与进度保存由应用负责；处理后、
保存游标前退出，可能导致重读，必要时让动作支持重复执行。同一提交的记录可以被拆到
不同页；需要完整提交级处理时，应查看有宿主权限的历史接口。

原 `view(last=N)` 仍表示最近上下文窗口，其 `View.revision` 不能充当该窗口的消费游标。
新接口不增加数据库结构、依赖、后台任务或自动同步。

运行 `python -m examples.paged_records` 可查看固定读取上界、另一连接写入，以及
关闭数据库后用 JSON 保存的位置恢复读取。
