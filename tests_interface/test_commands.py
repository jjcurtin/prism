"""Tests for utils/_commands.py.

`init_commands()` imports and calls into every menu module transitively --
importing it at all requires the whole `user_interface_menus` tree to
import cleanly (true post phase-03, since `_keyboard.py` replaced the
Windows-only `msvcrt` import). It builds and returns the single flat
"global command" dict consumed by `_menu_helper.load_menus()` and rebuilt
fresh for the assistant's system prompt on every query
(`assistant/_prism_assistant.py`), so we assert on structural shape
(expected keys present, each entry has the right fields) rather than exact
key count, per the fragility already noted in utils/CLAUDE.md ("Worth
caching after first build" -- not fixed here, out of scope for a coverage
pass).
"""
from user_interface_menus.utils._commands import init_commands


EXPECTED_KEYS = {
    'main', 'check', 'help', 'assistant', 'tasks', 'participants',
    'logs', 'settings', 'shutdown', 'command', 'register', 'debug',
    'recent', 'exit',
}


def test_init_commands_returns_a_dict():
    result = init_commands()
    assert isinstance(result, dict)
    assert len(result) > 0


def test_init_commands_contains_expected_top_level_keys():
    result = init_commands()
    missing = EXPECTED_KEYS - result.keys()
    assert not missing, f"missing expected menu keys: {missing}"


def test_init_commands_every_entry_has_description_and_menu_caller():
    result = init_commands()
    for key, entry in result.items():
        assert 'description' in entry, f"{key!r} missing 'description'"
        assert 'menu_caller' in entry, f"{key!r} missing 'menu_caller'"
        assert isinstance(entry['description'], str), f"{key!r} description is not a str"
        caller = entry['menu_caller']
        assert callable(caller) or isinstance(caller, str), (
            f"{key!r} menu_caller is neither callable nor a string: {caller!r}"
        )


def test_init_commands_known_entries_point_at_expected_callables():
    result = init_commands()
    # Spot-check a handful of specific, semantically important entries
    # (rather than the whole ~90-entry dict, which would be a brittle
    # over-specified test) to catch the exact positional-destructuring /
    # copy-paste mistakes this registry is prone to (see utils/CLAUDE.md).
    assert result['help']['description'] == 'Help'
    assert callable(result['help']['menu_caller'])
    assert result['shutdown']['description'] == 'Shutdown PRISM'
    assert callable(result['shutdown']['menu_caller'])
    assert result['command']['menu_caller'].__name__ == 'print_global_command_menu'


def test_init_commands_is_idempotent_and_rebuildable():
    """Called fresh on every assistant query (not cached, see
    assistant/_assistant_menu.py) -- calling it repeatedly must keep
    working and keep returning equivalent dicts. Compares keys and
    descriptions only (not menu_caller identity): most entries are
    `lambda`s rebuilt fresh on every call, so distinct calls never produce
    `==`-equal function objects even though the dicts are equivalent."""
    first = init_commands()
    second = init_commands()
    assert first is not second
    assert first.keys() == second.keys()
    assert {k: v['description'] for k, v in first.items()} == {
        k: v['description'] for k, v in second.items()
    }
