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
    parser.add_argument("--langgraph", action="store_true", help="Also run the installed LangGraph integration")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    package_path = root if args.wheel is None else args.wheel.resolve(strict=True)
    if args.wheel is not None and package_path.suffix != ".whl":
        parser.error("--wheel must name a .whl file")
    sys.path.insert(0, str(package_path))
    network_attempts = []
    socket_creations = []

    def audit(event, arguments):
        if event == "socket.__new__":
            socket_creations.append(event)
        blocked = event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                            "socket.sendto", "socket.sendmsg"}
        if event == "socket.bind":
            address = arguments[1]
            blocked = not (isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"})
        if blocked:
            network_attempts.append(event)
            raise RuntimeError("Network access is disabled during verification")

    sys.addaudithook(audit)
    import agent_state_core

    if not str(agent_state_core.__file__).startswith(str(package_path)):
        raise RuntimeError("Verification imported a different package copy")
    # Recipes remain in the checkout; keep the wheel first for all core imports.
    sys.path.append(str(root))
    started = perf_counter()
    suite = unittest.TestLoader().discover(str(root / "tests"))
    if args.langgraph:
        suite.addTests(unittest.TestLoader().discover(str(root / "integration_tests")))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    for name in ("information_flow", "collaboration", "context_handoff"):
        runpy.run_path(str(root / "examples" / f"{name}.py"), run_name="__main__")
    if args.langgraph:
        runpy.run_path(str(root / "examples" / "langgraph_collaboration.py"), run_name="__main__")
    print(json.dumps({
        "tests": result.testsRun, "examples": 4 if args.langgraph else 3,
        "network_attempts": len(network_attempts),
        "socket_creations": len(socket_creations),
        "package": str(agent_state_core.__file__),
        "python": sys.version.split()[0], "seconds": round(perf_counter() - started, 3),
    }, sort_keys=True))
    return 1 if network_attempts else 0


if __name__ == "__main__":
    raise SystemExit(main())
