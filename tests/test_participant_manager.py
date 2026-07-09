import queue

import pytest

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


PARTICIPANT = {
    'first_name': 'Jane',
    'last_name': 'Doe',
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
        'last_name': 'Doe',
        'first_name': 'Jane',
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


# --- Known pre-existing bugs, documented via xfail (not fixed here) -------
#
# load_participants() parses each CSV row positionally assuming
# first_name,last_name,unique_id,... — but the real study_participants.csv
# schema (verified against the actual file on the research drive, see
# config/README.md) is initials,subid,unique_id,on_study,phone_number,...
# The code has a matching unfinished-migration comment in save_participants().

def test_xfail_load_participants_matches_real_csv_schema(tmp_path, fake_app):
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

    # unique_id (column 3 in both schemas) happens to survive by coincidence
    # of position — the real symptom is first_name/last_name silently
    # holding initials/subid instead.
    participant = pm.participants[0]
    if participant['first_name'] != 'Jane':
        pytest.xfail(
            'Known bug: load_participants() parses columns positionally as '
            'first_name,last_name,unique_id,... but the real schema is '
            'initials,subid,unique_id,... — see config/README.md. '
            f'first_name actually holds {participant["first_name"]!r}.'
        )
    assert participant['first_name'] == 'Jane'


def test_xfail_on_study_parses_yes_no_not_true_false(tmp_path, fake_app):
    # load_participants() checks `.lower() == 'true'`, but real data uses
    # yes/no (see config/README.md's confirmed schema) — so an on-study
    # participant is always parsed as on_study=False.
    csv_file = tmp_path / 'study_participants.csv'
    csv_file.write_text(
        'first_name,last_name,unique_id,on_study,phone_number,ema_time,'
        'ema_reminder_time,feedback_time,feedback_reminder_time\n'
        'Jane,Doe,000000000,yes,5555550100,09:00:00,10:00:00,19:00:00,20:00:00\n'
    )
    fake_app.participants_path = str(csv_file)
    pm = make_manager(fake_app)
    pm.file_path = str(csv_file)

    pm.load_participants()

    if pm.participants[0]['on_study'] is not True:
        pytest.xfail(
            "Known bug: load_participants() checks on_study == 'true', but "
            "real data uses yes/no — an on-study participant parses as False."
        )
    assert pm.participants[0]['on_study'] is True
