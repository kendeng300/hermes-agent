"""Failure delivery must describe errors, not incidental report fields."""

import json

import pytest

from cron.scheduler import _summarize_cron_failure_for_delivery


@pytest.mark.parametrize("field", ["closure_authorized", "authorization_required", "authentication_checked"])
def test_report_metadata_is_not_provider_authentication_failure(field):
    error = "Script exited with code 1\nstdout:\n" + json.dumps(
        {field: False, "status": "FAIL", "reasons": ["scheduled_receipt_missing"]}
    )
    result = _summarize_cron_failure_for_delivery({"name": "Acceptance"}, error)
    assert "provider authentication error" not in result
    assert "Script exited with code 1" in result


@pytest.mark.parametrize(
    "error",
    [
        "AuthenticationError: invalid credential",
        "authentication failed",
        "AuthorizationError: request denied",
        "authorization failure",
        "request is not authorized",
        "HTTP 401 Unauthorized",
        "HTTP 403 Forbidden",
    ],
)
def test_real_authentication_failures_remain_recognizable(error):
    result = _summarize_cron_failure_for_delivery({"name": "Review"}, error)
    assert "provider authentication error" in result


def test_missing_provider_tokenizer_is_not_a_connection_or_auth_failure():
    error = "TokenizerUnavailable: TOKENIZER_UNAVAILABLE: official example/model assets unavailable or malformed"
    result = _summarize_cron_failure_for_delivery({"name": "Review"}, error)
    assert "TOKENIZER_UNAVAILABLE" in result
    assert "authentication error" not in result
    assert "provider timeout" not in result


@pytest.mark.parametrize("error", ["HTTP 429 rate limit", "ReadTimeout: provider timed out"])
def test_other_provider_failures_keep_existing_categories(error):
    result = _summarize_cron_failure_for_delivery({"name": "Review"}, error)
    assert "provider rate limit" in result or "provider timeout" in result


def test_auth_like_word_fragments_and_long_numbers_are_not_auth_errors():
    result = _summarize_cron_failure_for_delivery(
        {"name": "Acceptance"}, "OAuth callback completed; item 4015 needs review"
    )
    assert "authentication error" not in result


@pytest.mark.parametrize("report", [
    "closure not authorized",
    '{"rows_reviewed": 403, "missed_items": 401, "status": "FAIL"}',
    '{"rows_reviewed": 429, "status": "FAIL"}',
    'The source timeout budget was unchanged; coverage remains incomplete.',
])
def test_script_failure_envelope_takes_precedence_over_arbitrary_stdout(report):
    result = _summarize_cron_failure_for_delivery(
        {"name": "Acceptance"}, "Script exited with code 1\nstdout:\n" + report
    )
    assert "Script exited with code 1" in result
    assert "provider " not in result
    assert "Full details saved in cron output" in result
