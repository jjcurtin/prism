"""Main runner for the PRISM application"""

import os
import platform
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any
from _routes import create_flask_app
import pandas as pd
from waitress import serve
from _helper import clear
import signal
import argparse

from task_managers._system_task_manager import SystemTaskManager
from task_managers._participant_manager import ParticipantManager


def _verify_invocation_directory() -> None:
    """Exits cleanly if launched with a cwd other than src/. A standalone
    function, not a PRISM method: it runs before anything on `self` is
    initialized (see __init__ below), so it must not touch `self` at all --
    the old inline version called self.add_to_transcript(...) here, which
    itself reads self.mode/self.logs_dir, neither set yet at this point;
    hitting this guard raised AttributeError instead of the intended clean
    error message.

    Also a real cwd check now, not just reordering that old call: the
    previous version only ever compared __file__'s own on-disk location
    (os.path.dirname(os.path.abspath(__file__)).endswith('src')), which is
    fixed by the checkout layout regardless of the launching shell's
    working directory -- it could essentially never fail in practice, so
    it never actually caught the "wrong directory invocation" its message
    implied.
    """
    expected_dir = os.path.dirname(os.path.abspath(__file__))
    actual_dir = os.path.abspath(os.getcwd())
    if actual_dir != expected_dir:
        print(f"ERROR - Please run this script from the '{expected_dir}' directory (src/); current directory is '{actual_dir}'.")
        exit(1)



# Written to repo_root on startup, read (and removed) by stop_server.py --
# a precise, PID-targeted alternative to the old pattern-matching
# `pkill -f run_prism.py`, which would also kill any unrelated process
# whose command line merely contained that string (e.g. `vim run_prism.py`,
# a second checkout's server, a grep).
PID_FILE_NAME = '.run_prism.pid'


