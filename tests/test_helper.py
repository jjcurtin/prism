from _helper import notify_coordinators


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
    send_sms.assert_called_once_with(fake_app, ['5555550101'], mocker.ANY)
    assert any('Skipping malformed study coordinator entry' in msg for _, msg in fake_app.transcript)


def test_notify_coordinators_skips_blank_phone(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n"Alice",""\n"Bob","5555550101"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.mode = 'prod'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    notify_coordinators(fake_app, 'system failure message')

    send_sms.assert_called_once_with(fake_app, ['5555550101'], mocker.ANY)


def test_notify_coordinators_no_coordinators_returns_0_no_send(tmp_path, fake_app, mocker):
    coordinators_file = tmp_path / 'study_coordinators.csv'
    coordinators_file.write_text('"name","phone_number"\n')
    fake_app.study_coordinators_path = str(coordinators_file)
    fake_app.mode = 'prod'
    send_sms = mocker.patch('_helper.send_sms', return_value=0)

    result = notify_coordinators(fake_app, 'system failure message')

    assert result == 0
    send_sms.assert_not_called()
