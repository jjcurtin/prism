import queue
import threading

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
    pm._tasks_lock = threading.RLock()
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


def test_get_task_schedule_excludes_task_for_since_removed_participant(fake_app):
    """Regression test for a fixed bug: get_task_schedule() used to index
    self.get_participant(...)['on_study'] unconditionally whenever a task
    had a participant_id, without checking whether get_participant()
    returned None -- which it does for a task lingering after its
    participant was removed from the roster (see remove_participant(),
    which removes the participant but not necessarily every task some
    other path may have added). That indexed a None and crashed the whole
    schedule lookup. Now such a task is silently excluded from the
    returned schedule (it can no longer run meaningfully), matching how
    process_task() itself handles a since-removed participant (logs and
    skips, doesn't crash).
    """
    from datetime import time
    pm = make_manager(fake_app)
    pm.participants = [PARTICIPANT]  # only 000000000 is a known participant
    pm.tasks = [
        {'task_type': 'ema', 'task_time': time(9, 0, 0), 'participant_id': '000000000'},
        {'task_type': 'feedback', 'task_time': time(19, 0, 0), 'participant_id': 'removed-participant'},
    ]

    result = pm.get_task_schedule()

    assert [r['task_type'] for r in result] == ['ema']
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


def test_add_participant_success_returns_0(fake_app):
    pm = make_manager(fake_app)
    pm.save_participants = lambda: None  # None == success, per save_participants' convention
    new_participant = dict(PARTICIPANT)

    result = pm.add_participant(new_participant)

    assert result == 0
    assert new_participant in pm.participants


def test_add_participant_write_failure_returns_1_and_rolls_back(fake_app):
    """Regression test for a fixed bug: add_participant used to have no
    return statement at all and never checked save_participants()'s result,
    so a CSV write failure (disk full, permissions) was logged internally
    but the caller (the /participants/add_participant route) always
    reported success. Now returns 1 on a write failure and doesn't leave
    the unsaved participant in memory.
    """
    pm = make_manager(fake_app)
    pm.save_participants = lambda: 1  # simulate a write failure
    new_participant = dict(PARTICIPANT)

    result = pm.add_participant(new_participant)

    assert result == 1
    assert new_participant not in pm.participants


def test_update_participant_on_study_coerces_string_to_bool(fake_app):
    """Regression test for a fixed bug: update_participant used to store
    whatever raw URL string was passed for on_study (e.g. "false") without
    coercing it to a real bool -- since any non-empty string is truthy in
    Python, an explicitly off-study participant set via this endpoint still
    read as on-study everywhere else (e.g. study_announcement's on-study
    filter). Now coerces "true"/"false"/"yes"/"no" (case-insensitive) to an
    actual bool.
    """
    pm = make_manager(fake_app)
    participant = dict(PARTICIPANT)
    pm.participants = [participant]
    pm.save_participants = lambda: None

    result = pm.update_participant('000000000', 'on_study', 'False')

    assert result == 0
    assert participant['on_study'] is False


def test_update_participant_on_study_accepts_yes_no(fake_app):
    pm = make_manager(fake_app)
    participant = dict(PARTICIPANT)
    participant['on_study'] = True
    pm.participants = [participant]
    pm.save_participants = lambda: None

    result = pm.update_participant('000000000', 'on_study', 'no')

    assert result == 0
    assert participant['on_study'] is False


def test_update_participant_on_study_rejects_invalid_value(fake_app):
    pm = make_manager(fake_app)
    participant = dict(PARTICIPANT)
    pm.participants = [participant]

    result = pm.update_participant('000000000', 'on_study', 'maybe')

    assert result == 1
    assert participant['on_study'] is True  # unchanged
    assert any('Invalid value' in msg for _, msg in fake_app.transcript)


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


# --- process_task ----------------------------------------------------------