class PRISM():
    # Attributes populated by load_paths()/load_api_keys() below, rather
    # than directly in __init__ -- some (participants_path, reminders_path,
    # r_scripts_dir, and every API_FIELD_DEFAULTS-driven credential/message
    # field) are set via `setattr(self, attr, value)` with a dynamically
    # computed attribute name, which mypy can't see as an assignment to a
    # specific name. Declared here (type only, no value) so every other
    # module that reads these off an `App`-typed `app`/`app_instance`
    # (_helper.py, _routes.py, task_managers/, system_tasks/) type-checks
    # against the real shape of a fully-initialized PRISM instance.
    repo_root: Path
    logs_dir: str
    data_dir: str
    drive_mount: str
    environment: str
    config_base: str
    participants_path: str
    reminders_path: str
    r_scripts_dir: str
    system_task_schedule_path: str
    study_coordinators_path: str
    ema_survey_id: str
    feedback_survey_id: str
    ema_message: str
    ema_reminder_message: str
    feedback_message: str
    feedback_reminder_message: str
    coordinator_alert_message: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    flask_app: Any  # Flask app instance; see launch_web_app()

    def __init__(self, mode: str = "test") -> None:
        _verify_invocation_directory()

        clear()
        self.mode = mode
        self.start_time = datetime.now()
        self.load_paths()
        self._write_pid_file()
        self.add_to_transcript("Initializing PRISM application...", "INFO")

        self.load_api_keys()

        self.system_task_manager = SystemTaskManager(self)
        self.participant_manager = ParticipantManager(self)

        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        self.add_to_transcript(f"PRISM started in {self.mode} mode.", "INFO")
        self.launch_web_app()

    # system methods

    def _resolve_drive_path(self, raw_path: object) -> str:
        # translates an "S:/..." literal (as written on the drive's own
        # paths.csv, which is authored from Windows) into this platform's
        # real path by substituting self.drive_mount for the drive letter --
        # on production Windows that's just "S:" again (a no-op), but it's
        # what lets tests redirect drive_mount_windows to a fake temp dir.
        # Non-drive-letter (relative) values are returned as-is, for the
        # caller to resolve against config_base.
        raw_path = str(raw_path).strip()
        if len(raw_path) >= 2 and raw_path[1] == ':':
            raw_path = raw_path[2:].lstrip('/\\')
            return str((Path(self.drive_mount) / raw_path).resolve())
        return raw_path

    def load_paths(self, environment: str | None = None) -> None:
        # repo root is the parent of this file's directory (src/). Tests can
        # override by setting self.repo_root before calling this method, to
        # point at a fixture tree instead of the real checkout.
        repo_root = getattr(self, 'repo_root', None) or Path(__file__).resolve().parent.parent
        self.repo_root = repo_root

        # repo_paths.csv is tracked (not gitignored, unlike everything else
        # in config/) — it holds resolution facts internal to this repo
        # checkout itself (where logs live locally, how the research drive
        # mounts on this platform, which drive subpath this project lives
        # under), as opposed to research-drive-specific paths, which come
        # from the drive's own paths.csv below.
        repo_paths_defaults: dict[str, str] = {
            'logs_dir': 'logs',
            'data_dir': 'data',
            'drive_mount_windows': 'S:',
            'drive_mount_posix': '/mnt/research_drive',
            'prism_drive_subpath': 'optimize/prism',
        }
        try:
            df = pd.read_csv(str(repo_root / 'config' / 'repo_paths.csv'), quotechar='"', skipinitialspace=True, dtype=str)
            repo_paths: dict[str, str] = {str(row['key']).strip(): str(row['value']).strip() for _, row in df.iterrows()}
        except Exception:
            repo_paths = {}
        repo_paths = {**repo_paths_defaults, **repo_paths}

        # logs stay local to this checkout (per-machine operational data,
        # not shared study config) — set first so add_to_transcript (called
        # right after this) always has somewhere to write.
        self.logs_dir = str((repo_root / repo_paths['logs_dir']).resolve())
        # data_dir: where data-pulldown system tasks write raw/processed
        # output -- resolved the same way as logs_dir (repo-root-relative,
        # not cwd-relative), so callers no longer need to assume a cwd of
        # src/ (see tests_integration/conftest.py's real_app fixture).
        # Currently unused: PulldownQualtricsData and PulldownFollowmeeData,
        # the only tasks that wrote here, were both removed entirely
        # 2026-07-10 (see root CLAUDE.md's Changelog); kept in case a future
        # task needs a repo-root-relative data directory again.
        self.data_dir = str((repo_root / repo_paths['data_dir']).resolve())
        self.drive_mount = repo_paths['drive_mount_windows'] if platform.system() == 'Windows' else repo_paths['drive_mount_posix']

        # environment marker: a git-ignored, single-line file at the repo
        # root containing "dev" or "prod", selecting which paths.csv (and
        # everything under its config_base) this checkout loads from. This
        # stays gitignored (unlike repo_paths.csv above) because it's a
        # per-deployment choice, not something every checkout should share.
        # Defaults to "dev" (the safer default) if missing, and creates the
        # file so the choice is explicit and persisted for next time rather
        # than silently re-defaulting on every startup. Callers that need to
        # resolve a specific environment regardless of the marker (e.g.
        # tests_integration/test_environment_files.py, which checks both
        # "dev" and "prod" in the same run) can pass `environment` directly
        # instead.
        if environment:
            self.environment = environment
        else:
            env_file = repo_root / 'environment'
            self.environment = 'dev'
            if env_file.exists() and env_file.read_text().strip():
                self.environment = env_file.read_text().strip()
            elif env_file.exists():
                self.add_to_transcript(f"Environment file at {env_file} is empty — defaulting to 'dev'.", "WARNING")
            else:
                env_file.write_text('dev')
                self.add_to_transcript(f"No environment file at {env_file} — created it and set to 'dev'.", "WARNING")

        paths_csv = self._resolve_drive_path(f"S:/{repo_paths['prism_drive_subpath']}/{self.environment}/config/paths.csv")
        try:
            df = pd.read_csv(paths_csv, quotechar='"', skipinitialspace=True, dtype=str)
            raw: dict[str, str] = {str(row['key']).strip(): str(row['path']).strip() for _, row in df.iterrows()}
        except Exception as e:
            self.add_to_transcript(f"Failed to load paths configuration from {paths_csv}: {e}", "ERROR")
            raw = {}

        self.config_base = self._resolve_drive_path(raw.get('config_base', f"S:/optimize/prism/{self.environment}/"))

        key_to_attr = {
            'participants': 'participants_path',
            'reminders': 'reminders_path',
            'scripts': 'r_scripts_dir',
        }
        for key, attr in key_to_attr.items():
            value = raw.get(key)
            if value is None:
                self.add_to_transcript(f"paths.csv missing key '{key}' — {attr} left unset.", "WARNING")
                continue
            if key == 'scripts':
                # Unlike participants/reminders, the scripts folder isn't a
                # prism-specific, drive-hosted resource -- still configured
                # per-environment via the drive's paths.csv (so it can point
                # wherever that RA/machine's scripts actually live), but the
                # value itself is a local filesystem path and must NOT be
                # routed through _resolve_drive_path's "X:" substitution or
                # resolved relative to config_base (which lives on the
                # drive). A relative value resolves against the repo
                # checkout instead, the same local anchor logs_dir/data_dir
                # already use.
                resolved = value if Path(value).is_absolute() else str((repo_root / value).resolve())
            else:
                resolved = self._resolve_drive_path(value)
                if not Path(resolved).is_absolute():
                    resolved = str((Path(self.config_base) / resolved).resolve())
            setattr(self, attr, resolved)

        # These used to be separate paths.csv/paths.api entries; they now
        # live directly under config_base/config/ alongside everything else.
        config_dir = Path(self.config_base) / 'config'
        self.system_task_schedule_path = str(config_dir / 'system_task_schedule.csv')
        self.study_coordinators_path = str(config_dir / 'study_coordinators.csv')

    # sane defaults for fields that may not exist yet in an older api CSV
    # (e.g. the message columns, added after qualtrics.api files already
    # existed on the drive) — load_keys only overwrites these if the column
    # is actually present, so one missing column doesn't take down the
    # whole file's worth of fields.
    API_FIELD_DEFAULTS: dict[str, str] = {
        'ema_message': "Hello, it's time to take your daily survey.",
        'ema_reminder_message': "Hello, you have not yet completed your daily survey for today.",
        'feedback_message': "Hello, it's time to see your daily recovery message.",
        'feedback_reminder_message': "Hello, you have not yet viewed your daily recovery message for today.",
        'coordinator_alert_message': "{name}: {task_type} #{task_number} {outcome}. Script was executed at {task_start}.",
    }

    def load_api_keys(self) -> None:
        api_dir = Path(self.config_base) / 'api'
        for attr, default in self.API_FIELD_DEFAULTS.items():
            setattr(self, attr, default)

        def load_keys(file_name: str, field_map: dict[str, str], label: str) -> None:
            try:
                df = pd.read_csv(str(api_dir / file_name), quotechar='"', dtype=str)
            except Exception as e:
                self.add_to_transcript(f"Failed to load {label} API keys from {file_name}: {e}", "ERROR")
                return
            for attr, column in field_map.items():
                if column in df.columns:
                    setattr(self, attr, df.loc[0, column])
                elif attr not in self.API_FIELD_DEFAULTS:
                    self.add_to_transcript(f"{label} API file {file_name} missing column '{column}' — {attr} left unset.", "WARNING")
        load_keys('qualtrics.api', {
            'ema_survey_id': 'ema_survey_id',
            'feedback_survey_id': 'feedback_survey_id',
            'ema_message': 'ema_message',
            'ema_reminder_message': 'ema_reminder_message',
            'feedback_message': 'feedback_message',
            'feedback_reminder_message': 'feedback_reminder_message'
        }, "Qualtrics")
        load_keys('twilio.api', {
            'twilio_account_sid': 'account_sid',
            'twilio_auth_token': 'auth_token',
            'twilio_from_number': 'from_number',
            'coordinator_alert_message': 'coordinator_alert_message'
        }, "Twilio")

    def add_to_transcript(self, message: str, message_type: str = "INFO") -> None:
        transcript_message = f"{message_type} - {message}"
        print(transcript_message)
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self.mode == "test":
            file_path = os.path.join(self.logs_dir, 'transcripts', 'test_transcript.txt')
        else:
            file_path = os.path.join(self.logs_dir, 'transcripts', f'{current_date}_transcript.txt')
        os.makedirs(os.path.dirname(file_path), exist_ok = True)
        try:
            with open(file_path, 'a') as file:
                file.write(f"{datetime.now().strftime('%H:%M:%S')} - {transcript_message}\n")
        except FileNotFoundError:
            with open(file_path, 'w') as file:
                file.write(f"{datetime.now().strftime('%H:%M:%S')} - {transcript_message}\n")

    def get_transcript(
        self, num_lines: str | int = 10, target: str = "transcript"
    ) -> tuple[bool, list[dict[str, str]] | None]:
        # Returns an (ok, entries) tuple rather than a bare value: `ok` is
        # True whenever the read itself succeeded, `entries` is a (possibly
        # empty) list of {"timestamp", "message"} dicts in that case. This
        # keeps a genuinely empty/just-created log file (ok=True, entries=[])
        # distinguishable from a real I/O failure (ok=False, entries=None) --
        # both used to collapse to the same bare `None`.
        try:
            today_date = datetime.now().strftime('%Y-%m-%d')
            if self.mode == "test":
                transcript_path = os.path.join(self.logs_dir, f'{target}s', f'test_{target}.txt')
            else:
                transcript_path = os.path.join(self.logs_dir, f'{target}s', f'{today_date}_{target}.txt')
            os.makedirs(os.path.dirname(transcript_path), exist_ok = True)
            try:
                with open(transcript_path, 'r') as f:
                    num_lines = int(num_lines)
                    content = f.read().splitlines()[-num_lines:]
                    return True, [{"timestamp": line.split(' - ')[0], "message": ' - '.join(line.split(' - ')[1:])} for line in content]
            except FileNotFoundError:
                with open(transcript_path, 'w') as f:
                    f.write(f"{datetime.now().strftime('%H:%M:%S')} - {target} file created.\n")
                return True, []
        except Exception as e:
            self.add_to_transcript(f"Failed to read {target}: {e}", "ERROR")
            return False, None

    def _write_pid_file(self) -> None:
        try:
            (self.repo_root / PID_FILE_NAME).write_text(str(os.getpid()))
        except Exception as e:
            self.add_to_transcript(
                f"Failed to write PID file (stop_server.py will fall back to pattern-matching): {e}", "WARNING"
            )

    def launch_web_app(self) -> None:
        self.flask_app = create_flask_app(self)
        serve(self.flask_app, host = '127.0.0.1', port = 5000)

    def handle_shutdown(self, signum: int, frame: FrameType | None) -> None:
        self.add_to_transcript("Received shutdown signal. Stopping PRISM application...", "INFO")
        self.system_task_manager.stop()
        self.participant_manager.stop()
        Path(self.repo_root, PID_FILE_NAME).unlink(missing_ok = True)
        os._exit(0)

    def shutdown(self) -> None:
        self.handle_shutdown(signal.SIGINT, None)

# application entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Run the PRISM application.")
    parser.add_argument(
        '-mode', 
        choices = ['test', 'prod'], 
        default = 'test', 
        help = "Mode to run the application in. 'test' for development, 'prod' for production."
    )
    args = parser.parse_args()
    prism = PRISM(args.mode)