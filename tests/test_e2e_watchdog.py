"""The checks of the e2e watchdog (tests/e2e_watchdog.py); its abort is exercised by hand (see CONTRIBUTING)."""

import os
import subprocess
import sys

import e2e_watchdog
from e2e_watchdog import Watchdog, descendants


def test_descendants_include_a_child_process():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert child.pid in {pid for pid, _ in descendants(os.getpid())}
    finally:
        child.kill()
        child.wait()


def test_a_quiet_run_has_no_problem(tmp_path):
    assert Watchdog(tmp_path, max_pythons=10).problem() is None


def test_a_test_over_its_limit_is_a_problem(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBPILOT_E2E_TEST_LIMIT", "0")
    dog = Watchdog(tmp_path, max_pythons=10)
    dog.pytest_runtest_logstart("tests/e2e/test_x.py::test_y", None)
    assert "test_x.py::test_y ran for more than 0 s" in dog.problem()
    dog.pytest_runtest_logfinish("tests/e2e/test_x.py::test_y", None)
    assert dog.problem() is None


def test_too_many_pythons_and_low_memory_are_problems(tmp_path, monkeypatch):
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert "python processes descend from this run" in Watchdog(tmp_path, max_pythons=0).problem()
    finally:
        child.kill()
        child.wait()
    monkeypatch.setattr(e2e_watchdog, "free_memory", lambda: (0.05, 0.5))
    assert "free memory fell to 5% of RAM" in Watchdog(tmp_path, max_pythons=10).problem()
