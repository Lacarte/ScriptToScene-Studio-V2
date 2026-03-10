UI version detection happens earlier in x():


// uiVersion detection logic:
let uiVersion = 3; // default
if (jQuery(".group\\/attach-button").length > 0) {
    uiVersion = 1;  // v1 has attach-button group class
} else if (jQuery('div.inline-flex > div[role="radiogroup"]').length > 0) {
    uiVersion = 3;  // v3 has radiogroup
} else {
    uiVersion = 2;  // fallback = v2
}

    // --- PART B: Set Aspect Ratio ---
    if (uiVersion === 1 || uiVersion === 2) {
        // Reopen dropdown if it closed
        const wrapper = jQuery(selectors.modeSelectedWrapper);
        if (wrapper && wrapper.length === 0) {
            await clickElement(selectors.modeSelectTrigger, "Open configuration again");
        }
        // Build the selector dynamically: template has {aspectRatio} placeholder
        // e.g. "button[data-aspect-ratio='{aspectRatio}']" → "button[data-aspect-ratio='16:9']"
        const ratioSelector = selectors.aspectRatioTemplate
            .replace("{aspectRatio}", payload.aspectRatio);
        const ratioBtn = await waitForElement(ratioSelector);
        if (ratioBtn && ratioBtn.length > 0) {
            await clickElement(ratioSelector, `Aspect ratio option: ${payload.aspectRatio}`);
        }
    } else if (uiVersion === 3) {
        // v3: click the second inline-flex closed div to open aspect ratio dropdown
        await clickElement(
            'div.inline-flex[data-state="closed"]:eq(1) > button:eq(0)',
            "Select Aspect Ratio Mode"
        );
        const ratioSelector = selectors.aspectRatioTemplateV3
            .replace("{aspectRatio}", payload.aspectRatio);
        await clickElement(ratioSelector, `Aspect ratio: ${payload.aspectRatio}`);
    }

    // --- PART C: Set Video Length (6s or 10s) ---
    if (uiVersion === 1 || uiVersion === 2) {
        // Reopen dropdown if needed
        const wrapper = jQuery(selectors.modeSelectedWrapper);
        if (wrapper && wrapper.length === 0) {
            await clickElement(selectors.modeSelectTrigger, "Video configuration button");
        }
        const lengthMenu = await waitForElement(selectors.videoLengthMenu);
        if (lengthMenu && lengthMenu.length > 0) {
            if (payload.defaultVideoFrame.includes("6s")) {
                await clickElement(selectors.videoLength6sItem, "6s option");
            } else {
                await clickElement(selectors.videoLength10sItem, "10s option");
            }
        }
    } else if (uiVersion === 3) {
        // v3: direct click, no dropdown
        if (payload.defaultVideoFrame.includes("6s")) {
            await clickElement(selectors.videoLength6sItem, "6s option");
        } else {
            await clickElement(selectors.videoLength10sItem, "10s option");
        }
    }

    // --- PART D: Set Video Quality (480p or 720p) ---
    if (uiVersion === 1 || uiVersion === 2) {
        const qualityMenu = jQuery(selectors.videoQualityMenu);
        if (qualityMenu && qualityMenu.length > 0) {
            if (payload.autoDownloadResourceQuality === "720p") {
                await clickElement(selectors.videoQuality720pItem, "720p");
            } else {
                await clickElement(selectors.videoQuality480pItem, "480p");
            }
        }
        // Close the dropdown by clicking trigger again
        const wrapper = jQuery(selectors.modeSelectedWrapper);
        if (wrapper && wrapper.length > 0) {
            await clickElement(selectors.modeSelectTrigger, "Close menu");
        }
    }

    // --- PART E: Upload Reference Image (for imageToVideo mode) ---
    if (payload.mode === "imageToVideo" || payload.previousVideoElements) {
        // If chaining videos, extract last frame first
        if (payload.previousVideoElements) {
            const frameBase64 = await extractLastVideoFrame(payload.previousVideoElements);
            if (frameBase64) {
                payload.images = payload.images || [];
                payload.images.unshift({
                    base64: frameBase64,
                    name: `extracted-frame-${Date.now()}.jpg`
                });
            }
        }
        // Upload the image
        if (payload.images && payload.images.length > 0) {
            await uploadImage(payload, 0, remoteConfig);
            await sleep(3000);  // wait for upload UI
            await waitForElementToDisappear(selectors.imageUploading, 30000);
        }
    }
    return true;
}
The uploadImage function (b) — How image injection works

