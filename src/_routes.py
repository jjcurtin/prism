"""This file contains every Flask route for the PRISM application.
These routes are accessed by the ui."""

from typing import Any

from flask import Flask, jsonify, request
from flask.wrappers import Response
from werkzeug.exceptions import HTTPException
import time
from datetime import datetime

from _helper import is_valid_phone_number, send_sms, notify_coordinators
from _error_codes import code_prefix
from _types import App
from task_managers._participant_manager import (
    ADD_DUPLICATE_ID, ADD_INVALID_VALUE, ADD_SAVE_FAILED,
    UPDATE_IMMUTABLE_FIELD, UPDATE_INVALID_VALUE, UPDATE_NOT_FOUND,
    UPDATE_SAVE_FAILED, UPDATE_UNKNOWN_FIELD,
)

# Every route handler below returns either `(jsonify(...), <status code>)`
# or a bare `jsonify(...)` (Flask defaults the status to 200) -- this alias
# covers both idiomatically rather than fighting Flask's own dynamic return
# typing.
RouteResponse = Response | tuple[Response, int]

def create_flask_app(app_instance: App) -> Flask:
    flask_app = Flask(__name__)

    # No CORS/rate-limiting here -- deliberate, per the documented
    # local-only trust model (root CLAUDE.md's "Security model" section):
    # the server binds to 127.0.0.1 only and its one client
    # (prism_interface.py) is hardcoded to http://localhost:5000/. The
    # CORS origins this used to configure ("localhost:5000", no scheme)
    # could never match a real Origin header anyway, and Flask-Limiter was
    # instantiated with default_limits=[] -- no route ever called
    # .limit() -- so both were dead, half-configured scaffolding that
    # implied protection neither actually provided.

    ################
    #    System    #
    ################

    @flask_app.route('/system/get_mode', methods = ['GET'])
    def get_mode() -> RouteResponse:
        return jsonify({'mode': app_instance.mode}), 200
    
    @flask_app.route('/system/uptime', methods = ['GET'])
    def get_uptime() -> RouteResponse:
        return jsonify({"uptime": time.strftime('%H:%M:%S', time.gmtime((datetime.now() - app_instance.start_time).total_seconds()))})

    @flask_app.route('/system/start_time', methods = ['GET'])
    def get_start_time() -> RouteResponse:
        # The exact wall-clock moment PRISM started, as already stored in
        # app_instance.start_time -- distinct from /system/uptime above,
        # which only ever exposed the elapsed *duration* since then, not
        # the timestamp itself. Requested directly for the main menu's new
        # status panel.
        return jsonify({"start_time": app_instance.start_time.strftime('%Y-%m-%d %H:%M:%S')})

    @flask_app.route('/system/get_transcript/<num_lines>', methods = ['GET'])
    def get_transcript(num_lines: str) -> RouteResponse:
        ok, transcript = app_instance.get_transcript(num_lines)
        if not ok:
            return jsonify({"error": "Failed to read transcript"}), 500
        return jsonify({"transcript": transcript}), 200

    @flask_app.route('/system/shutdown', methods = ['POST'])
    def shutdown() -> RouteResponse:
        app_instance.shutdown()
        return jsonify({"message": "Shutdown initiated"}), 200
    
    @flask_app.route('/system/get_task_schedule', methods = ['GET'])
    def get_task_schedule() -> RouteResponse:
        # A legitimately empty schedule is not an error -- 404 used to
        # conflate the two, and the interface would print the generic
        # "failed to retrieve" error for what's actually just "no tasks
        # scheduled yet".
        tasks = app_instance.system_task_manager.get_task_schedule()
        return jsonify({"tasks": tasks}), 200

    @flask_app.route('/system/get_task_types', methods = ['GET'])
    def get_task_types() -> RouteResponse:
        return jsonify({"task_types": app_instance.system_task_manager.task_types}), 200

    @flask_app.route('/system/get_r_script_tasks', methods = ['GET'])
    def get_r_script_tasks() -> RouteResponse:
        tasks = app_instance.system_task_manager.get_r_script_tasks()
        return jsonify({"r_script_tasks": tasks}), 200
    
    @flask_app.route('/system/add_system_task/<task_type>/<task_time>', methods = ['POST'])
    def add_system_task(task_type: str, task_time: str) -> RouteResponse:
        if task_type not in app_instance.system_task_manager.task_types:
            return jsonify({"error": "Invalid task type"}), 400
        if task_type == "RUN_R_SCRIPT":
            # This route always adds with r_script_path="" -- RunRScript
            # requires a real path, so a task added here would persist as
            # a schedule row that raises TypeError every time it fires,
            # paging coordinators daily until manually removed. Use
            # /system/add_r_script_task/<r_script_path>/<task_time> instead,
            # which already validates a non-empty path.
            return jsonify({"error": "Use /system/add_r_script_task/<r_script_path>/<task_time> for RUN_R_SCRIPT."}), 400
        try:
            datetime.strptime(task_time, '%H:%M:%S')
        except ValueError:
            return jsonify({"error": "Invalid time format."}), 400
        app_instance.system_task_manager.add_task(task_type, task_time, r_script_path = "")
        app_instance.system_task_manager.save_tasks()
        app_instance.add_to_transcript(f"Added system task via API: {task_type} at {task_time}", "INFO")
        return jsonify({"message": "Task added successfully"}), 200
    
    @flask_app.route('/system/remove_system_task/<task_type>/<task_time>', methods = ['DELETE'])
    def remove_system_task(task_type: str, task_time: str) -> RouteResponse:
        if task_type not in app_instance.system_task_manager.task_types:
            return jsonify({"error": "Invalid task type."}), 400
        try:
            datetime.strptime(task_time, '%H:%M:%S')
        except ValueError:
            return jsonify({"error": "Invalid time format."}), 400
        if app_instance.system_task_manager.remove_task(task_type, task_time = task_time) != 0:
            return jsonify({"error": "Task not found."}), 404
        return jsonify({"message": "Task removed successfully."}), 200
    
    @flask_app.route('/system/clear_task_schedule', methods = ['DELETE'])
    def clear_task_schedule() -> RouteResponse:
        app_instance.system_task_manager.clear_schedule()
        app_instance.add_to_transcript("Task schedule cleared via API.", "INFO")
        return jsonify({"message": "Task schedule cleared successfully"}), 200
    
    @flask_app.route('/system/execute_task/<task_type>', methods = ['POST'])
    def execute_task(task_type: str) -> RouteResponse:
        if task_type not in app_instance.system_task_manager.task_types:
            return jsonify({"error": "Invalid task type."}), 400
        if task_type == "RUN_R_SCRIPT":
            # process_task would call RunRScript(app) with no r_script_path
            # at all -- TypeError. Use
            # /system/execute_r_script_task/<r_script_path> instead, which
            # already validates a non-empty path.
            return jsonify({"error": "Use /system/execute_r_script_task/<r_script_path> for RUN_R_SCRIPT."}), 400
        elif app_instance.system_task_manager.process_task({'task_type': task_type}) != 0:
            return jsonify({"error": f"Failed to execute {task_type}."}), 500
        return jsonify({"message": f"{task_type} executed successfully."}), 200
    
    @flask_app.route('/system/add_r_script_task/<r_script_path>/<task_time>', methods = ['POST'])
    def add_r_script_task(r_script_path: str, task_time: str) -> RouteResponse:
        if not r_script_path:
            return jsonify({"error": "R script path cannot be empty."}), 400
        try:
            datetime.strptime(task_time, '%H:%M:%S')
        except ValueError:
            return jsonify({"error": "Invalid time format."}), 400
        app_instance.system_task_manager.add_task("RUN_R_SCRIPT", task_time, r_script_path = r_script_path)
        app_instance.system_task_manager.save_tasks()
        app_instance.add_to_transcript(f"Added R script task via API: {r_script_path} at {task_time}", "INFO")
        return jsonify({"message": "R script task added successfully"}), 200
    
    @flask_app.route('/system/remove_r_script_task/<r_script_path>/<task_time>', methods = ['DELETE'])
    def remove_r_script_task(r_script_path: str, task_time: str) -> RouteResponse:
        if not r_script_path:
            return jsonify({"error": "R script path cannot be empty."}), 400
        try:
            datetime.strptime(task_time, '%H:%M:%S')
        except ValueError:
            return jsonify({"error": "Invalid time format."}), 400
        if app_instance.system_task_manager.remove_task("RUN_R_SCRIPT", task_time = task_time, r_script_path = r_script_path) != 0:
            return jsonify({"error": "R script task not found."}), 404
        return jsonify({"message": "R script task removed successfully."}), 200
    
    @flask_app.route('/system/execute_r_script_task/<r_script_path>', methods = ['POST'])
    def execute_r_script_task(r_script_path: str) -> RouteResponse:
        if not r_script_path:
            return jsonify({"error": "R script path cannot be empty."}), 400
        task = {'task_type': 'RUN_R_SCRIPT', 'r_script_path': r_script_path}
        if app_instance.system_task_manager.process_task(task) != 0:
            return jsonify({"error": f"Failed to execute R script task: {r_script_path}."}), 500
        return jsonify({"message": f"R script task {r_script_path} executed successfully."}), 200
        
    #################
    #  Participants #
    #################

    @flask_app.route('/participants/get_participants', methods = ['GET'])
    def get_participants() -> RouteResponse:
        # A legitimately empty roster is not an error -- see
        # get_task_schedule's comment above for the same fix applied here.
        participants = app_instance.participant_manager.get_participants()
        return jsonify({"participants": participants}), 200

    @flask_app.route('/participants/get_participant_task_schedule', methods = ['GET'])
    def get_participant_task_schedule() -> RouteResponse:
        tasks = app_instance.participant_manager.get_task_schedule()
        return jsonify({"tasks": tasks}), 200
    
    @flask_app.route('/participants/refresh_participants', methods = ['POST'])
    def refresh_participants() -> RouteResponse:
        if app_instance.participant_manager.load_participants() != 0:
            return jsonify({"error": "Failed to refresh participants"}), 500
        app_instance.add_to_transcript("Participants refreshed via API.", "WARNING")
        return jsonify({"message": "Participants refreshed successfully"}), 200
    
    @flask_app.route('/participants/get_participant/<unique_id>', methods = ['GET'])
    def get_participant(unique_id: str) -> RouteResponse:
        participant = app_instance.participant_manager.get_participant(unique_id)
        if not participant:
            app_instance.add_to_transcript(f"Participant {unique_id} not found for retrieval", "ERROR")
            return jsonify({"error": "Participant not found"}), 404
        app_instance.add_to_transcript(f"Participant #{unique_id} information requested via API.", "INFO")
        return jsonify({"participant": participant}), 200

    @flask_app.route('/participants/add_participant', methods = ['POST'])
    def add_participant() -> RouteResponse:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400
        required_fields = ['unique_id', 'initials', 'subid', 'on_study', 'phone_number', 'ema_time', 'ema_reminder_time', 'feedback_time', 'feedback_reminder_time']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400
        # A blank phone_number is still allowed here -- matches the
        # interface's existing "press enter to skip" behavior
        # (_add_participant_menu.py) -- only a non-empty, malformed value
        # is rejected. Written back into `data` (not just validated as a
        # local copy) so a padded value like " 5555550100 " -- which
        # validates fine after stripping -- doesn't then get persisted
        # with the whitespace still attached, which is what actually gets
        # saved and later handed to Twilio.
        phone_number = str(data.get('phone_number', '')).strip()
        if phone_number and not is_valid_phone_number(phone_number):
            return jsonify({"error": "phone_number must be exactly 10 digits"}), 400
        data['phone_number'] = phone_number
        # Distinct statuses per failure reason, not one generic 500 for
        # everything -- found by an external adversarial review: a
        # duplicate unique_id and a genuine disk-write failure were
        # previously indistinguishable to the API caller. See the ADD_*
        # code definitions in _participant_manager.py.
        add_result = app_instance.participant_manager.add_participant(data)
        if add_result == ADD_DUPLICATE_ID:
            return jsonify({"error": f"Participant {data['unique_id']} already exists"}), 409
        if add_result == ADD_INVALID_VALUE:
            return jsonify({"error": "Invalid field value (see server transcript for which field)"}), 400
        if add_result == ADD_SAVE_FAILED or add_result != 0:
            return jsonify({"error": "Failed to save participant"}), 500
        app_instance.add_to_transcript(f"Participant #{data['unique_id']} added via API.", "INFO")
        return jsonify({"message": "Participant added successfully"}), 200

    @flask_app.route('/participants/remove_participant/<unique_id>', methods = ['DELETE'])
    def remove_participant(unique_id: str) -> RouteResponse:
        if app_instance.participant_manager.remove_participant(unique_id) != 0:
            return jsonify({"error": "Participant not found"}), 404
        app_instance.add_to_transcript(f"Participant #{unique_id} removed via API.", "INFO")
        return jsonify({"message": "Participant removed successfully"}), 200

    @flask_app.route('/participants/update_participant/<unique_id>/<field>/<new_value>', methods = ['PUT'])
    def update_participant(unique_id: str, field: str, new_value: str) -> RouteResponse:
        # Distinct statuses per failure reason, not one generic 404 for
        # everything -- found live by an external adversarial review:
        # rejecting a unique_id edit, an invalid field value, and a
        # genuinely missing participant were all indistinguishable to the
        # API caller (a 404 "Participant not found" for an existing
        # participant is an outright lie). See the UPDATE_* code
        # definitions in _participant_manager.py.
        update_result = app_instance.participant_manager.update_participant(unique_id, field, new_value)
        if update_result == UPDATE_NOT_FOUND:
            return jsonify({"error": "Participant not found"}), 404
        if update_result == UPDATE_IMMUTABLE_FIELD:
            return jsonify({"error": "unique_id is immutable; remove and re-add the participant instead"}), 403
        if update_result == UPDATE_UNKNOWN_FIELD:
            return jsonify({"error": f"Field '{field}' does not exist"}), 400
        if update_result == UPDATE_INVALID_VALUE:
            return jsonify({"error": f"Invalid value '{new_value}' for field '{field}'"}), 400
        if update_result == UPDATE_SAVE_FAILED:
            return jsonify({"error": "Failed to persist update"}), 500
        if update_result != 0:
            return jsonify({"error": "Failed to update participant"}), 500
        app_instance.add_to_transcript(f"Participant #{unique_id} updated via API: {field} changed to {new_value}", "INFO")
        return jsonify({"message": "Participant updated successfully"}), 200
    
    @flask_app.route('/participants/send_survey/<unique_id>/<survey_type>', methods = ['POST'])
    def send_survey(unique_id: str, survey_type: str) -> RouteResponse:
        """Sends a single, one-off ema/feedback survey to one participant
        right now, synchronously -- distinct from the permanent recurring
        ema/ema_reminder/feedback/feedback_reminder tasks
        `schedule_participant_tasks` sets up for every participant. The
        task is added with `one_time=True, track=False` and processed
        immediately via `finish_task` instead of being queued for the
        polling loop to pick up ~10 seconds later and optimistically
        reporting success before the send is known to have worked.
        `track=False` is required, not just an optimization: task_time is
        `datetime.now()`, so a tracked task would be immediately eligible
        for the background poller's own `check_tasks()` tick (its ~1s
        firing window starts the moment it's appended) -- a real race that
        sent a genuine duplicate SMS in practice (two distinct Twilio SIDs
        for one EMA send) before this fix.
        """
        if survey_type not in ['ema', 'feedback']:
            return jsonify({"error": "Invalid survey type"}), 400
        elif not app_instance.participant_manager.get_participant(unique_id):
            return jsonify({"error": "Participant not found"}), 404
        task = app_instance.participant_manager.add_task(
            survey_type, datetime.now().strftime('%H:%M:%S'), participant_id = unique_id, one_time = True, track = False
        )
        if app_instance.participant_manager.finish_task(task) != 0:
            return jsonify({"error": f"Failed to send {survey_type} survey to participant {unique_id}"}), 502
        return jsonify({"message": f"{survey_type.capitalize()} survey sent to participant {unique_id}"}), 200

    @flask_app.route('/participants/send_custom_sms/<unique_id>', methods = ['POST'])
    def send_custom_sms(unique_id: str) -> RouteResponse:
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or 'message' not in data:
            return jsonify({"error": "Message content is required"}), 400
        participant = app_instance.participant_manager.get_participant(unique_id)
        if not participant:
            return jsonify({"error": "Participant not found"}), 404
        if app_instance.mode == "live":
            if send_sms(app_instance, [participant['phone_number']], [data['message']]) != 0:
                return jsonify({"error": f"Failed to send SMS to participant {unique_id}"}), 502
        else:
            # Found by an external adversarial review: unlike
            # study_announcement's own silent-mode branch just below (which
            # logs "Simulated sending messages."), this route had no
            # silent-mode transcript line at all -- nothing here or in
            # send_sms() (only called in the live branch above) ever
            # recorded that a "Custom SMS sent" response was actually a
            # no-op simulation, not a real send. The HTTP response message
            # itself is unchanged (matches study_announcement's own
            # precedent of leaving the response text identical between
            # modes) -- only the transcript, server-side, now tells them
            # apart.
            app_instance.add_to_transcript(f"Simulated custom SMS send to participant {unique_id} (silent mode).", "INFO")
        return jsonify({"message": f"Custom SMS sent to participant {unique_id}"}), 200
    
    @flask_app.route('/participants/study_announcement/<require_on_study>', methods = ['POST'])
    def study_announcement(require_on_study: str) -> RouteResponse:
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or 'message' not in data:
            app_instance.add_to_transcript("Study announcement failed: message content is required", "ERROR")
            return jsonify({"error": "Message content is required"}), 400

        # Goes through the locked accessor rather than touching
        # .participants directly -- the old code read it 3 separate times
        # here with no lock, racing a concurrent refresh_participants()
        # clearing the list mid-iteration. Paired with unique_id (not just
        # phone_number) so both the live send log and the silent-mode
        # simulated-send log can name which participant a message was
        # sent/simulated for.
        on_study_only = require_on_study.lower() == 'yes'
        participants = app_instance.participant_manager.get_participant_ids_and_phone_numbers(
            on_study_only = on_study_only
        )
        if not participants:
            app_instance.add_to_transcript("Study announcement failed: no participants found", "ERROR")
            return jsonify({"error": "No participants found"}), 404

        scope = "on-study participants only" if on_study_only else "all participants"
        app_instance.add_to_transcript(
            f"Study announcement ({scope}): {len(participants)} participant(s).", "INFO"
        )

        if app_instance.mode == "live":
            send_start = datetime.now()
            attempted = 0
            failed = 0
            for unique_id, phone_number in participants:
                if phone_number.strip():
                    attempted += 1
                    if send_sms(app_instance, [phone_number], [data['message']]) != 0:
                        failed += 1
                    else:
                        app_instance.add_to_transcript(f"Study announcement sent to participant {unique_id}", "INFO")
            elapsed_seconds = (datetime.now() - send_start).total_seconds()
            app_instance.add_to_transcript(
                f"Study announcement send finished in {elapsed_seconds:.1f}s "
                f"({attempted} attempted, {failed} failed).", "INFO"
            )
            if attempted and failed == attempted:
                return jsonify({"error": "Failed to send study announcement to any participant"}), 502
            if failed:
                return jsonify({"message": f"Study announcement sent, but failed for {failed} of {attempted} participants."}), 200
        else:
            for unique_id, phone_number in participants:
                if phone_number.strip():
                    app_instance.add_to_transcript(
                        f"Simulated study announcement send to participant {unique_id} (silent mode).", "INFO"
                    )
        return jsonify({"message": f"Study announcement sent to all participants, require on study: {require_on_study}"}), 200

    @flask_app.route('/participants/get_survey_pause_status', methods = ['GET'])
    def get_survey_pause_status() -> RouteResponse:
        return jsonify(app_instance.participant_manager.get_survey_pause_status()), 200

    @flask_app.route('/participants/get_send_counts', methods = ['GET'])
    def get_send_counts() -> RouteResponse:
        return jsonify(app_instance.participant_manager.get_send_counts()), 200

    @flask_app.route('/participants/ema_on', methods = ['POST'])
    def ema_on() -> RouteResponse:
        app_instance.participant_manager.set_ema_paused(False)
        return jsonify({"message": "EMA sends resumed for today."}), 200

    @flask_app.route('/participants/ema_off', methods = ['POST'])
    def ema_off() -> RouteResponse:
        app_instance.participant_manager.set_ema_paused(True)
        return jsonify({"message": "EMA sends paused for the rest of today."}), 200

    @flask_app.route('/participants/feedback_on', methods = ['POST'])
    def feedback_on() -> RouteResponse:
        app_instance.participant_manager.set_feedback_paused(False)
        return jsonify({"message": "Feedback sends resumed for today."}), 200

    @flask_app.route('/participants/feedback_off', methods = ['POST'])
    def feedback_off() -> RouteResponse:
        app_instance.participant_manager.set_feedback_paused(True)
        return jsonify({"message": "Feedback sends paused for the rest of today."}), 200

    @flask_app.route('/participants/send_studywide_survey/<survey_type>/<require_on_study>', methods = ['POST'])
    def send_studywide_survey(survey_type: str, require_on_study: str) -> RouteResponse:
        """Sends a one-off ema/feedback survey to every (optionally
        on-study-filtered) participant right now, synchronously -- the
        studywide counterpart to send_survey above, looped per participant
        the same way study_announcement loops its own sends. Each
        participant's send goes through add_task(one_time=True,
        track=False) + finish_task(), the exact same mechanism (and the
        exact same duplicate-send race fix) send_survey already uses for
        a single participant; process_task() internally handles the
        silent-vs-live mode branch and the ema_paused_date/
        feedback_paused_date pause switch's one_time carve-out, so
        neither needs to be re-checked here.

        Runs the whole loop synchronously within this one request, same
        as study_announcement -- for a very large roster this could hold
        the request open for a while (each send is bounded by
        SMS_SEND_TIMEOUT_SECONDS), a known, pre-existing tradeoff of that
        established pattern, not something newly introduced here.
        """
        if survey_type not in ['ema', 'feedback']:
            return jsonify({"error": "Invalid survey type"}), 400

        on_study_only = require_on_study.lower() == 'yes'
        participants = app_instance.participant_manager.get_participant_ids_and_phone_numbers(
            on_study_only = on_study_only
        )
        if not participants:
            app_instance.add_to_transcript(f"Studywide {survey_type} send failed: no participants found", "ERROR")
            return jsonify({"error": "No participants found"}), 404

        scope = "on-study participants only" if on_study_only else "all participants"
        app_instance.add_to_transcript(
            f"Studywide {survey_type} send ({scope}): {len(participants)} participant(s).", "INFO"
        )

        send_start = datetime.now()
        attempted = 0
        failed = 0
        for unique_id, phone_number in participants:
            if not phone_number.strip():
                continue
            attempted += 1
            task = app_instance.participant_manager.add_task(
                survey_type, datetime.now().strftime('%H:%M:%S'), participant_id = unique_id,
                one_time = True, track = False,
            )
            if app_instance.participant_manager.finish_task(task) != 0:
                failed += 1
        elapsed_seconds = (datetime.now() - send_start).total_seconds()
        app_instance.add_to_transcript(
            f"Studywide {survey_type} send finished in {elapsed_seconds:.1f}s "
            f"({attempted} attempted, {failed} failed).", "INFO"
        )
        if attempted and failed == attempted:
            return jsonify({"error": f"Failed to send {survey_type} to any participant"}), 502
        if failed:
            return jsonify({
                "message": f"Studywide {survey_type} sent, but failed for {failed} of {attempted} participants."
            }), 200
        return jsonify({"message": f"Studywide {survey_type} sent to {scope}."}), 200

    ########################
    #  Error handling      #
    ########################

    # Every route above returns its "failure" responses (400/404/500/502)
    # as plain `jsonify(...), <code>` values, not raised exceptions -- per
    # _routes.py's convention, 400/404 are user-input validation problems
    # already resolved before this handler would ever see them. This
    # handler exists only to catch what *isn't* already handled that way:
    # a genuinely unhandled exception escaping a view function (broken
    # system functionality), which Flask converts into an internal
    # InternalServerError unless we intervene here first.
    #
    # Flask/Werkzeug also raises HTTPException subclasses of its own for
    # routing problems (e.g. NotFound for an unmatched URL, MethodNotAllowed
    # for a mismatched HTTP verb) -- those aren't "system failures" either.
    # A generic `errorhandler(Exception)` catches HTTPExceptions too (Flask
    # falls back to the broadest matching handler when no handler is
    # registered for that specific HTTPException/code), so this returns the
    # exception itself unmodified -- HTTPException instances are valid WSGI
    # responses -- letting Flask render its normal default error page
    # instead of alerting coordinators. (Re-raising it here instead of
    # returning it would escape this handler entirely and hit Flask's
    # top-level exception propagation instead of its normal HTTPException
    # rendering -- with TESTING/DEBUG on, that surfaces as an uncaught
    # exception rather than a clean response.)
    @flask_app.errorhandler(Exception)
    def handle_unexpected_error(e: Exception) -> RouteResponse | HTTPException:
        if isinstance(e, HTTPException):
            return e
        app_instance.add_to_transcript(f"Unhandled exception in Flask route: {e}", "ERROR")
        notify_coordinators(app_instance, code_prefix('4001') + f"PRISM system failure: unhandled exception in Flask route: {e}")
        return jsonify({"error": "Internal server error"}), 500

    return flask_app