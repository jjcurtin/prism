"""This file contains every Flask route for the PRISM application.
These routes are accessed by the ui."""

from typing import Any

from flask import Flask, jsonify, request
from flask.wrappers import Response
from werkzeug.exceptions import HTTPException
import time
from datetime import datetime

from _helper import send_sms, notify_coordinators
from _error_codes import code_prefix
from _types import App

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
        tasks = app_instance.system_task_manager.get_task_schedule()
        if not tasks:
            return jsonify({"error": "No scheduled tasks found"}), 404
        return jsonify({"tasks": tasks}), 200
    
    @flask_app.route('/system/get_task_types', methods = ['GET'])
    def get_task_types() -> RouteResponse:
        if not app_instance.system_task_manager.task_types:
            return jsonify({"error": "No task types available"}), 404
        return jsonify({"task_types": app_instance.system_task_manager.task_types}), 200
    
    @flask_app.route('/system/get_r_script_tasks', methods = ['GET'])
    def get_r_script_tasks() -> RouteResponse:
        tasks = app_instance.system_task_manager.get_r_script_tasks()
        if not tasks:
            return jsonify({"error": "No R script tasks found"}), 404
        return jsonify({"r_script_tasks": tasks}), 200
    
    @flask_app.route('/system/add_system_task/<task_type>/<task_time>', methods = ['POST'])
    def add_system_task(task_type: str, task_time: str) -> RouteResponse:
        if task_type not in app_instance.system_task_manager.task_types:
            return jsonify({"error": "Invalid task type"}), 400
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
        participants = app_instance.participant_manager.get_participants()
        if not participants:
            return jsonify({"error": "No participants found"}), 404
        return jsonify({"participants": participants}), 200
    
    @flask_app.route('/participants/get_participant_task_schedule', methods = ['GET'])
    def get_participant_task_schedule() -> RouteResponse:
        tasks = app_instance.participant_manager.get_task_schedule()
        if not tasks:
            return jsonify({"error": "No participant tasks found"}), 404
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
        if app_instance.participant_manager.add_participant(data) != 0:
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
        if app_instance.participant_manager.update_participant(unique_id, field, new_value) != 0:
            return jsonify({"error": "Participant not found"}), 404
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
        if app_instance.mode == "prod":
            if send_sms(app_instance, [participant['phone_number']], [data['message']]) != 0:
                return jsonify({"error": f"Failed to send SMS to participant {unique_id}"}), 502
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
        # clearing the list mid-iteration.
        phone_numbers = app_instance.participant_manager.get_phone_numbers(
            on_study_only = (require_on_study.lower() == 'yes')
        )
        if not phone_numbers:
            app_instance.add_to_transcript("Study announcement failed: no participants found", "ERROR")
            return jsonify({"error": "No participants found"}), 404

        if app_instance.mode == "prod":
            send_start = datetime.now()
            attempted = 0
            failed = 0
            for phone_number in phone_numbers:
                if phone_number.strip():
                    attempted += 1
                    if send_sms(app_instance, [phone_number], [data['message']]) != 0:
                        failed += 1
                    else:
                        app_instance.add_to_transcript(f"Study announcement sent to {phone_number}", "INFO")
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
            app_instance.add_to_transcript(f"Simulated sending messages.")
        return jsonify({"message": f"Study announcement sent to all participants, require on study: {require_on_study}"}), 200

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