async function uploadImage(payload, imageIndex, remoteConfig) {
    const imageData = payload.images[imageIndex];
    let base64 = imageData.base64;
    
    // Strip data URL prefix if present ("data:image/jpeg;base64,...")
    if (base64.includes(",")) {
        base64 = base64.split(",")[1];
    }
    
    // Decode base64 → raw bytes
    const binaryString = atob(base64);
    const bytes = new Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    const uint8Array = new Uint8Array(bytes);
    
    // Create a real File object
    const blob = new Blob([uint8Array], { type: "image/jpeg" });
    const file = new File([blob], imageData.name || `image-${Date.now()}.jpg`, {
        type: "image/jpeg"
    });
    
    // Find the hidden <input type="file"> on the page
    const fileInputElements = await waitForElement(
        remoteConfig.selectors.fileInput, 10000, 100, false  // false = don't require visible
    );
    const fileInput = fileInputElements.first().get(0);  // raw DOM element
    
    // Inject the file using DataTransfer API
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    fileInput.files = dataTransfer.files;
    
    // Dispatch "change" event so React/framework picks it up
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
}
Key technique: You can't just set .files on a file input normally. The DataTransfer API lets you programmatically construct a file list and assign it, then dispatching change tricks the framework into thinking the user selected a file.

Step 3: E() — Fill Prompt and Submit

async function fillPromptAndSubmit(payload, remoteConfig) {
    const selectors = remoteConfig.selectors;
    
    // Determine which input element to use
    let inputSelector = selectors.promptContentEditable;
    // Check if there's an alternative textarea (dropUI)
    if (jQuery(selectors.promptDropUiTextarea).length > 0) {
        inputSelector = selectors.promptDropUiTextarea;
    }
    
    // Wait for input to be visible
    const inputElements = await waitForElement(inputSelector);
    const inputEl = inputElements.first()[0];  // raw DOM node
    
    // Focus and click the input first
    await clickElement(inputSelector, "Prompt input");
    inputEl.focus();
    
    // Set the text value
    if (inputEl instanceof HTMLTextAreaElement) {
        inputEl.value = payload.prompt;          // textarea
    } else {
        inputEl.textContent = payload.prompt;    // contenteditable div
    }
    
    // Dispatch ALL the events React/Vue might be listening to:
    
    // 1. Native "input" event
    inputEl.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
    
    // 2. Native "change" event
    inputEl.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
    
    // 3. jQuery-triggered events (for any jQuery listeners)
    inputElements.first().trigger("input");
    inputElements.first().trigger("change");
    
    // 4. Input event with explicit target (React needs this)
    const reactInput = new Event("input", { bubbles: true });
    Object.defineProperty(reactInput, "target", {
        writable: false,
        value: inputEl    // React reads event.target.value
    });
    inputEl.dispatchEvent(reactInput);
    
    // 5. Wait 500ms, then press Enter to submit
    await sleep(500);
    inputEl.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
        bubbles: true,
        cancelable: true
    }));
    
    return true;
}
Why so many events? Grok.com uses React. React doesn't listen to native DOM events directly — it uses a synthetic event system. The trick is:

Setting .value / .textContent directly (so the DOM has the text)
Dispatching input with target set to the element (so React's onChange handler reads event.target.value)
The jQuery .trigger() calls are a safety net for any jQuery-based listeners
Finally, a keydown Enter simulates the user pressing Enter to submit
The clickElement function (m) — Smart Click Simulation
This is used everywhere above. It's the core of the UI automation:


async function clickElement(selector, label = "Undefined", timeout = 5000, poll = 100) {
    // Runs inside a Mutex — only one click can happen at a time
    return mutex.runExclusive(async () => {
        const startTime = Date.now();
        
        while (Date.now() - startTime < timeout) {
            await sleep(poll);
            const elements = jQuery(selector);
            
            if (isElementReady(elements)) {
                const domNode = elements.get(0);
                if (domNode) {
                    // Dispatch FULL pointer event sequence
                    const eventSequence = [
                        "pointerover",   // pointer enters element
                        "mouseover",     // mouse enters (legacy)
                        "pointerdown",   // finger/button pressed
                        "mousedown",     // mouse button pressed (legacy)
                        "pointerup",     // finger/button released
                        "mouseup",       // mouse button released (legacy)
                        "click"          // final click
                    ];
                    
                    for (const eventName of eventSequence) {
                        const event = new MouseEvent(eventName, {
                            bubbles: true,      // propagates up DOM tree
                            cancelable: true,   // can be preventDefault'd
                            composed: true,     // crosses shadow DOM boundary
                            view: window,       // associated window
                            detail: 1           // single click
                        });
                        domNode.dispatchEvent(event);
                    }
                    await sleep(300);  // wait for UI reaction
                }
                return;  // success
            }
        }
        
        // Timeout — throw descriptive error
        if (jQuery(selector).length === 0) {
            throw new Error(`${label} - Element not found: ${selector} within ${timeout}ms`);
        } else {
            throw new Error(`${label} - Element found but not visible/ready within ${timeout}ms`);
        }
    });
}
Why the full pointer sequence? Modern frameworks (React, Vue) and especially UI libraries like Radix/Headless UI listen on pointerdown/pointerup, not just click. Dropdowns, menus, and toggle buttons often use pointer events. If you only dispatch click, dropdowns won't open. The full sequence mimics exactly what a real mouse interaction produces.

Why the Mutex? If two concurrent prompts both try to click UI elements simultaneously, they'd interfere with each other (e.g., one opens a dropdown, the other tries to click inside it before it's rendered). The Mutex ensures click operations are serialized.

