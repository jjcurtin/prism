"""Tests for src/_routes.py -- every Flask route PRISM exposes.

Uses Flask's own test client (`routes_client` fixture, conftest.py) against
a real `create_flask_app(app_instance)`, with `app_instance.system_task_manager`/
`.participant_manager` as MagicMocks (`routes_app_instance` fixture) --
no real network, no real config/API files.
"""
from unittest.mock import MagicMock

import pytest


# ------------------------------------------------------------
# System
# ------------------------------------------------------------

def test_get_mode(routes_client):
    resp = routes_client.get('/system/get_mode')
    assert resp.status_code == 200
    assert resp.get_json() == {'mode': 'test'}


def test_get_uptime(routes_client):
    resp = routes_client.get('/system/uptime')
    assert resp.status_code == 200
    assert 'uptime' in resp.get_json()


def test_get_transcript_found(routes_client, routes_app_instance):
    resp = routes_client.get('/system/get_transcript/10')
    assert resp.status_code == 200
    assert resp.get_json() == {'transcript': 'fake transcript line\n'}
    routes_app_instance.get_transcript.assert_called_once_with('10')


def test_get_transcript_empty_is_200(routes_client, routes_app_instance):
    """A genuinely empty (or just-created) transcript is a successful read,
    not a failure -- distinct from test_get_transcript_read_failure below."""
    routes_app_instance.get_transcript = MagicMock(return_value=(True, []))
    resp = routes_client.get('/system/get_transcript/10')
    assert resp.status_code == 200
    assert resp.get_json() == {'transcript': []}


def test_get_transcript_read_failure_returns_500(routes_client, routes_app_instance):
    routes_app_instance.get_transcript = MagicMock(return_value=(False, None))
    resp = routes_client.get('/system/get_transcript/10')
    assert resp.status_code == 500


def test_shutdown_calls_app_shutdown(routes_client, routes_app_instance):
    resp = routes_client.post('/system/shutdown')
    assert resp.status_code == 200
    routes_app_instance.shutdown.assert_called_once()


