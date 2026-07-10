"""Integration test: for EACH of PRISM's two environments ("dev"/"prod"),
confirms that if that environment is actually set up on this machine's
mounted research drive, every file `run_prism.py::load_paths()`/
`load_api_keys()` expect under its `config_base` really exists, and that the
drive-sourced credential/config files are populated beyond their checked-in
templates (not still `REPLACE_WITH_...` placeholders or empty CSVs with only
a header row).

Like every other file in tests_integration/, this is safe to run on any
machine: if the research drive isn't mounted, or a given environment was
never set up on it, the test skips (not fails) -- see
tests_integration/README.md. It only *fails* once an environment is
confirmed to exist but something required under it is missing or still a
template placeholder, which is a real, actionable problem.

Unlike the other tests_integration/ files, this one deliberately does not
use the `real_app` fixture, because that fixture always loads whichever
environment the real `environment` marker file at the repo root currently
points to. This test needs to independently check *both* "dev" and "prod"
regardless of that marker -- `load_paths()` grew an optional `environment`
param (run_prism.py) specifically so callers like this one can pick an
environment explicitly instead of going through the marker file.
"""

import csv
import os
from pathlib import Path

import pytest

from run_prism import PRISM
from _helper import _is_real_value

ENVIRONMENTS = ["dev", "prod"]

# Mirrors the attr keys (not the drive-side column names -- those are
# load_api_keys()'s concern, not this test's) that run_prism.py::
# load_api_keys() populates from each .api file's field_map. Deliberately
# excludes the message-text fields (ema_message, feedback_message,
# coordinator_alert_message, etc.) -- those fall back to sane hardcoded
# defaults in API_FIELD_DEFAULTS when the column is absent, so "still equal
# to the default" isn't a meaningful signal of an unfilled template the way
# a REPLACE_WITH_-prefixed credential is. Keep in sync with
# run_prism.py::load_api_keys() if its field_maps change.
REQUIRED_API_FIELDS = {
    'qualtrics.api': ['ema_survey_id', 'feedback_survey_id'],
    'twilio.api': ['twilio_account_sid', 'twilio_auth_token', 'twilio_from_number'],
}

CSV_MUST_HAVE_DATA_ROWS = [
    'config/system_task_schedule.csv',
    'config/study_coordinators.csv',
]


def _load_app_for_environment(environment):
    """A PRISM instance with __init__ bypassed, loaded against the real repo
    checkout's real drive-sourced config -- exactly what real_app in
    conftest.py does, except it forces a specific environment rather than
    reading whichever one the repo's `environment` marker file currently
    points to, so this test can check "dev" and "prod" independently in the
    same run.
    """
    app = PRISM.__new__(PRISM)
    app.mode = 'test'
    app.load_paths(environment=environment)
    return app


def _required_files(app):
    config_base = Path(app.config_base)
    api_dir = config_base / 'api'
    config_dir = config_base / 'config'
    return {
        'config/paths.csv': config_dir / 'paths.csv',
        'api/qualtrics.api': api_dir / 'qualtrics.api',
        'api/twilio.api': api_dir / 'twilio.api',
        'config/system_task_schedule.csv': config_dir / 'system_task_schedule.csv',
        'config/study_coordinators.csv': config_dir / 'study_coordinators.csv',
    }


def _csv_has_data_rows(path):
    with open(path, newline='') as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if any(cell.strip() for cell in row):
                return True
    return False


