import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / 'src'
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest

QUALTRICS_API = (
    '"api_token","datacenter","ema_survey_id","feedback_survey_id",'
    '"ema_message","ema_reminder_message","feedback_message","feedback_reminder_message"\n'
    '"fake_qualtrics_token","fake_dc","fake_ema_survey","fake_feedback_survey",'
    '"ema msg","ema reminder msg","feedback msg","feedback reminder msg"\n'
)
FOLLOWMEE_API = '"username","api_token"\n"fake_followmee_user","fake_followmee_token"\n'
TWILIO_API = '"account_sid","auth_token","from_number"\n"fake_sid","fake_token","+15555550100"\n'
RESEARCH_DRIVE_API = (
    '"destination_path","drive_letter","network_domain","network_username","wisc_netid","wisc_password"\n'
    '"fake_dest","Z","fake_domain","fake_netuser","fake_netid","fake_password"\n'
)
NGROK_API = '"auth_token","domain"\n"fake_ngrok_token","fake_ngrok_domain"\n'

STUDY_COORDINATORS_CSV = '"name","phone_number"\n"Test Coordinator","5555550100"\n'
SYSTEM_TASK_SCHEDULE_CSV = '"task_type","task_time","r_script_path","run_today"\n"CHECK_SYSTEM","03:00:00","","no"\n'
SCRIPT_PIPELINE_CSV = '"script_path","arguments","enabled"\n'
FOLLOWMEE_COORDS_CSV = (
    'DeviceName,DeviceID,Date,Latitude,Longitude,Type,Speed(mph),Speed(km/h),'
    'Direction,Altitude(ft),Altitude(m),Accuracy,Battery\n'
)
STUDY_PARTICIPANTS_CSV = (
    'initials,subid,unique_id,on_study,phone_number,ema_time,ema_reminder_time,'
    'feedback_time,feedback_reminder_time\n'
    'JD,3000,000000000,yes,5555550100,09:00:00,10:00:00,19:00:00,20:00:00\n'
)
REMINDERS_CSV = 'subid,unique_id,on_study,remind_ema,remind_feedback\n'


@pytest.fixture
def fake_prism_env(tmp_path):
    """Builds a fake repo checkout + fake research drive, both fully offline,
    matching the real config_base/paths.csv/environment-marker layout
    (config/README.md), and returns the fake repo_root for tests to point a
    PRISM instance at via `p.repo_root = fake_prism_env`.
    """
    repo_root = tmp_path / 'repo'
    drive_root = tmp_path / 'drive'

    (repo_root / 'config').mkdir(parents=True)
    (repo_root / 'config' / 'repo_paths.csv').write_text(
        '"key","value"\n'
        '"logs_dir","logs"\n'
        '"drive_mount_windows","S:"\n'
        f'"drive_mount_posix","{drive_root}"\n'
        '"prism_drive_subpath","optimize/prism"\n'
    )
    (repo_root / 'environment').write_text('dev')

    config_base = drive_root / 'optimize' / 'prism' / 'dev'
    (config_base / 'api').mkdir(parents=True)
    (config_base / 'config').mkdir(parents=True)
    (config_base / 'config' / 'paths.csv').write_text(
        '"key","path"\n'
        '"config_base","S:/optimize/prism/dev/"\n'
        '"participants","S:/optimize/data_raw/participants/dev_study_participants.csv"\n'
        '"reminders","S:/optimize/data_raw/participants/dev_reminders.csv"\n'
        '"scripts","../../proj_optimize/dev_automation/"\n'
    )
    (config_base / 'api' / 'qualtrics.api').write_text(QUALTRICS_API)
    (config_base / 'api' / 'followmee.api').write_text(FOLLOWMEE_API)
    (config_base / 'api' / 'twilio.api').write_text(TWILIO_API)
    (config_base / 'api' / 'research_drive.api').write_text(RESEARCH_DRIVE_API)
    (config_base / 'api' / 'ngrok.api').write_text(NGROK_API)
    (config_base / 'config' / 'study_coordinators.csv').write_text(STUDY_COORDINATORS_CSV)
    (config_base / 'config' / 'system_task_schedule.csv').write_text(SYSTEM_TASK_SCHEDULE_CSV)
    (config_base / 'config' / 'script_pipeline.csv').write_text(SCRIPT_PIPELINE_CSV)
    (config_base / 'config' / 'followmee_coords.csv').write_text(FOLLOWMEE_COORDS_CSV)

    participants_dir = drive_root / 'optimize' / 'data_raw' / 'participants'
    participants_dir.mkdir(parents=True)
    (participants_dir / 'dev_study_participants.csv').write_text(STUDY_PARTICIPANTS_CSV)
    (participants_dir / 'dev_reminders.csv').write_text(REMINDERS_CSV)

    (drive_root / 'optimize' / 'proj_optimize' / 'dev_automation').mkdir(parents=True)

    return repo_root


@pytest.fixture
def prism_instance(fake_prism_env):
    """A PRISM instance with __init__ bypassed (no signal handlers, no web
    server launch), pointed at fake_prism_env. Call .load_paths()/
    .load_api_keys() explicitly in the test.
    """
    from run_prism import PRISM

    p = PRISM.__new__(PRISM)
    p.mode = 'test'
    p.repo_root = fake_prism_env
    return p


class FakeApp:
    """A lightweight stand-in for the PRISM app instance, for testing
    task_managers/ and system_tasks/ without going through the real
    config-loading machinery. Records every add_to_transcript call (message,
    message_type) in .transcript for assertions, and every attribute a real
    PRISM instance would set is a plain settable attribute here — tests set
    only what the code path under test actually reads.
    """
    def __init__(self, mode='test'):
        self.mode = mode
        self.transcript = []

    def add_to_transcript(self, message, message_type='INFO'):
        self.transcript.append((message_type, message))


@pytest.fixture
def fake_app():
    return FakeApp()
