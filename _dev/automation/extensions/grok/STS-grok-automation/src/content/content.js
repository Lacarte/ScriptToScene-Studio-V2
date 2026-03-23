// STS Grok Automation - Content Script
// Runs on grok.com and automates image/video generation.
// Flow based on patterns reverse-engineered from the original Grok Automation extension.

console.log("[STS Grok] Content script loaded on", window.location.href);

const PRE_TYPE_DELAY_MS = 10000;
const RECENT_RESULT_TTL_MS = 30000;

const RATE_LIMIT_INITIAL_WAIT_MS = 2 * 60 * 60 * 1000; // 2 hours
const RATE_LIMIT_RETRY_WAIT_MS = 30 * 60 * 1000; // 30 minutes

const SEL = {
  promptDropUiTextarea: '[data-testid="drop-ui"] textarea',
  promptEditable: '[contenteditable="true"]',
  promptTextarea: "textarea",
  fileInput: 'input[type="file"]',
  imageUploading: '.animate-spin, [class*="uploading"], [class*="loading"]',
  closedInlineMenus: 'div.inline-flex[data-state="closed"]',
  attachButtonGroup: ".group\\/attach-button",
  radioGroups: 'div.inline-flex > div[role="radiogroup"]',
  clickableControl: 'button, [role="menuitem"], [role="option"], [role="radio"], [role="button"], a',
  mainArticle: "article",
  videoAssets: 'video[src*="assets.grok.com"]',
  thumbnailImg: 'button img[alt^="Thumbnail"]',
  progressSvg: "svg circle[stroke-dasharray]",
  spinner: ".animate-spin",
  generatingText: "span.animate-pulse",
  percentageText: ".tabular-nums",
  canvas: "canvas",
  downloadButton: 'button[aria-label="Download"], button:has(svg path[d*="M12 3v12"])',
  imagineNavLink: 'a[href="/imagine"], a[href*="/imagine"]',
  removeImageBtn: 'button[aria-label="Remove image"]',
  rateLimitToast: '[data-type="error"]',
};

// ── Rate Limit Detection ──

function isRateLimited() {
  const toasts = document.querySelectorAll(SEL.rateLimitToast);
  for (const toast of toasts) {
    if (toast.textContent?.includes("Rate limit reached")) {
      return true;
    }
  }
  return false;
}

async function waitForRateLimitCooldown() {
  console.warn("[STS Grok] Rate limit detected! Waiting 2 hours...");

  // Notify panel via runtime message
  try {
    chrome.runtime.sendMessage({
      type: "RATE_LIMITED",
      initialWaitMs: RATE_LIMIT_INITIAL_WAIT_MS,
    });
  } catch {}

  await sleep(RATE_LIMIT_INITIAL_WAIT_MS);

  // Retry loop: check every 30 minutes if still limited
  let retryCount = 0;
  while (isRateLimited()) {
    retryCount++;
    console.warn(`[STS Grok] Still rate limited after retry ${retryCount}. Waiting 30 minutes...`);
    try {
      chrome.runtime.sendMessage({
        type: "RATE_LIMITED",
        retryCount,
        retryWaitMs: RATE_LIMIT_RETRY_WAIT_MS,
      });
    } catch {}
    await sleep(RATE_LIMIT_RETRY_WAIT_MS);
  }

  console.log("[STS Grok] Rate limit cleared, resuming.");
  try {
    chrome.runtime.sendMessage({ type: "RATE_LIMIT_CLEARED" });
  } catch {}
}

let activeAnimateKey = null;
let activeAnimatePromise = null;
const recentAnimateResults = new Map();

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function $(selector) {
  return document.querySelector(selector);
}

function $$(selector) {
  return [...document.querySelectorAll(selector)];
}

async function waitForElement(selector, timeout = 30000, interval = 500) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const el = $(selector);
    if (el) return el;
    await sleep(interval);
  }
  return null;
}

async function waitForElementGone(selector, timeout = 30000, interval = 200) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (!$(selector)) return true;
    await sleep(interval);
  }
  return false;
}