def test_process_task_missing_participant_id_returns_neg1(fake_app):
    pm = make_manager(fake_app)

    result = pm.process_task({'task_type': 'ema'})

    assert result == -1
    assert any('missing' in msg.lower() for _, msg in fake_app.transcript)


def test_process_task_unknown_participant_returns_neg1_no_crash(fake_app):
    """Regression test for a fixed bug: process_task used to reference
    `participant` after a failed get_participant() call raised/returned None
    from inside a try/except that only logged (never re-raised or returned),
    so an unknown/removed participant crashed with an unhandled
    NameError/TypeError instead of failing gracefully.
    """
    pm = make_manager(fake_app)
    pm.participants = []

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})

    assert result == -1


def test_process_task_link_parsing_failure_returns_neg1_no_crash(fake_app, mocker):
    """Regression test for a fixed bug: `body` was built inside a try block
    (parsing the survey link/message via getattr(self.app, ...)) whose
    except branch only logged the error and fell through -- with no
    return. If that getattr() lookup failed (e.g. app not configured with
    ema_survey_id/ema_message), `body` was never assigned, and the
    following `send_sms(self.app, [...], [body])` call referenced an
    undefined name instead of failing cleanly. Now the except branch
    returns -1 immediately, matching every other failure path in this
    function.
    """
    fake_app.mode = 'prod'
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    # Deliberately don't set fake_app.ema_survey_id/ema_message, so the
    # getattr() lookups inside process_task()'s link-building try block
    # raise AttributeError.
    send_sms = mocker.patch('task_managers._participant_manager.send_sms')

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})

    assert result == -1
    send_sms.assert_not_called()
    assert any('Error parsing link' in msg for _, msg in fake_app.transcript)


def test_process_task_unknown_sms_task_type_does_not_notify_coordinators(fake_app, mocker):
    """Judgment call: an unrecognized task_type reaching this code is a
    data-shape/config-drift issue (e.g. survey_types gained a new key that
    task_attr_map never learned about), not a runtime malfunction like a
    Twilio/network failure -- it doesn't indicate PRISM's SMS-sending
    functionality is actually broken, so it's deliberately excluded from
    coordinator alerting here (unlike the genuine send-failure paths below).
    """
    fake_app.mode = 'prod'
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    notify = mocker.patch('task_managers._participant_manager.notify_coordinators')

    result = pm.process_task({'task_type': 'not_a_real_task_type', 'participant_id': '000000000'})

    assert result == -1
    notify.assert_not_called()


def test_process_task_off_study_returns_0_no_sms(fake_app, mocker):
    pm = make_manager(fake_app)
    participant = dict(PARTICIPANT, on_study=False)
    pm.participants = [participant]
    send_sms = mocker.patch('task_managers._participant_manager.send_sms')

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})

    assert result == 0
    send_sms.assert_not_called()


def test_process_task_off_study_one_time_task_still_sends(fake_app, mocker):
    """The recurring-task off-study skip above must not apply to a
    one-time task -- that's a deliberate RA-triggered send (send_survey
    route), already confirmed off-study-aware at the interface layer
    (see _individual_participant_menu.py's send_one_time_survey_menu), and
    should get the real, personalized survey link like any other send.
    """
    pm = make_manager(fake_app)
    participant = dict(PARTICIPANT, on_study=False)
    pm.participants = [participant]
    fake_app.mode = 'prod'
    fake_app.ema_survey_id = 'fake_survey'
    fake_app.ema_message = "Hello, it's time to take your daily survey."
    send_sms = mocker.patch('task_managers._participant_manager.send_sms')

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000', 'one_time': True})

    assert result == 0
    send_sms.assert_called_once_with(fake_app, ['5555550100'], mocker.ANY)


def test_process_task_sends_ema_sms_in_prod_mode(fake_app, mocker):
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    fake_app.mode = 'prod'
    fake_app.ema_survey_id = 'fake_survey'
    fake_app.ema_message = "Hello, it's time to take your daily survey."
    send_sms = mocker.patch('task_managers._participant_manager.send_sms')

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})

    assert result == 0
    send_sms.assert_called_once_with(fake_app, ['5555550100'], mocker.ANY)


