import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AUTOMA_PATH = ROOT / "Grok Assets Synchronizer.automa.json"
SOURCE_PATH = ROOT / "_extracted_code.js"


with SOURCE_PATH.open("r", encoding="utf-8") as handle:
    code = handle.read()

with AUTOMA_PATH.open("r", encoding="utf-8-sig") as handle:
    data = json.load(handle)

for node in data.get("drawflow", {}).get("nodes", []):
    if node.get("id") != "sync_js":
        continue
    node.setdefault("data", {})["code"] = code
    with AUTOMA_PATH.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Injected {len(code)} chars into {AUTOMA_PATH}")
    break
else:
    raise SystemExit("sync_js code block not found")
