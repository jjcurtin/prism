"""This file checks the system to make sure components work"""

import os
import shutil
import threading

from system_tasks._system_task import SystemTask

# os.path.ismount()/os.listdir() have no native timeout -- on a stale
# network mount they can block for minutes (empirically measured: 267s on
# a real stale CIFS mount) or, in a worse network-hang scenario,
# indefinitely. Since check_research_drive() runs synchronously on
# whichever TaskManager.run() thread called it, an unbounded hang here
# freezes that entire manager's pipeline (every other scheduled system
# task) for as long as it lasts. 20s is well under the observed real-world
# hang duration, so this proactively gives up and reports failure instead
# of passively waiting minutes.
DRIVE_CHECK_TIMEOUT_SECONDS = 20

class CheckSystem(SystemTask):
    def run(self) -> int:
        self.task_type = "CHECK_SYSTEM"
        self.app.add_to_transcript(f"{self.task_type} #{self.task_number} initiated.")
        research_drive_check = self.check_research_drive()
        rscript_check = self.check_rscript_available()
        participant_check = self.check_participants()
        return research_drive_check + rscript_check + participant_check

    def check_research_drive(self) -> int:
        if self.app.mode == "prod":
            self.app.add_to_transcript(f"INFO: Now checking Research Drive connection...")
            raw_drive_mount = getattr(self.app, 'drive_mount', None)
            if not raw_drive_mount:
                self.app.add_to_transcript("Failed to connect to Research Drive: drive_mount is not set.", "ERROR")
                return 1
            # A distinct, single-assignment, explicitly-str-typed name --
            # getattr(..., None) widens the type past App.drive_mount's own
            # `str` declaration (_types.py) to `Any | None`, and reusing
            # the same variable name for a narrowed reassignment doesn't
            # reliably narrow it inside the nested _run_probe() closure
            # below (mypy infers one unified type per variable per
            # function scope, not a flow-sensitive one per assignment).
            drive_mount: str = str(raw_drive_mount)
            # The research drive is assumed pre-mounted (config/README.md) --
            # this just confirms the mount point is actually there and
            # listable, rather than attempting to mount it ourselves.
            # os.path.ismount() alone isn't reliable for network shares on
            # every platform/filesystem, so also fail if the directory can't
            # be listed (e.g. present but not actually connected/stale).
            #
            # Run on a daemon thread with a hard deadline (Thread.join's
            # timeout) rather than calling these directly: neither
            # os.path.ismount() nor os.listdir() can be cancelled or given
            # a native timeout, so a stale/unresponsive mount can block for
            # minutes (or indefinitely). Plain threading.Thread(daemon=True)
            # rather than concurrent.futures.ThreadPoolExecutor: an
            # abandoned ThreadPoolExecutor worker is NOT a daemon thread, so
            # Python's atexit machinery (concurrent.futures.thread._python_
            # exit) unconditionally joins it with no timeout at interpreter
            # shutdown -- a probe truly stuck forever would then block
            # PRISM's own process exit too. A daemon thread is killed
            # outright at interpreter shutdown instead of joined, so an
            # abandoned probe can never block PRISM from exiting.
            result: dict[str, object] = {}

            def _run_probe() -> None:
                try:
                    result['mounted'] = self._probe_research_drive(drive_mount)
                except Exception as e:
                    result['error'] = e

            probe_thread = threading.Thread(target = _run_probe, daemon = True)
            probe_thread.start()
            probe_thread.join(timeout = DRIVE_CHECK_TIMEOUT_SECONDS)

            if probe_thread.is_alive():
                self.app.add_to_transcript(
                    f"Failed to connect to Research Drive: {drive_mount} did not respond within "
                    f"{DRIVE_CHECK_TIMEOUT_SECONDS}s -- mount may be stale.",
                    "ERROR",
                )
                return 1
            # is_alive() is False here, meaning _run_probe has fully
            # completed (including its write to `result`) -- safe to read
            # without any further synchronization.
            if 'error' in result:
                self.app.add_to_transcript(f"Failed to connect to Research Drive: {result['error']}", "ERROR")
                return 1
            if not result.get('mounted'):
                self.app.add_to_transcript(f"Failed to connect to Research Drive: {drive_mount} does not exist.", "ERROR")
                return 1
            self.app.add_to_transcript("INFO: Successfully connected to Research Drive.")
        return 0

    @staticmethod
    def _probe_research_drive(drive_mount: str) -> bool:
        """Runs on the daemon thread started by check_research_drive()
        above -- kept as a plain function (no self.app access) so it has no
        shared state to race against the caller if it ends up abandoned
        past the timeout.
        """
        mounted = os.path.ismount(drive_mount) or os.path.isdir(drive_mount)
        if not mounted:
            return False
        os.listdir(drive_mount)
        return True

    def check_rscript_available(self) -> int:
        """Unlike check_research_drive above, not gated on mode == "prod" --
        RUN_R_SCRIPT tasks can be scheduled and tested in either mode, and
        this is genuinely a live runtime-environment concern (is R actually
        installed and is its bin/ directory, containing the Rscript
        executable, on PATH), not a static local-file check the way the
        removed check_file_system was -- same class of dependency as the
        research drive connection, just for a local binary instead of a
        network mount. shutil.which() uses the same PATH-resolution logic
        subprocess.run(['Rscript', ...]) itself relies on (_run_r_script.py),
        so this catches the exact failure mode before a scheduled script
        ever tries to run and fails with a Windows [WinError 2]/POSIX
        FileNotFoundError instead.
        """
        self.app.add_to_transcript("INFO: Now checking Rscript availability...")
        if shutil.which('Rscript') is None:
            self.app.add_to_transcript(
                "Rscript executable not found on PATH -- RUN_R_SCRIPT tasks will fail. "
                "Is R installed on this machine, and is its bin/ directory (containing "
                "Rscript.exe) on PATH?",
                "ERROR",
            )
            return 1
        return 0

    def check_participants(self) -> int:
        self.app.add_to_transcript("INFO: Now checking participants...")

        # unique id check
        participants = self.app.participant_manager.get_participants()
        unique_ids: dict[str, list[str]] = {}
        for p in participants:
            unique_id = p.get('unique_id')
            if unique_id:
                if unique_id in unique_ids:
                    unique_ids[unique_id].append(p['initials'] + " " + p['subid'])
                else:
                    unique_ids[unique_id] = [p['initials'] + " " + p['subid']]
        duplicates = {uid: names for uid, names in unique_ids.items() if len(names) > 1}
        if duplicates:
            self.app.add_to_transcript("Duplicate unique IDs found among participants:", "ERROR")
            for uid, names in duplicates.items():
                self.app.add_to_transcript(f"Unique ID: {uid}, Participants: {', '.join(names)}", "ERROR")
            self.app.add_to_transcript("Please remedy these issues either through this interface or in the CSV file and refresh from CSV when you are ready.", "ERROR")
            return 1
        return 0