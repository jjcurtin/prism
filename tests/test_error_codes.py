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


def test_2004_survey_link_error_code_is_registered():
    """Regression test for the misconfigured-survey-ID coordinator page
    (ParticipantManager.process_task) -- that fix pages with code 2004,
    added specifically because reusing 2001 ("SMS send failed") would have
    misattributed a link-parsing failure as a send failure."""
    assert '2004' in ERROR_CODES
    assert code_prefix('2004') == '[2004] '
