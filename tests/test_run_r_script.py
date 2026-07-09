import os

from system_tasks._run_r_script import RunRScript


def test_run_missing_scripts_dir_returns_1(fake_app):
    fake_app.r_scripts_dir = '/nonexistent/scripts/dir'

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 1
    assert any('does not exist' in msg for _, msg in fake_app.transcript)


def test_run_missing_script_file_returns_1_and_restores_cwd(tmp_path, fake_app):
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()

    result = RunRScript(fake_app, 'missing.R').run()

    assert result == 1
    assert os.getcwd() == original_cwd
    assert any('missing.R' in msg and 'does not exist' in msg for _, msg in fake_app.transcript)


def test_run_success_restores_cwd_and_logs_output(tmp_path, fake_app, mocker):
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mock_result = mocker.Mock(returncode=0, stdout='done', stderr='')
    mock_run = mocker.patch('system_tasks._run_r_script.subprocess.run', return_value=mock_result)

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 0
    assert os.getcwd() == original_cwd
    mock_run.assert_called_once_with(['Rscript', 'cleanup.R'], capture_output=True, text=True)
    assert any('script run complete' in msg for _, msg in fake_app.transcript)


def test_run_rscript_nonzero_exit_returns_1_and_restores_cwd(tmp_path, fake_app, mocker):
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mock_result = mocker.Mock(returncode=1, stdout='', stderr='syntax error')
    mocker.patch('system_tasks._run_r_script.subprocess.run', return_value=mock_result)

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 1
    assert os.getcwd() == original_cwd
    assert any('syntax error' in msg for _, msg in fake_app.transcript)


def test_run_subprocess_raises_returns_1_and_restores_cwd(tmp_path, fake_app, mocker):
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mocker.patch('system_tasks._run_r_script.subprocess.run', side_effect=OSError('Rscript not found'))

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 1
    assert os.getcwd() == original_cwd
    assert any('Rscript not found' in msg for _, msg in fake_app.transcript)
