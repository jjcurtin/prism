"""Small registry of 4-digit codes for coordinator-facing SMS alerts, so a
text reads as e.g. "[3001] ..." instead of only free-form prose -- lets
coordinators (and anyone triaging later) immediately place a failure by
subsystem without parsing the message body. First digit = subsystem
(1=system task execution, 2=participant SMS dispatch, 3=task-manager
internals, 4=web/routes); remaining three digits distinguish failures
within that subsystem. Deliberately small and flat -- only covers the
handful of failure paths that actually page a coordinator today
(grep notify_coordinators( across src/ for the current call sites);
this is not a blanket code for every 0/1/-1 return value in the codebase.
"""

ERROR_CODES: dict[str, str] = {
    '1001': "system task run failed",
    '2001': "participant SMS send failed",
    '2002': "unexpected error processing participant SMS task",
    '2003': "reminders.csv unreadable during reminder-suppression check",
    '3001': "unhandled exception escaped task manager's own error handling",
    '4001': "unhandled exception in a Flask route",
}


def code_prefix(code: str) -> str:
    """Returns "[<code>] " for prepending to a coordinator-facing message
    body. Raises KeyError if `code` isn't registered -- a message should
    never claim a code that doesn't exist in the registry.
    """
    if code not in ERROR_CODES:
        raise KeyError(f"Unregistered error code: {code!r}")
    return f"[{code}] "
