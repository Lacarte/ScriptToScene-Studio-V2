# Application Diagnostic Report

## Scope
Static code audit across backend routes, schema validation, and key frontend/state files.  
No runtime tests were executed in this pass, so findings are based on code-path inspection.

## Findings (ordered by severity)

1. **Critical: Path traversal / arbitrary filesystem access in TTS filename routes**
- **Problem**: Route params are used to build filesystem paths without strict normalization/containment checks.
- **Affected**: `studio/tts/routes.py:911`, `studio/tts/routes.py:913`, `studio/tts/routes.py:978`, `studio/tts/routes.py:992`, `studio/tts/routes.py:218`
- **Severity**: Critical
- **Impact**: Crafted `filename` values can resolve outside `TTS_DIR`; worst case includes deleting/moving unintended directories.
- **Recommended fix**: Centralize a safe path resolver (normalize + `commonpath` check), reject traversal patterns, whitelist filename patterns.

2. **Critical: ZIP import allows path escape and unsafe extraction targets**
- **Problem**: ZIP entries are read and written using derived subpaths without containment validation.
- **Affected**: `studio/editor/routes.py:347`, `studio/editor/routes.py:414`, `studio/editor/routes.py:433`, `studio/editor/routes.py:441`, `studio/editor/routes.py:449`, `studio/editor/routes.py:404`
- **Severity**: Critical
- **Impact**: Malicious ZIP can write outside expected project folders; `source_folder` from manifest is not sanitized before path joins.
- **Recommended fix**: Validate each ZIP member path with safe-join containment checks; sanitize `source_folder`; enforce per-file and total extracted size limits.

3. **Critical: Unsanitized project IDs used in filesystem writes in multiple modules**
- **Problem**: Several endpoints accept project IDs and directly join them into output paths.
- **Affected**: `studio/scenes/routes.py:83`, `studio/scenes/routes.py:92`, `studio/captions/routes.py:243`, `studio/captions/routes.py:256`, `studio/captions/routes.py:277`, `studio/assets/routes.py:467`, `studio/assets/routes.py:666`, `studio/assets/routes.py:682`
- **Severity**: Critical
- **Impact**: Potential directory traversal/read-write outside intended module directories.
- **Recommended fix**: Enforce strict ID regex in all schemas and route params; add shared safe path utility and reject any path that escapes module root.

4. **High: Unsafe uploaded filename usage in timing upload**
- **Problem**: `audio_file.filename` is directly used in path join/save.
- **Affected**: `studio/timing/routes.py:146`, `studio/timing/routes.py:157`, `studio/timing/routes.py:229`, `studio/timing/routes.py:240`
- **Severity**: High
- **Impact**: Path traversal and overwrite risks from crafted multipart filenames.
- **Recommended fix**: Use `secure_filename`, reject path separators, and write only sanitized basenames.

5. **High: No authentication/authorization + permissive CORS + network exposure**
- **Problem**: App is publicly bindable with unrestricted CORS and destructive endpoints.
- **Affected**: `app.py:48`, `app.py:202`, `app.py:134`, `app.py:107`
- **Severity**: High
- **Impact**: Any reachable client can trigger project deletion/open-folder actions; high abuse risk on LAN/shared hosts.
- **Recommended fix**: Add auth (token/session), restrict origins, disable destructive endpoints without auth, default bind to localhost in non-explicit server mode.

6. **High: SSRF risk through user-provided webhook URLs**
- **Problem**: Backend posts to user-supplied `webhook_url` without host allowlist.
- **Affected**: `studio/scenes/schemas.py:21`, `studio/scenes/routes.py:58`, `studio/scenes/routes.py:239`, `studio/pipeline/schemas.py:14`, `studio/pipeline/routes.py:470`
- **Severity**: High
- **Impact**: Server can be coerced to make requests to internal network/services.
- **Recommended fix**: Enforce URL allowlist (or disable override in production), validate scheme/host/IP ranges, block localhost/private ranges if not needed.

7. **High: Concurrency races on shared in-memory job dictionaries**
- **Problem**: Shared dicts are read/written from multiple threads without consistent locking.
- **Affected**: `studio/assets/routes.py:54`, `studio/assets/routes.py:174`, `studio/assets/routes.py:183`, `studio/editor/routes.py:30`, `studio/editor/routes.py:709`, `studio/editor/routes.py:812`
- **Severity**: High
- **Impact**: Inconsistent job states, lost updates, intermittent failures under concurrent use.
- **Recommended fix**: Use locks for all read/write accesses or move to thread-safe queue/store abstraction.

