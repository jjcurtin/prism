"""script to get data from FollowMee and process it"""

import pandas as pd
import json
from datetime import datetime
import pytz
from datetime import timedelta
import requests
from requests.exceptions import RequestException
from collections import defaultdict
import os

from system_tasks._system_task import SystemTask

class PulldownFollowmeeData(SystemTask):
    def run(self):
        self.task_type = "PULLDOWN_FOLLOWMEE_DATA"
        self.app.add_to_transcript(f"{self.task_type} #{self.task_number} now attempting to pull down FollowMee data...", "INFO")

        if self.pull_down_followmee_data("raw_followmee_data.json", "processed_followmee_data.csv"):
            return 1
        
        return 0

    def get_one_day_ago_date(self):
        utc = pytz.UTC
        current_date = datetime.now(utc)
        one_day_ago = (current_date - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return one_day_ago.strftime("%Y-%m-%dT%H:%M:%SZ")

    def get_followmee_devices(self):
        """Fetches the device list from FollowMee and writes it to a local
        raw JSON file as a side effect. Returns that file's path (not the
        parsed device data) on success -- pull_down_followmee_data() re-reads
        it from disk -- or None on any fetch/parse failure.
        """
        self.app.add_to_transcript("Retrieving FollowMee devices...", "INFO")
        username = self.app.followmee_username
        api_key = self.app.followmee_api_token
        url = f"https://www.followmee.com/api/info.aspx?key={api_key}&username={username}&function=devicelist"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                try:
                    devices = response.json().get('Data', [])
                except ValueError as e:
                    self.app.add_to_transcript(f"Unexpected response shape from FollowMee: {e}", "ERROR")
                    return None
                if len(devices) == 0:
                    self.app.add_to_transcript("No devices found.", "ERROR")
                    return None
                else:
                    self.app.add_to_transcript(f"Retrieved {len(devices)} devices.", "INFO")
                    file_path = os.path.join(self.app.data_dir, 'followmee', 'raw', 'followmee_device_list.json')
                    os.makedirs(os.path.dirname(file_path), exist_ok = True)
                    with open(file_path, "w") as file:
                        json.dump(devices, file, indent = 4)
                    self.app.add_to_transcript(f"Device list saved to followmee_device_list.json.", "INFO")
                    return file_path
            else:
                self.app.add_to_transcript(f"Failed to retrieve device list. Status code: {response.status_code}", "ERROR")
                self.app.add_to_transcript(f"Response Text: {response.text}", "ERROR")
                return None
        except RequestException as e:
            self.app.add_to_transcript(f"Connection error occurred: {str(e)}", "ERROR")
            return None

    def pull_down_followmee_data(self, raw_file_name, processed_file_name):
        self.app.add_to_transcript("Now pulling down FollowMee data...", "INFO")
        username = self.app.followmee_username
        api_key = self.app.followmee_api_token
        device_list_file = self.get_followmee_devices()
        if not device_list_file:
            return 1

        try:
            with open(device_list_file, "r") as file:
                devices = json.load(file)
            device_ids = [device['DeviceID'] for device in devices]
        except (ValueError, KeyError, OSError) as e:
            self.app.add_to_transcript(f"Failed to read device list from {device_list_file}: {e}", "ERROR")
            return 1
        from_date = self.get_one_day_ago_date()
        to_date = datetime.now(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        device_id_param = f"&deviceid={','.join(map(str, device_ids))}"
        url = f"https://www.followmee.com/api/tracks.aspx?key={api_key}&username={username}&output=json&function=daterangeforalldevices&from={from_date}&to={to_date}{device_id_param}"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError as e:
                    self.app.add_to_transcript(f"Unexpected response shape from FollowMee: {e}", "ERROR")
                    return 1

                filepath = os.path.join(self.app.data_dir, 'followmee', 'raw', raw_file_name)
                os.makedirs(os.path.dirname(filepath), exist_ok = True)
                with open(filepath, "w") as file:
                    json.dump(data, file, indent=4)

                self.app.add_to_transcript(f"FollowMee data saved to {raw_file_name}.", "INFO")

                if self.process_followmee_data(raw_file_name, processed_file_name) == 0:
                    return 0
                else:
                    return 1
            else:
                self.app.add_to_transcript(f"Failed to download FollowMee data. Status code: {response.status_code}", "ERROR")
                self.app.add_to_transcript(f"Response Text: {response.text}", "ERROR")
                return 1
        except RequestException as e:
            self.app.add_to_transcript(f"Connection error occurred: {str(e)}", "ERROR")
            return 1
        
    def process_followmee_data(self, raw_file_name, processed_file_name):
        """Appends the newly pulled data onto each device's existing
        processed CSV (rather than overwriting it) and drops exact-duplicate
        rows -- this is what lets re-running the pulldown after a
        partial/previous run avoid double-counting overlapping records.
        """
        try:
            filepath = os.path.join(self.app.data_dir, 'followmee', 'raw', raw_file_name)
            with open(filepath, "r") as file:
                new_data = json.load(file)
            new_grouped_data = defaultdict(list)
            for entry in new_data['Data']:
                device_id = entry['DeviceID']
                new_grouped_data[device_id].append(entry)
            for device_id, entries in new_grouped_data.items():
                device_processed_file = os.path.join(self.app.data_dir, 'followmee', 'processed', f"{device_id}_{processed_file_name}")
                if os.path.exists(device_processed_file):
                    existing_data = pd.read_csv(device_processed_file)
                else:
                    os.makedirs(os.path.dirname(device_processed_file), exist_ok=True)
                    existing_data = pd.DataFrame()
                new_entries_df = pd.DataFrame(entries)
                updated_data = pd.concat([existing_data, new_entries_df]).drop_duplicates()
                updated_data.to_csv(device_processed_file, index=False)
                self.app.add_to_transcript(f"Processed data for device {device_id} saved to {device_processed_file}.", "INFO")
            return 0
        except Exception as e:
            self.app.add_to_transcript(f"Failed to process FollowMee data. Exception: {str(e)}", "ERROR")
            return 1