def test_get_task_schedule_found(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.get_task_schedule.return_value = [{'task_type': 'CHECK_SYSTEM'}]
    resp = routes_client.get('/system/get_task_schedule')
    assert resp.status_code == 200
    assert resp.get_json() == {'tasks': [{'task_type': 'CHECK_SYSTEM'}]}


def test_get_task_schedule_empty_is_404(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.get_task_schedule.return_value = []
    resp = routes_client.get('/system/get_task_schedule')
    assert resp.status_code == 404


def test_get_task_types(routes_client):
    resp = routes_client.get('/system/get_task_types')
    assert resp.status_code == 200
    assert resp.get_json() == {'task_types': {'CHECK_SYSTEM': 'CheckSystem', 'RUN_R_SCRIPT': 'RunRScript'}}


def test_get_task_types_empty_is_404(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.task_types = {}
    resp = routes_client.get('/system/get_task_types')
    assert resp.status_code == 404


def test_get_r_script_tasks_found(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.get_r_script_tasks.return_value = {'script1': 'script1'}
    resp = routes_client.get('/system/get_r_script_tasks')
    assert resp.status_code == 200


def test_get_r_script_tasks_empty_is_404(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.get_r_script_tasks.return_value = {}
    resp = routes_client.get('/system/get_r_script_tasks')
    assert resp.status_code == 404


def test_add_system_task_success(routes_client, routes_app_instance):
    resp = routes_client.post('/system/add_system_task/CHECK_SYSTEM/03:00:00')
    assert resp.status_code == 200
    routes_app_instance.system_task_manager.add_task.assert_called_once_with(
        'CHECK_SYSTEM', '03:00:00', r_script_path=''
    )
    routes_app_instance.system_task_manager.save_tasks.assert_called_once()


def test_add_system_task_invalid_type(routes_client):
    resp = routes_client.post('/system/add_system_task/NOT_A_TYPE/03:00:00')
    assert resp.status_code == 400


def test_add_system_task_invalid_time_is_clean_400(routes_client):
    """Regression test for a fixed bug: this route used to pass task_time
    straight into add_task, which unconditionally calls strptime -- a
    malformed time crashed with an unhandled 500 instead of a clean 400.
    """
    resp = routes_client.post('/system/add_system_task/CHECK_SYSTEM/not-a-time')
    assert resp.status_code == 400
    assert 'Invalid time format' in resp.get_json()['error']


def test_remove_system_task_success(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.remove_task.return_value = 0
    resp = routes_client.delete('/system/remove_system_task/CHECK_SYSTEM/03:00:00')
    assert resp.status_code == 200


def test_remove_system_task_not_found(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.remove_task.return_value = 1
    resp = routes_client.delete('/system/remove_system_task/CHECK_SYSTEM/03:00:00')
    assert resp.status_code == 404


def test_remove_system_task_invalid_time_is_clean_400(routes_client):
    resp = routes_client.delete('/system/remove_system_task/CHECK_SYSTEM/not-a-time')
    assert resp.status_code == 400


def test_clear_task_schedule(routes_client, routes_app_instance):
    resp = routes_client.delete('/system/clear_task_schedule')
    assert resp.status_code == 200
    routes_app_instance.system_task_manager.clear_schedule.assert_called_once()


def test_execute_task_success(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.process_task.return_value = 0
    resp = routes_client.post('/system/execute_task/CHECK_SYSTEM')
    assert resp.status_code == 200


def test_execute_task_failure(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.process_task.return_value = 1
    resp = routes_client.post('/system/execute_task/CHECK_SYSTEM')
    assert resp.status_code == 500


def test_execute_task_invalid_type(routes_client):
    resp = routes_client.post('/system/execute_task/NOT_A_TYPE')
    assert resp.status_code == 400


def test_add_r_script_task_success(routes_client, routes_app_instance):
    resp = routes_client.post('/system/add_r_script_task/myscript.R/03:00:00')
    assert resp.status_code == 200
    routes_app_instance.system_task_manager.add_task.assert_called_once_with(
        'RUN_R_SCRIPT', '03:00:00', r_script_path='myscript.R'
    )


def test_add_r_script_task_invalid_time(routes_client):
    resp = routes_client.post('/system/add_r_script_task/myscript.R/not-a-time')
    assert resp.status_code == 400


def test_remove_r_script_task_success(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.remove_task.return_value = 0
    resp = routes_client.delete('/system/remove_r_script_task/myscript.R/03:00:00')
    assert resp.status_code == 200


def test_remove_r_script_task_not_found(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.remove_task.return_value = 1
    resp = routes_client.delete('/system/remove_r_script_task/myscript.R/03:00:00')
    assert resp.status_code == 404


def test_remove_r_script_task_invalid_time_is_clean_400(routes_client):
    """Regression test for a fixed bug: same missing-validation shape as
    add_system_task -- a malformed task_time used to crash uncaught.
    """
    resp = routes_client.delete('/system/remove_r_script_task/myscript.R/not-a-time')
    assert resp.status_code == 400


def test_execute_r_script_task_success(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.process_task.return_value = 0
    resp = routes_client.post('/system/execute_r_script_task/myscript.R')
    assert resp.status_code == 200
    args, kwargs = routes_app_instance.system_task_manager.process_task.call_args
    assert args[0] == {'task_type': 'RUN_R_SCRIPT', 'r_script_path': 'myscript.R'}


def test_execute_r_script_task_failure(routes_client, routes_app_instance):
    routes_app_instance.system_task_manager.process_task.return_value = 1
    resp = routes_client.post('/system/execute_r_script_task/myscript.R')
    assert resp.status_code == 500


# ------------------------------------------------------------
# Participants
# ------------------------------------------------------------

def test_get_participants_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participants.return_value = [{'unique_id': '1'}]
    resp = routes_client.get('/participants/get_participants')
    assert resp.status_code == 200


def test_get_participants_empty_is_404(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participants.return_value = []
    resp = routes_client.get('/participants/get_participants')
    assert resp.status_code == 404


def test_get_participant_task_schedule_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_task_schedule.return_value = [{'task_type': 'ema'}]
    resp = routes_client.get('/participants/get_participant_task_schedule')
    assert resp.status_code == 200


def test_get_participant_task_schedule_empty_is_404(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_task_schedule.return_value = []
    resp = routes_client.get('/participants/get_participant_task_schedule')
    assert resp.status_code == 404


def test_refresh_participants_success(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.load_participants.return_value = 0
    resp = routes_client.post('/participants/refresh_participants')
    assert resp.status_code == 200


def test_refresh_participants_failure(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.load_participants.return_value = 1
    resp = routes_client.post('/participants/refresh_participants')
    assert resp.status_code == 500


def test_get_participant_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participant.return_value = {'unique_id': '1'}
    resp = routes_client.get('/participants/get_participant/1')
    assert resp.status_code == 200


def test_get_participant_not_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participant.return_value = None
    resp = routes_client.get('/participants/get_participant/1')
    assert resp.status_code == 404


ADD_PARTICIPANT_PAYLOAD = {
    'unique_id': '000000000', 'initials': 'JD', 'subid': '3000',
    'on_study': True, 'phone_number': '5555550100', 'ema_time': '09:00:00',
    'ema_reminder_time': '10:00:00', 'feedback_time': '19:00:00',
    'feedback_reminder_time': '20:00:00',
}


def test_add_participant_success(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.add_participant.return_value = 0
    resp = routes_client.post('/participants/add_participant', json=ADD_PARTICIPANT_PAYLOAD)
    assert resp.status_code == 200


def test_add_participant_write_failure_is_500(routes_client, routes_app_instance):
    """Regression test for a fixed bug: add_participant used to always
    report success regardless of whether the CSV write actually succeeded.
    """
    routes_app_instance.participant_manager.add_participant.return_value = 1
    resp = routes_client.post('/participants/add_participant', json=ADD_PARTICIPANT_PAYLOAD)
    assert resp.status_code == 500


def test_add_participant_missing_fields(routes_client):
    resp = routes_client.post('/participants/add_participant', json={'unique_id': '1'})
    assert resp.status_code == 400


def test_add_participant_non_dict_body_is_clean_400(routes_client):
    """Regression test for a fixed bug: a non-dict JSON body (e.g. a bare
    int/bool) used to crash with TypeError on `field in data`.
    """
    resp = routes_client.post('/participants/add_participant', data='42', content_type='application/json')
    assert resp.status_code == 400


def test_add_participant_malformed_json_is_clean_400(routes_client):
    resp = routes_client.post('/participants/add_participant', data='not json', content_type='application/json')
    assert resp.status_code == 400


def test_remove_participant_success(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.remove_participant.return_value = 0
    resp = routes_client.delete('/participants/remove_participant/1')
    assert resp.status_code == 200


def test_remove_participant_not_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.remove_participant.return_value = 1
    resp = routes_client.delete('/participants/remove_participant/1')
    assert resp.status_code == 404


def test_update_participant_success(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.update_participant.return_value = 0
    resp = routes_client.put('/participants/update_participant/1/phone_number/5555550199')
    assert resp.status_code == 200
    routes_app_instance.participant_manager.update_participant.assert_called_once_with('1', 'phone_number', '5555550199')


def test_update_participant_not_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.update_participant.return_value = 1
    resp = routes_client.put('/participants/update_participant/1/phone_number/5555550199')
    assert resp.status_code == 404


def test_send_survey_success(routes_client, routes_app_instance, mocker):
    """The route now sends synchronously: it adds a one_time task and
    processes it immediately via finish_task, returning the real outcome
    instead of optimistically reporting success ~10 seconds before the
    polling loop would even attempt the send.
    """
    routes_app_instance.participant_manager.get_participant.return_value = {'unique_id': '1'}
    fake_task = {'task_type': 'ema', 'participant_id': '1', 'one_time': True}
    routes_app_instance.participant_manager.add_task.return_value = fake_task
    routes_app_instance.participant_manager.finish_task.return_value = 0

    resp = routes_client.post('/participants/send_survey/1/ema')

    assert resp.status_code == 200
    routes_app_instance.participant_manager.add_task.assert_called_once_with(
        'ema', mocker.ANY, participant_id='1', one_time=True, track=False
    )
    routes_app_instance.participant_manager.finish_task.assert_called_once_with(fake_task)


def test_send_survey_invalid_type(routes_client):
    resp = routes_client.post('/participants/send_survey/1/not_a_type')
    assert resp.status_code == 400


def test_send_survey_participant_not_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participant.return_value = None
    resp = routes_client.post('/participants/send_survey/1/ema')
    assert resp.status_code == 404
    routes_app_instance.participant_manager.add_task.assert_not_called()


def test_send_survey_send_failure_is_502(routes_client, routes_app_instance):
    """Regression test for the fixed bug: this route used to queue the
    survey for the polling loop ~10 seconds later and always return 200
    immediately, regardless of whether the SMS actually sent. It must now
    mirror send_custom_sms's synchronous 502-on-failure contract.
    """
    routes_app_instance.participant_manager.get_participant.return_value = {'unique_id': '1'}
    fake_task = {'task_type': 'ema', 'participant_id': '1', 'one_time': True}
    routes_app_instance.participant_manager.add_task.return_value = fake_task
    routes_app_instance.participant_manager.finish_task.return_value = -1

    resp = routes_client.post('/participants/send_survey/1/ema')

    assert resp.status_code == 502
    routes_app_instance.participant_manager.finish_task.assert_called_once_with(fake_task)


def test_send_survey_feedback_type_success(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participant.return_value = {'unique_id': '1'}
    fake_task = {'task_type': 'feedback', 'participant_id': '1', 'one_time': True}
    routes_app_instance.participant_manager.add_task.return_value = fake_task
    routes_app_instance.participant_manager.finish_task.return_value = 0

    resp = routes_client.post('/participants/send_survey/1/feedback')

    assert resp.status_code == 200
    args, kwargs = routes_app_instance.participant_manager.add_task.call_args
    assert args[0] == 'feedback'
    assert kwargs == {'participant_id': '1', 'one_time': True, 'track': False}


def test_send_custom_sms_missing_message(routes_client, routes_app_instance):
    resp = routes_client.post('/participants/send_custom_sms/1', json={})
    assert resp.status_code == 400


def test_send_custom_sms_non_dict_body_is_clean_400(routes_client):
    resp = routes_client.post('/participants/send_custom_sms/1', data='42', content_type='application/json')
    assert resp.status_code == 400


def test_send_custom_sms_participant_not_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participant.return_value = None
    resp = routes_client.post('/participants/send_custom_sms/1', json={'message': 'hi'})
    assert resp.status_code == 404


def test_send_custom_sms_test_mode_does_not_send(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.participant_manager.get_participant.return_value = {'phone_number': '5555550100'}
    send_sms_mock = MagicMock()
    monkeypatch.setattr('_routes.send_sms', send_sms_mock)

    resp = routes_client.post('/participants/send_custom_sms/1', json={'message': 'hi'})

    assert resp.status_code == 200
    send_sms_mock.assert_not_called()


def test_send_custom_sms_prod_mode_success(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.get_participant.return_value = {'phone_number': '5555550100'}
    monkeypatch.setattr('_routes.send_sms', MagicMock(return_value=0))

    resp = routes_client.post('/participants/send_custom_sms/1', json={'message': 'hi'})

    assert resp.status_code == 200


def test_send_custom_sms_prod_mode_failure_is_502(routes_client, routes_app_instance, monkeypatch):
    """Regression test for a fixed bug: this route used to ignore
    send_sms()'s return value and always report success.
    """
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.get_participant.return_value = {'phone_number': '5555550100'}
    monkeypatch.setattr('_routes.send_sms', MagicMock(return_value=1))

    resp = routes_client.post('/participants/send_custom_sms/1', json={'message': 'hi'})

    assert resp.status_code == 502


def test_study_announcement_missing_message(routes_client):
    resp = routes_client.post('/participants/study_announcement/yes', json={})
    assert resp.status_code == 400


def test_study_announcement_no_participants(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_phone_numbers.return_value = []
    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})
    assert resp.status_code == 404


def test_study_announcement_passes_on_study_only_flag_through(routes_client, routes_app_instance, monkeypatch):
    """Filtering by on_study now happens inside ParticipantManager's locked
    get_phone_numbers() (see its own tests), not in the route -- this just
    confirms the route passes the right flag through and never touches
    .participants directly.
    """
    routes_app_instance.participant_manager.get_phone_numbers.return_value = ['5555550100']
    send_sms_mock = MagicMock(return_value=0)
    monkeypatch.setattr('_routes.send_sms', send_sms_mock)

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 200
    routes_app_instance.participant_manager.get_phone_numbers.assert_called_once_with(on_study_only=True)
    # test mode -- send_sms should never be invoked regardless of filtering
    send_sms_mock.assert_not_called()


def test_study_announcement_prod_mode_all_succeed(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.get_phone_numbers.return_value = ['5555550100', '5555550101']
    monkeypatch.setattr('_routes.send_sms', MagicMock(return_value=0))

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 200
    assert 'message' in resp.get_json()


def test_study_announcement_prod_mode_all_fail_is_502(routes_client, routes_app_instance, monkeypatch):
    """Regression test for a fixed bug: this route used to ignore
    send_sms()'s return value entirely and always report success even if
    every single SMS failed to send.
    """
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.get_phone_numbers.return_value = ['5555550100', '5555550101']
    monkeypatch.setattr('_routes.send_sms', MagicMock(return_value=1))

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 502


def test_study_announcement_prod_mode_partial_failure_notes_count(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.get_phone_numbers.return_value = ['5555550100', '5555550101']
    monkeypatch.setattr('_routes.send_sms', MagicMock(side_effect=[0, 1]))

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 200
    assert '1 of 2' in resp.get_json()['message']


def test_study_announcement_prod_mode_logs_elapsed_send_time(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.get_phone_numbers.return_value = ['5555550100']
    monkeypatch.setattr('_routes.send_sms', MagicMock(return_value=0))

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 200
    assert any('Study announcement send finished in' in msg for _, msg in routes_app_instance.transcript)


# ------------------------------------------------------------
# Unhandled-exception error handler
# ------------------------------------------------------------
#
# Every route above returns its 400/404/500/502 "failure" responses as
# plain `jsonify(...), <code>` values -- those are ordinary return values,
# not raised exceptions, so Flask's generic errorhandler(Exception) never
# sees them; it only fires for something that actually escapes a view
# function unhandled. These tests force that by making a mocked manager
# method raise instead of returning normally.

def test_unhandled_exception_returns_500_and_notifies_coordinators(routes_client, routes_app_instance, mocker):
    notify = mocker.patch('_routes.notify_coordinators', return_value=0)
    routes_app_instance.system_task_manager.get_task_schedule.side_effect = RuntimeError('boom')

    resp = routes_client.get('/system/get_task_schedule')

    assert resp.status_code == 500
    assert resp.get_json() == {"error": "Internal server error"}
    notify.assert_called_once()
    message = notify.call_args[0][1]
    assert message.startswith('[4001] ')
    assert 'boom' in message
    assert any('ERROR' == msg_type for msg_type, _ in routes_app_instance.transcript)


def test_unmatched_route_returns_default_404_no_coordinator_notify(routes_client, mocker):
    """A request to a URL that doesn't match any route raises Werkzeug's own
    NotFound (an HTTPException) during routing/dispatch, before any view
    function runs. That's not a "system failure" (broken PRISM
    functionality) -- it's just a bad URL -- so the generic exception
    handler must let it fall through to Flask's normal 404 handling instead
    of alerting coordinators.
    """
    notify = mocker.patch('_routes.notify_coordinators', return_value=0)

    resp = routes_client.get('/system/this_route_does_not_exist')

    assert resp.status_code == 404
    notify.assert_not_called()


def test_wrong_http_method_returns_default_405_no_coordinator_notify(routes_client, mocker):
    """Same idea as the 404 case above, but for MethodNotAllowed (e.g.
    GET-ing a POST-only route) -- also a routing-layer HTTPException, not a
    system failure.
    """
    notify = mocker.patch('_routes.notify_coordinators', return_value=0)

    resp = routes_client.get('/system/shutdown')  # shutdown is POST-only

    assert resp.status_code == 405
    notify.assert_not_called()


def test_flask_app_has_no_cors_or_limiter_extensions_registered(routes_client):
    """Locks in the removal of the dead CORS/Flask-Limiter scaffolding:
    the CORS origins ("localhost:5000", no scheme) could never match a
    real Origin header, and the limiter was configured with
    default_limits=[] and no route ever called .limit() -- both were
    half-configured and implied protection that didn't exist, so they were
    deleted outright rather than fixed, per the documented local-only
    trust model. This test exists so a future change can't silently
    reintroduce either without a deliberate decision.
    """
    assert 'flask_cors' not in routes_client.application.extensions
    assert 'limiter' not in routes_client.application.extensions
