import json

with open('d:/@Workspace/@Development/@Scripts/@Python/ScriptToScene-Studio/_dev/automation/automa/Assets Synchronizer.automa.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Find the javascript-code node (sync_js)
drawflow = data.get('drawflow', {}).get('drawflow', data.get('drawflow', {}))
for node_id, node in drawflow.items():
    if node.get('name') == 'javascript-code' or node.get('data', {}).get('everyNewTab'):
        code = node.get('data', {}).get('code', '')
        if code:
            with open('d:/@Workspace/@Development/@Scripts/@Python/ScriptToScene-Studio/_dev/automation/automa/_sync_js_code.js', 'w', encoding='utf-8') as out:
                out.write(code)
            print(f"Extracted {len(code)} chars, {code.count(chr(10))} lines")
            print(f"Node ID: {node_id}")
            break
