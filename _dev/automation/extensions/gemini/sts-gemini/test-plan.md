Test Plan
Pre-requisites
 Python test server running: cd _dev/automation/automa/gemini/python-test && python gemini_ws_test.py --prompts prompts.txt
 Dashboard visible at http://localhost:5056 showing 3 scenes PENDING
 Gemini open at https://gemini.google.com/app
 Workflow re-imported (delete old one first, import fresh STS Gemini Image Synchronizer.automa.json)
Test 1: debugMode + Script Injection
Goal: Verify Automa can inject JS code on Gemini via CDP

 Run the workflow on the Gemini tab
 Chrome shows yellow "Automa started debugging this browser" banner
 Console shows === STS Gemini Image Synchronizer v1 ===
 STS Gemini floating panel appears (top-right corner, dark theme)
 If panel does NOT appear → check console for errors, screenshot them
Test 2: WebSocket Connection
Goal: Verify WS connects to Python server

 Panel shows green dot + "Connected"
 Python server terminal shows Client connected
 Panel shows Project: pp_GEMTEST with 3 scenes listed
 Dashboard at :5056 shows 1 CLIENT
Test 3: Image Tool Enable
Goal: Verify Tools > Create Image click works

 Typing starts automatically (or click "Start Typing")
 Console shows Enabling image generation tool...
 Console shows Create Image tool enabled (or already active)
 The toolbox menu opens and closes cleanly
Test 4: Prompt Typing
Goal: Verify execCommand('insertText') works on Gemini's Quill editor

 Console shows Found input via: .ql-editor.textarea (or similar selector)
 Prompt text appears in Gemini's input box
 Console shows Prompt typed (XXX chars)
 If text does NOT appear → note which selector failed
Test 5: Submit
Goal: Verify Enter key or Send button submits the prompt

 Console shows Prompt submitted via Send button (or Enter key)
 Gemini starts generating (spinner/avatar thinking visible)
Test 6: Generation Wait
Goal: Verify generation detection works

 Console shows Generation started
 Panel shows scene status change to generating (sparkle icon)
 After Gemini finishes: console shows Image found: https://lh3.google...
 If timeout → console shows Image generation timed out
Test 7: Image Fetch + Base64
Goal: Verify image can be fetched from Google CDN

 Console shows Fetching image as base64...
 Console shows Image fetched (XXX KB, image/jpeg)
 If CORS error → note which fetch strategy failed
Test 8: WebSocket Upload
Goal: Verify base64 image reaches Python server

 Console shows Scene 0 completed and sent
 Python server shows IMAGE_UPLOAD: pp_GEMTEST scene 0
 Python server shows Saved: .../output/pp_GEMTEST/scene_000.png
 Dashboard shows 1 DONE
 Image file exists in python-test/output/pp_GEMTEST/
Test 9: Loop to Next Prompt
Goal: Verify it proceeds to scene 1, 2

 Console shows Waiting 3s...
 Scene 1 starts typing → generating → completed
 Scene 2 starts typing → generating → completed
 Final: === Typing complete: 3 done, 0 failed ===
 Dashboard shows 3 DONE, 100%
Test 10: Error Recovery
Goal: Verify timeout/refresh behavior

 If any scene times out → page should auto-refresh
 After refresh, re-run workflow to continue remaining scenes
Want to start with Test 1 (the critical one — does the debugMode injection actually work