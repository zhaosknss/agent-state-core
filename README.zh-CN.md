# agent-state-core：多智能体的状态与信息基础

这是 agent-state-core 的第一个开源版本。我把自己项目里的一些状态与信息处理逻辑拆出来，想让大家试试：能否用在你们的项目里，接口是否顺手，还有哪些地方需要改。

[试用版本](https://github.com/zhaosknss/agent-state-core/releases) · [讨论与建议](https://github.com/zhaosknss/agent-state-core/discussions) · [问题反馈](https://github.com/zhaosknss/agent-state-core/issues)

它把三件事分开处理：应用中已经成立的事实与状态、不同参与者接触到的记录，以及对外展示的信息。参与者可以收到过时的观察或未经证实的说法，这些内容不会自动改写共享状态。

数据内容、动作、规则、调用哪个模型、谁先参与，都由接入应用决定。讨论、角色推演和工具协作可以分别组合这些基础能力。核心没有要求使用导演、人物、章节、投票或固定讨论流程。

## 现在怎么运行

需要 Python 3.11 以上。在项目目录打开终端，直接运行，无需安装运行依赖或填写 API：

```powershell
git clone https://github.com/zhaosknss/agent-state-core.git
cd agent-state-core
python -m examples.information_flow
python -m examples.collaboration
python -m unittest discover -s tests -v
```

第一个例子里，钥匙实际交给了乙，但没有获知交接的丙仍只看到旧记录；后来收到的说法也不会改变钥匙归属。丙尝试转交钥匙失败，结果不会改写已经成立的状态。数据库关闭后重新打开，历史仍在。

第二个例子里，参与者先按预算 100 提方案；人把预算改成 50 后，旧版本方案无法直接提交，应用根据新条件重新选择方案。

这些例子使用普通 Python 函数，验证数据流和提交行为。真实模型生成、表现与费用尚未验证。

如果要放进自己的 Python 项目，可以从 [Releases](https://github.com/zhaosknss/agent-state-core/releases) 下载 wheel 后安装：

```powershell
python -m pip install ./agent_state_core-0.1.0a1-py3-none-any.whl
```

目前没有发布到 PyPI。

## 核心接口

| 对象或操作 | 作用 |
|---|---|
| `Ledger` | 保存提交历史；指定数据库文件路径即可跨进程保留 |
| `snapshot()` | 读取应用的全局状态，也可以指定历史版本；供宿主程序使用 |
| `Record` | 保存一条有种类、内容、接收范围和来源的记录 |
| `view(participant)` | 只取公开或明确发给该参与者的记录；不会自动带入全局状态 |
| `Intent` / `Transition` | 保存尝试的行动，以及由应用判定的结果和状态变化 |
| `commit()` | 同时提交结果与记录，检查基础版本，并支持相同请求重取原结果 |

`Record.audience=None` 表示公开，`("alice",)` 表示只发给 alice，空元组 `()` 表示仅宿主留存。记录来源也是随记录可见的内容，调用者应只放适合该接收范围的信息。

当前版本提供的是记录、历史和信息范围机制。任意分支推演、自动检查文字是否忠实、调度器和框架适配还需要后续实现。记录过滤也不能代替身份认证或不可信代码隔离。全局版本检查目前较保守，每次提交都会推进版本。

完整接口语义以 [设计文档](docs/DESIGN.md) 为准。代码来源见 [PROVENANCE](PROVENANCE.md)，实际检查见 [VALIDATION](docs/VALIDATION.md)。采用 [MIT 许可](LICENSE)。

## 欢迎提建议

你会想把它用在哪种项目里？哪些部分有用，哪些地方不好理解或不方便？也欢迎说说现有接口满足不了的情况，帮助我判断接下来应该怎么改。

想法和使用问题可以直接发到 [Discussions](https://github.com/zhaosknss/agent-state-core/discussions)。发现 bug 的话，在 [Issues](https://github.com/zhaosknss/agent-state-core/issues) 留下能复现的小例子、预期结果和实际结果就很有帮助。欢迎讨论，也欢迎直接改代码，见 [参与说明](CONTRIBUTING.md)。
