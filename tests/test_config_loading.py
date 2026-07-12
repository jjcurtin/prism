from pathlib import Path


def test_load_paths_resolves_everything_under_the_fake_drive(prism_instance, fake_prism_env):
    prism_instance.load_paths()

    drive_config_base = Path(prism_instance.config_base)
    assert drive_config_base.name == 'dev'
    assert drive_config_base.is_dir()

    assert prism_instance.environment == 'dev'
    assert prism_instance.logs_dir == str((fake_prism_env / 'logs').resolve())
    assert prism_instance.data_dir == str((fake_prism_env / 'data').resolve())
    assert Path(prism_instance.participants_path).name == 'dev_study_participants.csv'
    assert Path(prism_instance.reminders_path).name == 'dev_reminders.csv'
    # r_scripts_dir ('scripts' key in the drive's paths.csv) resolves
    # locally against the repo checkout, NOT against config_base/the drive
    # -- unlike participants_path/reminders_path above.
    assert prism_instance.r_scripts_dir == str((fake_prism_env / '..' / 'automation_scripts').resolve())
    assert Path(prism_instance.r_scripts_dir).is_dir()
    assert Path(prism_instance.system_task_schedule_path) == drive_config_base / 'config' / 'system_task_schedule.csv'
    assert Path(prism_instance.study_coordinators_path) == drive_config_base / 'config' / 'study_coordinators.csv'


def test_load_paths_corrupt_repo_paths_csv_falls_back_and_warns(prism_instance, fake_prism_env):
    """Regression test for a real bug (external adversarial review,
    confirmed by inspection): a corrupted/unreadable repo_paths.csv used to
    fall back to every default (logs_dir 'logs', drive mounts, etc.)
    completely silently -- a bare `except Exception: repo_paths = {}` with
    no transcript line at all, unlike the paths.csv load just below it,
    which already logs an ERROR on failure.
    """
    (fake_prism_env / 'config' / 'repo_paths.csv').write_text('not,valid\ncsv"""data')

    prism_instance.load_paths()  # must not raise

    assert prism_instance.logs_dir == str((fake_prism_env / 'logs').resolve())  # still falls back correctly
    transcript_text = (Path(prism_instance.logs_dir) / 'transcripts' / 'silent_transcript.txt').read_text()
    assert 'WARNING' in transcript_text
    assert 'Failed to load repo_paths.csv' in transcript_text


def test_load_paths_scripts_dir_not_resolved_relative_to_config_base(prism_instance, fake_prism_env):
    """r_scripts_dir is still configured per-environment via the drive's
    paths.csv 'scripts' key (it's not a prism-specific folder, so it can't
    just be a fixed repo-relative default the way logs_dir/data_dir are),
    but unlike participants_path/reminders_path, its value must resolve
    against the local repo checkout, not against config_base -- regression
    test for accidentally routing it back through the drive-relative branch.
    """
    prism_instance.load_paths()

    config_base = Path(prism_instance.config_base)
    r_scripts_dir = Path(prism_instance.r_scripts_dir)
    assert config_base not in r_scripts_dir.parents
    assert r_scripts_dir == (fake_prism_env / '..' / 'automation_scripts').resolve()


def test_load_paths_defaults_to_dev_when_environment_file_missing(prism_instance, fake_prism_env):
    (fake_prism_env / 'environment').unlink()

    prism_instance.load_paths()

    assert prism_instance.environment == 'dev'


def test_load_paths_creates_environment_file_when_missing(prism_instance, fake_prism_env):
    env_file = fake_prism_env / 'environment'
    env_file.unlink()

    prism_instance.load_paths()

    assert env_file.exists()
    assert env_file.read_text() == 'dev'


def test_load_paths_does_not_overwrite_existing_environment_file(prism_instance, fake_prism_env):
    env_file = fake_prism_env / 'environment'
    env_file.write_text('prod')

    prism_instance.load_paths()

    assert prism_instance.environment == 'prod'
    assert env_file.read_text() == 'prod'


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

    assert prism_instance.ema_survey_id == 'fake_ema_survey'
    assert prism_instance.feedback_survey_id == 'fake_feedback_survey'
    assert prism_instance.ema_message == 'ema msg'
    assert prism_instance.ema_reminder_message == 'ema reminder msg'
    assert prism_instance.feedback_message == 'feedback msg'
    assert prism_instance.feedback_reminder_message == 'feedback reminder msg'


def test_load_api_keys_reads_all_other_api_files(prism_instance):
    prism_instance.load_paths()
    prism_instance.load_api_keys()

    assert prism_instance.twilio_account_sid == 'fake_sid'
    assert prism_instance.twilio_auth_token == 'fake_token'
    assert prism_instance.twilio_from_number == '+15555550100'
    assert prism_instance.coordinator_alert_message == 'fake coordinator alert msg'


def test_load_api_keys_falls_back_to_message_defaults_when_columns_missing(prism_instance):
    prism_instance.load_paths()
    old_style_qualtrics = (
        '"ema_survey_id","feedback_survey_id"\n'
        '"fake_ema_survey","fake_feedback_survey"\n'
    )
    Path(prism_instance.config_base, 'api', 'qualtrics.api').write_text(old_style_qualtrics)
    old_style_twilio = (
        '"account_sid","auth_token","from_number"\n'
        '"fake_sid","fake_token","+15555550100"\n'
    )
    Path(prism_instance.config_base, 'api', 'twilio.api').write_text(old_style_twilio)

    prism_instance.load_api_keys()

    assert prism_instance.ema_survey_id == 'fake_ema_survey'
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
    assert prism_instance.ema_survey_id == 'fake_ema_survey'


def test_load_api_keys_header_only_file_does_not_crash(prism_instance):
    """Regression test for a real bug (external adversarial review,
    confirmed live via a direct pandas repro): pd.read_csv on a header-only
    CSV (columns but zero data rows) succeeds and returns an empty
    DataFrame -- df.loc[0, column] then raises KeyError: 0, uncaught (only
    the pd.read_csv call itself was inside load_keys's try), crashing
    PRISM.__init__ and the whole server at startup. Must degrade to the
    same WARNING path as a missing column instead.
    """
    prism_instance.load_paths()
    header_only_twilio = '"account_sid","auth_token","from_number"\n'
    Path(prism_instance.config_base, 'api', 'twilio.api').write_text(header_only_twilio)

    prism_instance.load_api_keys()  # must not raise

    assert not hasattr(prism_instance, 'twilio_account_sid')
    assert prism_instance.ema_survey_id == 'fake_ema_survey'
