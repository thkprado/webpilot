"""`webpilot script` and the lookup of local folders: WEBPILOT_PARSERS_DIR first, then the clone's parsers_user."""

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from webpilot import cli, registry

ARGPARSE = '''"""Echo the arguments it gets.

    webpilot script {name} -n 3
"""
import argparse
import sys

ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=1, help="how many")
args = ap.parse_args()
print("{name}", args.n, sys.argv[1:])
'''


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """A fake clone (root/parsers_user) and a WEBPILOT_PARSERS_DIR (env), both empty; never the real parsers_user."""
    root, env = tmp_path / "root", tmp_path / "env"
    (root / "parsers_user").mkdir(parents=True)
    env.mkdir()
    monkeypatch.setattr(registry, "PROJECT_ROOT", root)
    monkeypatch.setenv("WEBPILOT_PARSERS_DIR", str(env))
    return root / "parsers_user", env


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")
    return path


def run(*args):
    try:
        runner = CliRunner(mix_stderr=False)  # click < 8.2 mixes stderr into stdout by default
    except TypeError:
        runner = CliRunner()  # click >= 8.2 always keeps stderr apart
    return runner.invoke(cli.app, ["script", *args])


def test_env_dir_comes_first_and_shadows(dirs):
    clone, env = dirs
    write(clone / "scripts/same.py", ARGPARSE.replace("{name}", "clone"))
    write(env / "scripts/same.py", ARGPARSE.replace("{name}", "env"))
    write(clone / "scripts/only_clone.py", '"""Only in the clone."""\n')
    assert registry.script_dirs() == [env / "scripts", clone / "scripts"]
    assert registry.parser_dirs() == [env, clone, registry.BUILTIN_DIR]

    found, shadowed, errors = registry.scripts()
    assert [(s.name, s.path) for s in found] == [("same", env / "scripts/same.py"),
                                                ("only_clone", clone / "scripts/only_clone.py")]
    assert shadowed == [(clone / "scripts/same.py", env / "scripts/same.py")] and errors == []
    result = run()
    assert result.exit_code == 0
    assert "Echo the arguments it gets." in result.stdout and "Only in the clone." in result.stdout
    assert f"(shadowed by {env / 'scripts/same.py'})" in result.stdout
    assert run("same").stdout.startswith("env 1")


def test_fallback_without_env_and_missing_env(dirs, monkeypatch):
    clone, env = dirs
    write(clone / "scripts/one.py", ARGPARSE.replace("{name}", "one"))
    monkeypatch.delenv("WEBPILOT_PARSERS_DIR")
    assert registry.local_dirs() == [clone]
    assert run("one").stdout.startswith("one 1")

    monkeypatch.setenv("WEBPILOT_PARSERS_DIR", str(env / "missing"))
    assert registry.local_dirs() == [clone]
    result = run()
    assert result.exit_code == 0 and "one" in result.stdout
    assert f"WEBPILOT_PARSERS_DIR is not a folder: {env / 'missing'}" in result.stderr


def test_env_pointing_at_the_clone_is_not_listed_twice(dirs, monkeypatch):
    clone, _ = dirs
    monkeypatch.setenv("WEBPILOT_PARSERS_DIR", str(clone / ".." / "parsers_user"))
    assert len(registry.local_dirs()) == 1
    write(clone / "scripts/one.py", '"""One."""\n')
    assert registry.scripts()[1] == []


def test_notes_files_in_lookup_order(dirs):
    clone, env = dirs
    assert registry.notes_files() == []
    write(clone / "NOTES.md", "# clone")
    write(env / "NOTES.md", "# env")
    assert registry.notes_files() == [env / "NOTES.md", clone / "NOTES.md"]
    result = run()
    assert str(env / "NOTES.md") in result.stdout and str(clone / "NOTES.md") in result.stdout


def test_empty_listing(dirs):
    clone, env = dirs
    result = run()
    assert result.exit_code == 0 and "No scripts" in result.stdout
    assert str(env / "scripts") in result.stdout and str(clone / "scripts") in result.stdout
    assert "hn_top.py" in result.stdout
    clone.rmdir()
    assert "cp -r examples/parsers_user parsers_user" in run().stdout


def test_syntax_error_is_listed_and_helpers_are_not(dirs):
    clone, _ = dirs
    write(clone / "scripts/broken.py", "def (:\n")
    write(clone / "scripts/_wp_test_helper.py", "VALUE = 42\n")
    write(clone / "scripts/uses_helper.py", "from _wp_test_helper import VALUE\nprint(VALUE)\n")
    result = run()
    assert result.exit_code == 1
    assert "uses_helper" in result.stdout and "_wp_test_helper" not in result.stdout
    assert f"error: {clone / 'scripts/broken.py'}: SyntaxError" in result.stderr

    path = sys.path[:]
    assert run("uses_helper").stdout == "42\n"
    assert sys.path == path


def test_arguments_help_and_exit_codes(dirs, tmp_path, monkeypatch):
    _, env = dirs
    write(env / "scripts/echo.py", ARGPARSE.replace("{name}", "echo"))
    write(env / "scripts/three.py", "import sys\nsys.exit(3)\n")
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    argv = sys.argv[:]

    result = run("echo", "-n", "3", "--extra")
    assert result.exit_code == 2  # argparse rejects --extra
    result = run("echo.py", "-n", "3")
    assert result.exit_code == 0 and result.stdout == "echo 3 ['-n', '3']\n"
    result = run("echo", "--help")
    assert result.exit_code == 0 and "how many" in result.stdout and "Run a local script" not in result.stdout
    assert run("echo", "-h").exit_code == 0
    assert run("three").exit_code == 3
    assert sys.argv == argv


def test_not_found_lists_dirs(dirs):
    clone, env = dirs
    result = run("nope")
    assert isinstance(result.exception, cli.WebPilotError)
    assert str(env / "scripts") in str(result.exception) and str(clone / "scripts") in str(result.exception)


def test_command_help_without_name():
    result = run("--help")
    assert result.exit_code == 0 and "Run a local script" in result.stdout
