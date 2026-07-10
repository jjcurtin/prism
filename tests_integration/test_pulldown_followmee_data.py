"""Integration test: PulldownFollowmeeData.run() against the real FollowMee
API, using real dev credentials loaded the same way the app itself loads
them (see tests_integration/README.md). Skips if those credentials aren't
actually configured in this environment.
"""

from system_tasks._pulldown_followmee_data import PulldownFollowmeeData

from conftest import require_real_credentials


def test_run_pulls_down_and_processes_real_followmee_data(real_app):
    require_real_credentials(real_app, 'followmee_username', 'followmee_api_token')

    result = PulldownFollowmeeData(real_app).run()

    assert result == 0, (
        "PulldownFollowmeeData.run() failed against the real dev FollowMee "
        f"account -- see the test transcript under {real_app.logs_dir}/transcripts/test_transcript.txt"
    )
