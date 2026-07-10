"""This file checks the system to make sure components work"""

import os
import shutil

from system_tasks._system_task import SystemTask

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
            drive_mount = getattr(self.app, 'drive_mount', None)
            if not drive_mount:
                self.app.add_to_transcript("Failed to connect to Research Drive: drive_mount is not set.", "ERROR")
                return 1
            # The research drive is assumed pre-mounted (config/README.md) --
            # this just confirms the mount point is actually there and
            # listable, rather than attempting to mount it ourselves.
            # os.path.ismount() alone isn't reliable for network shares on
            # every platform/filesystem, so also fail if the directory can't
            # be listed (e.g. present but not actually connected/stale).
            try:
                mounted = os.path.ismount(drive_mount) or os.path.isdir(drive_mount)
                if not mounted:
                    self.app.add_to_transcript(f"Failed to connect to Research Drive: {drive_mount} does not exist.", "ERROR")
                    return 1
                os.listdir(drive_mount)
            except Exception as e:
                self.app.add_to_transcript(f"Failed to connect to Research Drive: {e}", "ERROR")
                return 1
            self.app.add_to_transcript("INFO: Successfully connected to Research Drive.")
        return 0

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