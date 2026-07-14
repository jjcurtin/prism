"""Tests for PRISMInterface.api() (src/prism_interface.py) -- bypasses
__init__ (which makes a real network call and can exit(0) the process if
no server is reachable) via __new__, same convention as
tests/test_run_prism.py's PRISM.__new__(PRISM).
"""
from prism_interface import PRISMInterface
from user_interface_menus._menu_helper import ui_state


def _make_interface():
    interface = PRISMInterface.__new__(PRISMInterface)
    interface.base_url = "http://localhost:5000"
    return interface


def test_api_202_is_treated_as_ok(mocker):
    """send_studywide_survey (_routes.py) returns 202 once its background
    send has started, not 200 -- api() must treat that as success too, not
    fall into the generic non-200 error branch."""
    interface = _make_interface()
    mocker.patch.object(ui_state, 'timeout', 5)
    response = mocker.Mock(status_code=202)
    response.json.return_value = {"message": "Studywide ema send started."}
    mocker.patch('prism_interface.requests.post', return_value=response)

    ok, data = interface.api("POST", "participants/send_studywide_survey/ema/yes")

    assert ok is True
    assert data == {"message": "Studywide ema send started."}


def test_api_non_200_prints_generic_message_when_body_has_no_error_key(mocker, capsys):
    interface = _make_interface()
    mocker.patch.object(ui_state, 'timeout', 5)
    response = mocker.Mock(status_code=500)
    response.json.return_value = {}
    mocker.patch('prism_interface.requests.get', return_value=response)

    ok, data = interface.api("GET", "some/endpoint")

    assert ok is False
    assert data is None
    assert "PRISM server returned an error (status 500)." in capsys.readouterr().out


def test_api_non_200_includes_server_error_message(mocker, capsys):
    """Regression test for a real bug (external adversarial review): this
    session's own Finding 2 fix (b72cbd6) gave _routes.py distinguishable
    statuses/messages (409 duplicate, 403 immutable, 400 invalid value,
    etc.), but api() discarded the whole response body on any non-200
    status -- the specific reason never reached the menu that asked, so
    every menu printed its own generic failure text regardless of why.
    """
    interface = _make_interface()
    mocker.patch.object(ui_state, 'timeout', 5)
    response = mocker.Mock(status_code=409)
    response.json.return_value = {"error": "unique_id already exists"}
    mocker.patch('prism_interface.requests.get', return_value=response)

    ok, data = interface.api("GET", "some/endpoint")

    assert ok is False
    assert data is None
    assert "unique_id already exists" in capsys.readouterr().out


def test_api_non_200_non_json_body_does_not_raise(mocker, capsys):
    """A non-200 response whose body isn't JSON at all (e.g. a proxy's own
    HTML error page) must fall back to the generic message, not raise on
    top of the original failure."""
    interface = _make_interface()
    mocker.patch.object(ui_state, 'timeout', 5)
    response = mocker.Mock(status_code=502)
    response.json.side_effect = ValueError("not JSON")
    mocker.patch('prism_interface.requests.get', return_value=response)

    ok, data = interface.api("GET", "some/endpoint")

    assert ok is False
    assert data is None
    assert "PRISM server returned an error (status 502)." in capsys.readouterr().out
