from system_tasks._system_task import SystemTask


class SucceedingTask(SystemTask):
    def run(self):
        self.task_type = 'SUCCEEDING_TASK'
        return 0


class FailingTask(SystemTask):
    def run(self):
        self.task_type = 'FAILING_TASK'
        return 1


def test_execute_success_in_prod_mode_also_notifies(fake_app, mocker):
    """Coordinators are notified on both success and failure, per Colin's
    explicit request -- not just on failure as before."""
    fake_app.mode = 'prod'
    notify = mocker.patch.object(SucceedingTask, 'notify_via_sms', return_value=0)

    result = SucceedingTask(fake_app).execute()

    assert result == 0
    notify.assert_called_once()


def test_execute_success_in_test_mode_does_not_notify(fake_app, mocker):
    fake_app.mode = 'test'
    notify = mocker.patch.object(SucceedingTask, 'notify_via_sms')

    result = SucceedingTask(fake_app).execute()

    assert result == 0
    notify.assert_not_called()


def test_execute_failure_in_prod_mode_notifies(fake_app, mocker):
    fake_app.mode = 'prod'
    notify = mocker.patch.object(FailingTask, 'notify_via_sms', return_value=0)

    result = FailingTask(fake_app).execute()

    assert result == 1
    notify.assert_called_once()


def test_execute_failure_in_test_mode_does_not_notify(fake_app, mocker):
    fake_app.mode = 'test'
    notify = mocker.patch.object(FailingTask, 'notify_via_sms')

    result = FailingTask(fake_app).execute()

    assert result == 1
    notify.assert_not_called()


def test_execute_logs_outcome(fake_app):
    fake_app.mode = 'test'

    SucceedingTask(fake_app).execute()

    assert any('completed with status: SUCCESS' in msg for _, msg in fake_app.transcript)


def test_notify_via_sms_sends_to_each_coordinator(tmp_path, fake_app, mocker):
    """Regression test for a fixed bug: notify_via_sms() used to `return`
    from inside the coordinator-parsing loop, so it sent an alert to only
    the FIRST study coordinator in study_coordinators.csv and silently never
    notified the rest. Now accumulates all coordinators and sends one
    batched send_sms() call after the loop.
    """
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('system_tasks._system_task.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    result = task.notify_via_sms()

    assert result == 0
    send_sms.assert_called_once()
    call_args = send_sms.call_args[0]
    assert call_args[1] == ['5555550100', '5555550101']


def test_notify_via_sms_missing_file_returns_1_and_warns(fake_app):
    fake_app.study_coordinators_path = '/nonexistent/study_coordinators.csv'

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    result = task.notify_via_sms()

    assert result == 1
    assert any('No study coordinators found' in msg for _, msg in fake_app.transcript)


def test_notify_via_sms_uses_default_template_when_app_has_no_override(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('system_tasks._system_task.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.task_number = '123456'
    task.outcome = 'FAILURE'
    task.notify_via_sms()

    body = send_sms.call_args[0][2][0]
    assert body.startswith('Alice: CHECK_SYSTEM #123456 FAILURE. Script was executed at ')


def test_notify_via_sms_uses_app_coordinator_alert_message_template(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.coordinator_alert_message = '{name} was alerted about {task_type} ({outcome})'
    send_sms = mocker.patch('system_tasks._system_task.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    task.notify_via_sms()

    body = send_sms.call_args[0][2][0]
    assert body == 'Alice was alerted about CHECK_SYSTEM (FAILURE)'


def test_notify_via_sms_skips_coordinators_with_blank_phone(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice",""\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('system_tasks._system_task.send_sms', return_value=0)

    task = SucceedingTask(fake_app)
    task.task_type = 'CHECK_SYSTEM'
    task.outcome = 'FAILURE'
    task.notify_via_sms()

    send_sms.assert_called_once_with(fake_app, ['5555550101'], mocker.ANY)
