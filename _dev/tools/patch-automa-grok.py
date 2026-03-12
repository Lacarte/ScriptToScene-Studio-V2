"""Patch the Grok Assets Synchronizer Automa workflow to:
1. Collect ALL video URLs from thumbnail buttons (not just sd-video preview)
2. Send all variants to backend for multi-file download per scene
"""
import json, sys, re

AUTOMA_PATH = "_dev/automation/automa/grok/Grok Assets Synchronizer.automa.json"

with open(AUTOMA_PATH, encoding="utf-8") as f:
    data = json.load(f)

OLD_ADD_SEEN = "  function addSeen(url) { if (url) seenVideoUrls.add(url.replace(/\\?.*$/, '')); }"
NEW_ADD_SEEN = """  function addSeen(url) {
    if (!url) return;
    var clean = url.replace(/\\?.*$/, '');
    seenVideoUrls.add(clean);
    // If we only observed a preview frame, also reserve its eventual video URL.
    if (clean.includes('/preview_image.')) {
      seenVideoUrls.add(clean.replace(/\\/preview_image\\.(jpg|jpeg|png|webp)$/i, '/generated_video.mp4'));
    }
  }"""

nodes = data["drawflow"]["nodes"]
for node in nodes:
    if node.get("id") != "sync_js":
        continue
    code = node["data"]["code"]
    original = code

    # ── 1. Add collectAllVideoUrls helper BEFORE waitForGeneration ──
    HELPER = r"""
// Collect ALL video .mp4 URLs from thumbnail buttons in the current article.
// Each thumbnail has an img with a preview_image.jpg URL; derive .mp4 from UUID.
function collectAllVideoUrls() {
  var urls = [];
  var seen = new Set();
  // Method 1: thumbnail buttons with preview images
  var thumbImgs = document.querySelectorAll('button img[alt^="Thumbnail"]');
  for (var ti = 0; ti < thumbImgs.length; ti++) {
    var src = thumbImgs[ti].src || thumbImgs[ti].getAttribute('src') || '';
    var uuidMatch = src.match(/generated\/([a-f0-9-]+)\//);
    var userMatch = src.match(/users\/([a-f0-9-]+)\//);
    if (uuidMatch && userMatch) {
      var mp4 = 'https://assets.grok.com/users/' + userMatch[1] + '/generated/' + uuidMatch[1] + '/generated_video.mp4';
      if (!seen.has(mp4)) { seen.add(mp4); urls.push(mp4); }
    }
  }
  // Method 2: also grab sd-video src as fallback
  var sdv = document.getElementById('sd-video');
  if (sdv) {
    var sdSrc = (sdv.src || sdv.getAttribute('src') || '').replace(/\?.*$/, '');
    if (sdSrc && sdSrc.includes('.mp4') && !seen.has(sdSrc)) { seen.add(sdSrc); urls.push(sdSrc); }
  }
  return urls;
}

"""

    # Insert before waitForGeneration function
    anchor = "// previousSrc: the video src from the previous generation"
    if "collectAllVideoUrls" not in code:
        code = code.replace(anchor, HELPER + anchor)
        print("[OK] Added collectAllVideoUrls helper")
    else:
        print("[SKIP] collectAllVideoUrls already exists")

    # ── 2. Modify waitForGeneration to return {primary, allUrls} instead of single URL ──
    # Change the return on video found (line ~1472-1474)
    old_return_video = (
        "      // Must be a NEW video not seen before\n"
        "      if (vSrc && !seenUrls.has(vSrc) && vSrc.includes('.mp4')) {\n"
        "        console.log('NEW video ready:', vSrc.split('/').pop());\n"
        "        return vSrc;\n"
        "      }"
    )
    new_return_video = (
        "      // Must be a NEW video not seen before\n"
        "      if (vSrc && !seenUrls.has(vSrc) && vSrc.includes('.mp4')) {\n"
        "        console.log('NEW video ready:', vSrc.split('/').pop());\n"
        "        // Collect ALL variant video URLs from thumbnails\n"
        "        var allUrls = collectAllVideoUrls();\n"
        "        if (!allUrls.length) allUrls = [vSrc];\n"
        "        console.log('Found', allUrls.length, 'video variant(s) for scene', sceneId);\n"
        "        return { primary: vSrc, allUrls: allUrls };\n"
        "      }"
    )
    if old_return_video in code:
        code = code.replace(old_return_video, new_return_video)
        print("[OK] Updated waitForGeneration video return to {primary, allUrls}")
    else:
        print("[WARN] Could not find video return pattern — may already be patched")

    # Change the image fallback return too
    old_return_img = (
        "      if (iSrc && !seenUrls.has(iSrc) && iSrc.includes('assets.grok.com')) {\n"
        "        console.log('NEW image ready:', iSrc.split('/').pop());\n"
        "        return iSrc;\n"
        "      }"
    )
    new_return_img = (
        "      if (iSrc && !seenUrls.has(iSrc) && iSrc.includes('assets.grok.com')) {\n"
        "        console.log('NEW image ready:', iSrc.split('/').pop());\n"
        "        return { primary: iSrc, allUrls: [iSrc] };\n"
        "      }"
    )
    if old_return_img in code:
        code = code.replace(old_return_img, new_return_img)
        print("[OK] Updated waitForGeneration image return to {primary, allUrls}")

    # ── 3. Update the first caller (main typing loop ~line 1170-1193) ──
    old_caller1 = (
        "      const videoUrl = await waitForGeneration(item.scene, seenVideoUrls);\n"
        "\n"
        "      if (videoUrl) {\n"
        "        seenVideoUrls.add(videoUrl);  // Track this URL so next scene ignores it\n"
        "        item.status = 'typed';\n"
        "        item.videoUrl = videoUrl;\n"
        "        S.typing.typedCount++;\n"
        "        S.typing.batchCount++;\n"
        "        console.log('Scene', item.scene, 'video ready:', videoUrl.split('/').pop());\n"
        "\n"
        "        // Step 4: Send result to backend IMMEDIATELY (one by one)\n"
        "        const sc = S.scenes[item.scene];\n"
        "        if (sc) {\n"
        "          sc.urls = [videoUrl];\n"
        "          sc.previewUrl = videoUrl.replace(/generated_video\\.mp4(\\?.*)?$/, 'preview_image.jpg');\n"
        "          sc.fileCount = 1;\n"
        "          sc.status = 'ready';\n"
        "        }\n"
        "        render();\n"
        "        await sendResults(item.scene, [videoUrl]);"
    )
    new_caller1 = (
        "      const genResult = await waitForGeneration(item.scene, seenVideoUrls);\n"
        "\n"
        "      if (genResult) {\n"
        "        const videoUrl = genResult.primary;\n"
        "        const allVideoUrls = genResult.allUrls || [videoUrl];\n"
        "        seenVideoUrls.add(videoUrl);  // Track primary URL so next scene ignores it\n"
        "        allVideoUrls.forEach(function(u) { seenVideoUrls.add(u); });\n"
        "        item.status = 'typed';\n"
        "        item.videoUrl = videoUrl;\n"
        "        S.typing.typedCount++;\n"
        "        S.typing.batchCount++;\n"
        "        console.log('Scene', item.scene, 'ready:', allVideoUrls.length, 'video(s)');\n"
        "\n"
        "        // Step 4: Send ALL variants to backend (one scene, multiple files)\n"
        "        const sc = S.scenes[item.scene];\n"
        "        if (sc) {\n"
        "          sc.urls = allVideoUrls;\n"
        "          sc.previewUrl = videoUrl.replace(/generated_video\\.mp4(\\?.*)?$/, 'preview_image.jpg');\n"
        "          sc.fileCount = allVideoUrls.length;\n"
        "          sc.status = 'ready';\n"
        "        }\n"
        "        render();\n"
        "        await sendResults(item.scene, allVideoUrls);"
    )
    if old_caller1 in code:
        code = code.replace(old_caller1, new_caller1)
        print("[OK] Updated main typing loop caller")
    else:
        print("[WARN] Could not find main typing loop caller pattern")

    # ── 4. Update the retry caller (~line 1240-1251) ──
    old_caller2 = (
        "        var videoUrl = await waitForGeneration(item.scene, seenVideoUrls);\n"
        "\n"
        "        if (videoUrl) {\n"
        "          seenVideoUrls.add(videoUrl);\n"
        "          item.status = 'typed';\n"
        "          item.videoUrl = videoUrl;\n"
        "          S.typing.typedCount++;\n"
        "          S.typing.batchCount++;\n"
        "          var sc = S.scenes[item.scene];\n"
        "          if (sc) { sc.urls = [videoUrl]; sc.previewUrl = videoUrl.replace(/generated_video\\.mp4(\\?.*)?$/, 'preview_image.jpg'); sc.fileCount = 1; sc.status = 'ready'; }\n"
        "          render();\n"
        "          await sendResults(item.scene, [videoUrl]);"
    )
    new_caller2 = (
        "        var genResult = await waitForGeneration(item.scene, seenVideoUrls);\n"
        "\n"
        "        if (genResult) {\n"
        "          var videoUrl = genResult.primary;\n"
        "          var allVideoUrls = genResult.allUrls || [videoUrl];\n"
        "          seenVideoUrls.add(videoUrl);\n"
        "          allVideoUrls.forEach(function(u) { seenVideoUrls.add(u); });\n"
        "          item.status = 'typed';\n"
        "          item.videoUrl = videoUrl;\n"
        "          S.typing.typedCount++;\n"
        "          S.typing.batchCount++;\n"
        "          var sc = S.scenes[item.scene];\n"
        "          if (sc) { sc.urls = allVideoUrls; sc.previewUrl = videoUrl.replace(/generated_video\\.mp4(\\?.*)?$/, 'preview_image.jpg'); sc.fileCount = allVideoUrls.length; sc.status = 'ready'; }\n"
        "          render();\n"
        "          await sendResults(item.scene, allVideoUrls);"
    )
    if old_caller2 in code:
        code = code.replace(old_caller2, new_caller2)
        print("[OK] Updated retry caller")
    else:
        print("[WARN] Could not find retry caller pattern")

    if OLD_ADD_SEEN in code:
        code = code.replace(OLD_ADD_SEEN, NEW_ADD_SEEN)
        print("[OK] Updated addSeen to reserve derived video URLs")
    else:
        print("[SKIP] addSeen already updated or pattern not found")

    # ── 5. Update rescan to collect all thumbnail URLs per scene ──
    old_rescan = (
        "      if (!S.sentScenes[rSceneNum]) {\n"
        "        console.log('Rescan: found unsent scene', rSceneNum, '- uploading...');\n"
        "        rSc.urls = [rVideoUrl];\n"
        "        rSc.fileCount = 1;\n"
        "        rSc.status = 'ready';\n"
        "        render();\n"
        "        await sendResults(rSceneNum, [rVideoUrl]);\n"
        "        rescanFound++;"
    )
    new_rescan = (
        "      if (!S.sentScenes[rSceneNum]) {\n"
        "        console.log('Rescan: found unsent scene', rSceneNum, '- collecting all variants...');\n"
        "        var rAllUrls = collectAllVideoUrls();\n"
        "        if (!rAllUrls.length) rAllUrls = [rVideoUrl];\n"
        "        rSc.urls = rAllUrls;\n"
        "        rSc.fileCount = rAllUrls.length;\n"
        "        rSc.status = 'ready';\n"
        "        render();\n"
        "        await sendResults(rSceneNum, rAllUrls);\n"
        "        rescanFound++;"
    )
    if old_rescan in code:
        code = code.replace(old_rescan, new_rescan)
        print("[OK] Updated rescan to collect all variants")
    else:
        print("[WARN] Could not find rescan pattern")

    # ── 6. Update the thumbnail-based video URL construction (~line 888-892) ──
    # This is the single-generation detection using sd-video thumbnail
    old_thumb_construct = (
        "        videoUrl = 'https://assets.grok.com/users/' + userId + '/generated/' + thumbUuid + '/generated_video.mp4';\n"
        "          console.log('Constructed video URL from thumbnail:', videoUrl);"
    )
    new_thumb_construct = (
        "        videoUrl = 'https://assets.grok.com/users/' + userId + '/generated/' + thumbUuid + '/generated_video.mp4';\n"
        "          console.log('Constructed video URL from thumbnail:', videoUrl);\n"
        "          // Note: all variants will be collected by collectAllVideoUrls() when sendResults is called"
    )
    if old_thumb_construct in code:
        code = code.replace(old_thumb_construct, new_thumb_construct)
        print("[OK] Added note at thumbnail construct")

    if code == original:
        print("\n[WARN] No changes were made!")
        sys.exit(1)

    node["data"]["code"] = code
    print(f"\nCode changed: {len(original)} -> {len(code)} chars")
    break

with open(AUTOMA_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"[DONE] Saved {AUTOMA_PATH}")
