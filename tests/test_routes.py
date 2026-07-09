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


def test_get_transcript_not_found(routes_client, routes_app_instance):
    routes_app_instance.get_transcript = MagicMock(return_value=None)
    resp = routes_client.get('/system/get_transcript/10')
    assert resp.status_code == 404


def test_get_ema_log(routes_client, routes_app_instance):
    resp = routes_client.get('/system/get_ema_log/5')
    assert resp.status_code == 200
    routes_app_instance.get_transcript.assert_called_once_with('5', 'ema_log')


def test_get_feedback_log(routes_client, routes_app_instance):
    resp = routes_client.get('/system/get_feedback_log/5')
    assert resp.status_code == 200
    routes_app_instance.get_transcript.assert_called_once_with('5', 'feedback_log')


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


def test_send_survey_success(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participant.return_value = {'unique_id': '1'}
    resp = routes_client.post('/participants/send_survey/1/ema')
    assert resp.status_code == 200
    routes_app_instance.participant_manager.add_task.assert_called_once()


def test_send_survey_invalid_type(routes_client):
    resp = routes_client.post('/participants/send_survey/1/not_a_type')
    assert resp.status_code == 400


def test_send_survey_participant_not_found(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.get_participant.return_value = None
    resp = routes_client.post('/participants/send_survey/1/ema')
    assert resp.status_code == 404


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
    routes_app_instance.participant_manager.participants = []
    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})
    assert resp.status_code == 404


def test_study_announcement_on_study_only_filters(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.participant_manager.participants = [
        {'phone_number': '5555550100', 'on_study': True},
        {'phone_number': '5555550101', 'on_study': False},
    ]
    send_sms_mock = MagicMock(return_value=0)
    monkeypatch.setattr('_routes.send_sms', send_sms_mock)

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 200
    # test mode -- send_sms should never be invoked regardless of filtering
    send_sms_mock.assert_not_called()


def test_study_announcement_no_on_study_participants_is_404(routes_client, routes_app_instance):
    routes_app_instance.participant_manager.participants = [{'phone_number': '5555550100', 'on_study': False}]
    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})
    assert resp.status_code == 404


def test_study_announcement_prod_mode_all_succeed(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.participants = [
        {'phone_number': '5555550100', 'on_study': True},
        {'phone_number': '5555550101', 'on_study': True},
    ]
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
    routes_app_instance.participant_manager.participants = [
        {'phone_number': '5555550100', 'on_study': True},
        {'phone_number': '5555550101', 'on_study': True},
    ]
    monkeypatch.setattr('_routes.send_sms', MagicMock(return_value=1))

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 502


def test_study_announcement_prod_mode_partial_failure_notes_count(routes_client, routes_app_instance, monkeypatch):
    routes_app_instance.mode = 'prod'
    routes_app_instance.participant_manager.participants = [
        {'phone_number': '5555550100', 'on_study': True},
        {'phone_number': '5555550101', 'on_study': True},
    ]
    monkeypatch.setattr('_routes.send_sms', MagicMock(side_effect=[0, 1]))

    resp = routes_client.post('/participants/study_announcement/yes', json={'message': 'hi'})

    assert resp.status_code == 200
    assert '1 of 2' in resp.get_json()['message']
