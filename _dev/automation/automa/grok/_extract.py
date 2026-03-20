import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
AUTOMA_PATH = ROOT / "Grok Assets Synchronizer.automa.json"
OUTPUT_PATH = ROOT / "_extracted_code.js"


def iter_nodes(payload):
    drawflow = payload.get("drawflow", {})
    if isinstance(drawflow, dict):
        nodes = drawflow.get("nodes")
        if isinstance(nodes, list):
            yield from nodes
            return
        if isinstance(nodes, dict):
            yield from nodes.values()
            return
        if all(isinstance(value, dict) for value in drawflow.values()):
            yield from drawflow.values()


with AUTOMA_PATH.open("r", encoding="utf-8-sig") as handle:
    data = json.load(handle)

for node in iter_nodes(data):
    if node.get("id") != "sync_js":
        continue
    code = node.get("data", {}).get("code", "")
    if not code:
        break
    normalized = code.lstrip("\ufeff").replace("\r\n", "\n")
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        handle.write(normalized)
    print(f"Extracted {len(code)} chars, {code.count(chr(10))} lines")
    print(f"Source: {AUTOMA_PATH}")
    print(f"Output: {OUTPUT_PATH}")
    break
else:
    raise SystemExit("sync_js code block not found")
