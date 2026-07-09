import queue

from task_managers._participant_manager import ParticipantManager


def make_manager(fake_app):
    """ParticipantManager with __init__ bypassed (no background thread, no
    load_participants() at construction) — tests set .participants/.tasks
    directly, or call load_participants() explicitly where that's the thing
    under test."""
    pm = ParticipantManager.__new__(ParticipantManager)
    pm.app = fake_app
    pm.name = 'ParticipantManager'
    pm.tasks = []
    pm.task_queue = queue.Queue()
    pm.participants = []
    pm.survey_types = {
        'ema': 'ema_time',
        'ema_reminder': 'ema_reminder_time',
        'feedback': 'feedback_time',
        'feedback_reminder': 'feedback_reminder_time',
    }
    return pm


# Matches the real study_participants.csv schema (verified against the
# actual file on the research drive, see config/README.md):
# initials,subid,unique_id,on_study,phone_number,ema_time,ema_reminder_time,
# feedback_time,feedback_reminder_time
PARTICIPANT = {
    'initials': 'JD',
    'subid': '3000',
    'unique_id': '000000000',
    'on_study': True,
    'phone_number': '5555550100',
    'ema_time': '09:00:00',
    'ema_reminder_time': '10:00:00',
    'feedback_time': '19:00:00',
    'feedback_reminder_time': '20:00:00',
}


def test_schedule_participant_tasks_adds_one_task_per_survey_type(fake_app):
    pm = make_manager(fake_app)

    pm.schedule_participant_tasks(PARTICIPANT)

    task_types = {t['task_type'] for t in pm.tasks}
    assert task_types == {'ema', 'ema_reminder', 'feedback', 'feedback_reminder'}
    assert all(t['participant_id'] == '000000000' for t in pm.tasks)


def test_schedule_participant_tasks_skips_survey_types_with_no_time_set(fake_app):
    pm = make_manager(fake_app)
    participant = dict(PARTICIPANT, feedback_time=None, feedback_reminder_time=None)

    pm.schedule_participant_tasks(participant)

    task_types = {t['task_type'] for t in pm.tasks}
    assert task_types == {'ema', 'ema_reminder'}


def test_get_participant_found(fake_app):
    pm = make_manager(fake_app)
    pm.participants = [PARTICIPANT]

    result = pm.get_participant('000000000')

    assert result == PARTICIPANT


def test_get_participant_not_found_logs_error(fake_app):
    pm = make_manager(fake_app)
    pm.participants = []

    result = pm.get_participant('000000000')

    assert result is None
    assert any('not found' in msg for _, msg in fake_app.transcript)


def test_get_participants_projects_only_summary_fields(fake_app):
    pm = make_manager(fake_app)
    pm.participants = [PARTICIPANT]

    result = pm.get_participants()

    assert result == [{
        'unique_id': '000000000',
        'subid': '3000',
        'initials': 'JD',
        'on_study': True,
    }]


def test_remove_task_removes_matching_participant_task(fake_app):
    pm = make_manager(fake_app)
    pm.tasks = [{'task_type': 'ema', 'participant_id': '000000000'}]

    result = pm.remove_task('ema', participant_id='000000000')

    assert result == 0
    assert pm.tasks == []


def test_remove_task_not_found_returns_1(fake_app):
    pm = make_manager(fake_app)
    pm.tasks = []

    result = pm.remove_task('ema', participant_id='000000000')

    assert result == 1


def test_remove_participant_removes_participant_and_all_their_tasks(fake_app):
    pm = make_manager(fake_app)
    pm.participants = [PARTICIPANT]
    pm.tasks = [
        {'task_type': 'ema', 'participant_id': '000000000'},
        {'task_type': 'feedback', 'participant_id': '000000000'},
    ]
    pm.save_participants = lambda: None  # avoid touching the filesystem

    result = pm.remove_participant('000000000')

    assert result == 0
    assert pm.participants == []
    assert pm.tasks == []


