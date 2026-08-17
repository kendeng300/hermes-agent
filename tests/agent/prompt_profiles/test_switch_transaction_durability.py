from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


STAGES = ("PREPARED", "CONFIG_APPLIED", "RUNTIME_STAGED", "COMMITTED", "CLEANUP_PENDING")


def _agent(home: Path, *, generation: int = 0):
    old_client = SimpleNamespace(closed=False, close=lambda: setattr(old_client, "closed", True))
    return SimpleNamespace(
        provider="old", model="old", client=old_client, _prompt_profile=None,
        _prompt_profile_state_version=generation, session_id="session-2977",
        hermes_home=home, context_compressor=None,
    )


def _prepared(agent, *, model="new"):
    from agent.prompt_profiles.transaction import PreparedModelSwitch

    candidate = SimpleNamespace(closed=False, close=lambda: setattr(candidate, "closed", True))
    return PreparedModelSwitch(
        provider="provider", model=model, api_key="", base_url="", api_mode="",
        profile=None, rendered_profile=None, admission=None, effective_window=None,
        old_identity=("old", "old", None), old_state_version=agent._prompt_profile_state_version,
        runtime_updates={"provider": "provider", "model": model}, candidate_client=candidate,
        session_id=agent.session_id, hermes_home=str(agent.hermes_home),
    )


def test_durable_commit_records_all_fsynced_transitions_and_retires_old_client(tmp_path, monkeypatch):
    from agent.prompt_profiles.transaction import commit_model_switch

    agent = _agent(tmp_path)
    old_client = agent.client
    seen = []
    monkeypatch.setattr(agent, "_switch_transition_observer", lambda state, record: seen.append(state), raising=False)
    commit_model_switch(agent, _prepared(agent))

    assert seen == list(STAGES)
    assert old_client.closed is True
    assert agent.model == "new"
    state = json.loads((tmp_path / "state/model_switch_state/session-2977.json").read_text())
    assert state["generation"] == 1 and state["model"] == "new"
    assert not list((tmp_path / "state/model_switch_journal").glob("*.json"))


def test_generation_compare_and_swap_rejects_second_writer(tmp_path):
    from agent.prompt_profiles.transaction import PromptProfileError, commit_model_switch

    first = _agent(tmp_path)
    stale = _agent(tmp_path)
    commit_model_switch(first, _prepared(first, model="winner"))
    with pytest.raises(PromptProfileError, match="SWITCH_CONFLICT"):
        commit_model_switch(stale, _prepared(stale, model="loser"))