# ------------------------------------------------------------
# finish_task / one-time survey send (send_survey route's underlying flow)
# ------------------------------------------------------------

def test_finish_task_one_time_survey_send_removes_only_the_one_time_task(fake_app, mocker):
    """Reproduces the exact scenario the send_survey route relies on: a
    participant already has a permanent recurring 'ema' task (from
    schedule_participant_tasks) and a coordinator triggers an ad hoc
    one-time 'ema' send on top of it. Both tasks share task_type +
    participant_id, so finishing the one-time task must not disturb the
    recurring one.
    """
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    fake_app.ema_survey_id = 'fake_survey'
    fake_app.ema_message = "Hello, it's time to take your daily survey."
    mocker.patch('task_managers._participant_manager.send_sms')
    recurring_task = pm.add_task('ema', '09:00:00', participant_id='000000000')

    one_time_task = pm.add_task('ema', '09:05:00', participant_id='000000000', one_time=True)
    result = pm.finish_task(one_time_task)

    assert result == 0
    assert pm.tasks == [recurring_task]


def test_finish_task_one_time_survey_send_removed_even_on_failure(fake_app, mocker):
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    fake_app.mode = 'prod'
    fake_app.ema_survey_id = 'fake_survey'
    fake_app.ema_message = "Hello, it's time to take your daily survey."
    mocker.patch('task_managers._participant_manager.send_sms', side_effect=Exception('boom'))
    mocker.patch('task_managers._participant_manager.notify_coordinators')

    one_time_task = pm.add_task('ema', '09:05:00', participant_id='000000000', one_time=True)
    result = pm.finish_task(one_time_task)

    assert result == -1
    assert pm.tasks == []


def test_process_task_ema_reminder_skipped_when_already_opened(tmp_path, fake_app, mocker):
    """Regression test for a fixed bug: process_task used to check
    ema_opened/feedback_opened columns that don't exist in the real
    reminders.csv schema (config/README.md: remind_ema/remind_feedback),
    so a KeyError was silently swallowed and every reminder fired regardless
    of whether the participant had already opened that survey today.
    remind_ema/remind_feedback == "no" means already opened -- skip (the
    column tracks whether the participant should *still* be reminded, per
    main's original semantics -- the column-name fix was correct but the
    "yes"-means-skip polarity that landed alongside it was inverted).
    """
    reminders_file = tmp_path / 'reminders.csv'
    reminders_file.write_text(
        'subid,unique_id,on_study,remind_ema,remind_feedback\n'
        '3000,000000000,yes,no,yes\n'
    )
    fake_app.reminders_path = str(reminders_file)
    fake_app.mode = 'prod'
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    send_sms = mocker.patch('task_managers._participant_manager.send_sms')

    result = pm.process_task({'task_type': 'ema_reminder', 'participant_id': '000000000'})

    assert result == 0
    send_sms.assert_not_called()


def test_process_task_ema_reminder_sent_when_not_yet_opened(tmp_path, fake_app, mocker):
    reminders_file = tmp_path / 'reminders.csv'
    reminders_file.write_text(
        'subid,unique_id,on_study,remind_ema,remind_feedback\n'
        '3000,000000000,yes,yes,no\n'
    )
    fake_app.reminders_path = str(reminders_file)
    fake_app.mode = 'prod'
    fake_app.ema_survey_id = 'fake_survey'
    fake_app.ema_reminder_message = "Hello, you have not yet completed your daily survey for today."
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    send_sms = mocker.patch('task_managers._participant_manager.send_sms')

    result = pm.process_task({'task_type': 'ema_reminder', 'participant_id': '000000000'})

    assert result == 0
    send_sms.assert_called_once_with(fake_app, ['5555550100'], mocker.ANY)