def test_get_task_schedule_sorts_by_participant_then_time(fake_app):
    from datetime import time
    pm = make_manager(fake_app)
    pm.participants = [PARTICIPANT]
    pm.tasks = [
        {'task_type': 'feedback', 'task_time': time(19, 0, 0), 'participant_id': '000000000'},
        {'task_type': 'ema', 'task_time': time(9, 0, 0), 'participant_id': '000000000'},
    ]

    result = pm.get_task_schedule()

    assert [r['task_type'] for r in result] == ['ema', 'feedback']
    assert result[0]['on_study'] is True


def test_update_participant_unknown_field_returns_1(fake_app):
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]

    result = pm.update_participant('000000000', 'not_a_real_field', 'value')

    assert result == 1
    assert any('does not exist' in msg for _, msg in fake_app.transcript)


def test_update_participant_unknown_id_returns_1(fake_app):
    pm = make_manager(fake_app)
    pm.participants = []

    result = pm.update_participant('000000000', 'phone_number', '5555550199')

    assert result == 1


def test_update_participant_updates_field_and_reschedules_task(fake_app):
    pm = make_manager(fake_app)
    participant = dict(PARTICIPANT)
    pm.participants = [participant]
    pm.tasks = [{'task_type': 'ema', 'participant_id': '000000000'}]
    pm.save_participants = lambda: None  # avoid touching the filesystem

    result = pm.update_participant('000000000', 'ema_time', '08:00:00')

    assert result == 0
    assert participant['ema_time'] == '08:00:00'
    task_types = [t['task_type'] for t in pm.tasks]
    assert task_types.count('ema') == 1  # old one removed, new one added, no duplicate


# --- Previously-documented bugs, now fixed -------------------------------
#
# load_participants() used to parse each CSV row assuming
# first_name,last_name,unique_id,... and check on_study == 'true'. Fixed to
# match the real study_participants.csv schema (verified against the actual
# file on the research drive, see config/README.md):
# initials,subid,unique_id,on_study(yes/no),phone_number,...

def test_load_participants_matches_real_csv_schema(tmp_path, fake_app):
    csv_file = tmp_path / 'study_participants.csv'
    csv_file.write_text(
        'initials,subid,unique_id,on_study,phone_number,ema_time,'
        'ema_reminder_time,feedback_time,feedback_reminder_time\n'
        'JD,3000,000000000,yes,5555550100,09:00:00,10:00:00,19:00:00,20:00:00\n'
    )
    fake_app.participants_path = str(csv_file)
    pm = make_manager(fake_app)
    pm.file_path = str(csv_file)

    pm.load_participants()

    participant = pm.participants[0]
    assert participant['initials'] == 'JD'
    assert participant['subid'] == '3000'
    assert participant['unique_id'] == '000000000'


def test_load_participants_on_study_parses_yes_no(tmp_path, fake_app):
    csv_file = tmp_path / 'study_participants.csv'
    csv_file.write_text(
        'initials,subid,unique_id,on_study,phone_number,ema_time,'
        'ema_reminder_time,feedback_time,feedback_reminder_time\n'
        'JD,3000,000000000,yes,5555550100,09:00:00,10:00:00,19:00:00,20:00:00\n'
        'AB,3001,000000001,no,5555550101,09:00:00,10:00:00,19:00:00,20:00:00\n'
    )
    fake_app.participants_path = str(csv_file)
    pm = make_manager(fake_app)
    pm.file_path = str(csv_file)

    pm.load_participants()

    assert pm.participants[0]['on_study'] is True
    assert pm.participants[1]['on_study'] is False


def test_save_participants_round_trips_through_load(tmp_path, fake_app):
    csv_file = tmp_path / 'study_participants.csv'
    fake_app.participants_path = str(csv_file)
    pm = make_manager(fake_app)
    pm.file_path = str(csv_file)
    pm.participants = [dict(PARTICIPANT)]

    pm.save_participants()
    pm.load_participants()

    assert pm.participants[0]['initials'] == 'JD'
    assert pm.participants[0]['subid'] == '3000'
    assert pm.participants[0]['on_study'] is True
