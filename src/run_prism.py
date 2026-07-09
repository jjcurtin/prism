# Main runner for the PRISM application

import os
from datetime import datetime
from pathlib import Path
from _routes import create_flask_app
import pandas as pd
from waitress import serve
from _helper import clear
import signal
from pyngrok import ngrok
import subprocess
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

    def load_paths(self):
        # repo root is the parent of this file's directory (src/)
        repo_root = Path(__file__).resolve().parent.parent
        # sane defaults in case config/paths.api is missing or unreadable, so
        # add_to_transcript (called immediately after this) always has a
        # logs_dir to write to.
        defaults = {
            'logs_dir': 'logs',
            'participants_path': 'config/study_participants.csv',
            'reminders_path': 'config/reminders.csv',
            'followmee_coords_path': 'config/followmee_coords.csv',
            'system_task_schedule_path': 'config/system_task_schedule.csv',
            'study_coordinators_path': 'config/study_coordinators.csv',
            'r_scripts_dir': '../proj_optimize/automation',
            'script_pipeline_path': 'config/script_pipeline.csv',
        }
        for name, rel_path in defaults.items():
            setattr(self, name, str((repo_root / rel_path).resolve()))
        try:
            df = pd.read_csv('../config/paths.api', quotechar='"')
            for column in df.columns:
                setattr(self, column, str((repo_root / df.loc[0, column]).resolve()))
        except Exception as e:
            self.add_to_transcript(f"Failed to load paths configuration from ../config/paths.api, using defaults: {e}", "WARNING")

    def load_api_keys(self):
        def load_keys(file_path, field_map, label):
            try:
                df = pd.read_csv(file_path, quotechar='"')
                for attr, column in field_map.items():
                    setattr(self, attr, df.loc[0, column])
            except Exception as e:
                self.add_to_transcript(f"Failed to load {label} API keys: {e}", "ERROR")
        load_keys('../api/qualtrics.api', {
            'qualtrics_api_token': 'api_token',
            'qualtrics_data_center': 'datacenter',
            'ema_survey_id': 'ema_survey_id',
            'feedback_survey_id': 'feedback_survey_id'
        }, "Qualtrics")
        load_keys('../api/followmee.api', {
            'followmee_username': 'username',
            'followmee_api_token': 'api_token'
        }, "FollowMee")
        load_keys('../api/twilio.api', {
            'twilio_account_sid': 'account_sid',
            'twilio_auth_token': 'auth_token',
            'twilio_from_number': 'from_number'
        }, "Twilio")
        load_keys('../api/research_drive.api', {
            'destination_path': 'destination_path',
            'drive_letter': 'drive_letter',
            'network_domain': 'network_domain',
            'network_username': 'network_username',
            'wisc_netid': 'wisc_netid',
            'wisc_password': 'wisc_password'
        }, "Research Drive")
        load_keys('../api/ngrok.api', {
            'ngrok_auth_token': 'auth_token',
            'ngrok_domain': 'domain'
        }, "Ngrok")

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
                    if not content:
                        return None
                    return [{"timestamp": line.split(' - ')[0], "message": ' - '.join(line.split(' - ')[1:])} for line in content]
            except FileNotFoundError:
                with open(transcript_path, 'w') as f:
                    f.write(f"{datetime.now().strftime('%H:%M:%S')} - {target} file created.\n")
        except Exception as e:
            self.add_to_transcript(f"Failed to read {target}: {e}", "ERROR")
            return None    

    def launch_web_app(self):
        self.flask_app = create_flask_app(self)
        if self.mode == "prod":
            ngrok.set_auth_token(self.ngrok_auth_token)
            subprocess.Popen(
                ["ngrok", "http", f"--url={self.ngrok_domain}", "5000"], 
                stdout = subprocess.DEVNULL,
                stderr = subprocess.DEVNULL
            )
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