"""Helper methods for PRISM"""

from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from twilio.base.exceptions import TwilioRestException
import csv
import os
import re

from _types import App

# README.md's (Appendix A) documented phone_number format: 10
# digits, no separators. Kept as a single source of truth server-side; the interface
# layer (user_interface_menus/_menu_helper.py) keeps its own copy since it
# never imports backend modules from src/ (see that module's own comment).
PHONE_NUMBER_RE = re.compile(r'^\d{10}$')


def is_valid_phone_number(value: str) -> bool:
    return bool(PHONE_NUMBER_RE.fullmatch(value.strip()))

# twilio-python's TwilioHttpClient defaults to timeout=None (confirmed
# against the installed 9.0.5 package) -- an unbounded requests call. Since
# every SMS send happens synchronously on TaskManager.run()'s single
# background thread (one task at a time, no concurrency), a network stall
# here doesn't just fail one send -- it freezes that entire manager's
# pipeline (every other participant's scheduled EMA/reminder/feedback, or
# all system tasks) for as long as the stall lasts, with no other task
# able to run until it resolves. 30s is generous for Twilio's normal
# response time (sub-second to a few seconds) while still bounding the
# worst case to something that resolves and gets logged/alerted on,
# instead of hanging indefinitely.
SMS_SEND_TIMEOUT_SECONDS = 30

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
    if isinstance(value, float) and value != value:
        # NaN -- pd.read_csv(..., dtype=str) still returns float('nan') for
        # a blank cell (a pandas quirk, not a dtype bug), so a caller
        # reading straight from a CSV can hand this function a float even
        # though every other "real" value it sees is a str. `value != value`
        # is the standard NaN self-inequality check (true for NaN and only
        # NaN, per IEEE 754) -- checked before the str(value) below, which
        # would otherwise stringify it to the non-empty, non-placeholder
        # "nan" and let it straight through.
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
    `-mode silent`/`-mode live` flag gating whether sends happen at all),
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

    # getattr, not a bare attribute access: these have no defaults in
    # API_FIELD_DEFAULTS (run_prism.py) the way message-text fields do, so
    # if twilio.api ever fails to load (drive hiccup during startup,
    # corrupted/missing file), the attributes are simply never set. A bare
    # `app.twilio_account_sid` would raise AttributeError here -- and this
    # function is called from inside failure-notification paths
    # (SystemTask.notify_via_sms/TaskManager.run()'s own exception
    # handler), so that AttributeError previously escaped uncaught and
    # crashed the entire background task-processing thread the moment
    # anything else failed and tried to alert a coordinator about it.
    account_sid = getattr(app, 'twilio_account_sid', None)
    auth_token = getattr(app, 'twilio_auth_token', None)
    from_number = getattr(app, 'twilio_from_number', None)
    # _is_real_value(), not a bare truthiness check: pd.read_csv(...,
    # dtype=str) still returns float('nan') for a blank cell (a pandas
    # quirk, not a dtype bug) -- and `not nan` is False in Python, so a
    # twilio.api file with a blank account_sid/auth_token/from_number cell
    # used to silently pass this guard and reach the real Twilio client
    # constructor below with a NaN credential, rather than being caught
    # here with the clear "credentials not loaded" message. Also rejects
    # an unfilled-in template placeholder ("REPLACE_WITH_..."), which a
    # bare truthiness check would have let through as well.
    if not all(_is_real_value(v) for v in (account_sid, auth_token, from_number)):
        app.add_to_transcript(
            "Twilio credentials not loaded (twilio.api failed to load, or is missing "
            "required fields) -- cannot send SMS.",
            "ERROR",
        )
        return len(receiver_numbers)
    try:
        http_client = TwilioHttpClient(timeout = SMS_SEND_TIMEOUT_SECONDS)
        client = Client(account_sid, auth_token, http_client = http_client)
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
    `app.mode == "live"` -- returns 0 immediately otherwise, matching the
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
    if app.mode != "live":
        return 0

    try:
        with open(app.study_coordinators_path, 'r', newline = '') as f:
            # csv.DictReader (maps by the file's own header row) rather
            # than a naive line.split(',') + strip('"') -- immune to an
            # embedded comma or quote in a coordinator's name corrupting
            # the phone_number field alongside it.
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        app.add_to_transcript("No study coordinators found. SMS notifications will not be sent.", "WARNING")
        return 1
    except Exception as e:
        app.add_to_transcript(f"Failed to read study coordinators. Error message: {e}", "ERROR")
        return 1

    phone_numbers: list[str] = []
    bodies: list[str] = []
    for row in rows:
        try:
            # DictReader fills a row shorter than the header with None for
            # its missing trailing columns (restval) -- distinct from a
            # column that's present but genuinely blank (""), which is a
            # normal "no phone number on file" case, not malformed.
            if row.get('name') is None or row.get('phone_number') is None:
                raise ValueError(f"row is missing a column: {row}")
            name = row['name'].strip()
            phone_number = row['phone_number'].strip()
            if phone_number:
                try:
                    body = message.format(name=name)
                except (KeyError, IndexError, ValueError):
                    # str.format() also raises ValueError for a malformed
                    # format string (e.g. an unbalanced "{") -- confirmed
                    # live, not just documented. Realistic trigger: callers
                    # build `message` by interpolating an exception's own
                    # text into an f-string before calling here (e.g.
                    # _participant_manager.py's
                    # code_prefix('2001') + f"...Error: {e}"), so any
                    # error message containing a literal "{" (a dict repr,
                    # a stack trace fragment, a Windows path artifact) used
                    # to trip this. Since `message` is the same string for
                    # every row in this loop, an uncaught ValueError here
                    # escaped to the outer `except Exception`, mislabeled a
                    # real page as "malformed study coordinator entry", and
                    # -- because it hit on the FIRST row and skipped every
                    # row after it too -- silently paged nobody at all for
                    # what was actually a real system failure.
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