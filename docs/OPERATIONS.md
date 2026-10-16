# Operations and troubleshooting / 运行与排错

## Check the installation

```bash
python -B tools/verify.py
python -m examples.information_flow
```

For the optional integration, install `.[langgraph]` first, then run
`python -B tools/verify.py --langgraph`. To verify a built wheel instead of source,
use `python -I -B tools/verify.py --wheel /path/to/file.whl`; the runner checks
which package copy was imported. It reports connection attempts separately from
socket creation used by upstream local capability probes.

Optional test CI sets `LANGSMITH_TRACING=false` and `LANGCHAIN_TRACING_V2=false`
to disable upstream tracing. The core does not read those variables. If an
existing environment enables tracing, turn it off for the offline example checks.

## Database upgrade and backups

Alpha 2 uses schema v2. Opening an alpha-1 schema-v1 ledger creates its indexed
query projections from the existing journal and advances the schema version in
one SQLite transaction. Original commits, request IDs, timestamps, and request
fingerprints are preserved. A failure rolls back the new tables and version
change; the old journal remains available for another attempt.

The older alpha-1 library does not understand a schema-v2 file. Keep a backup
before upgrading valuable data. When all ledger connections are closed, copy
the file normally. For a live database use SQLite's backup API rather than
copying an in-use database file:

```python
import sqlite3
from contextlib import closing

with closing(sqlite3.connect("session.db")) as source:
    with closing(sqlite3.connect("session.backup.db")) as destination:
        source.backup(destination)
```

Use a dedicated ledger database. Do not add unrelated tables or edit the
journal/query projections manually; schema ownership is checked on open.

## Common errors

| Error or observation | Action |
|---|---|
| `StaleRevision` | Read a new base; decide whether the result remains applicable before submitting again |
| `RequestConflict` | An ID was reused with changed base/intent/result; retrieve the original or use a new operation ID |
| Empty participant view | Check audience, revision bounds, and kinds; updating state does not publish an observation |
| Old information remains | Historical records are preserved; the application decides how to interpret or summarize them |
| `SchemaError` | Check that this is a supported dedicated ledger file and that schema migration was not manually altered |
| SQLite lock timeout | Finish/close competing transactions; use separate connections per thread |
| Optional import failure | Install `.[langgraph]` in the same Python environment running the example |
| Invalid JSON / rejected updates | Use finite JSON values with string keys; rejected results must not contain state changes |

## Performance and size

Scoped record reads use public/audience indexes. State reads use per-key versions.
Complete `history()` intentionally reads the full journal. `last` bounds the
returned context but is not a pagination cursor. The journal and its projections
duplicate some data; no compaction or retention policy is supplied.

Reproduce the synthetic read comparison with `python tools/benchmark_reads.py`.
Measure your own history shape and storage medium before making performance
assumptions. This alpha has not been validated for large production workloads.

## 中文速查

升级前备份有价值的数据库。旧库打开后自动在同一事务内升级，失败会回滚；旧版程序不能直接读取已经升级的 v2 文件。关闭全部连接后可以复制数据库，运行中请使用 SQLite 的 backup 接口。

版本冲突先读新状态再判断；请求冲突检查是否复用了同一操作 ID；信息为空时检查接收者、记录种类和版本范围。状态更新与“向参与者告知”是两个操作，历史里的旧观察也会继续保留。