@pytest.mark.parametrize('environment', ENVIRONMENTS)
def test_environment_files_exist_and_are_populated(environment):
    app = _load_app_for_environment(environment)

    # Graceful skip #1: the research drive itself isn't mounted on this
    # machine at all -- mirrors CheckSystem.check_research_drive()'s
    # ismount-or-isdir check, including its try/except: a *stale* mount
    # (present in e.g. /etc/fstab but the remote host is currently
    # unreachable -- VPN not connected, etc.) doesn't cleanly return False
    # from is_dir(), it raises OSError (observed: "[Errno 112] Host is
    # down"), which check_research_drive() already treats as "not
    # connected" rather than letting it propagate. This test previously
    # lacked that try/except and would fail with an unhandled OSError
    # instead of skipping in exactly the situation it's meant to skip for.
    drive_mount = Path(app.drive_mount)
    try:
        reachable = os.path.ismount(str(drive_mount)) or drive_mount.is_dir()
    except OSError as e:
        reachable = False
        skip_reason_suffix = f" ({e})"
    else:
        skip_reason_suffix = ""
    if not reachable:
        pytest.skip(
            f"research drive not mounted at {drive_mount} on this machine{skip_reason_suffix} -- "
            f"skipping {environment} environment file checks"
        )

    # Graceful skip #2: the drive is mounted, but this particular
    # environment was never set up under it (e.g. a dev-only machine with no
    # S:/optimize/prism/prod/ tree).
    config_base = Path(app.config_base)
    if not config_base.is_dir():
        pytest.skip(
            f"{environment} environment not set up on this machine's drive "
            f"(config_base {config_base} does not exist)"
        )

    app.load_api_keys()

    # 1. Every required file must exist.
    required_files = _required_files(app)
    missing = [label for label, path in required_files.items() if not path.is_file()]

    for attr, label in [
        ('participants_path', "participants file (paths.csv 'participants' key)"),
        ('reminders_path', "reminders file (paths.csv 'reminders' key)"),
    ]:
        path = getattr(app, attr, None)
        if not path:
            missing.append(f"{label} -- not resolved (paths.csv missing the key, or paths.csv failed to load)")
        elif not Path(path).is_file():
            missing.append(f"{label} -- resolved to {path}, which does not exist")

    assert not missing, (
        f"{environment} environment (config_base={config_base}) is missing required files:\n  "
        + "\n  ".join(missing)
    )

    # 2. The three .api files' real fields must be populated beyond the
    # checked-in template placeholder.
    placeholder_fields = []
    for file_name, attrs in REQUIRED_API_FIELDS.items():
        for attr in attrs:
            if not _is_real_value(getattr(app, attr, None)):
                placeholder_fields.append(f"{file_name}: {attr}")

    assert not placeholder_fields, (
        f"{environment} environment (config_base={config_base}) has fields still set to a template "
        f"placeholder value (REPLACE_WITH_...) or empty:\n  " + "\n  ".join(placeholder_fields)
    )

    # 3. The CSVs must contain at least one data row beyond the header.
    csv_files_to_check = {label: required_files[label] for label in CSV_MUST_HAVE_DATA_ROWS}
    if getattr(app, 'participants_path', None):
        csv_files_to_check['study_participants.csv'] = Path(app.participants_path)
    if getattr(app, 'reminders_path', None):
        csv_files_to_check['reminders.csv'] = Path(app.reminders_path)

    empty_csvs = [label for label, path in csv_files_to_check.items() if not _csv_has_data_rows(path)]

    assert not empty_csvs, (
        f"{environment} environment (config_base={config_base}) has CSVs with no data rows beyond "
        f"the header -- still just a template:\n  " + "\n  ".join(empty_csvs)
    )

    # 4. r_scripts_dir (paths.csv 'scripts' key) must resolve to a real,
    # existing directory. Unlike the files checked above, this isn't read
    # at startup -- only when a RUN_R_SCRIPT task actually fires
    # (_run_r_script.py checks os.path.exists() itself and fails gracefully
    # rather than crashing PRISM) -- so a broken scripts path wouldn't
    # otherwise surface until the first scheduled R script silently fails.
    # Resolution is relative to config_base, not the process's cwd (see
    # run_prism.py::load_paths()), so this is stable regardless of how/from
    # where PRISM was launched.
    r_scripts_dir = getattr(app, 'r_scripts_dir', None)
    assert r_scripts_dir and Path(r_scripts_dir).is_dir(), (
        f"{environment} environment (config_base={config_base}) has an r_scripts_dir "
        f"that doesn't resolve to a real directory (paths.csv 'scripts' key) -- "
        f"resolved to: {r_scripts_dir!r}"
    )
