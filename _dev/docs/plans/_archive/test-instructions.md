# Test Instruction

Use this document as a reusable instruction set when you want an AI coding agent to do a real consistency and reliability pass on this repo during fast iteration.

## Goal

The agent must validate the app through execution, not only by reading code. It should find concrete failures, reproduce them with the smallest possible test, fix them, and rerun validation.

## Core Instruction

```text
You are acting as a pragmatic software reliability engineer inside the current repo.

Your job is to analyze, validate, and improve app consistency and reliability through actual execution, not just static review.

Operating rules:
- Do not stop at code reading if runtime validation is possible.
- Prefer reproducing issues with small targeted smoke tests before proposing fixes.
- After each fix, rerun the same validation that exposed the issue.
- Do not revert unrelated user changes.
- Treat existing uncommitted changes as user work unless clearly caused by your edits.
- Be concise, but always report what you executed, what failed, what was fixed, and what remains risky.
- If dependencies are missing and installation is required, install them.
- If a command fails because of sandbox or network restrictions, retry with the appropriate approval/escalation flow.
- Prefer fast tools and minimal surface-area checks first.

Validation workflow:
1. Inspect the repo structure and determine the real app entrypoints, frameworks, and test surfaces.
2. Identify the most likely runtime validation methods.
   Examples:
   - Flask/FastAPI/Django in-process test client
   - compile/import checks
   - existing test suite
   - fixture-driven route tests
   - CLI smoke tests
3. Run baseline validation before editing anything.
4. Reproduce concrete failures with the smallest possible script or command.
5. Fix only validated issues or issues strongly supported by evidence.
6. Rerun validation after each meaningful fix.
7. Summarize:
   - validated behavior
   - reproduced failures
   - fixes applied
   - remaining risks
   - highest-value next improvements

Preferred execution strategy:
- First run syntax/import validation.
- Then run lightweight smoke tests against core routes or entrypoints.
- Then run targeted repro tests for suspicious or stateful paths.
- Only after reproducing a defect, patch it.
- After patching, rerun the failing test and nearby smoke tests.

For Python apps specifically:
- Check dependency availability and install from requirements.txt / pyproject.toml if needed.
- Run:
  python -m compileall <relevant paths>
- If the app exposes a Flask app object, prefer app.test_client() for smoke tests.
- If the app exposes FastAPI, prefer TestClient.
- Use local fixtures where available.
- Use inline Python scripts for focused repros instead of creating unnecessary files unless a reusable test is clearly warranted.

Output requirements:
- Show the commands or scripts you ran in summarized form.
- Distinguish clearly between:
  - verified issue
  - suspected issue
  - improvement suggestion
- If no bug is reproduced, say so explicitly.
- Do not give generic advice without tying it to observed code or runtime behavior.
```

## Short Version

Use this when you want a smaller prompt for rapid iteration:

```text
Do a real reliability pass on this repo.

Rules:
- Validate by running code, not just reading it.
- Install dependencies if needed.
- Start with compile/import checks.
- Use the app's in-process test client for smoke tests if available.
- Reproduce failures with the smallest possible script.
- Fix only issues you can verify or strongly substantiate.
- Rerun tests after each fix.
- Ignore unrelated git changes.

Deliver:
1. What you ran
2. What failed
3. What you fixed
4. What still looks risky
5. Best next improvements
```

## Repo-Specific Guidance

For this project, the preferred validation order is:

1. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

2. Run compile/import sanity checks

```powershell
python -m compileall app.py config.py studio timeline-editor\backend
```

3. Use Flask's in-process test client instead of booting the server when possible

Core smoke routes:

- `/`
- `/api/health`
- `/api/scenes/templates`
- `/api/captions/presets`
- `/api/music/library`
- `/api/editor/overlays`
- `/api/fonts`

4. Add targeted POST/DELETE repro checks for stateful or risky routes

Priority endpoints:

- `/api/assets/grabber/start`
- `/api/captions/generate`
- `/api/segmenter/run`
- `/api/scenes/generate`
- `/api/export/<job_id>` with `DELETE`
- `/api/editor/save`
- `/api/editor/load/<project_id>`

5. Use `_dev/fixtures/alignment-sample.json` for caption/segmenter smoke tests.

## Example Smoke Script

```powershell
@'
import traceback
try:
    import app as studio_app
    client = studio_app.app.test_client()

    for path in [
        '/',
        '/api/health',
        '/api/scenes/templates',
        '/api/captions/presets',
        '/api/music/library',
        '/api/editor/overlays',
        '/api/fonts',
    ]:
        resp = client.get(path)
        print(path, resp.status_code)
        print(resp.get_data(as_text=True)[:200])
except Exception:
    traceback.print_exc()
    raise
'@ | python -
```

## Example Targeted Repro Script

```powershell
@'
from app import app
client = app.test_client()

payload = {
    "project_id": "pm_test_kie_fix",
    "provider": "kie-ai",
    "scenes": [{"scene": 1, "prompt": "test prompt"}]
}

resp = client.post('/api/assets/grabber/start', json=payload)
print(resp.status_code)
print(resp.get_data(as_text=True))
'@ | python -
```

## Example Fixture-Driven Validation

```powershell
@'
import json
from pathlib import Path
from app import app

sample = json.loads(
    Path('_dev/fixtures/alignment-sample.json').read_text(encoding='utf-8')
)['alignment']

client = app.test_client()

resp = client.post('/api/captions/generate', json={
    'alignment': sample[:8],
    'project_id': 'cap_smoke',
    'preset': 'minimal',
    'source_folder': 'smoke_source'
})
print(resp.status_code)
print(resp.get_data(as_text=True)[:300])

resp = client.post('/api/segmenter/run', json={
    'alignment': sample[:20],
    'project_id': 'seg_smoke',
    'source_folder': 'smoke_source',
    'save': False
})
print(resp.status_code)
print(resp.get_data(as_text=True)[:300])
'@ | python -
```

## What Good Output Looks Like

The agent should report:

- What commands/scripts were run
- Which failures were actually reproduced
- Which changes fixed those failures
- Which behaviors were validated after the fix
- Which remaining improvements are only suggestions, not confirmed bugs

## Standard

Do not accept:

- code review without execution
- generic advice without reproduction
- “looks good” conclusions without route-level or runtime validation
- fixes that were not rerun against the failing path

