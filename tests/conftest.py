"""End-to-end runs (`-m e2e`): several workers, each with its own daemon and browser (tests/e2e/conftest.py),
watched by tests/e2e_watchdog.py so a run that hangs or eats memory is stopped without anyone's help."""

from __future__ import annotations

import os

import pytest
from e2e_watchdog import Watchdog

E2E_WORKERS = 3  # a headless browser each


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> None:
    """`uv run pytest -m e2e` means `-n 3 --dist loadgroup --max-worker-restart 0` unless -n or --pdb is given.
    Runs before xdist's own hook of the same name, which turns -n into workers.

    Workers call this hook too, with -n cleared: without the worker check each one would start workers of
    its own, recursively (it once filled a machine with python processes)."""
    opt = config.option
    if hasattr(config, "workerinput") or os.environ.get("PYTEST_XDIST_WORKER"):
        return
    if opt.markexpr.strip() != "e2e" or opt.numprocesses is not None or opt.usepdb:
        return
    opt.numprocesses = E2E_WORKERS
    if opt.dist == "no":
        opt.dist = "loadgroup"  # test_blocked.py's own browser starts once, on one worker
    if opt.maxworkerrestart is None:
        opt.maxworkerrestart = 0  # a crashed worker is not replaced (each new one would start a browser)


@pytest.hookimpl(trylast=True)  # after pytest's tmp_path setup
def pytest_configure(config: pytest.Config) -> None:
    """The watchdog runs in the process that reports results (not in xdist workers) when e2e tests may run."""
    expr = config.option.markexpr.replace(" ", "")
    if "e2e" in expr and expr != "note2e" and not hasattr(config, "workerinput"):
        dog = Watchdog(config._tmp_path_factory.getbasetemp(), max_pythons=3 * (config.option.numprocesses or 0) + 4)
        config.pluginmanager.register(dog, "e2e-watchdog")
        dog.start()