def test_process_task_send_sms_failure_notifies_coordinators_and_returns_neg1(fake_app, mocker):
    """A Twilio/network-level send failure is broken system functionality
    (not a user-input/data-shape problem), so it should alert coordinators
    via the shared notify_coordinators() helper and return -1 for a
    consistent failure contract.
    """
    fake_app.mode = 'prod'
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    fake_app.ema_survey_id = 'fake_survey'
    fake_app.ema_message = "Hello, it's time to take your daily survey."
    mocker.patch('task_managers._participant_manager.send_sms', side_effect=RuntimeError('twilio down'))
    notify = mocker.patch('task_managers._participant_manager.notify_coordinators', return_value=0)

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})

    assert result == -1
    notify.assert_called_once()
    message = notify.call_args[0][1]
    assert message.startswith('[2001] ')
    assert '000000000' in message
    assert 'twilio down' in message


def test_process_task_unexpected_error_notifies_coordinators_and_returns_neg1(fake_app, mocker):
    """Regression test for a fixed bug: the outermost catch-all used to fall
    off the end of the function with no return statement, implicitly
    returning None instead of a failure code -- inconsistent with every
    other failure path in this function (which all return -1). A genuine
    unexpected exception here is broken system functionality, so it should
    also alert coordinators.
    """
    pm = make_manager(fake_app)
    fake_app.mode = 'prod'
    notify = mocker.patch('task_managers._participant_manager.notify_coordinators', return_value=0)
    # get_participant() is called early in process_task(); make it blow up
    # with something other than the handled lookup-failure path to exercise
    # the outer try/except's catch-all.
    pm.get_participant = mocker.Mock(side_effect=RuntimeError('unexpected'))

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})

    assert result == -1
    notify.assert_called_once()
    message = notify.call_args[0][1]
    assert message.startswith('[2002] ')
    assert 'unexpected' in message


def test_process_task_notify_coordinators_failure_after_send_failure_does_not_propagate(fake_app, mocker):
    """Regression test: the notify_coordinators() call after an SMS send
    failure used to be unguarded -- if it too failed (e.g. the same
    broken-Twilio-credentials root cause that likely caused the original
    send failure), that second exception propagated out of process_task
    entirely, which -- called from finish_task()/run() on the background
    scheduler thread -- used to be exactly the cascade that silently
    killed that thread the first time anything went wrong.
    """
    fake_app.mode = 'prod'
    pm = make_manager(fake_app)
    pm.participants = [dict(PARTICIPANT)]
    fake_app.ema_survey_id = 'fake_survey'
    fake_app.ema_message = "Hello, it's time to take your daily survey."
    mocker.patch('task_managers._participant_manager.send_sms', side_effect=RuntimeError('twilio down'))
    mocker.patch(
        'task_managers._participant_manager.notify_coordinators',
        side_effect=RuntimeError('twilio also broken'),
    )

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})  # must not raise

    assert result == -1
    assert any(
        'Also failed to notify coordinators' in msg and 'twilio also broken' in msg
        for _, msg in fake_app.transcript
    )


def test_process_task_notify_coordinators_failure_after_unexpected_error_does_not_propagate(fake_app, mocker):
    """Same regression as above, for the outermost catch-all's
    notify_coordinators() call."""
    pm = make_manager(fake_app)
    fake_app.mode = 'prod'
    mocker.patch(
        'task_managers._participant_manager.notify_coordinators',
        side_effect=RuntimeError('twilio also broken'),
    )
    pm.get_participant = mocker.Mock(side_effect=RuntimeError('unexpected'))

    result = pm.process_task({'task_type': 'ema', 'participant_id': '000000000'})  # must not raise

    assert result == -1
    assert any(
        'Also failed to notify coordinators' in msg and 'twilio also broken' in msg
        for _, msg in fake_app.transcript
    )


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
