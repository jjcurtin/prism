"""Tests for assistant/_prism_assistant.py and assistant/_assistant_menu.py."""
import os
from unittest.mock import MagicMock

import pytest

import user_interface_menus._menu_helper as menu_helper
import user_interface_menus.assistant._prism_assistant as _prism_assistant
import user_interface_menus.assistant._assistant_menu as _assistant_menu


@pytest.fixture(autouse=True)
def _no_real_terminal(monkeypatch):
    monkeypatch.setattr(os, 'system', lambda *a, **k: 0)


# ------------------------------------------------------------
# make_assistant_call
# ------------------------------------------------------------

@pytest.fixture
def fake_repo_with_prompt(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "system_prompt.txt").write_text("You are the PRISM assistant.")
    monkeypatch.chdir(src_dir)
    return tmp_path


def test_make_assistant_call_missing_prompt_file_returns_none(monkeypatch, tmp_path):
    # no ../config/system_prompt.txt reachable from tmp_path -- the whole
    # function body is wrapped in a bare try/except that swallows this.
    monkeypatch.chdir(tmp_path)
    result = _prism_assistant.make_assistant_call(
        "hi", menu_options={}, api_key="k", endpoint="http://x", context=[]
    )
    assert result is None


def test_make_assistant_call_success_builds_payload_and_returns_json(fake_repo_with_prompt, monkeypatch):
    monkeypatch.setattr(menu_helper, 'ASSISTANT_TOKENS', 500)
    monkeypatch.setattr(menu_helper, 'ASSISTANT_TEMPERATURE', 0.5)
    monkeypatch.setattr(menu_helper, 'COLOR_ON', False)
    monkeypatch.setattr(menu_helper, 'TIMEOUT', 5)

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "hi there"}}]}

    def fake_post(endpoint, headers=None, json=None, timeout=None):
        captured.update(endpoint=endpoint, headers=headers, json=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(_prism_assistant.requests, 'post', fake_post)

    menu_options = {'help': {'description': 'Help menu'}}
    result = _prism_assistant.make_assistant_call(
        "What is PRISM?", menu_options=menu_options, api_key="secretkey",
        endpoint="http://example.com/chat", context=["previous topic"],
    )

    assert result == {"choices": [{"message": {"content": "hi there"}}]}
    assert captured['endpoint'] == "http://example.com/chat"
    assert captured['headers']['Authorization'] == "Bearer secretkey"
    assert captured['json']['model'] == "optimize-v2"
    assert captured['json']['max_tokens'] == 500
    assert captured['json']['temperature'] == 0.5
    assert captured['timeout'] == 5
    assert captured['json']['messages'][1] == {"role": "user", "content": "What is PRISM?"}
    assert "Help menu" in captured['json']['messages'][0]['content']
    assert "previous topic" in captured['json']['messages'][0]['content']


def test_make_assistant_call_swallows_request_exceptions(fake_repo_with_prompt, monkeypatch):
    def fake_post(*a, **k):
        raise ConnectionError("boom")
    monkeypatch.setattr(_prism_assistant.requests, 'post', fake_post)
    result = _prism_assistant.make_assistant_call(
        "hi", menu_options={}, api_key="k", endpoint="http://x", context=[]
    )
    assert result is None


# ------------------------------------------------------------
# get_credentials
# ------------------------------------------------------------

def test_get_credentials_reads_existing_file(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "azure.api").write_text("key,endpoint\nsecret123,http://endpoint\n")
    monkeypatch.chdir(src_dir)

    api_key, endpoint = _prism_assistant.get_credentials()
    assert api_key == "secret123"
    assert endpoint == "http://endpoint"


def test_get_credentials_prompts_and_saves_when_missing(tmp_path, monkeypatch):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (tmp_path / "api").mkdir()
    monkeypatch.chdir(src_dir)
    inputs = iter(["mykey", "http://myendpoint"])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(inputs))

    api_key, endpoint = _prism_assistant.get_credentials()
    assert api_key == "mykey"
    assert endpoint == "http://myendpoint"
    saved = (tmp_path / "api" / "azure.api").read_text()
    assert "mykey" in saved
    assert "myendpoint" in saved


