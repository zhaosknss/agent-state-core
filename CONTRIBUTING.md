# Contributing / 参与

Thanks for trying this early version. You do not need a finished proposal to
start a discussion. Use [Discussions](https://github.com/zhaosknss/agent-state-core/discussions)
for questions, use cases, API suggestions, or a different design you would prefer.
Use [Issues](https://github.com/zhaosknss/agent-state-core/issues) for bugs; a small
reproducer, expected result, actual result, and Python/OS version are helpful.

To work on the code, clone the repository and run:

```bash
python -B tools/verify.py
```

This runs the behavior tests and base deterministic examples with network access
blocked. No model key or third-party runtime package is needed. If you change
state history, audience projection, or commit behavior, include a case that shows
the intended behavior and keep docs/DESIGN.md in sync. Small, focused pull
requests are welcome. Contributions are made under the project's MIT license.

For the optional integration, install `.[langgraph]` or the pinned
`requirements/langgraph-test.txt` environment, then run
`python -B tools/verify.py --langgraph`. Keep upstream version/license references
and the integration guide in sync when changing that boundary.

For the separate retrieval recipe, install `requirements/retrieval-test.txt`
and run `python -B tools/verify.py --retrieval`. The flags can be combined when
both dependencies are installed. Run `python -B tools/audit_composition.py`
to reproduce the documented capabilities and restrictions; a passing restriction
check does not mean the limitation is removed. See [composition](docs/COMPOSITION.md).

欢迎直接说使用感受，不用先写完整方案。想用在哪、哪里不顺手、有什么不同的设计想法，都可以发到 Discussions。报告 bug 时，留一个能复现的小例子，以及预期和实际结果会很有帮助。

改代码前可以先运行上面的检查；修改状态、信息范围或提交行为时，补上对应的行为案例。请使用虚构数据或去掉敏感内容的小样例。
