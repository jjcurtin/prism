"""Helper methods for PRISM"""

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
    """Returns the number of recipients the send failed for (0 on success,
    or `len(receiver_numbers)` if the Twilio client itself couldn't be
    built) -- not a bool. notify_coordinators() re-uses this same contract
    when it delegates here.
    """
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

def notify_coordinators(app, message):
    """Send `message` to every study coordinator listed in
    `app.study_coordinators_path`, via send_sms(). Gated internally on
    `app.mode == "prod"` -- returns 0 immediately otherwise, matching the
    gating SystemTask.execute() already applies at its own call site (so
    this is a no-op safety net, not a second independent gate in practice).

    `message` may contain a `{name}` placeholder, which gets filled in with
    each coordinator's own name from the CSV (SystemTask's per-coordinator
    "Alice: ..." alert template relies on this); a plain message with no
    `{name}` placeholder is sent verbatim to every coordinator.

    CSV-parsing behavior (skip malformed entries, warn if the file itself is
    missing) matches SystemTask.notify_via_sms(), which delegates to this
    helper. Returns the number of coordinators the send failed for (0 on
    success, or when there's nothing to send), same contract as send_sms().
    """
    if app.mode != "prod":
        return 0

    try:
        with open(app.study_coordinators_path, 'r') as f:
            lines = f.readlines()[1:]
    except FileNotFoundError:
        app.add_to_transcript("No study coordinators found. SMS notifications will not be sent.", "WARNING")
        return 1
    except Exception as e:
        app.add_to_transcript(f"Failed to read study coordinators. Error message: {e}", "ERROR")
        return 1

    phone_numbers = []
    bodies = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            name, phone_number = line.split(',')
            name = name.strip('"')
            phone_number = phone_number.strip('"')
            if phone_number:
                try:
                    body = message.format(name=name)
                except (KeyError, IndexError):
                    body = message
                phone_numbers.append(phone_number)
                bodies.append(body)
        except Exception as e:
            app.add_to_transcript(f"Skipping malformed study coordinator entry: {e}", "ERROR")

    if not phone_numbers:
        return 0

    return send_sms(app, phone_numbers, bodies)

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')