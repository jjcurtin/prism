# Helper methods for PRISM

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import os

# Placeholder marker used in the checked-in-nowhere, drive-sourced .api
# template files (e.g. "REPLACE_WITH_QUALTRICS_API_TOKEN") -- a value still
# carrying this prefix means the credential/field was never actually filled
# in, not that it's missing outright. Shared between app runtime code and
# tests_integration/ (see tests_integration/conftest.py, tests_integration/
# test_environment_files.py) so both agree on what counts as "still a
# template placeholder".
PLACEHOLDER_PREFIX = "REPLACE_WITH_"


def _is_real_value(value):
    if value is None:
        return False
    value = str(value).strip()
    if not value:
        return False
    if value.startswith(PLACEHOLDER_PREFIX):
        return False
    return True

def send_sms(app, receiver_numbers, messages):
    account_sid = app.twilio_account_sid
    auth_token = app.twilio_auth_token
    from_number = app.twilio_from_number
    try:
        client = Client(account_sid, auth_token)
    except Exception as e:
        app.add_to_transcript(f"Failed to initialize Twilio client (check credentials): {e}", "ERROR")
        return len(receiver_numbers)

    result = 0

    for index, (to_number, message_body) in enumerate(zip(receiver_numbers, messages), start = 1):
        try:
            message = client.messages.create(body = message_body, from_ = from_number, to = to_number)
            app.add_to_transcript(f"SMS {index} sent to {to_number}. Message SID: {message.sid}", "INFO")
        except TwilioRestException as e:
            app.add_to_transcript(f"Failed to send SMS {index} to {to_number}. Twilio error {e.code}: {e.msg}", "ERROR")
            result += 1
        except Exception as e:
            app.add_to_transcript(f"Failed to send SMS {index} to {to_number}. Error message: {e}", "ERROR")
            result += 1

    return result

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')