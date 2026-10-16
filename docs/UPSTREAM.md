# Upstream reuse and implementation review

Reviewed on 2026-10-17. This distinguishes a real runtime dependency from design
references and projects that were only compared. The core implementation remains
independent of an agent orchestration framework.

## LangGraph: actual optional dependency

The `langgraph` extra pins **langgraph 1.2.15**. The fixed source revision reviewed
was [`b0cabd93d05508d246318c92b41b3952fe56f5c3`](https://github.com/langchain-ai/langgraph/tree/b0cabd93d05508d246318c92b41b3952fe56f5c3).
`libs/langgraph/pyproject.toml` at that revision declares version 1.2.15, Python
>=3.10, and the dependencies used by that distribution.

Inspected files at that revision:

- [Package metadata](https://github.com/langchain-ai/langgraph/blob/b0cabd93d05508d246318c92b41b3952fe56f5c3/libs/langgraph/pyproject.toml).
- `libs/langgraph/langgraph/graph/state.py`: StateGraph and compile/checkpointer API.
- `libs/langgraph/langgraph/types.py`: Command and interrupt API.
- [InMemorySaver](https://github.com/langchain-ai/langgraph/blob/b0cabd93d05508d246318c92b41b3952fe56f5c3/libs/checkpoint/langgraph/checkpoint/memory/__init__.py):
  checkpoint lookup and filtered/bounded listing. The source explicitly presents
  this saver as suitable for debugging/testing, not production durability.
- [Root MIT license](https://github.com/langchain-ai/langgraph/blob/b0cabd93d05508d246318c92b41b3952fe56f5c3/LICENSE)
  and the checkpoint package's MIT license.

The example actually calls LangGraph `StateGraph`, `InMemorySaver`, `interrupt`,
and `Command`. LangGraph handles graph execution and the in-process pause/resume;
agent-state-core handles domain records, scoped input, and authoritative commits.
The graph nodes pass the participant function scoped JSON rather than the host's
complete state. Completed host requests can be looked up before replaying a node.

This is ordinary API usage with an original example, not vendored LangGraph
source. The dependency retains its own MIT license in its distribution. The
optional dependency closure is larger than the core; the exact local test set
is pinned in [requirements/langgraph-test.txt](../requirements/langgraph-test.txt),
with installed version/license metadata in [langgraph-environment.json](langgraph-environment.json).
Core installation does not install that extra. Integration checks use deterministic
functions, not paid model calls. This is not a claim of complete LangGraph adapter
coverage or coordination of two stores in a single distributed transaction.

Official API references used:
[quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart),
[interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts),
[persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

## Apache Burr: storage design reference

Inspected [`burr/core/persistence.py`](https://github.com/apache/burr/blob/f8488d0cd034fa292c6d7e5fd1a431f12f403ff5/burr/core/persistence.py)
at commit `f8488d0cd034fa292c6d7e5fd1a431f12f403ff5`, including `SQLitePersister`
table/index creation and `load` queries constrained by partition, application,
and sequence, with ordered `LIMIT` reads. Its
[license](https://github.com/apache/burr/blob/f8488d0cd034fa292c6d7e5fd1a431f12f403ff5/LICENSE)
is Apache-2.0.

The useful lesson was to push scope and history selection into the database
rather than deserialize a complete execution journal for every read. In this
library that became independently implemented record/audience projections,
per-key state versions, and filtered views. The query keys and schema differ
from Burr's snapshots. No Burr code was copied, adapted, or included as a runtime
dependency. This is design reuse, not a claim to have integrated Burr.

## Related projects, not installed integrations

Graphiti, Generative Agents, and Concordia remain useful comparisons for
temporal facts, ongoing interaction, and environment observations. They are not
dependencies of this release. Earlier broad comparisons do not imply that their
code was reused or that this library implements all their capabilities.

The project's own changes and measured limits are recorded in
[CHANGELOG](../CHANGELOG.md) and [validation](VALIDATION.md).
