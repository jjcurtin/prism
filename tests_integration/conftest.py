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

# Placeholder marker used in the checked-in-nowhere, drive-sourced .api
# template files (e.g. "REPLACE_WITH_QUALTRICS_API_TOKEN") -- a value still
# carrying this prefix means the credential was never actually filled in,
# not that it's missing outright.
PLACEHOLDER_PREFIX = "REPLACE_WITH_"


def _is_real_value(value):
    if value is None:
        return False
    value = str(value).strip()
    if not value:
        return False
    if value.startswith(PLACEHOLDER_PREFIX):
        return False
    return True


@pytest.fixture
def real_app(monkeypatch):
    """A PRISM instance with __init__ bypassed (no signal handlers, no web
    server launch, no clear()), loaded against the real repo checkout's
    real `environment` marker + real drive-sourced config_base -- exactly
    what run_prism.py itself would load. mode='test' so add_to_transcript
    writes to the local test transcript, not a dated prod one, and so
    SystemTask.execute() (not used directly by these tests, which call
    .run() instead) wouldn't fire coordinator SMS even if it were.

    Also chdir's into src/ for the duration of the test, since the task
    classes under test (PulldownQualtricsData, PulldownFollowmeeData,
    PushDataToResearchDrive) resolve their output paths as "../data/..."
    relative to a cwd of src/, matching how they run in the real app.
    """
    from run_prism import PRISM

    monkeypatch.chdir(SRC_DIR)

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
