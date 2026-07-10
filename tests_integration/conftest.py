"""Shared fixtures for tests_integration/.

These fixtures build a real PRISM app instance the same way run_prism.py
does -- against the real, git-ignored `environment` marker file and the
real drive-sourced config_base (see config/README.md) -- instead of the
fully-offline fake_prism_env fixture that tests/conftest.py uses. See
tests_integration/README.md for what this directory is and how to run it.
"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

# PLACEHOLDER_PREFIX/_is_real_value live in src/_helper.py so both app
# runtime code and tests_integration/ (this file, test_environment_files.py)
# agree on what counts as "still a template placeholder" -- re-exported here
# under their old names so existing imports (`from conftest import
# require_real_credentials`, and any direct `_is_real_value` usage) keep
# working unchanged.
from _helper import PLACEHOLDER_PREFIX, _is_real_value  # noqa: F401


@pytest.fixture
def real_app():
    """A PRISM instance with __init__ bypassed (no signal handlers, no web
    server launch, no clear()), loaded against the real repo checkout's
    real `environment` marker + real drive-sourced config_base -- exactly
    what run_prism.py itself would load. mode='test' so add_to_transcript
    writes to the local test transcript, not a dated prod one, and so
    SystemTask.execute() (not used directly by these tests, which call
    .run() instead) wouldn't fire coordinator SMS even if it were.

    No chdir needed: the task classes under test (PulldownQualtricsData,
    PulldownFollowmeeData) resolve their output paths via `self.app.data_dir`
    (repo-root-relative, set in run_prism.py::load_paths() the same way as
    logs_dir -- see config/repo_paths.csv's `data_dir` key), not a
    cwd-relative "../data/..." literal. This fixture used to chdir into
    src/ before 2026-07-10's move away from those hardcoded relative paths.
    """
    from run_prism import PRISM

    app = PRISM.__new__(PRISM)
    app.mode = 'test'
    app.load_paths()
    app.load_api_keys()
    return app


def require_real_credentials(app, *attrs):
    """Skip the calling test if any of the given attributes on `app` is
    missing or still holds a "REPLACE_WITH_..." placeholder value -- i.e.
    real dev credentials for this integration path aren't actually
    configured in this environment. This is the graceful-skip path these
    tests are required to take instead of failing when run somewhere
    without real dev credentials on the mounted research drive.
    """
    missing = [attr for attr in attrs if not _is_real_value(getattr(app, attr, None))]
    if missing:
        pytest.skip(
            "dev credentials not available: "
            f"{', '.join(missing)} missing or still a placeholder value "
            "in the drive-sourced .api file(s) -- see config/README.md"
        )
