"""Main runner for the PRISM application"""

import os
import platform
import subprocess
import sys
import time
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


# There is deliberately no "must run from src/" startup guard. There used
# to be two versions of one: the original compared __file__'s own on-disk
# location (fixed by the checkout layout, so it could never actually fail
# regardless of invocation directory -- a no-op that happened to never
# fire), and a later replacement did a real os.getcwd() check that DID
# fire -- and broke `python src/run_prism.py` run from the repo root,
# which used to "work" (i.e. never hit the no-op guard). Neither version's
# underlying premise holds: Python puts a script's own directory on
# sys.path[0] regardless of the launching shell's cwd (verified), so every
# sibling import below (`from _routes import ...`, `from _helper import
# ...`, `task_managers.*`) already resolves the same way no matter where
# this is launched from. And every filesystem path this program touches is
# anchored to `repo_root` (derived from `__file__`, see load_paths() below)
# or to the drive-mount config, never to a bare cwd-relative literal
# (verified: no relative `open(...)`/`Path('...')`/`os.path.join('...` in
# src/). cwd is not a real requirement of this program. If a genuinely
# cwd-relative path is ever found, that path is the bug -- anchor it,
# don't reintroduce this guard to paper over it.

# Written to repo_root on startup, read (and removed) by stop_server.py --
# a precise, PID-targeted alternative to the old pattern-matching
# `pkill -f run_prism.py`, which would also kill any unrelated process
# whose command line merely contained that string (e.g. `vim run_prism.py`,
# a second checkout's server, a grep). Also read at startup itself (see
# PRISM._acquire_pid_file) to refuse a second launch while a first is
# still live, rather than just overwriting it.
PID_FILE_NAME = '.run_prism.pid'

# A separate, short-lived lock file spanning _acquire_pid_file's entire
# read-check-write critical section -- found by an external adversarial
# review: reading PID_FILE_NAME, liveness-checking it, and writing it back
# were three separate steps with no lock across them, leaving a genuine
# TOCTOU race window where two near-simultaneous launches could both read
# "no live PID" and both proceed to construct their managers -- exactly the
# double-launch scenario _acquire_pid_file exists to prevent. Uses
# os.O_CREAT | os.O_EXCL (atomic create-if-absent on POSIX *and* Windows --
# Python's os.open translates this to CreateFile's CREATE_NEW flag there,
# no msvcrt-specific code needed) on its own file rather than on
# PID_FILE_NAME directly, so the existing stale-PID-file tolerance
# (overwrite a dead-process's recorded PID) doesn't need to change shape.
PID_LOCK_FILE_NAME = '.run_prism.pid.lock'
# Generous relative to the critical section it guards (a few filesystem
# calls, sub-millisecond in practice) -- this is contention time, not
# processing time, so a real second launch should never need anywhere
# close to this long to get in.
PID_LOCK_ACQUIRE_TIMEOUT_SECONDS = 2.0
# A lock file older than this is treated as abandoned (e.g. a crash between
# creating the lock and its own `finally: unlink()`), not real contention --
# mirrors _acquire_pid_file's own stale-PID-file tolerance, applied to the
# lock file itself so a single crash can't permanently wedge every future
# launch.
PID_LOCK_STALE_AGE_SECONDS = 30.0


def _acquire_pid_lock(repo_root: Path) -> int:
    """Blocks (briefly) until the exclusive lock file can be created,
    self-healing past a stale lock rather than ever waiting past
    PID_LOCK_STALE_AGE_SECONDS. Returns the open file descriptor -- caller
    is responsible for os.close()-ing it and unlinking the lock file
    (see _acquire_pid_file's `finally`).
    """
    lock_path = Path(repo_root, PID_LOCK_FILE_NAME)
    deadline = time.monotonic() + PID_LOCK_ACQUIRE_TIMEOUT_SECONDS
    while True:
        try:
            return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                time.sleep(0.01)  # lock file vanished between the failed open and this stat -- brief pause, not a busy-spin, before retrying
                continue
            if age > PID_LOCK_STALE_AGE_SECONDS:
                lock_path.unlink(missing_ok = True)
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"could not acquire {lock_path} within {PID_LOCK_ACQUIRE_TIMEOUT_SECONDS}s "
                    "(another instance may be starting concurrently)"
                )
            time.sleep(0.02)