function normalizeText(text = "") {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

function isVisible(el) {
  if (!el) return false;
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return style.display !== "none" &&
    style.visibility !== "hidden" &&
    style.opacity !== "0" &&
    rect.width > 0 &&
    rect.height > 0;
}

function getPromptInput() {
  return $(SEL.promptDropUiTextarea) || $(SEL.promptEditable) || $(SEL.promptTextarea);
}

function dispatchFullClickSequence(el) {
  if (!el) return;

  const pointerCtor = window.PointerEvent || window.MouseEvent;
  const opts = { bubbles: true, cancelable: true, composed: true, view: window, detail: 1 };
  const events = [
    new pointerCtor("pointerover", opts),
    new MouseEvent("mouseover", opts),
    new pointerCtor("pointerdown", opts),
    new MouseEvent("mousedown", opts),
    new pointerCtor("pointerup", opts),
    new MouseEvent("mouseup", opts),
    new MouseEvent("click", opts),
  ];

  for (const event of events) {
    el.dispatchEvent(event);
  }
}

async function clickSelector(selector, label = "", timeout = 5000) {
  const el = await waitForElement(selector, timeout, 100);
  if (!el) throw new Error(`Element not found: ${label || selector}`);
  dispatchFullClickSequence(el);
  await sleep(300);
  return el;
}

function scoreControlCandidate(el, texts) {
  const text = normalizeText(el.getAttribute("aria-label") || el.textContent || el.value || "");
  if (!text) return -1;

  let score = -1;
  for (const candidate of texts.map(normalizeText)) {
    if (!candidate) continue;
    if (text === candidate) score = Math.max(score, 100);
    else if (text.startsWith(candidate)) score = Math.max(score, 80);
    else if (text.includes(candidate)) score = Math.max(score, 60);
  }

  if (score < 0) return score;
  if (!el.closest("article")) score += 15;
  if (el.getBoundingClientRect().top < window.innerHeight * 0.8) score += 5;
  return score;
}

function findClickableByText(texts) {
  const candidates = $$(SEL.clickableControl)
    .filter(isVisible)
    .map((el) => ({ el, score: scoreControlCandidate(el, texts) }))
    .filter((entry) => entry.score >= 0)
    .sort((a, b) => b.score - a.score);

  return candidates[0]?.el || null;
}

async function tryClickByText(texts, label = "") {
  const el = findClickableByText(texts);
  if (!el) return false;
  dispatchFullClickSequence(el);
  await sleep(300);
  console.log(`[STS Grok] Clicked ${label || texts.join("/")}:`, normalizeText(el.textContent || el.getAttribute("aria-label") || ""));
  return true;
}

function getClosedMenuButtons() {
  return $$(SEL.closedInlineMenus)
    .map((menu) => menu.querySelector("button"))
    .filter((button) => button && isVisible(button));
}

async function clickClosedMenuButton(index) {
  const button = getClosedMenuButtons()[index];
  if (!button) return false;
  dispatchFullClickSequence(button);
  await sleep(350);
  return true;
}

function detectUiVariant() {
  if ($$(SEL.attachButtonGroup).length > 0) return 1;
  if ($$(SEL.radioGroups).length > 0) return 3;
  return 2;
}

function getAspectRatioTexts(aspectRatio = "9:16") {
  const value = String(aspectRatio || "9:16");
  const map = {
    "16:9": ["16:9", "youtube"],
    "9:16": ["9:16", "shorts", "reels"],
    "1:1": ["1:1", "square"],
    "2:3": ["2:3", "portrait"],
    "3:2": ["3:2", "landscape"],
  };
  return map[value] || [value];
}

function getDurationTexts(duration = "6s") {
  const value = String(duration || "6s").toLowerCase();
  return value.includes("10") ? ["10s"] : ["6s"];
}

function isVideoMode(mode = "") {
  return String(mode || "").toLowerCase().includes("video");
}

function usesReferenceImage(mode = "") {
  const value = String(mode || "").toLowerCase();
  return value === "imagetovideo" ||
    value === "imagetoimage" ||
    value === "componentstovideo" ||
    value === "ingredienttovideo";
}

function normalizeJobImages(image, images) {
  if (Array.isArray(images) && images.length > 0) {
    return images.filter(Boolean);
  }
  return image ? [image] : [];
}

async function ensureControlSelection(texts, label, openerIndexes = [0, 1]) {
  if (await tryClickByText(texts, label)) return true;

  for (const index of openerIndexes) {
    const opened = await clickClosedMenuButton(index);
    if (!opened) continue;
    if (await tryClickByText(texts, label)) return true;
  }

  console.warn(`[STS Grok] Control not found for ${label}`);
  return false;
}

async function configureVideoMode(mode, duration, aspectRatio, uiVariant) {
  const modeSelected = await ensureControlSelection(["video"], "video mode", [0]);
  const aspectSelected = await ensureControlSelection(
    getAspectRatioTexts(aspectRatio),
    `aspect ratio ${aspectRatio}`,
    uiVariant === 3 ? [1, 0] : [0, 1]
  );
  const durationSelected = await ensureControlSelection(getDurationTexts(duration), `duration ${duration}`, [0, 1]);

  console.log("[STS Grok] Video config", { modeSelected, aspectSelected, durationSelected, uiVariant });

  if (usesReferenceImage(mode)) {
    await sleep(300);
  }
}

async function configureImageMode(aspectRatio, uiVariant) {
  const modeSelected = await ensureControlSelection(["image"], "image mode", [0]);
  const aspectSelected = await ensureControlSelection(
    getAspectRatioTexts(aspectRatio),
    `aspect ratio ${aspectRatio}`,
    uiVariant === 3 ? [1, 0] : [0, 1]
  );

  console.log("[STS Grok] Image config", { modeSelected, aspectSelected, uiVariant });
}

async function clearUploadedImages() {
  for (let pass = 0; pass < 20; pass++) {
    const removeButtons = $$(SEL.removeImageBtn);
    if (removeButtons.length === 0) break;

    const button = removeButtons[0];
    button.style.opacity = "1";
    button.style.pointerEvents = "auto";
    await sleep(100);

    const group = button.closest(".group");
    if (group) {
      group.dispatchEvent(new MouseEvent("mouseenter", { bubbles: true }));
      await sleep(100);
    }

    dispatchFullClickSequence(button);
    await sleep(500);
  }

  const remaining = $$(SEL.removeImageBtn);
  if (remaining.length > 0) {
    console.warn(`[STS Grok] ${remaining.length} uploaded images could not be removed`);
  }
}

async function resetInput() {
  if (!window.location.pathname.includes("/imagine")) {
    throw new Error("Grok tab is not ready on /imagine");
  }

  await clearUploadedImages();

  const input = getPromptInput();
  if (input) {
    if (input instanceof HTMLTextAreaElement || input.tagName === "TEXTAREA") {
      input.value = "";
    } else {
      input.textContent = "";
    }
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  await sleep(500);
}

async function uploadImage(base64Data) {
  if (!base64Data) return false;

  const raw = base64Data.includes(",") ? base64Data.split(",").pop() : base64Data;
  const binaryString = atob(raw);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  const mimeMatch = base64Data.match(/data:([^;]+);/);
  const mimeType = mimeMatch ? mimeMatch[1] : "image/jpeg";
  const blob = new Blob([bytes], { type: mimeType });
  const file = new File([blob], `sts-input-${Date.now()}.jpg`, { type: mimeType });

  const fileInput = await waitForElement(SEL.fileInput, 10000, 200);
  if (!fileInput) {
    console.error("[STS Grok] File input not found");
    return false;
  }

  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  fileInput.files = dataTransfer.files;
  fileInput.dispatchEvent(new Event("change", { bubbles: true }));

  console.log("[STS Grok] Image injected, waiting for upload...");

  await sleep(1000);
  await waitForElementGone(SEL.imageUploading, 30000, 200);
  await sleep(500);

  console.log("[STS Grok] Image upload complete");
  return true;
}

async function fillPromptAndSubmit(text) {
  let input = getPromptInput();
  let isTextarea = input instanceof HTMLTextAreaElement;

  if (!input) {
    input = await waitForElement(SEL.promptDropUiTextarea, 3000, 200) ||
      await waitForElement(SEL.promptEditable, 10000, 300) ||
      await waitForElement(SEL.promptTextarea, 5000, 200);
    isTextarea = input instanceof HTMLTextAreaElement;
  }
  if (!input) return false;

  dispatchFullClickSequence(input);
  input.focus();
  await sleep(200);

  if (isTextarea || input instanceof HTMLTextAreaElement) {
    input.value = text;
  } else {
    input.textContent = text;
  }

  const inputEvent = new Event("input", { bubbles: true, cancelable: true });
  Object.defineProperty(inputEvent, "target", { value: input, writable: false });
  input.dispatchEvent(inputEvent);
  input.dispatchEvent(new Event("change", { bubbles: true }));

  console.log("[STS Grok] Prompt typed:", text.slice(0, 50));

  await sleep(500);
  input.dispatchEvent(new KeyboardEvent("keydown", {
    key: "Enter",
    code: "Enter",
    keyCode: 13,
    which: 13,
    bubbles: true,
    cancelable: true,
  }));

  console.log("[STS Grok] Prompt submitted");
  return true;
}

function parseSvgProgress() {
  const circles = $$(SEL.progressSvg);
  for (let i = circles.length - 1; i >= 0; i--) {
    const dasharray = circles[i].getAttribute("stroke-dasharray") || "";
    const dashoffset = circles[i].getAttribute("stroke-dashoffset") || "";
    const circumference = parseFloat(dasharray.split(" ")[0]);
    const offset = parseFloat(dashoffset);
    if (isNaN(circumference) || isNaN(offset) || circumference === 0) continue;
    return Math.round(100 * (1 - offset / circumference));
  }
  return -1;
}

function readTextProgress() {
  const pctEl = $(SEL.percentageText);
  if (pctEl) {
    const match = (pctEl.textContent || "").match(/(\d+)\s*%/);
    if (match) return parseInt(match[1], 10);
  }
  return -1;
}

function isStillGenerating() {
  const pulseSpan = $(SEL.generatingText);
  if (pulseSpan && /generating/i.test(pulseSpan.textContent || "")) return true;

  const svgPct = parseSvgProgress();
  if (svgPct >= 0 && svgPct < 100) return true;

  if ($(SEL.spinner)) return true;
  if ($(SEL.canvas)) return true;

  return false;
}

function rewriteVideoUrl(src) {
  const generatedMatch = src.match(/generated\/([a-f0-9-]+)/i);
  const userMatch = src.match(/users\/([a-f0-9-]+)/i);

  if (generatedMatch && userMatch) {
    return `https://assets.grok.com/users/${userMatch[1]}/generated/${generatedMatch[1]}/generated_video.mp4`;
  }
  if (generatedMatch) {
    return `https://assets.grok.com/generated/${generatedMatch[1]}.mp4`;
  }
  return src;
}

function extractVideoUrl(scope) {
  const assetsVideos = [...scope.querySelectorAll(SEL.videoAssets)];
  if (assetsVideos.length > 0) {
    const src = assetsVideos[assetsVideos.length - 1].src;
    if (src) return rewriteVideoUrl(src);
  }

  const allVideos = [...scope.querySelectorAll("video")];
  for (const video of allVideos) {
    const src = video.src || video.getAttribute("src") || "";
    if (src && !src.startsWith("blob:") && src.includes("assets.grok.com")) {
      return rewriteVideoUrl(src);
    }

    const sourceSrc = video.querySelector("source[src]")?.getAttribute("src") || "";
    if (sourceSrc && !sourceSrc.startsWith("blob:") && sourceSrc.includes("assets.grok.com")) {
      return rewriteVideoUrl(sourceSrc);
    }
  }

  const sdVideo = document.getElementById("sd-video");
  if (sdVideo) {
    const src = sdVideo.src || sdVideo.getAttribute("src") || "";
    if (src && src.includes("assets.grok.com")) return rewriteVideoUrl(src);
  }

  const thumbs = [...scope.querySelectorAll(SEL.thumbnailImg)];
  for (const thumb of thumbs) {
    const src = thumb.src || "";
    const uuidMatch = src.match(/generated\/([a-f0-9-]+)\//i);
    const userMatch = src.match(/users\/([a-f0-9-]+)\//i);
    if (uuidMatch && userMatch) {
      return `https://assets.grok.com/users/${userMatch[1]}/generated/${uuidMatch[1]}/generated_video.mp4`;
    }
  }

  for (const video of allVideos) {
    if (video.src && video.src.length > 10 && video.readyState >= 2) {
      const href = scope.querySelector(SEL.downloadButton)?.closest("a")?.href;
      if (href) return href;
      return video.src;
    }
  }

  return null;
}

function reportProgress(jobId, sceneIndex, percentage) {
  try {
    chrome.runtime.sendMessage({
      type: "ANIMATE_PROGRESS",
      jobId,
      sceneIndex,
      percentage,
    });
  } catch {}
}

async function waitForVideoResult(jobId, sceneIndex, articleCountBefore = 0) {
  console.log("[STS Grok] Waiting for video result...");
  let lastProgressSent = -1;

  let generationStarted = false;
  for (let i = 0; i < 60; i++) {
    if (isRateLimited()) {
      console.warn("[STS Grok] Rate limit hit while waiting for generation to start");
      await waitForRateLimitCooldown();
      return { success: false, error: "Rate limited — re-queue" };
    }
    const hasNewArticle = $$(SEL.mainArticle).length > articleCountBefore;
    if (hasNewArticle || isStillGenerating() || parseSvgProgress() >= 0) {
      generationStarted = true;
      console.log("[STS Grok] Generation started");
      break;
    }
    await sleep(1000);
  }

  if (!generationStarted) {
    return { success: false, error: "Generation never started (60s timeout)" };
  }

  const maxIterations = 150;
  const pollInterval = 2000;
  let idleCount = 0;

  for (let i = 0; i < maxIterations; i++) {
    if (isRateLimited()) {
      console.warn("[STS Grok] Rate limit hit during generation");
      await waitForRateLimitCooldown();
      return { success: false, error: "Rate limited — re-queue" };
    }

    let percentage = parseSvgProgress();
    if (percentage < 0) percentage = readTextProgress();

    if (percentage >= 0 && percentage !== lastProgressSent) {
      lastProgressSent = percentage;
      reportProgress(jobId, sceneIndex, percentage);
    }

    const generating = isStillGenerating();
    const articles = $$(SEL.mainArticle);
    const scope = articles.length > articleCountBefore ? articles[articles.length - 1] : document;
    const videoUrl = extractVideoUrl(scope);

    if (videoUrl) {
      console.log("[STS Grok] Video found:", videoUrl.slice(0, 120));
      reportProgress(jobId, sceneIndex, 100);
      await sleep(1000);
      return { success: true, videoUrl };
    }

    if (!generating) {
      idleCount += 1;
      if (idleCount >= 5) {
        const finalUrl = extractVideoUrl(scope);
        if (finalUrl) {
          reportProgress(jobId, sceneIndex, 100);
          return { success: true, videoUrl: finalUrl };
        }

        const errorEl = document.querySelector('[class*="error"], [class*="Error"]');
        if (errorEl) {
          return {
            success: false,
            error: "Grok error: " + (errorEl.textContent || "").slice(0, 120),
          };
        }

        return { success: false, error: "Generation finished but no video found" };
      }
    } else {
      idleCount = 0;
    }

    await sleep(pollInterval);
  }

  return { success: false, error: "Timeout waiting for video (5 min)" };
}

async function waitForImageResult(jobId, sceneIndex, articleCountBefore = 0) {
  console.log("[STS Grok] Waiting for image result...");
  const maxIterations = 60;

  for (let i = 0; i < maxIterations; i++) {
    const articles = $$(SEL.mainArticle);
    if (articles.length > articleCountBefore) {
      const lastArticle = articles[articles.length - 1];
      const images = [...lastArticle.querySelectorAll("img")].filter((img) => {
        const src = img.src || "";
        return src.startsWith("data:image") && src.length >= 130000;
      });

      if (images.length > 0) {
        console.log("[STS Grok] Image result found");
        return { success: true, imageData: images[0].src };
      }
    }
    await sleep(2000);
  }

  return { success: false, error: "Timeout waiting for image (2 min)" };
}

function makeJobKey(jobId, sceneIndex) {
  return `${jobId || "unknown"}:${sceneIndex ?? "unknown"}`;
}

function cloneResult(result) {
  return result ? JSON.parse(JSON.stringify(result)) : result;
}

function pruneRecentAnimateResults() {
  const now = Date.now();
  for (const [key, entry] of recentAnimateResults.entries()) {
    if (!entry || (now - entry.at) > RECENT_RESULT_TTL_MS) {
      recentAnimateResults.delete(key);
    }
  }
}

async function runAnimate(msg) {
  const { jobId, sceneIndex, prompt, image, images, mode, duration, aspectRatio } = msg;
  const jobImages = normalizeJobImages(image, images);

  console.log(`[STS Grok] Starting job ${jobId} scene ${sceneIndex}: ${mode}`);

  await resetInput();

  const articleCountBefore = $$(SEL.mainArticle).length;
  const uiVariant = detectUiVariant();
  console.log(`[STS Grok] Detected Grok UI variant ${uiVariant}`);

  if (isVideoMode(mode)) {
    await configureVideoMode(mode, duration, aspectRatio, uiVariant);
  } else if (String(mode || "").toLowerCase() === "imagetoimage") {
    await configureImageMode(aspectRatio, uiVariant);
  }

  if (jobImages.length > 0 && usesReferenceImage(mode)) {
    const uploaded = await uploadImage(jobImages[0]);
    if (!uploaded) {
      return { success: false, error: "Failed to upload image" };
    }
    await sleep(1000);
  }

  console.log(`[STS Grok] Waiting ${PRE_TYPE_DELAY_MS}ms before typing prompt...`);
  await sleep(PRE_TYPE_DELAY_MS);

  const submitted = await fillPromptAndSubmit(prompt);
  if (!submitted) {
    return { success: false, error: "Failed to type/submit prompt" };
  }

  // Check for rate limit after submission (toast appears ~1-2s after submit)
  await sleep(2000);
  if (isRateLimited()) {
    await waitForRateLimitCooldown();
    // Re-submit the prompt after cooldown
    const resubmitted = await fillPromptAndSubmit(prompt);
    if (!resubmitted) {
      return { success: false, error: "Failed to re-submit prompt after rate limit" };
    }
    await sleep(2000);
    // If still rate limited after retry, fail
    if (isRateLimited()) {
      return { success: false, error: "Rate limit persists after cooldown" };
    }
  }

  if (isVideoMode(mode) || String(mode || "").toLowerCase() === "imagetovideo") {
    return await waitForVideoResult(jobId, sceneIndex, articleCountBefore);
  }
  return await waitForImageResult(jobId, sceneIndex, articleCountBefore);
}

function handleAnimate(msg, sendResponse) {
  const jobKey = makeJobKey(msg.jobId, msg.sceneIndex);
  pruneRecentAnimateResults();

  const recent = recentAnimateResults.get(jobKey);
  if (recent) {
    console.log(`[STS Grok] Duplicate finished job ignored: ${jobKey}`);
    sendResponse(cloneResult(recent.result));
    return;
  }

  if (activeAnimatePromise) {
    if (activeAnimateKey === jobKey) {
      console.log(`[STS Grok] Duplicate in-flight job attached: ${jobKey}`);
      activeAnimatePromise
        .then((result) => sendResponse(cloneResult(result)))
        .catch((err) => sendResponse({ success: false, error: err.message || String(err) }));
      return;
    }

    console.warn(`[STS Grok] Rejecting overlapping job ${jobKey}; active=${activeAnimateKey}`);
    sendResponse({ success: false, error: `Animator busy with ${activeAnimateKey}` });
    return;
  }

  activeAnimateKey = jobKey;
  activeAnimatePromise = runAnimate(msg)
    .then((result) => {
      recentAnimateResults.set(jobKey, { at: Date.now(), result: cloneResult(result) });
      return result;
    })
    .catch((err) => {
      console.error("[STS Grok] Animation error:", err);
      return { success: false, error: err.message || String(err) };
    })
    .finally(() => {
      activeAnimateKey = null;
      activeAnimatePromise = null;
    });

  activeAnimatePromise.then((result) => sendResponse(cloneResult(result)));
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  switch (msg.type) {
    case "CHECK_PAGE":
      sendResponse({
        isGrokPage: true,
        isImaginePage: window.location.pathname.includes("/imagine"),
        url: window.location.href,
      });
      return false;

    case "PING":
      sendResponse({ pong: true, from: "content" });
      return false;

    case "RESET":
      // Force-clear busy state between jobs
      activeAnimateKey = null;
      activeAnimatePromise = null;
      sendResponse({ success: true });
      return false;

    case "ANIMATE":
      handleAnimate(msg, sendResponse);
      return true;

    case "NAVIGATE_IMAGINE": {
      // Clear busy state — previous job is done
      activeAnimateKey = null;
      activeAnimatePromise = null;
      const link = $(SEL.imagineNavLink);
      if (!link) {
        sendResponse({ success: false, error: "Imagine nav link not found" });
        return false;
      }

      dispatchFullClickSequence(link);
      (async () => {
        for (let i = 0; i < 20; i++) {
          await sleep(500);
          if (window.location.pathname.includes("/imagine")) {
            sendResponse({ success: true });
            return;
          }
        }
        sendResponse({ success: false, error: "Route did not change to /imagine" });
      })();
      return true;
    }
  }

  return false;
});
