import pytest

from _error_codes import ERROR_CODES, code_prefix


def test_code_prefix_returns_bracketed_code_for_known_code():
    assert code_prefix('1001') == '[1001] '


def test_code_prefix_raises_keyerror_for_unknown_code():
    with pytest.raises(KeyError):
        code_prefix('9999')


def test_every_registered_code_is_a_4_digit_string():
    for code in ERROR_CODES:
        assert isinstance(code, str)
        assert len(code) == 4
        assert code.isdigit()
