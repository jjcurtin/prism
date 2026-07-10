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


def test_run_rejects_script_path_that_escapes_scripts_dir(tmp_path, fake_app, mocker):
    """RunRScript previously only checked os.path.exists() on the requested
    script path with no confinement to scripts_dir -- a path like
    '../outside/evil.R' would pass that check and get handed straight to
    Rscript. Now refuses to run anything outside scripts_dir.
    """
    scripts_dir = tmp_path / 'scripts'
    scripts_dir.mkdir()
    outside_dir = tmp_path / 'outside'
    outside_dir.mkdir()
    (outside_dir / 'evil.R').write_text('# fake R script outside scripts dir')
    fake_app.r_scripts_dir = str(scripts_dir)
    original_cwd = os.getcwd()
    mock_run = mocker.patch('system_tasks._run_r_script.subprocess.run')

    result = RunRScript(fake_app, '../outside/evil.R').run()

    assert result == 1
    assert os.getcwd() == original_cwd
    mock_run.assert_not_called()
    assert any('escapes' in msg for _, msg in fake_app.transcript)


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


def test_run_rscript_executable_missing_gives_actionable_message(tmp_path, fake_app, mocker):
    """Regression test for a real-world failure: subprocess.run raises
    FileNotFoundError (not a generic OSError) specifically when the
    executable itself -- 'Rscript', not the .R script file, which is
    already confirmed to exist by this point -- can't be found on PATH.
    On Windows this is the well-known gotcha where installing R doesn't
    add its bin/ directory to PATH automatically. This must be called out
    explicitly rather than falling into the generic failure message.
    """
    (tmp_path / 'Test.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mocker.patch(
        'system_tasks._run_r_script.subprocess.run',
        side_effect=FileNotFoundError(2, 'The system cannot find the file specified'),
    )

    result = RunRScript(fake_app, 'Test.R').run()

    assert result == 1
    assert os.getcwd() == original_cwd
    assert any(
        "could not launch the 'Rscript' executable" in msg and 'is R installed' in msg
        for _, msg in fake_app.transcript
    )
