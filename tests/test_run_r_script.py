import os
import subprocess

from system_tasks._run_r_script import RunRScript, R_SCRIPT_TIMEOUT_SECONDS


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


def test_run_commonpath_value_error_is_treated_as_escape(tmp_path, fake_app, mocker):
    """Regression test: os.path.commonpath() raises ValueError when the two
    paths can't be compared at all (e.g. different drives on Windows). That
    call used to sit outside any try/except, so the ValueError propagated
    as a generic unhandled exception instead of the same clear refusal
    message an actual escape gets.
    """
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mock_run = mocker.patch('system_tasks._run_r_script.subprocess.run')
    mocker.patch(
        'system_tasks._run_r_script.os.path.commonpath',
        side_effect=ValueError("Paths don't have the same drive"),
    )

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 1
    assert os.getcwd() == original_cwd
    mock_run.assert_not_called()
    assert any('escapes' in msg for _, msg in fake_app.transcript)


def test_run_allows_scripts_dir_that_differs_only_in_case(tmp_path, fake_app, mocker):
    """Regression test: commonpath() is case-sensitive, but Windows/older
    macOS filesystems are case-insensitive -- a script path resolving to
    the same real directory as scripts_dir, differing only in letter case,
    used to be falsely rejected as escaping. This repo runs on Linux, where
    os.path.normcase() is a no-op (POSIX paths are genuinely
    case-sensitive), so os.path.normcase is patched here to fold case the
    way it actually does on Windows/ntpath -- exercising the code's use of
    normcase rather than relying on this host's own case-sensitivity.
    """
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mock_result = mocker.Mock(returncode=0, stdout='done', stderr='')
    mock_run = mocker.patch('system_tasks._run_r_script.subprocess.run', return_value=mock_result)
    real_script_path = str(tmp_path / 'cleanup.R')
    mocker.patch(
        'system_tasks._run_r_script.os.path.realpath',
        side_effect=lambda p: real_script_path.upper() if p.endswith('cleanup.R') else str(tmp_path),
    )
    mocker.patch('system_tasks._run_r_script.os.path.normcase', side_effect=lambda p: p.lower())

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 0
    assert os.getcwd() == original_cwd
    mock_run.assert_called_once()
    assert not any('escapes' in msg for _, msg in fake_app.transcript)


def test_run_rechecks_containment_immediately_before_subprocess_run(tmp_path, fake_app, mocker):
    """Regression test for a fixed TOCTOU gap: the containment check used
    to run once, well before subprocess.run -- a script swapped out (e.g. a
    symlink repointed) in that window would slip through. Now
    _escapes_scripts_dir() is called again immediately before
    subprocess.run; simulating that second call detecting an escape (first
    call says safe, second says escaped) proves the re-check actually
    guards the call, not just that it runs twice harmlessly.
    """
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    mock_run = mocker.patch('system_tasks._run_r_script.subprocess.run')
    task = RunRScript(fake_app, 'cleanup.R')
    mocker.patch.object(task, '_escapes_scripts_dir', side_effect=[False, True])

    result = task.run()

    assert result == 1
    mock_run.assert_not_called()
    assert any('re-checked immediately before running' in msg for _, msg in fake_app.transcript)


def test_run_success_restores_cwd_and_logs_output(tmp_path, fake_app, mocker):
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mock_result = mocker.Mock(returncode=0, stdout='done', stderr='')
    mock_run = mocker.patch('system_tasks._run_r_script.subprocess.run', return_value=mock_result)

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 0
    assert os.getcwd() == original_cwd
    mock_run.assert_called_once_with(
        ['Rscript', 'cleanup.R'], capture_output=True, text=True,
        cwd=str(tmp_path), timeout=R_SCRIPT_TIMEOUT_SECONDS,
    )
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


def test_run_rscript_timeout_returns_1_and_logs_error(tmp_path, fake_app, mocker):
    """Regression test: subprocess.run had no timeout= at all, so a hung
    Rscript process would block the single-threaded SystemTaskManager
    pipeline forever. Now bounded by R_SCRIPT_TIMEOUT_SECONDS and caught
    explicitly rather than falling into the generic Exception branch.
    """
    (tmp_path / 'cleanup.R').write_text('# fake R script')
    fake_app.r_scripts_dir = str(tmp_path)
    original_cwd = os.getcwd()
    mocker.patch(
        'system_tasks._run_r_script.subprocess.run',
        side_effect=subprocess.TimeoutExpired(cmd=['Rscript', 'cleanup.R'], timeout=R_SCRIPT_TIMEOUT_SECONDS),
    )

    result = RunRScript(fake_app, 'cleanup.R').run()

    assert result == 1
    assert os.getcwd() == original_cwd
    assert any(
        'did not finish within' in msg and str(R_SCRIPT_TIMEOUT_SECONDS) in msg
        for _, msg in fake_app.transcript
    )


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
