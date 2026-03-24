"""Build the Automa workflow JSON with the sync code properly embedded."""
import json
from pathlib import Path

HERE = Path(__file__).parent
WORKFLOW_PATH = HERE / "STS Gemini Image Synchronizer.automa.json"
CODE_PATH = HERE / "_sync_code.js"

with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
    wf = json.load(f)

with open(CODE_PATH, "r", encoding="utf-8") as f:
    code = f.read()

# Update the JS block
js_node = wf["drawflow"]["nodes"][2]
js_node["data"]["code"] = code
js_node["data"]["context"] = "website"

with open(WORKFLOW_PATH, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

print(f"Workflow updated: {len(code)} chars of JS code")
print(f"Context: {js_node['data']['context']}")
print(f"PreloadScripts: {js_node['data']['preloadScripts']}")
