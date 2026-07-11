from _helper import SMS_SEND_TIMEOUT_SECONDS, is_valid_phone_number, notify_coordinators, send_sms


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


def test_send_sms_constructs_client_with_bounded_timeout(fake_app, mocker):
    """Regression test: twilio-python's TwilioHttpClient defaults to
    timeout=None (an unbounded requests call) unless a caller sets one
    explicitly. Every SMS send runs synchronously on TaskManager.run()'s
    single background thread -- a network stall with no timeout would
    freeze that entire manager's pipeline (every other participant's
    scheduled message, or all system tasks) for as long as the stall
    lasts, not just fail the one send. send_sms() must always construct
    its Twilio client with an explicit, bounded timeout.
    """
    fake_app.twilio_account_sid = 'fake_sid'
    fake_app.twilio_auth_token = 'fake_token'
    fake_app.twilio_from_number = '+15555550199'
    mock_http_client_cls = mocker.patch('_helper.TwilioHttpClient')
    mock_client_cls = mocker.patch('_helper.Client')
    mock_client_cls.return_value.messages.create.return_value.sid = 'FAKE_SID'

    send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    mock_http_client_cls.assert_called_once_with(timeout=SMS_SEND_TIMEOUT_SECONDS)
    _, kwargs = mock_client_cls.call_args
    assert kwargs['http_client'] is mock_http_client_cls.return_value


def test_send_sms_missing_credentials_returns_failure_without_raising(fake_app):
    """Regression test: twilio_account_sid/auth_token/from_number have no
    defaults (unlike message-text fields, see API_FIELD_DEFAULTS in
    run_prism.py) -- if twilio.api ever fails to load (drive hiccup during
    startup, corrupted/missing file), those attributes are simply never
    set on the app. A bare attribute access used to raise AttributeError
    here -- and since send_sms() is called from inside failure-
    notification paths themselves (notify_coordinators/
    SystemTask.notify_via_sms), that AttributeError could cascade into
    crashing whatever called this to report an unrelated failure, up to
    and including the background scheduler thread itself. fake_app
    deliberately has none of the twilio_* attributes set here.
    """
    result = send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    assert result == 1
    assert any('Twilio credentials not loaded' in msg for _, msg in fake_app.transcript)


def test_send_sms_blank_credential_cell_returns_failure_without_raising(fake_app):
    """Regression test for a real bug (external adversarial review,
    confirmed live): pd.read_csv(..., dtype=str) still returns
    float('nan') for a blank cell -- a pandas quirk, not a dtype bug --
    and `not nan` is False in Python, so the old bare truthiness check
    (`if not account_sid or not auth_token or not from_number:`) silently
    let a blank twilio.api credential cell through instead of catching it
    with the "credentials not loaded" message. account_sid is float('nan')
    here, matching exactly what run_prism.py's load_api_keys would set it
    to for a blank cell (auth_token/from_number are real strings, so this
    also confirms _is_real_value() is applied per-credential, not just to
    the first one).
    """
    fake_app.twilio_account_sid = float('nan')
    fake_app.twilio_auth_token = 'fake_token'
    fake_app.twilio_from_number = '+15555550199'

    result = send_sms(fake_app, ['5555550100'], ['Time for your survey.'])

    assert result == 1
    assert any('Twilio credentials not loaded' in msg for _, msg in fake_app.transcript)


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


def test_notify_coordinators_round_trips_embedded_comma_and_quote_in_name(tmp_path, fake_app, mocker):
    """Regression test for a fixed bug: the old naive line.split(',') +
    strip('"') parser corrupted a coordinator name containing a comma or
    embedded quote (and everything after it on that line). csv.DictReader
    is immune to both.
    """
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Smith, ""Bob""","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.mode = 'prod'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    notify_coordinators(fake_app, 'Hi {name}, something broke.')

    send_sms.assert_called_once_with(
        fake_app, ['5555550101'], ['Hi Smith, "Bob", something broke.'], is_coordinator_message = True
    )


def test_notify_coordinators_reads_old_naive_serializer_output(tmp_path, fake_app, mocker):
    """"Verify, don't assume" compatibility check: the old writer always
    quoted every field with no embedded metacharacters in this sample, so
    its output happens to already be valid CSV -- confirms the new
    csv.DictReader-based reader still accepts it."""
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice","5555550100"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.mode = 'prod'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    result = notify_coordinators(fake_app, 'system failure message')

    assert result == 0
    send_sms.assert_called_once_with(fake_app, ['5555550100'], mocker.ANY, is_coordinator_message = True)


# ------------------------------------------------------------
# is_valid_phone_number
# ------------------------------------------------------------

def test_is_valid_phone_number_accepts_10_digits():
    assert is_valid_phone_number('5555550100') is True


def test_is_valid_phone_number_rejects_wrong_length():
    assert is_valid_phone_number('555555010') is False  # 9 digits
    assert is_valid_phone_number('55555501000') is False  # 11 digits


def test_is_valid_phone_number_rejects_non_digit_characters():
    assert is_valid_phone_number('555-555-0100') is False
    assert is_valid_phone_number('(555)5550100') is False


def test_is_valid_phone_number_rejects_empty_string():
    assert is_valid_phone_number('') is False