8. **Medium: Inconsistent JSON error handling in TTS routes**
- **Problem**: `request.get_json(force=True)` and raw `request.get_json()` can produce non-uniform failures/500s.
- **Affected**: `studio/tts/routes.py:459`, `studio/tts/routes.py:788`
- **Severity**: Medium
- **Impact**: Bad payloads may return inconsistent responses or runtime errors (`NoneType`).
- **Recommended fix**: Standardize on validated request schemas or `get_json(silent=True)` + explicit checks.

9. **Medium: Incorrect stream error propagation in TTS**
- **Problem**: Error event sends `str(Exception)` instead of actual exception message.
- **Affected**: `studio/tts/routes.py:853`, `studio/tts/routes.py:854`
- **Severity**: Medium
- **Impact**: Debugging production stream failures is much harder; client receives useless error context.
- **Recommended fix**: Capture `except Exception as e` and emit `str(e)`.

10. **Medium: Overly permissive schema acceptance (`extra = allow`) across API contracts**
- **Problem**: Most schemas allow unknown fields, weakening input contracts and masking invalid payloads.
- **Affected**: `studio/scenes/schemas.py:26`, `studio/pipeline/schemas.py:18`, `studio/captions/schemas.py:32`, `studio/editor/schemas.py:25`
- **Severity**: Medium
- **Impact**: Hidden client bugs, accidental field drift, harder migrations.
- **Recommended fix**: Switch most schemas to `extra="forbid"` and explicitly whitelist extension points.

11. **Medium: Expensive synchronous history/listing endpoints**
- **Problem**: Repeated full filesystem scans and metadata extraction per request.
- **Affected**: `studio/assets/routes.py:547`, `studio/assets/routes.py:648`, `studio/music/routes.py:39`, `studio/music/routes.py:53`, `studio/editor/routes.py:870`
- **Severity**: Medium
- **Impact**: UI lag and server slowdown as project/media count grows.
- **Recommended fix**: Cache summaries, precompute thumbnails/durations on write, add pagination and lightweight list views.

12. **Low: CSS duplication and UI state inconsistency**
- **Problem**: Duplicate keyframes and initial mobile active tab mismatch.
- **Affected**: `static/css/styles.css:106`, `static/css/styles.css:807`, `static/index.html:426`, `static/index.html:361`
- **Severity**: Low
- **Impact**: Harder maintainability and subtle UX confusion on first render (mobile).
- **Recommended fix**: Remove duplicate animation blocks; initialize mobile nav active state from active page on load.

13. **Low: Silent exception swallowing in many history readers**
- **Problem**: Broad `except` blocks discard parse/IO issues.
- **Affected**: `studio/scenes/routes.py:353`, `studio/captions/routes.py:306`, `studio/assets/routes.py:572`
- **Severity**: Low
- **Impact**: Corruption and partial failures can go unnoticed.
- **Recommended fix**: Log warnings with file/project context, optionally expose non-fatal diagnostics in admin/health endpoint.

## Prioritized Improvement Plan

1. **Security hardening first (block critical risk)**
- Implement shared safe-path utilities and apply to all file-based endpoints.
- Sanitize/validate all route IDs and filenames with strict regex.
- Harden ZIP import: path containment checks, zip bomb safeguards, sanitized `source_folder`.

2. **Access control and network safety**
- Add authentication for API mutations and destructive operations.
- Restrict CORS by environment.
- Default runtime bind to localhost; require explicit opt-in for external bind.

3. **Webhook and outbound request controls**
- Add webhook URL allowlist/denylist + private-network blocking.
- Enforce validated URL schema in Pydantic models.

4. **Reliability under concurrency**
- Normalize locking strategy for job stores (`_export_jobs`, `grabber_jobs`, pipeline jobs).
- Add atomic state transition helpers and consistent lock boundaries.

5. **Validation contract tightening**
- Change schemas from `extra="allow"` to `forbid` where possible.
- Add missing constraints for `project_id`, `source_folder`, and format fields.

6. **Performance/scalability improvements**
- Cache metadata summaries, precompute expensive media metadata, add pagination for history/library endpoints.
- Avoid per-request ffprobe/thumbnail generation where possible.

7. **Maintainability and UX cleanup**
- Remove duplicated CSS definitions.
- Fix initial mobile nav active-state mismatch.
- Replace silent catches with structured warnings.
