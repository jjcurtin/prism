# task to push processed data to the research drive (already mounted --
# Windows: drive letter per config/repo_paths.csv's drive_mount_windows,
# Linux: CIFS mount at drive_mount_posix -- both resolved into
# self.app.drive_mount by run_prism.py::load_paths())

import platform
import subprocess
from pathlib import Path

from system_tasks._system_task import SystemTask

class PushDataToResearchDrive(SystemTask):
    def upload_files(self):
        source_paths = [
                "../data"
            ]
        for source_path in source_paths:
            source_path = Path(source_path)
            source_folder = source_path.name
            destination_folder = Path(self.app.drive_mount) / self.app.destination_path / source_folder
            try:
                destination_folder.mkdir(parents = True, exist_ok = True)
            except Exception as e:
                self.app.add_to_transcript(f"ERROR: Failed to create destination directory {destination_folder} on Research Drive. Error: {str(e)}", "ERROR")
                return 1

            try:
                if platform.system() == 'Windows':
                    result = subprocess.run(
                        ['robocopy', str(source_path), str(destination_folder), '/MIR'],
                        capture_output = True, text = True
                    )
                    # robocopy exit codes are a bitmask: 0-7 are various
                    # degrees of success (files copied/extra/mismatched), 8+
                    # means at least one file failed to copy or a more
                    # serious error occurred.
                    if result.returncode >= 8:
                        self.app.add_to_transcript(f"ERROR: robocopy reported failure copying {source_folder} to Research Drive (exit code {result.returncode}). {result.stderr.strip()}", "ERROR")
                        return 1
                else:
                    # rsync mirrors the *contents* of source_path into
                    # destination_folder only when source_path has a
                    # trailing slash -- without it, rsync would nest a
                    # source_path-named subdirectory inside
                    # destination_folder instead of mirroring into it.
                    result = subprocess.run(
                        ['rsync', '-a', '--delete', str(source_path) + '/', str(destination_folder)],
                        capture_output = True, text = True
                    )
                    if result.returncode != 0:
                        self.app.add_to_transcript(f"ERROR: rsync reported failure copying {source_folder} to Research Drive (exit code {result.returncode}). {result.stderr.strip()}", "ERROR")
                        return 1
            except Exception as e:
                self.app.add_to_transcript(f"ERROR: Failed to copy {source_folder} to Research Drive. Error: {str(e)}", "ERROR")
                return 1
            self.app.add_to_transcript(f"INFO: {source_folder} copied to Research Drive.")
        return 0

    def run(self):
        self.task_type = "PUSH_DATA_TO_RESEARCH_DRIVE"

        if self.upload_files() != 0:
            return 1

        return 0
