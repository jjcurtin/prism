"""Helper methods for PRISM"""

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import os

from _types import App

# Placeholder marker used in the checked-in-nowhere, drive-sourced .api
# template files (e.g. "REPLACE_WITH_QUALTRICS_API_TOKEN") -- a value still
# carrying this prefix means the credential/field was never actually filled
# in, not that it's missing outright. Shared between app runtime code and
# tests_integration/ (see tests_integration/conftest.py, tests_integration/
# test_environment_files.py) so both agree on what counts as "still a
# template placeholder".
PLACEHOLDER_PREFIX = "REPLACE_WITH_"


def _is_real_value(value: object) -> bool:
    if value is None:
        return False
    value = str(value).strip()
    if not value:
        return False
    if value.startswith(PLACEHOLDER_PREFIX):
        return False
    return True

def send_sms(app: App, receiver_numbers: list[str], messages: list[str], is_coordinator_message: bool = False) -> int:
    """Returns the number of recipients the send failed for (0 on success,
    or `len(receiver_numbers)` if the Twilio client itself couldn't be
    built) -- not a bool. notify_coordinators() re-uses this same contract
    when it delegates here (passing `is_coordinator_message=True`).

    Every per-recipient transcript line (success or failure) is labeled
    "Participant SMS"/"Coordinator SMS" so a mixed transcript reads
    unambiguously. A coordinator send's success line also includes the
    full message body as its "reason" -- coordinator alerts exist
    specifically to page someone about something, and the why (including
    the `[XXXX]` error code from `_error_codes.py`, when there is one) is
    already baked into that body by the caller; a participant send's
    survey-type/reason context, if any, is logged separately by its own
    caller (e.g. `_participant_manager.py::process_task`'s "Processing SMS
    task: ..." line) before it ever reaches here.

    Prepends an environment marker to the outbound message body (not the
    transcript log line, which is already environment-scoped by which
    machine's logs it lands in): "DEV: " for every message when
    `app.environment == "dev"` (participant and coordinator alike, since a
    dev-environment message may still reach a real phone during testing and
    must never be mistaken for a real study communication); "PROD: " only
    for coordinator messages when `app.environment == "prod"` (so
    coordinators can tell prod alerts apart from anything else, but real
    participants never see an internal environment tag on their real survey
    texts -- prod participant-facing messages get no prefix at all).

    This is `app.environment` (the "which environment's data/credentials"
    marker set by `run_prism.py::load_paths()`) -- not `app.mode` (the
    `-mode test`/`-mode prod` flag gating whether sends happen at all),
    which is an orthogonal axis. `getattr(app, 'environment', 'dev')` is
    used instead of a bare attribute access so a caller whose app object
    doesn't have `environment` set yet (e.g. a test fixture, or
    mid-construction before `load_paths()` has run) doesn't crash message
    sending; this mirrors `load_paths()`'s own "defaults to dev if unset"
    behavior.
    """
    environment = getattr(app, 'environment', 'dev')
    if environment == 'dev':
        prefix = "DEV: "
    elif is_coordinator_message:
        prefix = "PROD: "
    else:
        prefix = ""
    messages = [prefix + message for message in messages]

    account_sid = app.twilio_account_sid
    auth_token = app.twilio_auth_token
    from_number = app.twilio_from_number
    try:
        client = Client(account_sid, auth_token)
    except Exception as e:
        app.add_to_transcript(f"Failed to initialize Twilio client (check credentials): {e}", "ERROR")
        return len(receiver_numbers)

    result = 0
    recipient_kind = "Coordinator" if is_coordinator_message else "Participant"

    for index, (to_number, message_body) in enumerate(zip(receiver_numbers, messages), start = 1):
        try:
            message = client.messages.create(body = message_body, from_ = from_number, to = to_number)
            if is_coordinator_message:
                # Coordinator alerts exist specifically to page someone about
                # something -- the "why" (including the [XXXX] error code
                # from _error_codes.py, when there is one) is already baked
                # into message_body by the caller (SystemTask.notify_via_sms/
                # notify_coordinators), so surface it here rather than
                # leaving the transcript saying only that *a* text went out.
                app.add_to_transcript(
                    f"Coordinator SMS {index} sent to {to_number} -- reason: {message_body}. Message SID: {message.sid}",
                    "INFO",
                )
            else:
                app.add_to_transcript(f"Participant SMS {index} sent to {to_number}. Message SID: {message.sid}", "INFO")
        except TwilioRestException as e:
            app.add_to_transcript(
                f"Failed to send {recipient_kind} SMS {index} to {to_number}. Twilio error {e.code}: {e.msg}", "ERROR"
            )
            result += 1
        except Exception as e:
            app.add_to_transcript(
                f"Failed to send {recipient_kind} SMS {index} to {to_number}. Error message: {e}", "ERROR"
            )
            result += 1

    return result

def notify_coordinators(app: App, message: str) -> int:
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

    phone_numbers: list[str] = []
    bodies: list[str] = []
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

    return send_sms(app, phone_numbers, bodies, is_coordinator_message = True)

def clear() -> None:
    os.system('cls' if os.name == 'nt' else 'clear')