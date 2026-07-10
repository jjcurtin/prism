"""Cross-platform dev task runner; single source of truth for `setup`/`run`/
`interface`/`test` logic. The Makefile is a thin wrapper delegating each
target to a subcommand here, kept only because Linux/macOS users are used to
`make` -- Windows has no `make` by default, so `python tasks.py <command>`
is the entry point that actually works everywhere. Uses plain `--long-flag`
argparse convention for its own arguments; this does not need to mirror
run_prism.py's pre-existing single-dash `-mode` flag, which predates this
script and is left as-is.

`setup` must be invoked with the SYSTEM python (no venv exists yet) and
computes the venv's interpreter paths itself, mirroring the old Makefile's
OS-branch exactly (Windows: plain pip install; Linux: apt-installed pandas +
`--system-site-packages` venv, since pandas has no prebuilt wheel for
cp313/aarch64). Every other subcommand assumes it's already being run via
the venv's python (so `sys.executable` correctly points at the venv) and
just relays to the right script/subprocess.
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"


def _venv_paths():
    """Return (python, pip) paths inside .venv, OS-branched the same way the
    old Makefile branched on $(OS)."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe", VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "python", VENV_DIR / "bin" / "pip"


def cmd_setup(args):
    """Create .venv and install dependencies, then run setup_env.py."""
    venv_python, venv_pip = _venv_paths()

    if sys.platform == "win32":
        # Windows has prebuilt wheels for every requirement (including
        # pandas), so a plain venv + pip install is enough.
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        subprocess.run([str(venv_pip), "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(venv_pip), "install", "-r", "requirements.txt"], check=True)
        subprocess.run([str(venv_pip), "install", "-r", "requirements-dev.txt"], check=True)
    else:
        # pandas has no prebuilt wheel for this platform (cp313/aarch64);
        # install it via apt and build the venv with --system-site-packages
        # so pip doesn't try (and fail/hang) to compile it from source.
        subprocess.run(["sudo", "apt-get", "install", "-y", "python3-pandas"], check=True)
        subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(VENV_DIR)],
            check=True,
        )
        subprocess.run([str(venv_pip), "install", "--upgrade", "pip"], check=True)
        with open(REPO_ROOT / "requirements.txt") as f:
            stripped = "".join(line for line in f if not line.startswith("pandas"))
        subprocess.run(
            [str(venv_pip), "install", "-r", "/dev/stdin"],
            input=stripped,
            text=True,
            check=True,
        )
        subprocess.run([str(venv_pip), "install", "-r", "requirements-dev.txt"], check=True)

    subprocess.run([sys.executable, "setup_env.py"], check=True)

    # Every other subcommand relies on sys.executable already being the
    # venv's python -- print the exact correct next command rather than
    # assuming the user knows to invoke tasks.py via .venv's interpreter
    # (or has activated the venv) instead of a bare `python`/`python3` on
    # PATH, which would silently hit the system interpreter and fail with
    # missing-dependency errors. `make run-test`/`make run-prod` already
    # get this right automatically; this message matters most for Windows
    # users, who don't have `make` to shield them from the distinction.
    print(
        f"\nSetup complete. Start PRISM with:\n"
        f"  {venv_python} tasks.py run --mode test\n"
        f"or, once ready for a real run:\n"
        f"  {venv_python} tasks.py run --mode prod\n"
        f"\nNote: this only sets up the code. If the `environment` file (a "
        f"git-ignored file at the repo root containing \"dev\" or \"prod\") "
        f"is missing, PRISM defaults to \"dev\" and expects the research "
        f"drive already mounted with dev credentials in place -- see "
        f"config/README.md."
    )


def cmd_run(args):
    """Stop any running server, then start run_prism.py in the given mode."""
    subprocess.run([sys.executable, "stop_server.py"], check=True)
    subprocess.run([sys.executable, "run_prism.py", "-mode", args.mode], cwd="src", check=True)


def cmd_interface(args):
    """Launch the RA terminal interface (src/prism_interface.py)."""
    subprocess.run([sys.executable, "prism_interface.py"], cwd="src", check=True)


_TEST_TARGETS = {
    "server": "tests",
    "client": "tests_interface",
    "integration": "tests_integration",
}


def cmd_test(args):
    """Run the requested pytest suite(s) via `sys.executable -m pytest`."""
    if args.target == "all":
        targets = ["server", "client", "integration"]
    else:
        targets = [args.target]

    for target in targets:
        subprocess.run(
            [sys.executable, "-m", "pytest", _TEST_TARGETS[target], "-v"],
            check=True,
        )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tasks.py",
        description="Cross-platform dev task runner for PRISM (single source of truth; "
        "the Makefile delegates to this on Linux/macOS).",
    )
    subparsers = parser.add_subparsers(dest="command")

    p_setup = subparsers.add_parser(
        "setup",
        help="Create .venv and install all dependencies (run with the system python).",
    )
    p_setup.set_defaults(func=cmd_setup)

    p_run = subparsers.add_parser(
        "run",
        help="Stop any running server and start PRISM (run with the venv python).",
    )
    p_run.add_argument(
        "--mode",
        choices=["test", "prod"],
        required=True,
        help="Mode to run PRISM in. 'test' for development, 'prod' for production. "
        "No default: never boot -mode prod casually.",
    )
    p_run.set_defaults(func=cmd_run)

    p_interface = subparsers.add_parser(
        "interface",
        help="Launch the RA terminal interface (run with the venv python).",
    )
    p_interface.set_defaults(func=cmd_interface)

    p_test = subparsers.add_parser("test", help="Run a pytest suite.")
    test_subparsers = p_test.add_subparsers(dest="target", required=True)
    test_subparsers.add_parser("server", help="Run the server-side suite (pytest tests -v).")
    test_subparsers.add_parser(
        "client", help="Run the interface-side suite (pytest tests_interface -v)."
    )
    test_subparsers.add_parser(
        "integration",
        help="Run the real end-to-end suite against live external services "
        "(pytest tests_integration -v); local-only, skips cleanly without dev credentials.",
    )
    test_subparsers.add_parser(
        "all", help="Run server, client, and integration suites, in that order."
    )
    p_test.set_defaults(func=cmd_test)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
