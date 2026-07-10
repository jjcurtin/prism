"""Integration test: PushDataToResearchDrive.run() against the real,
already-mounted research drive, using the real dev destination_path loaded
the same way the app itself loads it (see tests_integration/README.md).
Skips if that isn't actually configured/mounted in this environment.

Note this actually mirrors ../data into the real dev destination on the
research drive (robocopy /MIR on Windows, rsync -a --delete on Linux) --
that's the whole point of exercising it end-to-end, but it means this test
is only as safe to run as the dev destination_path itself is.
"""

import os

import pytest

from system_tasks._push_data_to_research_drive import PushDataToResearchDrive

from conftest import require_real_credentials


def test_run_mirrors_data_to_the_real_research_drive(real_app):
    require_real_credentials(real_app, 'destination_path')

    drive_mount = getattr(real_app, 'drive_mount', None)
    if not drive_mount or not (os.path.ismount(drive_mount) or os.path.isdir(drive_mount)):
        pytest.skip(f"dev credentials not available: research drive not mounted at {drive_mount}")

    result = PushDataToResearchDrive(real_app).run()

    assert result == 0, (
        "PushDataToResearchDrive.run() failed pushing to the real dev research "
        f"drive -- see the test transcript under {real_app.logs_dir}/transcripts/test_transcript.txt"
    )
