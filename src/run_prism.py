# Main runner for the PRISM application

import os
import platform
from datetime import datetime
from pathlib import Path
from _routes import create_flask_app
import pandas as pd
from waitress import serve
from _helper import clear
import signal
import argparse

from task_managers._system_task_manager import SystemTaskManager
from task_managers._participant_manager import ParticipantManager

class PRISM():
    def __init__(self, mode = "test"):
        if not os.path.dirname(os.path.abspath(__file__)).endswith('src'):
            self.add_to_transcript("Please run this script from the 'src' directory.", "ERROR")
            exit(1)
        
        clear()
        self.mode = mode
        self.start_time = datetime.now()
        self.load_paths()
        self.add_to_transcript("Initializing PRISM application...", "INFO")

        self.load_api_keys()

        self.system_task_manager = SystemTaskManager(self)
        self.participant_manager = ParticipantManager(self)

        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        self.add_to_transcript(f"PRISM started in {self.mode} mode.", "INFO")
        self.launch_web_app()

    # system methods

    def _resolve_drive_path(self, raw_path):
        # translates an "S:/..." literal (as written on the drive's own
        # paths.csv, which is authored from Windows) into this platform's
        # real path. Non-drive-letter (relative) values are returned as-is,
        # for the caller to resolve against config_base.
        raw_path = str(raw_path).strip()
        if platform.system() == 'Windows':
            return str(Path(raw_path))
        if len(raw_path) >= 2 and raw_path[1] == ':':
            raw_path = raw_path[2:].lstrip('/\\')
            return str((Path(self.drive_mount) / raw_path).resolve())
        return raw_path

    def load_paths(self, environment=None):
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
        repo_paths_defaults = {
            'logs_dir': 'logs',
            'drive_mount_windows': 'S:',
            'drive_mount_posix': '/mnt/research_drive',
            'prism_drive_subpath': 'optimize/prism',
        }
        try:
            df = pd.read_csv(str(repo_root / 'config' / 'repo_paths.csv'), quotechar='"', skipinitialspace=True, dtype=str)
            repo_paths = {str(row['key']).strip(): str(row['value']).strip() for _, row in df.iterrows()}
        except Exception:
            repo_paths = {}
        repo_paths = {**repo_paths_defaults, **repo_paths}

        # logs stay local to this checkout (per-machine operational data,
        # not shared study config) — set first so add_to_transcript (called
        # right after this) always has somewhere to write.
        self.logs_dir = str((repo_root / repo_paths['logs_dir']).resolve())
        self.drive_mount = repo_paths['drive_mount_windows'] if platform.system() == 'Windows' else repo_paths['drive_mount_posix']

        # environment marker: a git-ignored, single-line file at the repo
        # root containing "dev" or "prod", selecting which paths.csv (and
        # everything under its config_base) this checkout loads from. This
        # stays gitignored (unlike repo_paths.csv above) because it's a
        # per-deployment choice, not something every checkout should share.
        # Defaults to "dev" (the safer default) if missing. Callers that
        # need to resolve a specific environment regardless of the marker
        # (e.g. tests_integration/test_environment_files.py, which checks
        # both "dev" and "prod" in the same run) can pass `environment`
        # directly instead.
        if environment:
            self.environment = environment
        else:
            env_file = repo_root / 'environment'
            self.environment = 'dev'
            if env_file.exists() and env_file.read_text().strip():
                self.environment = env_file.read_text().strip()
            else:
                self.add_to_transcript(f"No environment file at {env_file} (or it's empty) — defaulting to 'dev'.", "WARNING")

        paths_csv = self._resolve_drive_path(f"S:/{repo_paths['prism_drive_subpath']}/{self.environment}/config/paths.csv")
        try:
            df = pd.read_csv(paths_csv, quotechar='"', skipinitialspace=True, dtype=str)
            raw = {str(row['key']).strip(): str(row['path']).strip() for _, row in df.iterrows()}
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
            resolved = self._resolve_drive_path(value)
            if not Path(resolved).is_absolute():
                resolved = str((Path(self.config_base) / resolved).resolve())
            setattr(self, attr, resolved)

        # These used to be separate paths.csv/paths.api entries; they now
        # live directly under config_base/config/ alongside everything else.
        config_dir = Path(self.config_base) / 'config'
        self.followmee_coords_path = str(config_dir / 'followmee_coords.csv')
        self.system_task_schedule_path = str(config_dir / 'system_task_schedule.csv')
        self.study_coordinators_path = str(config_dir / 'study_coordinators.csv')
        self.script_pipeline_path = str(config_dir / 'script_pipeline.csv')

    # sane defaults for fields that may not exist yet in an older api CSV
    # (e.g. the message columns, added after qualtrics.api files already
    # existed on the drive) — load_keys only overwrites these if the column
    # is actually present, so one missing column doesn't take down the
    # whole file's worth of fields.
    API_FIELD_DEFAULTS = {
        'ema_message': "Hello, it's time to take your daily survey.",
        'ema_reminder_message': "Hello, you have not yet completed your daily survey for today.",
        'feedback_message': "Hello, it's time to see your daily recovery message.",
        'feedback_reminder_message': "Hello, you have not yet viewed your daily recovery message for today.",
        'coordinator_alert_message': "{name}: {task_type} #{task_number} {outcome}. Script was executed at {task_start}.",
    }

    def load_api_keys(self):
        api_dir = Path(self.config_base) / 'api'
        for attr, default in self.API_FIELD_DEFAULTS.items():
            setattr(self, attr, default)

        def load_keys(file_name, field_map, label):
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
            'qualtrics_api_token': 'api_token',
            'qualtrics_data_center': 'datacenter',
            'ema_survey_id': 'ema_survey_id',
            'feedback_survey_id': 'feedback_survey_id',
            'ema_message': 'ema_message',
            'ema_reminder_message': 'ema_reminder_message',
            'feedback_message': 'feedback_message',
            'feedback_reminder_message': 'feedback_reminder_message'
        }, "Qualtrics")
        load_keys('followmee.api', {
            'followmee_username': 'username',
            'followmee_api_token': 'api_token'
        }, "FollowMee")
        load_keys('twilio.api', {
            'twilio_account_sid': 'account_sid',
            'twilio_auth_token': 'auth_token',
            'twilio_from_number': 'from_number',
            'coordinator_alert_message': 'coordinator_alert_message'
        }, "Twilio")

    def add_to_transcript(self, message, message_type = "INFO"):
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

    def get_transcript(self, num_lines = 10, target = "transcript"):
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

    def launch_web_app(self):
        self.flask_app = create_flask_app(self)
        serve(self.flask_app, host = '127.0.0.1', port = 5000)

    def handle_shutdown(self, signum, frame):
        self.add_to_transcript("Received shutdown signal. Stopping PRISM application...", "INFO")
        self.system_task_manager.stop()
        self.participant_manager.stop()
        os._exit(0)

    def shutdown(self):
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