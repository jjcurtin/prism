"""This file checks the system to make sure components work"""

import os

from system_tasks._system_task import SystemTask

class CheckSystem(SystemTask):
    def run(self) -> int:
        self.task_type = "CHECK_SYSTEM"
        self.app.add_to_transcript(f"{self.task_type} #{self.task_number} initiated.")
        research_drive_check = self.check_research_drive()
        participant_check = self.check_participants()
        return research_drive_check + participant_check

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