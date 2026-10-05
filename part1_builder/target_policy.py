"""Google Play target-API policy. Values live in android_policy.json so they can be
refreshed every year (by the agent or by hand) without touching code."""
from __future__ import annotations

import json
from pathlib import Path

POLICY_FILE = Path(__file__).with_name("android_policy.json")

_DEFAULT = {
    "target_api": 36, "min_api": 24,
    "python_version": "3.11.9",
    "archs": ["arm64-v8a", "armeabi-v7a"], "artifact": "aab",
    "pygame_version": "2.6.1",
    "cython_version": "3.0.12",
    "ndk_version": "28c",
    "page_size_16k": True,
    "checked_on": "unknown", "source": "",
}

def load_policy() -> dict:
    policy = dict(_DEFAULT)
    try:
        policy.update(json.loads(POLICY_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return policy


def update_policy(**changes) -> dict:
    """Used by the agent after it confirms a new Play requirement."""
    policy = load_policy()
    policy.update(changes)
    POLICY_FILE.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    return policy
