from pathlib import Path


def test_load_paths_resolves_everything_under_the_fake_drive(prism_instance, fake_prism_env):
    prism_instance.load_paths()

    drive_config_base = Path(prism_instance.config_base)
    assert drive_config_base.name == 'dev'
    assert drive_config_base.is_dir()

    assert prism_instance.environment == 'dev'
    assert prism_instance.logs_dir == str((fake_prism_env / 'logs').resolve())
    assert Path(prism_instance.participants_path).name == 'dev_study_participants.csv'
    assert Path(prism_instance.reminders_path).name == 'dev_reminders.csv'
    assert Path(prism_instance.r_scripts_dir).name == 'dev_automation'
    assert Path(prism_instance.r_scripts_dir).is_dir()
    assert Path(prism_instance.followmee_coords_path) == drive_config_base / 'config' / 'followmee_coords.csv'
    assert Path(prism_instance.system_task_schedule_path) == drive_config_base / 'config' / 'system_task_schedule.csv'
    assert Path(prism_instance.study_coordinators_path) == drive_config_base / 'config' / 'study_coordinators.csv'
    assert Path(prism_instance.script_pipeline_path) == drive_config_base / 'config' / 'script_pipeline.csv'


def test_load_paths_defaults_to_dev_when_environment_file_missing(prism_instance, fake_prism_env):
    (fake_prism_env / 'environment').unlink()

    prism_instance.load_paths()

    assert prism_instance.environment == 'dev'


def test_load_paths_respects_prod_environment_marker(prism_instance, fake_prism_env):
    drive_root = fake_prism_env / 'config' / 'repo_paths.csv'
    drive_mount = [
        line.split(',')[1].strip().strip('"')
        for line in drive_root.read_text().splitlines()
        if line.startswith('"drive_mount_posix"')
    ][0]
    prod_base = Path(drive_mount) / 'optimize' / 'prism' / 'prod'
    (prod_base / 'config').mkdir(parents=True)
    (prod_base / 'config' / 'paths.csv').write_text(
        '"key","path"\n'
        '"config_base","S:/optimize/prism/prod/"\n'
    )
    (fake_prism_env / 'environment').write_text('prod')

    prism_instance.load_paths()

    assert prism_instance.environment == 'prod'
    assert Path(prism_instance.config_base).name == 'prod'


def test_load_api_keys_reads_qualtrics_fields(prism_instance):
    prism_instance.load_paths()
    prism_instance.load_api_keys()

    assert prism_instance.qualtrics_api_token == 'fake_qualtrics_token'
    assert prism_instance.qualtrics_data_center == 'fake_dc'
    assert prism_instance.ema_survey_id == 'fake_ema_survey'
    assert prism_instance.feedback_survey_id == 'fake_feedback_survey'
    assert prism_instance.ema_message == 'ema msg'
    assert prism_instance.ema_reminder_message == 'ema reminder msg'
    assert prism_instance.feedback_message == 'feedback msg'
    assert prism_instance.feedback_reminder_message == 'feedback reminder msg'


def test_load_api_keys_reads_all_other_api_files(prism_instance):
    prism_instance.load_paths()
    prism_instance.load_api_keys()

    assert prism_instance.followmee_username == 'fake_followmee_user'
    assert prism_instance.followmee_api_token == 'fake_followmee_token'
    assert prism_instance.twilio_account_sid == 'fake_sid'
    assert prism_instance.twilio_auth_token == 'fake_token'
    assert prism_instance.twilio_from_number == '+15555550100'
    assert prism_instance.coordinator_alert_message == 'fake coordinator alert msg'


def test_load_api_keys_falls_back_to_message_defaults_when_columns_missing(prism_instance):
    prism_instance.load_paths()
    old_style_qualtrics = (
        '"api_token","datacenter","ema_survey_id","feedback_survey_id"\n'
        '"fake_qualtrics_token","fake_dc","fake_ema_survey","fake_feedback_survey"\n'
    )
    Path(prism_instance.config_base, 'api', 'qualtrics.api').write_text(old_style_qualtrics)
    old_style_twilio = (
        '"account_sid","auth_token","from_number"\n'
        '"fake_sid","fake_token","+15555550100"\n'
    )
    Path(prism_instance.config_base, 'api', 'twilio.api').write_text(old_style_twilio)

    prism_instance.load_api_keys()

    assert prism_instance.qualtrics_api_token == 'fake_qualtrics_token'
    assert prism_instance.ema_message == "Hello, it's time to take your daily survey."
    assert prism_instance.feedback_reminder_message == (
        "Hello, you have not yet viewed your daily recovery message for today."
    )
    assert prism_instance.coordinator_alert_message == (
        "{name}: {task_type} #{task_number} {outcome}. Script was executed at {task_start}."
    )


def test_load_api_keys_missing_file_does_not_crash_other_files(prism_instance):
    prism_instance.load_paths()
    Path(prism_instance.config_base, 'api', 'twilio.api').unlink()

    prism_instance.load_api_keys()

    assert not hasattr(prism_instance, 'twilio_account_sid')
    assert prism_instance.qualtrics_api_token == 'fake_qualtrics_token'
