from _helper import notify_coordinators, send_sms


def _mock_twilio_client(mocker, fake_app):
    """Patches _helper.Client so send_sms() runs for real (not mocked
    itself) but never hits the network -- returns the mock client so tests
    can inspect exactly what body was passed to messages.create(). Also
    sets the twilio_* credential attributes send_sms() reads directly (not
    via getattr), since the plain fake_app fixture doesn't set these by
    default."""
    fake_app.twilio_account_sid = 'fake_sid'
    fake_app.twilio_auth_token = 'fake_token'
    fake_app.twilio_from_number = '+15555550199'
    mock_client = mocker.MagicMock()
    mock_client.messages.create.return_value.sid = 'FAKE_SID'
    mocker.patch('_helper.Client', return_value=mock_client)
    return mock_client


def test_send_sms_dev_environment_prefixes_participant_message(fake_app, mocker):
    fake_app.environment = 'dev'
    client = _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    body = client.messages.create.call_args.kwargs['body']
    assert body == 'DEV: Time for your survey.'


def test_send_sms_dev_environment_prefixes_coordinator_message(fake_app, mocker):
    fake_app.environment = 'dev'
    client = _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['A task failed.'], is_coordinator_message=True)

    body = client.messages.create.call_args.kwargs['body']
    assert body == 'DEV: A task failed.'


def test_send_sms_prod_environment_does_not_prefix_participant_message(fake_app, mocker):
    fake_app.environment = 'prod'
    client = _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    body = client.messages.create.call_args.kwargs['body']
    assert body == 'Time for your survey.'


def test_send_sms_prod_environment_prefixes_coordinator_message(fake_app, mocker):
    fake_app.environment = 'prod'
    client = _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['A task failed.'], is_coordinator_message=True)

    body = client.messages.create.call_args.kwargs['body']
    assert body == 'PROD: A task failed.'


def test_send_sms_missing_environment_defaults_to_dev_prefix(fake_app, mocker):
    del fake_app.environment
    client = _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    body = client.messages.create.call_args.kwargs['body']
    assert body == 'DEV: Time for your survey.'


def test_send_sms_transcript_log_line_has_no_prefix(fake_app, mocker):
    fake_app.environment = 'dev'
    _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    log_messages = [msg for _, msg in fake_app.transcript]
    assert any('SMS 1 sent to 5555550100' in msg and 'DEV:' not in msg for msg in log_messages)


def test_send_sms_participant_transcript_labeled_participant(fake_app, mocker):
    """Regression test: a mixed transcript must be able to tell a
    participant send apart from a coordinator alert at a glance."""
    fake_app.environment = 'prod'
    _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    log_messages = [msg for _, msg in fake_app.transcript]
    assert any('Participant SMS 1 sent to 5555550100' in msg for msg in log_messages)
    assert not any('Coordinator' in msg for msg in log_messages)


def test_send_sms_coordinator_transcript_labeled_with_reason(fake_app, mocker):
    """Regression test: a coordinator alert's transcript line must say why
    it was sent, including the [XXXX] error code embedded in the message
    body by the caller -- not just that some SMS went out."""
    fake_app.environment = 'prod'
    _mock_twilio_client(mocker, fake_app)

    send_sms(fake_app, ['5555550100'], ['[1001] Alice: CHECK_SYSTEM #123 FAILURE.'], is_coordinator_message=True)

    log_messages = [msg for _, msg in fake_app.transcript]
    assert any(
        'Coordinator SMS 1 sent to 5555550100' in msg
        and '[1001] Alice: CHECK_SYSTEM #123 FAILURE' in msg
        for msg in log_messages
    )


def test_send_sms_failure_transcript_labeled_by_recipient_kind(fake_app, mocker):
    fake_app.environment = 'prod'
    client = _mock_twilio_client(mocker, fake_app)
    client.messages.create.side_effect = Exception('boom')

    send_sms(fake_app, ['5555550100'], ['A task failed.'], is_coordinator_message=True)

    log_messages = [msg for _, msg in fake_app.transcript]
    assert any('Failed to send Coordinator SMS 1 to 5555550100' in msg for msg in log_messages)


def test_notify_coordinators_noop_when_not_prod(tmp_path, fake_app, mocker):
    fake_app.mode = 'test'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    result = notify_coordinators(fake_app, 'system failure message')

    assert result == 0
    send_sms.assert_not_called()


def test_notify_coordinators_sends_plain_message_to_each_coordinator(tmp_path, fake_app, mocker):
    fake_app.mode = 'prod'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    result = notify_coordinators(fake_app, 'PRISM system failure: something broke.')

    assert result == 0
    send_sms.assert_called_once_with(
        fake_app,
        ['5555550100', '5555550101'],
        ['PRISM system failure: something broke.', 'PRISM system failure: something broke.'],
        is_coordinator_message = True,
    )


def test_notify_coordinators_fills_in_name_placeholder_per_coordinator(tmp_path, fake_app, mocker):
    fake_app.mode = 'prod'
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    notify_coordinators(fake_app, 'Hi {name}, something broke.')

    bodies = send_sms.call_args[0][2]
    assert bodies == ['Hi Alice, something broke.', 'Hi Bob, something broke.']


def test_notify_coordinators_missing_file_returns_1_and_warns(fake_app):
    fake_app.mode = 'prod'
    fake_app.study_coordinators_path = '/nonexistent/study_coordinators.csv'

    result = notify_coordinators(fake_app, 'system failure message')

    assert result == 1
    assert any('No study coordinators found' in msg for _, msg in fake_app.transcript)


def test_notify_coordinators_skips_malformed_entries(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice"\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.mode = 'prod'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    result = notify_coordinators(fake_app, 'system failure message')

    assert result == 0
    send_sms.assert_called_once_with(fake_app, ['5555550101'], mocker.ANY, is_coordinator_message = True)
    assert any('Skipping malformed study coordinator entry' in msg for _, msg in fake_app.transcript)


def test_notify_coordinators_skips_blank_phone(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice",""\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.mode = 'prod'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    notify_coordinators(fake_app, 'system failure message')

    send_sms.assert_called_once_with(fake_app, ['5555550101'], mocker.ANY, is_coordinator_message = True)


def test_notify_coordinators_no_coordinators_returns_0_no_send(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.mode = 'prod'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    result = notify_coordinators(fake_app, 'system failure message')

    assert result == 0
    send_sms.assert_not_called()