def _pid_is_alive(pid: int) -> bool:
    """Cross-platform liveness check for a PID recorded in PID_FILE_NAME.

    POSIX: os.kill(pid, 0) sends no signal, just probes existence --
    raises ProcessLookupError for a dead PID, succeeds (or raises
    PermissionError, still "exists") for a live one.

    Windows has no os.kill(pid, 0) equivalent; `tasklist` is already this
    codebase's convention for Windows process inspection (see
    stop_server.py's Windows branch).

    pid <= 0 is treated as dead outright rather than probed: os.getpid()
    never returns one, so the only way _acquire_pid_file would ever pass
    one in is a corrupted PID file (e.g. literally "0" or "-1"). POSIX
    os.kill(pid, 0) treats those as process-group/broadcast signals, not
    single-PID probes -- pid 0 targets this process's own group (would
    return True, since the caller's own process is always "alive"), and a
    negative pid targets the process group named by its absolute value --
    neither answers "is PID <pid> alive", so probing would silently
    misreport a corrupted file as a live instance and refuse to start
    indefinitely instead of the existing "stale file, warn and proceed"
    path a genuinely dead recorded PID already takes.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output = True, text = True, timeout = 5,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else
    except OSError:
        return False
    return True


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

    def __init__(self, mode: str = "silent") -> None:
        clear()
        self.mode = mode
        self.start_time = datetime.now()
        self.load_paths()
        self._acquire_pid_file()
        self.add_to_transcript("Initializing PRISM application...", "INFO")

        self.load_api_keys()

        # Registered before either manager is constructed -- both start a
        # non-daemon background thread immediately, so a SIGINT/SIGTERM
        # landing between construction and registration used to have no
        # handler installed yet: it killed the main thread while those
        # threads kept running the schedule headless, the exact
        # zombie-process shape _acquire_pid_file()'s docstring describes
        # for the double-launch case, just reached a different way.
        # handle_shutdown() guards each manager with hasattr() to tolerate
        # the (now much narrower) case where a signal arrives before the
        # managers below have been constructed yet.
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        self.system_task_manager = SystemTaskManager(self)
        self.participant_manager = ParticipantManager(self)

        self.add_to_transcript(f"PRISM started in {self.mode} mode.", "INFO")
        self._launch_web_app_or_shutdown()

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
        repo_paths_load_error: Exception | None = None
        try:
            df = pd.read_csv(str(repo_root / 'config' / 'repo_paths.csv'), quotechar='"', skipinitialspace=True, dtype=str)
            repo_paths: dict[str, str] = {str(row['key']).strip(): str(row['value']).strip() for _, row in df.iterrows()}
        except Exception as e:
            repo_paths = {}
            repo_paths_load_error = e
        repo_paths = {**repo_paths_defaults, **repo_paths}

        # logs stay local to this checkout (per-machine operational data,
        # not shared study config) — set first so add_to_transcript (called
        # right after this) always has somewhere to write.
        self.logs_dir = str((repo_root / repo_paths['logs_dir']).resolve())
        # Logged here, not inside the try/except above -- add_to_transcript
        # reads self.logs_dir directly with no guard of its own, which
        # isn't set until the line just above this one. Found by an
        # external adversarial review: this fallback used to be entirely
        # silent (a bare `except Exception: repo_paths = {}`, no transcript
        # line at all), unlike the paths.csv load just below, which already
        # logs an ERROR on failure -- a corrupted or unreadable
        # repo_paths.csv would silently fall back to every default (logs_dir
        # 'logs', drive mounts, etc.) with nothing in the transcript
        # pointing at why.
        if repo_paths_load_error is not None:
            self.add_to_transcript(
                f"Failed to load repo_paths.csv ({repo_root / 'config' / 'repo_paths.csv'}): "
                f"{repo_paths_load_error} -- falling back to defaults ({repo_paths_defaults}).", "WARNING"
            )
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
            if len(df) == 0:
                # A header-only CSV (no data row) has every column but no
                # row 0 -- df.loc[0, column] below would raise KeyError: 0,
                # uncaught (this whole method is called bare from
                # __init__), crashing server startup entirely. Treated the
                # same as a missing column: every field in this file left
                # at its default/unset, same WARNING path.
                self.add_to_transcript(f"{label} API file {file_name} has no data row — all its fields left unset.", "WARNING")
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
        if self.mode == "silent":
            # Dated the same as live mode's file (below) -- silent mode is
            # the stated default day-to-day mode, so an unrotated single
            # file here grew unbounded while live mode rotated daily.
            # get_transcript()'s read path builds this same name; keep the
            # two in sync.
            file_path = os.path.join(self.logs_dir, 'transcripts', f'{current_date}_silent_transcript.txt')
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
            if self.mode == "silent":
                # Must match add_to_transcript()'s write-side filename above.
                transcript_path = os.path.join(self.logs_dir, f'{target}s', f'{today_date}_silent_{target}.txt')
            else:
                transcript_path = os.path.join(self.logs_dir, f'{target}s', f'{today_date}_{target}.txt')
            os.makedirs(os.path.dirname(transcript_path), exist_ok = True)
            try:
                with open(transcript_path, 'r') as f:
                    num_lines = int(num_lines)
                    # Found by an external adversarial review, confirmed
                    # live: content[-num_lines:] silently does the wrong
                    # thing for a non-positive num_lines rather than
                    # raising -- a negative value (e.g. -3) slices from the
                    # FRONT instead ("everything except the first 3 lines",
                    # not "the last -3 lines"), and 0 returns the ENTIRE
                    # file (`-0 == 0` in Python, so content[-0:] ==
                    # content[0:]) instead of "no lines". Both are
                    # reachable directly from the API
                    # (GET /system/get_transcript/<num_lines>, a raw
                    # unvalidated path string). Rejected the same way a
                    # non-numeric num_lines already is (caught by the
                    # outer except ValueError-from-int() below).
                    if num_lines <= 0:
                        raise ValueError(f"num_lines must be a positive integer, got {num_lines}")
                    content = f.read().splitlines()[-num_lines:]
                    return True, [{"timestamp": line.split(' - ')[0], "message": ' - '.join(line.split(' - ')[1:])} for line in content]
            except FileNotFoundError:
                with open(transcript_path, 'w') as f:
                    f.write(f"{datetime.now().strftime('%H:%M:%S')} - {target} file created.\n")
                return True, []
        except Exception as e:
            self.add_to_transcript(f"Failed to read {target}: {e}", "ERROR")
            return False, None

    def _acquire_pid_file(self) -> None:
        """Refuses to start if the PID file already names a live process --
        the actual fix for a double-launch producing a headless zombie, not
        just a nice-to-have: called before self.system_task_manager/
        self.participant_manager are constructed (see __init__ below), so a
        refused start never spins up their background threads at all.

        Found by an external adversarial review: a second launch used to
        just overwrite the PID file and continue constructing everything.
        If its own later launch_web_app() then failed (port already bound
        by the first instance), nothing caught that failure (a separate,
        following fix wraps launch_web_app() itself as defense in depth
        for the cases this check can't prevent -- e.g. a port held by an
        unrelated process, not another PRISM instance): the second
        instance's main thread died while its two non-daemon manager
        threads -- already fully loaded with the participant schedule --
        kept running headless, silently duplicate-firing every scheduled
        SMS to every participant at the next midnight run_today reset.
        Refusing to construct the managers at all, here, is what actually
        closes this off for the common case (two launches of the same
        PRISM instance).

        A stale file (naming a PID that's no longer running -- e.g. a
        prior crash that skipped clean shutdown) is tolerated: logged as a
        WARNING and overwritten with this process's own PID, same as
        before this check existed.

        The read-check-write sequence below runs while holding
        PID_LOCK_FILE_NAME (see _acquire_pid_lock) -- found by an external
        adversarial review: without a lock spanning all three steps, two
        near-simultaneous launches could both read "no live PID" and both
        proceed to construct their managers, which is exactly the
        double-launch scenario this whole method exists to prevent. The
        lock only serializes THIS method's brief critical section; it is
        released (and its file removed) before this method returns, one
        way or another.
        """
        pid_file = Path(self.repo_root, PID_FILE_NAME)
        try:
            lock_fd = _acquire_pid_lock(self.repo_root)
        except TimeoutError as e:
            self.add_to_transcript(f"Refusing to start: {e}.", "ERROR")
            exit(1)
        try:
            try:
                recorded_pid: int | None = int(pid_file.read_text().strip())
            except (FileNotFoundError, ValueError, OSError):
                recorded_pid = None

            if recorded_pid is not None and _pid_is_alive(recorded_pid):
                self.add_to_transcript(
                    f"Refusing to start: {pid_file} names process {recorded_pid}, which is "
                    "still running. Stop it first (stop_server.py), or remove the PID file "
                    "yourself if you're certain it's stale.", "ERROR"
                )
                exit(1)

            if recorded_pid is not None:
                self.add_to_transcript(
                    f"PID file named a no-longer-running process ({recorded_pid}) -- replacing it.", "WARNING"
                )

            try:
                pid_file.write_text(str(os.getpid()))
            except Exception as e:
                self.add_to_transcript(
                    f"Failed to write PID file (stop_server.py will fall back to pattern-matching): {e}", "WARNING"
                )
        finally:
            os.close(lock_fd)
            Path(self.repo_root, PID_LOCK_FILE_NAME).unlink(missing_ok = True)

    def launch_web_app(self) -> None:
        self.flask_app = create_flask_app(self)
        serve(self.flask_app, host = '127.0.0.1', port = 5000)

    def _launch_web_app_or_shutdown(self) -> None:
        """Defense in depth for whatever _acquire_pid_file's liveness check
        doesn't catch -- e.g. a port already held by an unrelated process,
        not another PRISM instance, so there's no PID file to refuse on.

        Found by the same external adversarial review as _acquire_pid_file:
        an exception escaping launch_web_app() (e.g. OSError: Address
        already in use) used to just kill this thread (Python's main
        thread, on an uncaught exception) -- the two non-daemon manager
        threads, started earlier in __init__ and already fully loaded with
        the schedule, would keep running headless indefinitely (verified
        directly: a non-daemon thread survives an uncaught exception in the
        main thread). handle_shutdown already stops both managers and
        unlinks the PID file (now ownership-checked); reused as-is here
        rather than writing a second shutdown path.
        """
        try:
            self.launch_web_app()
        except Exception as e:
            self.add_to_transcript(
                f"Web server failed to start or crashed: {e} -- shutting down task managers "
                "so no headless instance keeps processing the schedule.", "ERROR"
            )
            self.handle_shutdown(signal.SIGTERM, None, exit_code = 1)

    def _unlink_pid_file_if_owned(self) -> None:
        """Only removes the PID file if it currently names THIS process.

        Found by an external adversarial review of the double-launch
        scenario: the old unconditional unlink() meant a second instance
        launched while a first was still running -- which, before
        _acquire_pid_file's liveness check existed, clobbered the first's
        PID file unconditionally -- would, on its own later shutdown,
        delete a file that had already stopped being "its" file, leaving
        the ORIGINAL still-live instance with no PID file at all and
        untargetable by stop_server.py's precise path, forcing it onto the
        blind pattern-match fallback instead. _acquire_pid_file now
        prevents the clobber itself; this check is defense in depth for
        any other path that still leaves a stale/foreign PID recorded.
        """
        pid_file = Path(self.repo_root, PID_FILE_NAME)
        try:
            recorded_pid = int(pid_file.read_text().strip())
        except (FileNotFoundError, ValueError, OSError):
            return
        if recorded_pid != os.getpid():
            self.add_to_transcript(
                f"PID file names process {recorded_pid}, not this process ({os.getpid()}) -- "
                "leaving it in place; a later-launched instance must have overwritten it.", "WARNING"
            )
            return
        pid_file.unlink(missing_ok = True)

    def handle_shutdown(self, signum: int, frame: FrameType | None, exit_code: int = 0) -> None:
        """`exit_code` defaults to 0 -- a real SIGINT/SIGTERM (the normal
        case: signal.signal registers this directly, so signum/frame must
        stay the first two positional params) is a clean, requested
        shutdown. _launch_web_app_or_shutdown passes exit_code=1: before
        this parameter existed, a launch failure and a clean shutdown were
        indistinguishable at the process-exit-code level (both ended in
        the same unconditional os._exit(0)) even though the ERROR
        transcript line already told them apart -- any process supervisor
        driven by exit code (not this codebase today, but a plausible
        future systemd/supervisor wrapper) couldn't tell a failed launch
        from a successful one asked to stop.
        """
        self.add_to_transcript("Received shutdown signal. Stopping PRISM application...", "INFO")
        # hasattr-guarded: signal handlers are now registered before either
        # manager is constructed (see __init__), so a signal in that brief
        # window would otherwise hit an AttributeError here instead of
        # shutting down cleanly.
        if hasattr(self, 'system_task_manager'):
            self.system_task_manager.stop()
        if hasattr(self, 'participant_manager'):
            self.participant_manager.stop()
        self._unlink_pid_file_if_owned()
        os._exit(exit_code)

    def shutdown(self) -> None:
        self.handle_shutdown(signal.SIGINT, None)

# application entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = "Run the PRISM application.")
    parser.add_argument(
        '-mode',
        choices = ['silent', 'live'],
        default = 'silent',
        help = "Mode to run the application in. 'silent' does not send real texts. 'live' does."
    )
    args = parser.parse_args()
    prism = PRISM(args.mode)