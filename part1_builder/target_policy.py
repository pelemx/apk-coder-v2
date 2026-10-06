"""Android target policy for the native WebView/Gradle packaging path."""
from __future__ import annotations
import json
from pathlib import Path
POLICY_FILE = Path(__file__).with_name("android_policy.json")
_DEFAULT = {
    "target_api": 36, "min_api": 35, "compile_sdk": 36,
    "architectures": ["arm64-v8a", "x86_64"], "artifact": "aab",
    "web_runtime": "androidx.webkit", "offline_first": True,
    "page_size_16k": True, "checked_on": "unknown", "source": ""
}
def load_policy():
    policy=dict(_DEFAULT)
    try: policy.update(json.loads(POLICY_FILE.read_text(encoding="utf-8")))
    except (OSError,ValueError): pass
    return policy
def update_policy(**changes):
    policy=load_policy(); policy.update(changes); POLICY_FILE.write_text(json.dumps(policy,indent=2),encoding="utf-8"); return policy
