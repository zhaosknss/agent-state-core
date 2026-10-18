# Source and design origins

The initial implementation was written for this repository. No source code from
Graphiti, Generative Agents, Concordia, LangGraph, or other third-party agent
frameworks was copied or vendored. Alpha 2 uses LangGraph as an actual optional
dependency, while Apache Burr is a storage design reference. Fixed revisions,
inspected files, licenses, and use are documented in [upstream review](docs/UPSTREAM.md).

The design grew from mechanisms in the oc-world story application. The source
review used commit `266b2141d1f0fb752133d612f0151b2e69e64e5e` as a reference:

| Source mechanism | New implementation |
|---|---|
| `src/context.py`: observations and restricted source views | Explicit audience records and detached participant views |
| `src/chapters.py`: actor context and public descriptions | Host state is omitted from participant views by construction |
| `src/settlement.py`: hearing a claim differs from world state | Records never implicitly mutate authoritative state |
| `src/chapter_store.py`: version/owner checks and publication | Atomic journal commits with optimistic revision checks |

This is a redesign, not a file extraction or a port of the story schema. It
introduces a generic JSON journal and tests its own replay semantics. The original
application's chapter scheduling, resource rules, prompts, character data, model
adapter, browser worker, databases, and source history are not included. The old
application's tests or model runs are not evidence that this new library works.

Related projects for comparison:

- [Graphiti](https://github.com/getzep/graphiti): temporal facts and provenance.
- [Generative Agents](https://github.com/joonspk-research/generative_agents):
  ongoing interaction among agents in a shared environment.
- [Concordia](https://github.com/google-deepmind/concordia): social simulation
  and action/environment/observation boundaries.
- [LangGraph](https://github.com/langchain-ai/langgraph): orchestration,
  persistence, and human intervention.

The core runtime depends only on the Python standard library (including SQLite).
The context-handoff recipe is original example code with fictional messages and
application-defined note policy; it includes no private chat exports or model
output dataset. It adds no upstream code or dependency.
The optional LangGraph integration has its own dependency closure and tests;
it is not installed for core-only users.
Setuptools is the build backend (82.0.1 used for the initial local build).
The CI workflow pins these official actions, whose root licenses were checked
at the indicated revisions on 2026-10-17; they run on Node 24 in CI:

| CI tool | Fixed revision | License |
|---|---|---|
| [actions/checkout v7.0.1](https://github.com/actions/checkout/tree/3d3c42e5aac5ba805825da76410c181273ba90b1) | `3d3c42e5aac5ba805825da76410c181273ba90b1` | MIT |
| [actions/setup-python v7.0.0](https://github.com/actions/setup-python/tree/5fda3b95a4ea91299a34e894583c3862153e4b97) | `5fda3b95a4ea91299a34e894583c3862153e4b97` | MIT |

CI actions are not runtime dependencies or code vendored into the Python package.
Any future reuse of upstream source requires checking its specific revision,
files, license, and dependencies first.

The project code is licensed under [MIT](LICENSE), using the
[OSI MIT license text](https://opensource.org/license/mit). This repository does
not grant rights to assets or datasets that are not included here.
