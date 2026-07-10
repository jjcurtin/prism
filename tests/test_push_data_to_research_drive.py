from pathlib import Path

from system_tasks._push_data_to_research_drive import PushDataToResearchDrive


def test_upload_files_windows_calls_robocopy_and_creates_destination(tmp_path, fake_app, mocker):
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Windows')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'optimize/prism/dev/data_processed'
    mock_result = mocker.Mock(returncode=1, stdout='', stderr='')
    mock_run = mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', return_value=mock_result)

    result = PushDataToResearchDrive(fake_app).upload_files()

    assert result == 0
    expected_destination = Path(fake_app.drive_mount) / fake_app.destination_path / 'data'
    assert expected_destination.is_dir()
    mock_run.assert_called_once_with(
        ['robocopy', '../data', str(expected_destination), '/MIR'],
        capture_output=True, text=True,
    )
    assert any('data copied to Research Drive' in msg for _, msg in fake_app.transcript)


def test_upload_files_windows_robocopy_low_exit_code_is_success(tmp_path, fake_app, mocker):
    """robocopy exit codes 0-7 are all varying degrees of success (files
    copied/extra/mismatched) -- only >=8 is a real failure."""
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Windows')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'dest'
    mock_result = mocker.Mock(returncode=3, stdout='', stderr='')
    mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', return_value=mock_result)

    result = PushDataToResearchDrive(fake_app).upload_files()

    assert result == 0


def test_upload_files_windows_robocopy_failure_exit_code_returns_1(tmp_path, fake_app, mocker):
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Windows')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'dest'
    mock_result = mocker.Mock(returncode=8, stdout='', stderr='access denied')
    mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', return_value=mock_result)

    result = PushDataToResearchDrive(fake_app).upload_files()

    assert result == 1
    assert any('robocopy reported failure' in msg and 'access denied' in msg for _, msg in fake_app.transcript)


def test_upload_files_linux_calls_rsync_with_trailing_slash_on_source(tmp_path, fake_app, mocker):
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Linux')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'optimize/prism/dev/data_processed'
    mock_result = mocker.Mock(returncode=0, stdout='', stderr='')
    mock_run = mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', return_value=mock_result)

    result = PushDataToResearchDrive(fake_app).upload_files()

    assert result == 0
    expected_destination = Path(fake_app.drive_mount) / fake_app.destination_path / 'data'
    # trailing slash on source is required so rsync mirrors the *contents*
    # of ../data into the destination folder, instead of nesting a
    # data/ subdirectory inside it.
    mock_run.assert_called_once_with(
        ['rsync', '-a', '--delete', '../data/', str(expected_destination)],
        capture_output=True, text=True,
    )


def test_upload_files_linux_rsync_nonzero_exit_returns_1(tmp_path, fake_app, mocker):
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Linux')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'dest'
    mock_result = mocker.Mock(returncode=23, stdout='', stderr='rsync: some files/attrs were not transferred')
    mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', return_value=mock_result)

    result = PushDataToResearchDrive(fake_app).upload_files()

    assert result == 1
    assert any('rsync reported failure' in msg for _, msg in fake_app.transcript)


def test_upload_files_subprocess_raises_returns_1(tmp_path, fake_app, mocker):
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Linux')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'dest'
    mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', side_effect=OSError('rsync not found'))

    result = PushDataToResearchDrive(fake_app).upload_files()

    assert result == 1
    assert any('rsync not found' in msg for _, msg in fake_app.transcript)


def test_run_returns_0_on_success(tmp_path, fake_app, mocker):
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Linux')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'dest'
    mock_result = mocker.Mock(returncode=0, stdout='', stderr='')
    mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', return_value=mock_result)

    result = PushDataToResearchDrive(fake_app).run()

    assert result == 0


def test_run_returns_1_when_upload_fails(tmp_path, fake_app, mocker):
    mocker.patch('system_tasks._push_data_to_research_drive.platform.system', return_value='Linux')
    fake_app.drive_mount = str(tmp_path / 'drive')
    fake_app.destination_path = 'dest'
    mock_result = mocker.Mock(returncode=99, stdout='', stderr='boom')
    mocker.patch('system_tasks._push_data_to_research_drive.subprocess.run', return_value=mock_result)

    result = PushDataToResearchDrive(fake_app).run()

    assert result == 1
