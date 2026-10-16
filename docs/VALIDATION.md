# Local validation evidence

Checked on 2026-10-17 (Asia/Shanghai) on Windows with Python 3.13.3,
SQLite from that Python installation, and setuptools 82.0.1. These are local
checks, not results from GitHub Actions or a model benchmark.

## Behavior and examples

```powershell
python -I -B tools/verify.py
```

Result: **20 tests passed; both examples completed; 0 network attempts**.
The source run took 0.154 seconds for tests plus examples; this is an
execution record, not a performance benchmark.

The tests exercise participant/public/host-only projections, a false claim and
outdated observations, historical reads, rejected actions, stale proposals,
duplicate and conflicting requests, source references, detached mutable values,
strict JSON validation, custom action/state schemas, deletion, reopening a file,
competing writers, a failed SQLite insertion, and refusing unrelated/future-schema
databases without modifying them. The write-failure test uses an SQLite ABORT
trigger; it is not a power-loss or failing-hardware experiment.

On the initial run, three Windows test-fixture cleanup failures exposed SQLite
connections that were not explicitly closed by the test code. The fixtures were
corrected to close them; the final suite above completed without cleanup errors.

The examples produced these material results:

- Global key holder is `bob`; Carol receives only the earlier `alice` observation,
  an unverified `alice` claim, and her rejected action result. The public view has
  only the earlier observation. Reopening the database preserves revision 4.
- A proposal based on budget 100 is rejected after the human changes it to 50;
  the application commits a new plan costing 50 at revision 3.

The verification runner blocks socket construction, connection, and DNS lookup
via a Python audit hook. No model adapter is installed or invoked by these checks.

## Initial local artifact, before the public release

```powershell
python -B -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir dist
```

Built `agent_state_core-0.1.0a1-py3-none-any.whl` (9,159 bytes), SHA-256:

```text
c8f0480b82db02d59bf078988af58537d8bdf27700b3851aaf49cd2d9d17c989
```

The wheel contains the three package modules, metadata, and the MIT license.
Metadata declares Python >=3.11, MIT, and no runtime dependencies. The build used
locally available tooling with package-index access disabled; no install into the
user's Python environment was performed.

The same behavior checks and both examples were then run against the wheel,
using isolated Python from outside the source checkout:

```powershell
python -I -B /path/to/agent-state-core/tools/verify.py --wheel /path/to/agent_state_core-0.1.0a1-py3-none-any.whl
```

Result: **20 tests passed; both examples completed; 0 network attempts** in
0.194 seconds. The runner confirmed the imported package came from the wheel,
not the source directory. Its modules and license were also compared byte for
byte with the checkout and matched. The artifact is a local build and has not
been uploaded. Python 3.11 syntax parsing, local Markdown link checks, a token
pattern scan, and wheel ZIP integrity checks completed successfully.

## CI and remaining limits

The CI configuration targets Ubuntu and Windows with Python 3.11 and 3.13.
Local evidence above covers Python 3.13.3 on Windows. Current remote results are
available in [Behavior checks](https://github.com/zhaosknss/agent-state-core/actions/workflows/test.yml);
release notes link the specific run checked for that release. A configured matrix
alone is not evidence that it passed.

No real model behavior, framework adapter, arbitrary branch recovery,
large-history performance, multi-tenant authorization, or semantic consistency
judge has been validated. Release assets may differ from the initial local wheel
above as README and package metadata are prepared for publication; the release
includes its own SHA-256 checksums.
