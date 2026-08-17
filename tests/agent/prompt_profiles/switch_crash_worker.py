from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from agent.prompt_profiles.transaction import (
    DurableMutation, PreparedModelSwitch, commit_model_switch, recover_model_switches,
)


home = Path(os.environ["HERMES_HOME"])
session_id = "session-2977"

if sys.argv[1] == "recover":
    results = recover_model_switches(home, session_id=session_id)
    print(json.dumps(results[0] if results else {"outcome": "NONE", "generation": 0}))
    raise SystemExit(0)

old_client = SimpleNamespace(close=lambda: None)
old_provider = os.environ.get("SYS2977_OLD_PROVIDER", "old")
old_model = os.environ.get("SYS2977_OLD_MODEL", "old")
new_provider = os.environ.get("SYS2977_NEW_PROVIDER", "provider")
new_model = os.environ.get("SYS2977_NEW_MODEL", "new")
durable_path = home / "durable-model.txt"
if not durable_path.exists():
    durable_path.write_text(f"{old_provider}/{old_model}", encoding="utf-8")
agent = SimpleNamespace(
    provider=old_provider, model=old_model, client=old_client, _prompt_profile=None,
    _prompt_profile_state_version=0, session_id=session_id, hermes_home=home,
    context_compressor=None,
)

def crash(state, _record):
    if state == os.environ.get("SYS2977_CRASH_AFTER"):
        os._exit(97)

agent._switch_transition_observer = crash


def apply_durable():
    durable_path.write_text(f"{new_provider}/{new_model}", encoding="utf-8")
    if os.environ.get("SYS2977_CRASH_AFTER_DURABLE") == "1":
        os._exit(97)


def compensate_durable():
    durable_path.write_text(f"{old_provider}/{old_model}", encoding="utf-8")


prepared = PreparedModelSwitch(
    provider=new_provider, model=new_model, api_key="", base_url="", api_mode="",
    profile=None, rendered_profile=None, admission=None, effective_window=None,
    old_identity=(old_provider, old_model, None), old_state_version=0,
    runtime_updates={"provider": new_provider, "model": new_model},
    durable_mutations=(DurableMutation(
        apply_durable, compensate_durable, "durable crash probe",
    ),),
    session_id=session_id, hermes_home=str(home),
)
commit_model_switch(agent, prepared)
