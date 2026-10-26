"""Typed Echo failure facts must survive the real failed cron delivery path."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cron import scheduler


COUNTS = ("received_rows", "unique_received", "completed_new", "completed_reused",
          "unprocessed", "pending", "failed", "backlog")
RECEIVED = COUNTS[:5]


def envelope(*, unknown=False):
    counts = dict(zip(COUNTS, (405, 404, 2, 1, 401, 401, 0, 403)))
    return {
        "schema": "echo_poll_failure_v1", "status": "ERROR",
        "stage": "child_exit", "result_status": "UNKNOWN" if unknown else "VERIFIED",
        "exit_code": 1, "counts": {key: None for key in COUNTS} if unknown else counts,
        "reasons": {} if unknown else {"model_pending": 400, "queue_capped": 1},
        "sources": {} if unknown else {"cnbc_rss": {key: counts[key] for key in RECEIVED}},
        "oldest_unprocessed_age_seconds": None if unknown else 27.5,
        "unresolved_article_ids": [] if unknown else ["a" * 64],
    }


def failure(value, *, encoded=None):
    raw = encoded if encoded is not None else json.dumps(value, separators=(",", ":"))
    return "Script exited with code 1\nstderr:\nECHO_FAILURE_V1=" + raw


@pytest.fixture
def echo_job(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    scripts = home / "scripts"
    (scripts / "echo").mkdir(parents=True)
    for name in ("run_echo_poll.py", "run_scheduled_echo_poll.py", "run_scheduled_echo_poll_extra.py"):
        (scripts / "echo" / name).write_text("# synthetic wrapper fixture\n")
    monkeypatch.setattr(scheduler, "_get_hermes_home", lambda: home)
    return {"id": "synthetic-echo", "name": "Synthetic Echo", "no_agent": True,
            "script": "echo/run_scheduled_echo_poll.py", "deliver": "slack:C_SYNTHETIC"}


@pytest.mark.parametrize("script", ["echo/run_echo_poll.py", "echo/run_scheduled_echo_poll.py",
                                    "echo/run_scheduled_echo_poll_extra.py"])
def test_only_typed_failure_facts_are_formatted(echo_job, script):
    echo_job["script"] = script
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, failure(envelope()))
    for fragment in ("received=405", "unique=404", "completed_new=2", "completed_reused=1",
                     "unprocessed=401", "pending=401", "failed=0", "backlog=403",
                     "model_pending=400", "queue_capped=1"):
        assert fragment in text
    assert "provider authentication" not in text
    assert "accounting=VERIFIED" in text
    assert "completion=VERIFIED" not in text
    assert "a" * 64 not in text  # Internal article identity is not needed in chat.
    assert "ECHO_FAILURE_V1" not in text
    assert "next poll" not in text.lower()


def test_unknown_completion_never_becomes_zero(echo_job):
    value = envelope(unknown=True)
    value.update(stage="timeout", exit_code=124)
    text = scheduler._summarize_cron_failure_for_delivery(
        echo_job, failure(value).replace("code 1\n", "code 124\n"))
    assert "completion=UNKNOWN" in text
    assert "received=0" not in text
    assert "unprocessed=0" not in text
    assert "next poll" not in text.lower()


def test_huge_exit_code_does_not_create_an_unbounded_typed_summary(echo_job):
    value = envelope()
    value["exit_code"] = 10**1000
    error = failure(value).replace("code 1\n", f"code {value['exit_code']}\n")
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, error)
    assert "Echo processing error" not in text
    assert "received=405" not in text


@pytest.mark.parametrize("change", [
    {"no_agent": False}, {"no_agent": "true"}, {"script": "other/run_echo_poll.py"},
    {"script": "echo/run_echo_daily.py"}, {"script": "../echo/run_echo_poll.py"},
    {"script": "/untrusted/echo/run_echo_poll.py"},
])
def test_marker_does_not_authorize_an_unrelated_job(echo_job, change):
    echo_job.update(change)
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, failure(envelope()))
    assert "Script exited with code 1" in text
    assert "received=405" not in text
    assert "provider authentication" not in text


def test_wrapper_symlink_escape_is_not_trusted(echo_job, tmp_path):
    path = scheduler._get_hermes_home() / "scripts" / echo_job["script"]
    path.unlink()
    elsewhere = tmp_path / "not_echo.py"
    elsewhere.write_text("# not the configured wrapper\n")
    path.symlink_to(elsewhere)
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, failure(envelope()))
    assert "received=405" not in text


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(status="OK"),
    lambda v: v.update(stage="unexpected"),
    lambda v: v.update(exit_code=2),
    lambda v: v.update(exit_code=True),
    lambda v: v.update(extra="PRIVATE SOURCE PROSE"),
    lambda v: v["counts"].update(unprocessed=True),
    lambda v: v["counts"].update(unprocessed=-1),
    lambda v: v["counts"].update(received_rows=10**20),
    lambda v: v["counts"].update(unique_received=403),
    lambda v: v["reasons"].update(model_pending=399),
    lambda v: v["reasons"].update(secret_headline=0),
    lambda v: v["sources"]["cnbc_rss"].update(completed_new=9),
    lambda v: v["sources"].update(private_headline=v["sources"].pop("cnbc_rss")),
    lambda v: v.update(oldest_unprocessed_age_seconds=float("nan")),
    lambda v: v.update(oldest_unprocessed_age_seconds=10**1000),
    lambda v: v.update(unresolved_article_ids=["PRIVATE SOURCE PROSE"]),
    lambda v: v.update(result_status="UNKNOWN"),
])
def test_invalid_receipt_uses_generic_script_failure(echo_job, mutation):
    value = envelope()
    mutation(value)
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, failure(value))
    assert "Script exited with code 1" in text
    assert "received=405" not in text
    assert "PRIVATE SOURCE PROSE" not in text
    assert "provider authentication" not in text


@pytest.mark.parametrize("variant", ["duplicate_key", "duplicate_record", "oversize", "stdout_only", "transcript"])
def test_only_one_bounded_stderr_record_is_authoritative(echo_job, variant):
    raw = json.dumps(envelope())
    if variant == "duplicate_key":
        error = failure(None, encoded=raw[:-1] + ', "status":"ERROR"}')
    elif variant == "duplicate_record":
        error = failure(envelope()) + "\nECHO_FAILURE_V1=" + raw
    elif variant == "oversize":
        error = failure(None, encoded=" " * 32768 + raw)
    elif variant == "stdout_only":
        error = failure(envelope()).replace("\nstderr:\n", "\nstdout:\n")
    else:
        error = "Script exited with code 1\nstderr:\narticle said:\nECHO_FAILURE_V1=" + raw
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, error)
    assert "Script exited with code 1" in text
    assert "received=405" not in text


@pytest.mark.parametrize("unknown", [False, True])
def test_real_failed_script_execution_reaches_delivery_and_stays_failed(echo_job, monkeypatch, unknown):
    value = envelope(unknown=unknown)
    transport = Mock(return_value=SimpleNamespace(returncode=1, stdout="[SILENT]\nPRIVATE SOURCE PROSE",
        stderr="ECHO_FAILURE_V1=" + json.dumps(value)))
    monkeypatch.setattr(scheduler, "_run_script_process", transport)
    monkeypatch.setattr(scheduler, "claim_dispatch", lambda _: True)
    save, deliver, mark = Mock(), Mock(return_value=None), Mock()
    monkeypatch.setattr(scheduler, "save_job_output", save)
    monkeypatch.setattr(scheduler, "_deliver_result", deliver)
    monkeypatch.setattr(scheduler, "mark_job_run", mark)
    # Real shared fire body, run_job, no-agent path, script adapter and formatter.
    assert scheduler._run_one_job(echo_job)
    transport.assert_called_once()
    save.assert_called_once()
    deliver.assert_called_once()
    text = deliver.call_args.args[1]
    assert ("completion=UNKNOWN" if unknown else "unprocessed=401") in text
    assert "PRIVATE SOURCE PROSE" not in text
    assert "[SILENT]" not in text
    assert mark.call_args.args[1] is False
    assert "Script exited with code 1" in mark.call_args.args[2]
    assert "ECHO_FAILURE_V1=" in save.call_args.args[1]


def test_successful_silent_script_is_still_silent(echo_job, monkeypatch):
    monkeypatch.setattr(scheduler, "_run_script_process", Mock(return_value=SimpleNamespace(
        returncode=0, stdout="[SILENT]", stderr="")))
    monkeypatch.setattr(scheduler, "claim_dispatch", lambda _: True)
    monkeypatch.setattr(scheduler, "save_job_output", Mock())
    deliver, mark = Mock(), Mock()
    monkeypatch.setattr(scheduler, "_deliver_result", deliver)
    monkeypatch.setattr(scheduler, "mark_job_run", mark)
    assert scheduler._run_one_job(echo_job)
    deliver.assert_not_called()
    assert mark.call_args.args[1] is True


def test_unrelated_provider_auth_error_contract_is_unchanged():
    text = scheduler._summarize_cron_failure_for_delivery({"name": "Other agent"}, "HTTP 401 unauthorized")
    assert "provider authentication error" in text


def alert_accounting(*, unknown=False):
    values = {"considered": 3, "verified": 1, "routine": 1, "pending": 1, "unscanned_rows": 0}
    return {"status": "UNKNOWN" if unknown else "VERIFIED",
            **({key: None for key in values} if unknown else values),
            "reasons": {} if unknown else {"delivery_not_verified": 1}}


@pytest.mark.parametrize("received_unknown,alert_unknown", [(False, False), (True, False), (False, True)])
def test_alert_accounting_is_independent_of_received_processing(echo_job, received_unknown, alert_unknown):
    value = envelope(unknown=received_unknown)
    value["market_event_alerts"] = alert_accounting(unknown=alert_unknown)
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, failure(value))
    if alert_unknown:
        assert "market-event completion=UNKNOWN" in text
        assert "market-event pending=0" not in text
    else:
        assert "market-event accounting=VERIFIED" in text
        assert "considered=3, verified=1, routine=1, pending=1, unscanned_rows=0" in text
        assert "delivery_not_verified=1" in text
    assert ("completion=UNKNOWN" if received_unknown else "received=405") in text


@pytest.mark.parametrize("mutation", [
    lambda v: v.update(extra="PRIVATE SOURCE PROSE"),
    lambda v: v.update(status="COMPLETE"),
    lambda v: v.update(verified=True),
    lambda v: v.update(pending=-1),
    lambda v: v.update(pending=10**20),
    lambda v: v.update(considered=0),
    lambda v: v["reasons"].update(secret_headline=0),
    lambda v: v["reasons"].update(delivery_not_verified=2),
    lambda v: v.update(status="UNKNOWN"),
    lambda v: v.update(pending=0, reasons={}, unscanned_rows=1),
])
def test_invalid_alert_accounting_cannot_inject_delivery_text(echo_job, mutation):
    value = envelope()
    value["market_event_alerts"] = alert_accounting()
    mutation(value["market_event_alerts"])
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, failure(value))
    assert "Script exited with code 1" in text
    assert "market-event accounting=VERIFIED" not in text
    assert "received=405" not in text
    assert "PRIVATE SOURCE PROSE" not in text and "secret_headline" not in text


def test_global_scan_failure_does_not_invent_received_sources(echo_job):
    value = envelope()
    value["market_event_alerts"] = {"status": "VERIFIED", "considered": 0,
        "verified": 0, "routine": 0, "pending": 1, "unscanned_rows": 17,
        "reasons": {"source_scan_deadline_exhausted": 1}}
    text = scheduler._summarize_cron_failure_for_delivery(echo_job, failure(value))
    assert "received=405" in text and "source_scan_deadline_exhausted=1" in text
    assert "unscanned_rows=17" in text


@pytest.mark.parametrize("alert_unknown", [False, True])
def test_timeout_cannot_certify_alert_completion(echo_job, alert_unknown):
    value = envelope(unknown=True)
    value.update(stage="timeout", exit_code=124)
    value["market_event_alerts"] = alert_accounting(unknown=alert_unknown)
    text = scheduler._summarize_cron_failure_for_delivery(
        echo_job, failure(value).replace("code 1\n", "code 124\n"))
    assert "market-event accounting=VERIFIED" not in text
    if alert_unknown:
        assert "stage=timeout" in text and "market-event completion=UNKNOWN" in text
    else:
        assert "Script exited with code 124" in text
        assert "Echo processing error" not in text


def test_actual_failed_script_delivers_alert_failure_with_completed_source_work(echo_job, monkeypatch):
    value = envelope()
    counts = dict(zip(COUNTS, (3, 3, 3, 0, 0, 0, 0, 0)))
    value.update(counts=counts, reasons={},
        sources={"cnbc_rss": {key: counts[key] for key in RECEIVED}},
        oldest_unprocessed_age_seconds=None, unresolved_article_ids=[],
        market_event_alerts=alert_accounting())
    monkeypatch.setattr(scheduler, "_run_script_process", Mock(return_value=SimpleNamespace(
        returncode=1, stdout="[SILENT]\nPRIVATE SOURCE PROSE", stderr="ECHO_FAILURE_V1=" + json.dumps(value))))
    monkeypatch.setattr(scheduler, "claim_dispatch", lambda _: True)
    monkeypatch.setattr(scheduler, "save_job_output", Mock())
    delivered, marked = Mock(return_value=None), Mock()
    monkeypatch.setattr(scheduler, "_deliver_result", delivered)
    monkeypatch.setattr(scheduler, "mark_job_run", marked)
    assert scheduler._run_one_job(echo_job)
    delivered.assert_called_once()
    text = delivered.call_args.args[1]
    assert "unprocessed=0" in text and "delivery_not_verified=1" in text
    assert "PRIVATE SOURCE PROSE" not in text and "[SILENT]" not in text
    assert marked.call_args.args[1] is False