def test_concurrent_process_writers_have_one_cas_winner(tmp_path):
    script = Path(__file__).with_name("switch_crash_worker.py")
    env = dict(os.environ, HERMES_HOME=str(tmp_path))
    writers = [
        subprocess.Popen([sys.executable, str(script), "switch"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    results = [writer.communicate(timeout=10) + (writer.returncode,) for writer in writers]
    assert sorted(result[2] for result in results) == [0, 1]
    assert sum("SWITCH_CONFLICT" in result[1] for result in results) == 1
    state = json.loads((tmp_path / "state/model_switch_state/session-2977.json").read_text())
    assert state["generation"] == 1


def test_lock_acquisition_is_bounded_and_visible_across_processes(tmp_path):
    from agent.prompt_profiles.transaction import InterprocessSwitchLock, PromptProfileError

    lock = InterprocessSwitchLock(tmp_path / "locks/session.lock", timeout=0.15)
    with lock:
        code = (
            "from pathlib import Path\n"
            "from agent.prompt_profiles.transaction import InterprocessSwitchLock\n"
            f"with InterprocessSwitchLock(Path({str(lock.path)!r}), timeout=.1): pass\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parents[3], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "SWITCH_LOCK_TIMEOUT" in proc.stderr


@pytest.mark.parametrize("direction", ("openai_to_deepseek", "deepseek_to_openai"))
@pytest.mark.parametrize("mode", ("session", "global"))
@pytest.mark.parametrize("stage", STAGES)
def test_subprocess_crash_matrix_is_derived_from_executed_records(tmp_path, stage, direction, mode):
    script = Path(__file__).with_name("switch_crash_worker.py")
    old_provider, old_model, new_provider, new_model = (
        ("openai-codex", "gpt-5.6-sol", "deepseek", "deepseek-v4-flash")
        if direction == "openai_to_deepseek" else
        ("deepseek", "deepseek-v4-flash", "openai-codex", "gpt-5.6-sol")
    )
    env = dict(
        os.environ, HERMES_HOME=str(tmp_path), SYS2977_CRASH_AFTER=stage,
        SYS2977_OLD_PROVIDER=old_provider, SYS2977_OLD_MODEL=old_model,
        SYS2977_NEW_PROVIDER=new_provider, SYS2977_NEW_MODEL=new_model,
        SYS2977_MODE=mode,
    )
    crashed = subprocess.run([sys.executable, str(script), "switch"], env=env, capture_output=True, text=True)
    assert crashed.returncode == 97

    journals = list((tmp_path / "state/model_switch_journal").glob("*.json"))
    assert len(journals) == 1
    crash_record = json.loads(journals[0].read_text())
    assert crash_record["state"] == stage

    recovered = subprocess.run([sys.executable, str(script), "recover"], env=env, capture_output=True, text=True)
    assert recovered.returncode == 0, recovered.stderr
    record = json.loads(recovered.stdout)
    expected = "COMMITTED" if stage in {"COMMITTED", "CLEANUP_PENDING"} else "ABORTED"
    assert record["outcome"] == expected
    assert record["generation"] == (1 if expected == "COMMITTED" else 0)
    # These are derived invariants from the executed crash/recovery records;
    # no rollback_identical/prior_probe_usable/partial_persist claim is used.
    expected_provider = new_provider if expected == "COMMITTED" else old_provider
    expected_model = new_model if expected == "COMMITTED" else old_model
    if expected == "COMMITTED":
        state = json.loads((tmp_path / "state/model_switch_state/session-2977.json").read_text())
        assert (state["provider"], state["model"]) == (expected_provider, expected_model)
    assert not journals[0].exists()


def test_ambiguous_and_corrupt_recovery_fail_closed(tmp_path):
    from agent.prompt_profiles.transaction import PromptProfileError, recover_model_switches

    journal_dir = tmp_path / "state/model_switch_journal"
    journal_dir.mkdir(parents=True)
    (journal_dir / "bad.json").write_text("{truncated", encoding="utf-8")
    with pytest.raises(PromptProfileError, match="SWITCH_JOURNAL_AMBIGUOUS"):
        recover_model_switches(tmp_path, session_id="session-2977")


def test_recovery_aborts_next_generation_when_authoritative_state_retains_prior_transaction(tmp_path):
    from agent.prompt_profiles.transaction import SwitchJournal, recover_model_switches

    state_dir = tmp_path / "state/model_switch_state"
    state_dir.mkdir(parents=True)
    (state_dir / "session-2977.json").write_text(json.dumps({
        "schema_version": 1,
        "session_id": "session-2977",
        "generation": 1,
        "transaction_id": "prior-transaction",
        "provider": "old-provider",
        "model": "old-model",
    }), encoding="utf-8")
    journal = SwitchJournal(tmp_path / "state/model_switch_journal/pending.json")
    journal.transition("PREPARED", generation=2, payload={
        "transaction_id": "pending-transaction",
        "session_id": "session-2977",
        "old": {"provider": "old-provider", "model": "old-model"},
        "new": {"provider": "new-provider", "model": "new-model"},
    })

    assert recover_model_switches(tmp_path, session_id="session-2977") == [{
        "outcome": "ABORTED",
        "generation": 1,
        "session_id": "session-2977",
        "transaction_id": "pending-transaction",
    }]
    assert not journal.path.exists()


def test_duplicate_live_journals_fail_closed_before_partial_recovery(tmp_path):
    from agent.prompt_profiles.transaction import PromptProfileError, SwitchJournal, recover_model_switches

    journal_dir = tmp_path / "state/model_switch_journal"
    journals = []
    for transaction_id in ("first-transaction", "second-transaction"):
        journal = SwitchJournal(journal_dir / f"{transaction_id}.json")
        journal.transition("PREPARED", generation=1, payload={
            "transaction_id": transaction_id,
            "session_id": "session-2977",
            "old": {"provider": "old", "model": "old"},
            "new": {"provider": "new", "model": "new"},
        })
        journals.append(journal)

    with pytest.raises(PromptProfileError, match="SWITCH_JOURNAL_AMBIGUOUS"):
        recover_model_switches(tmp_path, session_id="session-2977")
    assert all(journal.path.exists() for journal in journals)


def test_journal_rejects_secret_before_first_persisted_byte(tmp_path):
    from agent.prompt_profiles.transaction import PromptProfileError, SwitchJournal

    path = tmp_path / "journal.json"
    journal = SwitchJournal(path, secret_values=("sekrit-canary",))
    with pytest.raises(PromptProfileError, match="SECRET_BOUNDARY_VIOLATION"):
        journal.transition("PREPARED", generation=1, payload={"transaction_id": "sekrit-canary", "session_id": "session", "old": {"provider": "old", "model": "old"}, "new": {"provider": "new", "model": "new"}})
    assert not path.exists()


def _valid_payload():
    return {"transaction_id": "transaction-1", "session_id": "session-2977", "old": {"provider": "old", "model": "old"}, "new": {"provider": "new", "model": "new"}}


def test_journal_enforces_graph_terminal_immutability_and_exact_schema(tmp_path):
    from agent.prompt_profiles.transaction import PromptProfileError, SwitchJournal

    journal = SwitchJournal(tmp_path / "journal.json")
    for illegal_initial in (
        "CONFIG_APPLIED", "RUNTIME_STAGED", "COMMITTED",
        "CLEANUP_PENDING", "DONE", "ABORTED",
    ):
        fresh = SwitchJournal(tmp_path / f"initial-{illegal_initial}.json")
        with pytest.raises(PromptProfileError, match="SWITCH_JOURNAL_AMBIGUOUS"):
            fresh.transition(illegal_initial, generation=1, payload=_valid_payload())
        assert not fresh.path.exists()
    journal.transition("PREPARED", generation=1, payload=_valid_payload())
    for illegal in ("RUNTIME_STAGED", "COMMITTED", "CLEANUP_PENDING", "DONE", "PREPARED"):
        with pytest.raises(PromptProfileError, match="SWITCH_JOURNAL_AMBIGUOUS"):
            journal.transition(illegal, generation=1, payload=_valid_payload())
    journal.transition("CONFIG_APPLIED", generation=1, payload=_valid_payload())
    journal.transition("ABORTED", generation=1, payload=_valid_payload())
    with pytest.raises(PromptProfileError, match="SWITCH_JOURNAL_AMBIGUOUS"):
        journal.transition("PREPARED", generation=1, payload=_valid_payload())

    raw = json.loads(journal.path.read_text())
    mutations = [
        {k: v for k, v in raw.items() if k != "schema_version"},
        {**raw, "generation": True},
        {**raw, "extra": 1},
        {**raw, "payload": {}},
    ]
    for index, record in enumerate(mutations):
        path = tmp_path / f"bad-{index}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        with pytest.raises(PromptProfileError, match="SWITCH_JOURNAL_AMBIGUOUS"):
            SwitchJournal(path).recover(expected_generation=None)


def test_journal_recovery_rejects_leaf_symlink(tmp_path):
    from agent.prompt_profiles.transaction import PromptProfileError, SwitchJournal

    target = tmp_path / "outside.json"
    target.write_text(json.dumps({"schema_version": 1, "state": "PREPARED", "generation": 1, "payload": _valid_payload()}))
    link = tmp_path / "journal.json"
    link.symlink_to(target)
    with pytest.raises(PromptProfileError, match="SWITCH_JOURNAL_AMBIGUOUS"):
        SwitchJournal(link).recover(expected_generation=None)


def test_safe_session_path_is_contained_distinct_and_type_strict(tmp_path):
    from agent.prompt_profiles.transaction import PromptProfileError, _safe_session_id

    root = tmp_path / "sessions"
    root.mkdir()
    first, second = root / "one", root / "two"
    assert _safe_session_id(first, session_root=root) != _safe_session_id(second, session_root=root)
    for value in (tmp_path / "outside", root / ".." / "outside", True, object()):
        with pytest.raises(PromptProfileError, match="INVALID_SWITCH_SESSION_ID"):
            _safe_session_id(value, session_root=root)


@pytest.mark.parametrize("failure_state", ("COMMITTED", "CLEANUP_PENDING", "DONE"))
def test_post_cas_transition_failure_rolls_forward_and_preserves_journal(tmp_path, monkeypatch, failure_state):
    from agent.prompt_profiles.transaction import SwitchJournal, commit_model_switch

    agent = _agent(tmp_path)
    prepared = _prepared(agent)
    original = SwitchJournal.transition
    def fail(self, state, **kwargs):
        if state == failure_state:
            raise OSError(f"injected {state}")
        return original(self, state, **kwargs)
    monkeypatch.setattr(SwitchJournal, "transition", fail)
    with pytest.raises(OSError, match="injected"):
        commit_model_switch(agent, prepared)
    authority = json.loads((tmp_path / "state/model_switch_state/session-2977.json").read_text())
    assert (authority["provider"], authority["model"], authority["generation"]) == ("provider", "new", 1)
    assert (agent.provider, agent.model, agent._prompt_profile_state_version) == ("provider", "new", 1)
    assert len(list((tmp_path / "state/model_switch_journal").glob("*.json"))) == 1


def test_post_cas_cleanup_failure_rolls_forward_and_preserves_journal(tmp_path):
    from agent.prompt_profiles.transaction import commit_model_switch

    agent = _agent(tmp_path)
    prepared = _prepared(agent)
    agent.client.close = lambda: (_ for _ in ()).throw(OSError("injected cleanup"))
    # The retiring client is the pre-switch client captured from the agent.
    with pytest.raises(OSError, match="injected cleanup"):
        commit_model_switch(agent, prepared)
    authority = json.loads((tmp_path / "state/model_switch_state/session-2977.json").read_text())
    assert (authority["provider"], authority["model"], authority["generation"]) == ("provider", "new", 1)
    assert (agent.provider, agent.model, agent._prompt_profile_state_version) == ("provider", "new", 1)
    journals = list((tmp_path / "state/model_switch_journal").glob("*.json"))
    assert len(journals) == 1
    assert json.loads(journals[0].read_text())["state"] == "CLEANUP_PENDING"


def test_durable_mutations_execute_before_authoritative_cas_with_ledger(tmp_path):
    from dataclasses import replace
    from agent.prompt_profiles.transaction import DurableMutation, commit_model_switch

    agent = _agent(tmp_path)
    observed = []

    def apply_durable():
        # Runs BEFORE CAS: the authority state file does not yet exist and the
        # journal is still at a pre-CAS state (RUNTIME_STAGED), so an
        # in-process failure can compensate to OLD.
        journal_dir = tmp_path / "state/model_switch_journal"
        journals = list(journal_dir.glob("*.json"))
        observed.append((len(journals), json.loads(journals[0].read_text())["state"]))

    prepared = replace(
        _prepared(agent),
        durable_mutations=(DurableMutation(
            apply_durable, lambda: None, "CAS-order probe",
        ),),
    )
    commit_model_switch(agent, prepared)

    # Durable mutations execute pre-CAS so an in-process failure can
    # compensate to OLD (the TUI "failed switch is a no-op" contract).
    assert observed == [(1, "RUNTIME_STAGED")]


def test_crash_after_durable_write_pre_cas_fails_closed(tmp_path):
    script = Path(__file__).with_name("switch_crash_worker.py")
    env = dict(
        os.environ,
        HERMES_HOME=str(tmp_path),
        SYS2977_CRASH_AFTER_DURABLE="1",
        SYS2977_OLD_PROVIDER="old-provider",
        SYS2977_OLD_MODEL="old-model",
        SYS2977_NEW_PROVIDER="new-provider",
        SYS2977_NEW_MODEL="new-model",
    )
    crashed = subprocess.run(
        [sys.executable, str(script), "switch"], env=env,
        capture_output=True, text=True,
    )
    assert crashed.returncode == 97
    assert (tmp_path / "durable-model.txt").read_text(encoding="utf-8") == "new-provider/new-model"

    recovered = subprocess.run(
        [sys.executable, str(script), "recover"], env=env,
        capture_output=True, text=True,
    )
    # A crash between a durable write and CAS leaves NEW durable state that
    # process-local compensation cannot repair. Recovery MUST fail closed
    # (RECOVERY_CONFLICT) rather than silently ABORTing the journal while the
    # durable surface stays on the NEW route.
    assert recovered.returncode != 0, recovered.stdout