def test_get_credentials_malformed_file_exits(tmp_path, monkeypatch, capsys):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "azure.api").write_text("foo,bar\n1,2\n")  # missing key/endpoint columns
    monkeypatch.chdir(src_dir)
    exit_calls = []
    monkeypatch.setattr('builtins.exit', lambda code=0: exit_calls.append(code))

    _prism_assistant.get_credentials()

    assert exit_calls == [1]
    assert "Error reading API credentials" in capsys.readouterr().out


# ------------------------------------------------------------
# assistant_menu
# ------------------------------------------------------------

def test_assistant_menu_empty_choice_returns_immediately(fake_interface, monkeypatch):
    monkeypatch.setattr(_assistant_menu, 'get_credentials', lambda: ('key', 'endpoint'))
    monkeypatch.setattr('user_interface_menus.utils._commands.init_commands', lambda: {})
    fake_interface.inputs_queue.put('')

    result = _assistant_menu.assistant_menu(fake_interface)

    assert result is None
    assert fake_interface.assistant_active is True


def test_assistant_menu_successful_response_strips_bold_markers(fake_interface, monkeypatch):
    monkeypatch.setattr(_assistant_menu, 'get_credentials', lambda: ('key', 'endpoint'))
    monkeypatch.setattr('user_interface_menus.utils._commands.init_commands',
                         lambda: {'help': {'description': 'Help'}})
    mock_call = MagicMock(return_value={'choices': [{'message': {'content': '**Hello** there'}}]})
    monkeypatch.setattr(_assistant_menu, 'make_assistant_call', mock_call)
    mock_write = MagicMock()
    monkeypatch.setattr(_assistant_menu, 'assistant_header_write', mock_write)
    fake_interface.inputs_queue.put('hi')

    _assistant_menu.assistant_menu(fake_interface)

    mock_call.assert_called_once()
    assert mock_call.call_args[0][0] == 'hi'
    written_messages = [c.args[1][0] for c in mock_write.call_args_list]
    assert any("Please wait" in m for m in written_messages)
    assert any("Hello there" in m for m in written_messages)
    assert all('**' not in m for m in written_messages)


def test_assistant_menu_missing_content_key_reports_error(fake_interface, monkeypatch):
    monkeypatch.setattr(_assistant_menu, 'get_credentials', lambda: ('key', 'endpoint'))
    monkeypatch.setattr('user_interface_menus.utils._commands.init_commands', lambda: {})
    monkeypatch.setattr(_assistant_menu, 'make_assistant_call',
                         MagicMock(return_value={'choices': [{'message': {}}]}))
    mock_write = MagicMock()
    monkeypatch.setattr(_assistant_menu, 'assistant_header_write', mock_write)
    fake_interface.inputs_queue.put('hi')

    _assistant_menu.assistant_menu(fake_interface)

    written_messages = [c.args[1][0] for c in mock_write.call_args_list]
    assert any("Error processing assistant response." in m for m in written_messages)


def test_assistant_menu_no_response_reports_and_returns(fake_interface, monkeypatch):
    monkeypatch.setattr(_assistant_menu, 'get_credentials', lambda: ('key', 'endpoint'))
    monkeypatch.setattr('user_interface_menus.utils._commands.init_commands', lambda: {})
    monkeypatch.setattr(_assistant_menu, 'make_assistant_call', MagicMock(return_value=None))
    mock_write = MagicMock()
    monkeypatch.setattr(_assistant_menu, 'assistant_header_write', mock_write)
    fake_interface.inputs_queue.put('hi')

    result = _assistant_menu.assistant_menu(fake_interface)

    assert result is None
    written_messages = [c.args[1][0] for c in mock_write.call_args_list]
    assert any("No response from the assistant" in m for m in written_messages)
