"""Integration test: PulldownQualtricsData.run() against the real Qualtrics
API, using real dev credentials loaded the same way the app itself loads
them (see tests_integration/README.md). Skips if those credentials aren't
actually configured in this environment.
"""

from system_tasks._pulldown_qualtrics_data import PulldownQualtricsData

from conftest import require_real_credentials


def test_run_pulls_down_and_processes_real_qualtrics_data(real_app):
    require_real_credentials(
        real_app,
        'qualtrics_api_token', 'qualtrics_data_center',
        'ema_survey_id', 'feedback_survey_id',
    )

    result = PulldownQualtricsData(real_app).run()

    assert result == 0, (
        "PulldownQualtricsData.run() failed against the real dev Qualtrics "
        f"survey -- see the test transcript under {real_app.logs_dir}/transcripts/test_transcript.txt"
    )
