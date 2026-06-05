import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")

REQUIRED = ["numpy", "scipy", "matplotlib"]
missing = [p for p in REQUIRED if importlib.util.find_spec(p) is None]
if missing:
    print("Installing missing libraries:", ", ".join(missing))
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)

BENCHMARK_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BENCHMARK_DIR / "tfa-environment-settings.json"
RESULTS_DIR   = BENCHMARK_DIR / "results"
PACKAGE_ROOT  = BENCHMARK_DIR.parent.parent

approved = json.loads(
    (PACKAGE_ROOT / "scripts" / "tfa_common" / "approved-version.json")
    .read_text(encoding="utf-8")
)
sys.path.insert(0, str(PACKAGE_ROOT / "scripts" / "tfa_common" / approved["approved_folder"]))

import tfa_common as tfa  # noqa: E402

result = tfa.run(settings_path=SETTINGS_FILE, results_root=RESULTS_DIR)

print("code      :", result["code"])
print("run_folder:", result.get("run_folder"))
for c in result.get("calls", []):
    mark = "OK " if c["code"] == "OK" else "ERR"
    print("  [" + mark + "] " + c["specialist"].ljust(44) + " " + c["desc"])
