"""Run behavior tests and examples, optionally against an isolated wheel import."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import sys
from time import perf_counter
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, help="Import the package from this wheel")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    package_path = root if args.wheel is None else args.wheel.resolve(strict=True)
    if args.wheel is not None and package_path.suffix != ".whl":
        parser.error("--wheel must name a .whl file")
    sys.path.insert(0, str(package_path))
    network_attempts = []

    def audit(event, arguments):
        if event in {"socket.__new__", "socket.connect", "socket.getaddrinfo"}:
            network_attempts.append(event)
            raise RuntimeError("Network access is disabled during verification")

    sys.addaudithook(audit)
    import agent_state_core

    if not str(agent_state_core.__file__).startswith(str(package_path)):
        raise RuntimeError("Verification imported a different package copy")
    started = perf_counter()
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    for name in ("information_flow", "collaboration"):
        runpy.run_path(str(root / "examples" / f"{name}.py"), run_name="__main__")
    print(json.dumps({
        "tests": result.testsRun, "examples": 2, "network_attempts": len(network_attempts),
        "package": str(agent_state_core.__file__),
        "python": sys.version.split()[0], "seconds": round(perf_counter() - started, 3),
    }, sort_keys=True))
    return 1 if network_attempts else 0


if __name__ == "__main__":
    raise SystemExit(main())
