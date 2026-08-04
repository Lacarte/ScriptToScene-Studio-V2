# 3-Day Terminal Session — Health Report

**Captured:** 2026-04-16 17:02 local
**Scope:** dev terminal left running continuously since system boot

## Uptime

- System booted **2026-04-13 15:30:20**; snapshot taken **2026-04-16 17:02:17** → **~73.5 hours** (≈ 3 days 1 h 32 m) continuous run.
- Oldest dev PIDs (python 15180, pythonw 9356, node 15648) started shortly after boot and are still the same PIDs — no crashes, no respawn loops.

## Memory footprint (dev stack only)

| Process family | Count | Working set | Private |
|---|---|---|---|
| chrome (Chromium CDP) | 48 | **12,519 MB** | 10,285 MB |
| python | 9 | 656 MB | 1,024 MB |
| node (Vite + helpers) | 4 | 417 MB | 478 MB |
| pythonw | 2 | 195 MB | 164 MB |
| **Total** | **63** | **≈13.8 GB** | ≈11.9 GB |

Top offenders:

- **chrome 11648 — 2,406 MB** (started 2026-04-15 09:09, ~56 h old)
- **chrome 7368 — 2,150 MB** (started 2026-04-13 15:37, ~73 h old — boot-era tab)
- Several other chrome tabs in the 300–540 MB range

The two multi-GB chrome processes are the Gemini and Grok conversation tabs, which have been accumulating generated images / DOM in-place for 2–3 days. Everything else (Flask, Vite, ai-web-auto WS, extensions) is stable in the tens-to-low-hundreds of MB.

## Log volume

| File | Size | Lines | Notes |
|---|---|---|---|
| `logs/studio_2026-04-16.log` | 72 KB | 558 | today, rotated at 16:00 (≈1 h in at capture) |
| `logs/studio_2026-04-10.log` | 1.3 MB | 10,010 | biggest uncompressed on disk |
| `logs/studio_2026-04-12.log` | 347 KB | 2,689 | partial |
| `logs/studio_2026-04-{11,13,14,15}.log.zip` | ~60 KB each | — | daily rotation working |
| `logs/forcealign_2026-02-24.log` | 1 KB | — | stale, one-off |
| `_dev/.../sdc_backend.log` | 159 KB | — | unrelated (skool-down-course), last write 2026-04-05 |

Log rotation is healthy — one file per day, prior days compressed. Total on-disk log footprint is ~2 MB. No runaway growth.

## Noise pattern in the studio log

The active log is dominated by a **steady 60-second heartbeat**:

```
xx:yy:50.0xx  Gemini WS closed (1001)
xx:yy:50.0xx  Grok   WS closed (1001)
xx:yy:52.3xx  Grok   WS client connected
xx:yy:52.3xx  Gemini WS client connected
xx:yy:53.5xx  HANDSHAKE ← sts-gemini-ext
xx:yy:53.5xx  HANDSHAKE ← sts-grok-sync
```

- ~9 log lines per minute → **~13,000 lines/day** of reconnect chatter.
- Client sends WebSocket close 1001 ("going away") and reconnects ~2 s later — classic keep-alive cycle from the extension side.
- Functionally fine, but it accounts for the bulk of the log volume.

## ai-web-auto backend — faster loop

The ai-web-auto backend (visible in the terminal screenshots) runs a much tighter cycle — roughly **one reconnect per second**:

```
DEBUG  Auth attempt — received token: 'local-dev-token', expected: 'local-dev-token'
INFO   Replacing existing connection (::1, NNNNN, 0, 0) with new connection from (::1, MMMMM, 0, 0)
INFO   Extension authenticated from (::1, MMMMM, 0, 0)
```

- Separate process; its log is not under the project tree (stdout-only in its own terminal pane).
- A 1 Hz reconnect as steady state is wasteful even when nothing is wrong — worth investigating independently of the studio stack.

## Bottom line

- **No memory leaks in the backend.** Python/Node processes are flat at normal working-set sizes after 73 h.
- **Chrome tabs are the RAM hotspot** — two tabs near 2 GB each. Refreshing or closing the Gemini/Grok tabs reclaims the bulk of the 12 GB chrome footprint.
- **Disk usage from logs is negligible** (~2 MB total across all days; rotation + zip working).
- **Log noise is dominated by a 60 s WS close/reconnect cycle.** Not errors, just a chatty keep-alive.

## Follow-up ideas

1. Raise the Gemini/Grok extension heartbeat interval so it doesn't force a WS cycle every 60 s, **or** drop `WS closed` / `client connected` / `HANDSHAKE` lines from INFO to DEBUG so INFO stays clean.
2. Investigate why ai-web-auto is replacing connections once per second in steady state — likely the extension reconnecting because the server drops the prior socket on every new auth, not a genuine need for the churn.
3. If long Gemini/Grok sessions will be routine, add a periodic tab-refresh hook (e.g. every N completed scenes) to reclaim the per-tab memory that accumulates with generated images.
