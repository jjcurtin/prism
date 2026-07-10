"""This file checks the system to make sure components work"""

import os

import requests
from requests.exceptions import RequestException

from system_tasks._system_task import SystemTask

class CheckSystem(SystemTask):
    def run(self):
        self.task_type = "CHECK_SYSTEM"
        self.app.add_to_transcript(f"{self.task_type} #{self.task_number} initiated.")
        file_system_check = self.check_file_system()
        qualtrics_check = self.check_qualtrics()
        followmee_check = self.check_followmee()
        research_drive_check = self.check_research_drive()
        participant_check = self.check_participants()
        return (
            file_system_check + qualtrics_check + followmee_check
            + research_drive_check + participant_check
        )

    def check_file_system(self):
        self.app.add_to_transcript(f"INFO: Now checking file system...")
        try:
            directories = [
                '../data',
                '../scripts',
                '../logs',
                'system_tasks'
            ]
            files = [
                [], # data
                [], # scripts
                [], # logs
                ['_check_system.py', # obviously
                 '_pulldown_qualtrics_data.py', '_pulldown_followmee_data.py',
                 '_system_task.py' # obviously
                ] # tasks
            ]

            all_present = True
            for index, (directory, files_list) in enumerate(zip(directories, files)):
                if not os.path.exists(directory):
                    self.app.add_to_transcript(f"The '{directory}' directory is missing.", "ERROR")
                    all_present = False
                for file in files_list:
                    file_path = os.path.join(directory, file)
                    if not os.path.isfile(file_path):
                        self.app.add_to_transcript(f"The file '{file_path}' is missing.", "ERROR")
                        all_present = False

            # these live on the drive-sourced config_base, not locally under
            # ../config (config/README.md, 2026-07-09 migration) -- check the
            # paths PRISM itself already resolved rather than a local guess.
            drive_sourced_paths = [
                'system_task_schedule_path', 'study_coordinators_path',
                'participants_path'
            ]
            for attr in drive_sourced_paths:
                path = getattr(self.app, attr, None)
                if not path or not os.path.isfile(path):
                    self.app.add_to_transcript(f"The file for '{attr}' ({path}) is missing.", "ERROR")
                    all_present = False

            if not all_present:
                return 1

        except Exception as e:
            self.app.add_to_transcript(f"Error checking file system: {e}", "ERROR")
            return 1

        return 0
    
    def check_qualtrics(self):
        self.app.add_to_transcript(f"INFO: Now checking Qualtrics connection...")
        survey_id = self.app.ema_survey_id
        data_center = self.app.qualtrics_data_center
        api_token = self.app.qualtrics_api_token
        url = f"https://{data_center}.qualtrics.com/API/v3/survey-definitions/{survey_id}/metadata"
        headers = {"X-API-TOKEN": api_token}
        try:
            response = requests.get(url, headers = headers, timeout = 10)
            if response.status_code == 200:
                return 0
            self.app.add_to_transcript(f"Status code: {response.status_code}", "ERROR")
            return 1
        except RequestException as e:
            self.app.add_to_transcript(f"Connection error occurred: {str(e)}", "ERROR")
            return 1

    def check_followmee(self):
        self.app.add_to_transcript(f"INFO: Now checking FollowMee connection...")
        username = self.app.followmee_username
        api_key = self.app.followmee_api_token
        url = f"https://www.followmee.com/api/info.aspx?key={api_key}&username={username}&function=devicelist"
        try:
            response = requests.get(url, timeout = 10)
            if response.status_code == 200:
                return 0
            self.app.add_to_transcript(f"FollowMee connection failed. Status code: {response.status_code}", "ERROR")
            return 1
        except RequestException as e:
            self.app.add_to_transcript(f"FollowMee connection error occurred: {str(e)}", "ERROR")
            return 1
        
    def check_research_drive(self):
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
    
    def check_participants(self):
        self.app.add_to_transcript("INFO: Now checking participants...")
        
        # unique id check
        participants = self.app.participant_manager.get_participants()
        unique_ids = {}
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