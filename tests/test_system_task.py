from system_tasks._system_task import SystemTask


class SucceedingTask(SystemTask):
    def run(self):
        self.task_type = 'SUCCEEDING_TASK'
        return 0


class FailingTask(SystemTask):
    def run(self):
        self.task_type = 'FAILING_TASK'
        return 1


def test_execute_success_in_live_mode_also_notifies(fake_app, mocker):
    """Coordinators are notified on both success and failure, per Colin's
    explicit request -- not just on failure as before."""
    fake_app.mode = 'live'
    notify = mocker.patch.object(SucceedingTask, 'notify_via_sms', return_value=0)

    result = SucceedingTask(fake_app).execute()

    assert result == 0
    notify.assert_called_once()


def test_execute_success_in_silent_mode_does_not_notify(fake_app, mocker):
    fake_app.mode = 'silent'
    notify = mocker.patch.object(SucceedingTask, 'notify_via_sms')

    result = SucceedingTask(fake_app).execute()

    assert result == 0
    notify.assert_not_called()


def test_execute_failure_in_live_mode_notifies(fake_app, mocker):
    fake_app.mode = 'live'
    notify = mocker.patch.object(FailingTask, 'notify_via_sms', return_value=0)

    result = FailingTask(fake_app).execute()

    assert result == 1
    notify.assert_called_once()


def test_execute_failure_in_silent_mode_does_not_notify(fake_app, mocker):
    fake_app.mode = 'silent'
    notify = mocker.patch.object(FailingTask, 'notify_via_sms')

    result = FailingTask(fake_app).execute()

    assert result == 1
    notify.assert_not_called()


def test_execute_logs_outcome(fake_app):
    fake_app.mode = 'silent'

    SucceedingTask(fake_app).execute()

    assert any('completed with status: SUCCESS' in msg for _, msg in fake_app.transcript)


def test_execute_notify_via_sms_failure_does_not_propagate(fake_app, mocker):
    """Regression test: execute() used to call notify_via_sms() outside
    any try/except of its own -- notify_via_sms() failing (Twilio down,
    credentials broken, coordinators file unreadable) would propagate out
    of execute() entirely, crashing whatever called it (the background
    scheduler thread, if this task ran off TaskManager.run()'s queue) over
    a *notification* failure, not the task's own actual work, which had
    already completed successfully.
    """
    fake_app.mode = 'live'
    mocker.patch.object(SucceedingTask, 'notify_via_sms', side_effect=RuntimeError('twilio broken'))

    result = SucceedingTask(fake_app).execute()  # must not raise

    assert result == 0  # the task itself still succeeded
    assert any('Failed to send coordinator SMS notifications' in msg and 'twilio broken' in msg for _, msg in fake_app.transcript)


def test_notify_via_sms_sends_to_each_coordinator(tmp_path, fake_app, mocker):
    """Regression test for a fixed bug: notify_via_sms() used to `return`
    from inside the coordinator-parsing loop, so it sent an alert to only
    the FIRST study coordinator in study_coordinators.csv and silently never
    notified the rest. Now accumulates all coordinators and sends one
    batched send_sms() call after the loop.

    notify_via_sms() now delegates coordinator-list-reading/sending to the
    shared _helper.notify_coordinators() (which itself calls _helper.send_sms),
    so that's what gets mocked here instead of system_tasks._system_task.send_sms
    (which no longer exists -- notify_via_sms() no longer imports send_sms
    directly). notify_coordinators() is gated on app.mode == "live", same as
    the real dispatch path via SystemTask.execute(), so mode is set to 'live'.
    """
    fake_app.mode = 'live'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    result = task.notify_via_sms()

    assert result == 0
    send_sms.assert_called_once()
    call_args = send_sms.call_args[0]
    assert call_args[1] == ['5555550100', '5555550101']


def test_notify_via_sms_missing_file_returns_1_and_warns(fake_app):
    fake_app.mode = 'live'
    fake_app.study_coordinators_path = '/nonexistent/study_coordinators.csv'

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    result = task.notify_via_sms()

    assert result == 1
    assert any('No study coordinators found' in msg for _, msg in fake_app.transcript)


def test_notify_via_sms_uses_default_template_when_app_has_no_override(tmp_path, fake_app, mocker):
    fake_app.mode = 'live'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.task_number = '123456'
    task.outcome = 'FAILURE'
    task.notify_via_sms()

    body = send_sms.call_args[0][2][0]
    assert body.startswith('[1001] Alice: CHECK_SYSTEM #123456 FAILURE. Script was executed at ')


def test_notify_via_sms_uses_app_coordinator_alert_message_template(tmp_path, fake_app, mocker):
    fake_app.mode = 'live'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.coordinator_alert_message = '{name} was alerted about {task_type} ({outcome})'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    task.notify_via_sms()

    body = send_sms.call_args[0][2][0]
    assert body == '[1001] Alice was alerted about CHECK_SYSTEM (FAILURE)'


def test_notify_via_sms_success_outcome_has_no_error_code(tmp_path, fake_app, mocker):
    """A SUCCESS outcome isn't an error, so its message shouldn't carry an
    error code -- only the FAILURE branch gets code_prefix('1001')."""
    fake_app.mode = 'live'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.coordinator_alert_message = '{name} was alerted about {task_type} ({outcome})'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'SUCCESS'
    task.notify_via_sms()

    body = send_sms.call_args[0][2][0]
    assert body == 'Alice was alerted about CHECK_SYSTEM (SUCCESS)'
    assert not body.startswith('[')


def test_notify_via_sms_skips_coordinators_with_blank_phone(tmp_path, fake_app, mocker):
    fake_app.mode = 'live'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice",""\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    task.notify_via_sms()

    send_sms.assert_called_once_with(fake_app, ['5555550101'], mocker.ANY, is_coordinator_message = True)


def test_notify_via_sms_noop_when_not_prod(tmp_path, fake_app, mocker):
    """notify_coordinators() (and therefore notify_via_sms(), which now
    delegates to it) is a no-op outside live mode -- in real dispatch this is
    redundant with SystemTask.execute()'s own "only call notify_via_sms() in
    prod" gate, but notify_via_sms() can also be called directly (as these
    tests do), so the gate needs to hold on its own too.
    """
    fake_app.mode = 'silent'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    result = task.notify_via_sms()

    assert result == 0
    send_sms.assert_not_called()