isElementReady (f) — Visibility Check

function isElementReady(jQueryEl) {
    if (jQueryEl.length === 0) return false;
    const domNode = jQueryEl[0];
    
    // jQuery visibility/disabled checks
    if (!jQueryEl.is(":visible")) return false;
    if (jQueryEl.is(":disabled")) return false;
    
    // Bounding rect check (has actual size)
    const rect = domNode.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return false;
    
    // Computed style check
    const style = window.getComputedStyle(domNode);
    if (style.display === "none") return false;
    if (style.visibility === "hidden") return false;
    if (style.opacity === "0") return false;
    
    // Must be within viewport
    if (rect.top < 0 || rect.left < 0) return false;
    if (rect.bottom > window.innerHeight) return false;
    
    return true;
}
This is thorough — it checks jQuery's :visible, CSS display/visibility/opacity, physical dimensions, and viewport bounds. An element can exist in DOM but be hidden in many different ways.

PROCESS 2: Grabbing the URL and Downloading
This happens in function S (renamed waitForResultAndDownload). It has two sub-processes: detecting when generation finishes, and downloading the result.

Part A: Polling for Generated Content

async function waitForResultAndDownload(payload, isCancelled, remoteConfig) {
    const selectors = remoteConfig.selectors;
    let resultElements = [];
    let pollCount = 0;
    const MAX_POLLS = 150;  // 150 × 2sec = 5 minutes max wait
    
    while (pollCount < MAX_POLLS) {
        if (isCancelled && isCancelled()) return { success: false, resourceElements: [] };
        
        let container = null;
        let isMasonryLayout = false;
        
        // Different container selectors based on mode:
        if (payload.mode.includes("textToImage")) {
            // For text-to-image, look for masonry grid first
            container = await waitForElement(selectors.imagineMasonrySection);
            if (container && container.length > 0) {
                container = container.last();  // latest generation
                isMasonryLayout = true;
            } else {
                // Fallback to main article container
                container = await waitForElement(selectors.mainArticle);
                if (container) container = container.last();
            }
        } else if (payload.mode.includes("imageToImage")) {
            container = await waitForElement(selectors.imageToImageResultGrid);
            if (container) container = container.last();
        } else if (payload.mode.includes("ToVideo")) {
            container = await waitForElement(selectors.mainArticle);
            if (container) container = container.last();
        }
Key insight: It always takes .last() — because previous generations may still be on the page. The latest result is the last matching container.


        if (container && container.length > 0) {
            let mediaElements = [];
            
            if (payload.mode.includes("ToImage")) {
                // Find all <img> inside the container
                const allImages = Array.from(container.find("img"));
                
                if (isMasonryLayout) {
                    // Filter: only base64 data URLs that are large enough (>130KB)
                    // This filters out thumbnails and UI icons
                    mediaElements = allImages.filter(img => {
                        const src = img.src || "";
                        return src.startsWith("data:image") && src.length >= 130000;
                    });
                } else {
                    mediaElements = allImages;
                }
            } else {
                // For video modes, find all <video> elements
                mediaElements = Array.from(container.find("video"));
            }
The image filter trick: Grok renders generated images as inline base64 data URLs. The extension distinguishes real generated images from UI icons/thumbnails by checking if the base64 string is at least ~130KB (about 100KB decoded). Real AI-generated images are much larger than UI elements.


            // Check if we have enough results
            const isComplete = payload.mode.includes("textToImage")
                ? mediaElements.length >= payload.outputCount   // need N images
                : payload.mode.includes("imageToImage")
                    ? mediaElements.length === 1                // need 1 image
                    : mediaElements.length > 0;                 // need at least 1 video
            
            if (isComplete && mediaElements[0].src) {
                // DONE! We have our results
                resultElements = mediaElements.slice(0, payload.outputCount);
                
                // Report 100% progress
                chrome.runtime.sendMessage({
                    type: "VIDEO_GENERATION_PROGRESS",
                    data: {
                        promptIndex: payload.promptIndex,
                        percentage: 100,
                        status: "completed",
                        prompt: payload.prompt
                    }
                });
                break;
            }
Part A.2: Progress Tracking (while waiting)
For videos, it reads the circular SVG progress indicator:


            // For videos: parse the SVG progress circle
            let percentage = -1;
            const svgCircles = await waitForElement(selectors.percentageSvg);
            
            if (svgCircles && svgCircles.length > 0) {
                // SVG circular progress uses stroke-dasharray and stroke-dashoffset
                // dasharray = total circumference, dashoffset = remaining
                const dashArray = svgCircles.first().attr("stroke-dasharray") || "";
                const dashOffset = svgCircles.first().attr("stroke-dashoffset") || "";
                
                const circumference = parseFloat(dashArray.split(" ")[0]);
                const offset = parseFloat(dashOffset);
                
                if (!isNaN(circumference) && !isNaN(offset) && circumference > 0) {
                    // percentage = (1 - offset/circumference) × 100
                    percentage = Math.round(100 * (1 - offset / circumference));
                    percentage = Math.max(0, Math.min(100, percentage));
                }
            }
            
            // Also check for loading spinner
            if (jQuery(".animate-spin").length > 0) {
                percentage = percentage > 0 ? percentage + 1 : 1;
            }
The SVG trick: Grok's circular progress bar is an SVG <circle> with:

stroke-dasharray = total circumference (e.g. "251.2 251.2")
stroke-dashoffset = how much is "hidden" (starts at 251.2, decreases to 0)
Progress = 1 - (offset / circumference) → gives 0.0 to 1.0

        await sleep(2000);  // poll every 2 seconds
        pollCount++;
    }
    
    if (resultElements.length === 0) {
        return { success: false, resourceElements: [] };
    }
Part B: Downloading Videos

    if (payload.mode.includes("ToVideo")) {
        // --- UPSCALE TO HD (if configured) ---
        // Check if HD button already exists
        const hdBtn = jQuery(selectors.hdButton);
        if (!hdBtn || hdBtn.length === 0) {
            // No HD button yet — trigger upscale via "More Options" menu
            const moreOptions = await waitForElement(selectors.moreOptionsButton, 5000);
            if (moreOptions && moreOptions.length > 0) {
                await clickElement(selectors.moreOptionsButton, "More options");
                
                const upscaleItem = jQuery(selectors.upscaleMenuItem);
                if (upscaleItem && upscaleItem.length > 0) {
                    await clickElement(selectors.upscaleMenuItem, "Upscale video");
                    
                    // Wait up to 2 minutes for HD version to be ready
                    let waitCount = 0;
                    while (waitCount < 60 && !isCancelled()) {
                        const hdReady = await waitForElement(selectors.hdButton);
                        if (hdReady && hdReady.length > 0) break;
                        await sleep(2000);
                        waitCount++;
                    }
                } else {
                    // No upscale option, close menu
                    await clickElement(selectors.moreOptionsButton, "Close menu");
                }
            }
        }
        
        // Click the download button on the page
        const downloadBtn = await waitForElement(selectors.downloadButton, 3000);
        if (downloadBtn && downloadBtn.length > 0) {
            await clickElement(selectors.downloadButton, "Download button");
        }
For concat/chaining — it also clicks a "Share" button to generate a share URL:


        if (payload.isConcat) {
            const shareBtn = await waitForElement(selectors.shareButton, 5000);
            if (shareBtn && shareBtn.length > 0) {
                await clickElement(selectors.shareButton, "Create share link");
            }
        }
HD URL rewriting — back in the main x() function, after S() returns:


    // If video mode and we got video elements back
    if (payload.mode.includes("ToVideo") && result.resourceElements.length > 0) {
        const hdSuffix = payload.autoDownloadResourceQuality === "720p" ? "_hd" : "";
        const videoSrcRegex = new RegExp(remoteConfig.videoSrcRegex);
        
        result.resourceElements.forEach(videoEl => {
            if (videoEl instanceof HTMLVideoElement 
                && videoEl.src.includes("assets.grok.com") 
                && videoEl.src.includes("/generated/")) {
                
                // Extract UUID from video URL using regex
                const match = videoEl.src.match(videoSrcRegex);
                if (match) {
                    const uuid = match[1];
                    // Rewrite to direct download URL
                    videoEl.src = remoteConfig.shareUrlTemplate
                        .replace("{uuid}", uuid)
                        .replace("{suffix}", hdSuffix);
                }
            }
        });
    }