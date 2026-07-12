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
OS-branch exactly (Windows: plain pip install, since pandas ships a
prebuilt wheel for every Windows-supported CPython version we target;
everywhere else: probe pip for a prebuilt pandas wheel first, since wheel
availability depends on CPython version + CPU arch rather than distro --
e.g. it's missing on the Pi's cp313/aarch64 but present on a typical Fedora
x86_64 host. Only when no wheel is found do we fall back to a system-package
install (apt on Debian/Ubuntu, dnf on Fedora) + `--system-site-packages`
venv). Every other subcommand assumes it's already being run via the venv's
python (so `sys.executable` correctly points at the venv) and just relays to
the right script/subprocess.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
VENV_DIR = REPO_ROOT / ".venv"


def _venv_paths():
    """Return (python, pip) paths inside .venv, OS-branched the same way the
    old Makefile branched on $(OS)."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe", VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "python", VENV_DIR / "bin" / "pip"


def _pandas_requirement():
    """Return the pinned pandas requirement line from requirements.txt, so
    the wheel probe and the system-package fallback both track the same
    pin instead of duplicating the version."""
    with open(REPO_ROOT / "requirements.txt") as f:
        for line in f:
            if line.strip().startswith("pandas"):
                return line.strip()
    raise RuntimeError("pandas requirement not found in requirements.txt")


def _pandas_wheel_available():
    """Probe (without installing anything) whether pip can source a
    prebuilt pandas wheel for this interpreter/platform. `pip download`
    isn't gated by PEP 668's externally-managed-environment check the way
    `pip install` is, so this is safe to run with the system python."""
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable, "-m", "pip", "download",
                "--no-deps", "--only-binary=:all:", "--dest", tmp,
                _pandas_requirement(),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
        )
    return result.returncode == 0


def _system_pandas_install_command():
    """Pick the system package manager available on this host to install
    pandas as a fallback when no prebuilt wheel exists."""
    if shutil.which("apt-get"):
        return ["sudo", "apt-get", "install", "-y", "python3-pandas"]
    if shutil.which("dnf"):
        return ["sudo", "dnf", "install", "-y", "python3-pandas"]
    raise RuntimeError(
        "No prebuilt pandas wheel is available for this Python/platform, "
        "and neither apt-get nor dnf was found to install a system package. "
        "Install pandas manually, then re-run setup."
    )


def cmd_setup(args):
    """Create .venv and install dependencies, then run setup_env.py."""
    venv_python, venv_pip = _venv_paths()

    if sys.platform == "win32" or _pandas_wheel_available():
        # A prebuilt wheel exists for this interpreter/platform, so a plain
        # venv + pip install is enough -- no system package or
        # --system-site-packages workaround needed.
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True, cwd=REPO_ROOT)
        subprocess.run([str(venv_pip), "install", "--upgrade", "pip"], check=True, cwd=REPO_ROOT)
        subprocess.run([str(venv_pip), "install", "-r", "requirements.txt"], check=True, cwd=REPO_ROOT)
        subprocess.run([str(venv_pip), "install", "-r", "requirements-dev.txt"], check=True, cwd=REPO_ROOT)
    else:
        # No prebuilt wheel for this platform (e.g. the Pi's cp313/aarch64);
        # install pandas via the system package manager and build the venv
        # with --system-site-packages so pip doesn't try (and fail/hang) to
        # compile it from source.
        subprocess.run(_system_pandas_install_command(), check=True)
        subprocess.run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(VENV_DIR)],
            check=True,
            cwd=REPO_ROOT,
        )
        subprocess.run([str(venv_pip), "install", "--upgrade", "pip"], check=True, cwd=REPO_ROOT)
        with open(REPO_ROOT / "requirements.txt") as f:
            stripped = "".join(line for line in f if not line.startswith("pandas"))
        subprocess.run(
            [str(venv_pip), "install", "-r", "/dev/stdin"],
            input=stripped,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        subprocess.run([str(venv_pip), "install", "-r", "requirements-dev.txt"], check=True, cwd=REPO_ROOT)

    subprocess.run([sys.executable, "setup_env.py"], check=True, cwd=REPO_ROOT)

    # Every other subcommand relies on sys.executable already being the
    # venv's python -- print the exact correct next command rather than
    # assuming the user knows to invoke tasks.py via .venv's interpreter
    # (or has activated the venv) instead of a bare `python`/`python3` on
    # PATH, which would silently hit the system interpreter and fail with
    # missing-dependency errors. `make run-silent`/`make run-live` already
    # get this right automatically; this message matters most for Windows
    # users, who don't have `make` to shield them from the distinction.
    print(
        f"\nSetup complete. Start PRISM with:\n"
        f"  {venv_python} tasks.py run --mode silent\n"
        f"or, once ready for a real run:\n"
        f"  {venv_python} tasks.py run --mode live\n"
        f"\nNote: this only sets up the code. If the `environment` file (a "
        f"git-ignored file at the repo root containing \"dev\" or \"prod\") "
        f"is missing, PRISM defaults to \"dev\" and expects the research "
        f"drive already mounted with dev credentials in place -- see "
        f"config/README.md."
    )


def cmd_run(args):
    """Stop any running server, then start run_prism.py in the given mode."""
    # check=False: stop_server.py now exits nonzero when it can't find a
    # precise PID to target and refuses to kill-by-pattern instead of
    # blindly doing so (see its own module docstring) -- that's a real,
    # human-actionable warning printed to stdout, not a reason to abort
    # the subsequent start.
    subprocess.run([sys.executable, "stop_server.py"], check=False, cwd=REPO_ROOT)
    try:
        subprocess.run(
            [sys.executable, "run_prism.py", "-mode", args.mode], cwd=REPO_ROOT / "src", check=True
        )
    except KeyboardInterrupt:
        print("\nPRISM server stopped.")


def cmd_interface(args):
    """Launch the RA terminal interface (src/prism_interface.py)."""
    try:
        subprocess.run([sys.executable, "prism_interface.py"], cwd=REPO_ROOT / "src", check=True)
    except KeyboardInterrupt:
        print("\nInterface closed.")


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
            cwd=REPO_ROOT,
        )


def cmd_typecheck(args):
    """Run mypy over src/ (see mypy.ini; gradual/non-strict, src/ only --
    tests/, tests_interface/, tests_integration/ are out of scope)."""
    subprocess.run([sys.executable, "-m", "mypy", "src"], check=True, cwd=REPO_ROOT)


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
        choices=["silent", "live"],
        required=True,
        help="Mode to run PRISM in. 'silent' does not send real texts. 'live' does. "
        "No default: never boot -mode live casually.",
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

    p_typecheck = subparsers.add_parser(
        "typecheck",
        help="Run mypy over src/ (run with the venv python).",
    )
    p_typecheck.set_defaults(func=cmd_typecheck)

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
