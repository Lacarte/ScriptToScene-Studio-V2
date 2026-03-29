<script setup>
import { Teleport } from 'vue'
import { useWelcomeOverlay } from '@/shared/composables/useWelcomeOverlay.js'

defineOptions({ name: 'WelcomeOverlay' })

const welcome = useWelcomeOverlay()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="welcome.isVisible.value"
      id="welcome-overlay"
      :class="{ dismissing: welcome.isDismissing.value }"
      style="display:flex;position:fixed;inset:0;z-index:9999;align-items:center;justify-content:center;background:#0a0e13;overflow:hidden;flex-direction:column;gap:0"
    >
      <div style="position:absolute;inset:0;overflow:hidden">
        <div
          id="welcome-gradient"
          style="position:absolute;inset:-50%;width:200%;height:200%;background:linear-gradient(135deg,#0a0e13 0%,#0f1a2a 10%,#163040 20%,rgba(78,205,196,0.22) 35%,#0f1520 45%,#221a45 55%,rgba(167,139,250,0.18) 65%,#0f1520 75%,rgba(78,205,196,0.15) 85%,#0a0e13 100%);background-size:200% 200%;animation:welcomeGradient 12s ease infinite"
        ></div>

        <div
          style="position:absolute;inset:0;background-image:linear-gradient(rgba(78,205,196,0.06) 1px,transparent 1px),linear-gradient(90deg,rgba(78,205,196,0.06) 1px,transparent 1px);background-size:60px 60px"
        ></div>

        <div
          style="position:absolute;top:20%;left:15%;width:300px;height:300px;border-radius:50%;background:radial-gradient(circle,rgba(78,205,196,0.15),transparent 70%);animation:welcomeFloat 8s ease-in-out infinite"
        ></div>
        <div
          style="position:absolute;bottom:20%;right:15%;width:250px;height:250px;border-radius:50%;background:radial-gradient(circle,rgba(167,139,250,0.14),transparent 70%);animation:welcomeFloat 10s ease-in-out infinite reverse"
        ></div>

        <!-- Floating studio icons -->
        <!-- Gear 1 (top-left) -->
        <svg style="position:absolute;top:12%;left:8%;width:64px;height:64px;opacity:0.14;animation:welcomeSpin 20s linear infinite,welcomeFloat 8s ease-in-out infinite" viewBox="0 0 24 24" fill="none" stroke="#4ECDC4" stroke-width="1.5">
          <path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
        </svg>

        <!-- Gear 2 (bottom-right, larger, slower) -->
        <svg style="position:absolute;bottom:18%;right:10%;width:90px;height:90px;opacity:0.10;animation:welcomeSpin 30s linear infinite reverse,welcomeFloat 12s ease-in-out infinite reverse" viewBox="0 0 24 24" fill="none" stroke="#A78BFA" stroke-width="1.2">
          <path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
        </svg>

        <!-- Camera (top-right) -->
        <svg style="position:absolute;top:22%;right:18%;width:56px;height:56px;opacity:0.12;animation:welcomeFloat 9s ease-in-out 1s infinite,welcomeDrift 25s linear infinite" viewBox="0 0 24 24" fill="none" stroke="#4ECDC4" stroke-width="1.5">
          <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/>
        </svg>

        <!-- Film strip (left-center) -->
        <svg style="position:absolute;top:45%;left:5%;width:72px;height:72px;opacity:0.10;animation:welcomeFloat 11s ease-in-out 2s infinite" viewBox="0 0 24 24" fill="none" stroke="#A78BFA" stroke-width="1.3">
          <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/>
        </svg>

        <!-- Scissors (bottom-left) -->
        <svg style="position:absolute;bottom:25%;left:15%;width:52px;height:52px;opacity:0.12;animation:welcomeFloat 10s ease-in-out 3s infinite,welcomeSpin 40s linear infinite" viewBox="0 0 24 24" fill="none" stroke="#4ECDC4" stroke-width="1.5">
          <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>
        </svg>

        <!-- Audio wave (right-center) -->
        <svg style="position:absolute;top:55%;right:8%;width:60px;height:60px;opacity:0.12;animation:welcomeFloat 7s ease-in-out 1.5s infinite" viewBox="0 0 24 24" fill="none" stroke="#A78BFA" stroke-width="1.5" stroke-linecap="round">
          <rect x="1" y="8" width="3" height="8" rx="1" style="animation:welcomeBar 1.5s ease-in-out infinite"/><rect x="5.5" y="5" width="3" height="14" rx="1" style="animation:welcomeBar 1.5s ease-in-out 0.2s infinite"/><rect x="10" y="2" width="3" height="20" rx="1" style="animation:welcomeBar 1.5s ease-in-out 0.4s infinite"/><rect x="14.5" y="6" width="3" height="12" rx="1" style="animation:welcomeBar 1.5s ease-in-out 0.6s infinite"/><rect x="19" y="9" width="3" height="6" rx="1" style="animation:welcomeBar 1.5s ease-in-out 0.8s infinite"/>
        </svg>

        <!-- Gear 3 (small, center-top) -->
        <svg style="position:absolute;top:8%;left:45%;width:40px;height:40px;opacity:0.09;animation:welcomeSpin 15s linear infinite,welcomeFloat 6s ease-in-out 4s infinite" viewBox="0 0 24 24" fill="none" stroke="#4ECDC4" stroke-width="1.5">
          <path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
        </svg>

        <!-- Camera 2 (bottom-center, small) -->
        <svg style="position:absolute;bottom:10%;left:40%;width:44px;height:44px;opacity:0.09;animation:welcomeFloat 13s ease-in-out 5s infinite,welcomeDrift 35s linear infinite reverse" viewBox="0 0 24 24" fill="none" stroke="#4ECDC4" stroke-width="1.5">
          <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
      </div>

      <div
        style="position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;gap:40px;animation:welcomeFadeUp 1.2s cubic-bezier(0.16,1,0.3,1) both"
      >
        <svg
          id="welcome-logo"
          width="80"
          height="80"
          viewBox="0 0 80 80"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          style="filter:drop-shadow(0 0 40px rgba(78,205,196,0.45))"
        >
          <rect x="4" y="4" width="72" height="72" rx="16" fill="#0f1520" stroke="url(#welcome-stroke-grad)" stroke-width="2" />
          <path d="M24 4v72" stroke="url(#welcome-stroke-grad)" stroke-width="2" opacity="0.6" style="stroke-dasharray:72;stroke-dashoffset:72;animation:welcomeStroke 2s ease 0.6s forwards" />
          <circle cx="46" cy="40" r="12" fill="none" stroke="url(#welcome-stroke-grad)" stroke-width="2" style="stroke-dasharray:76;stroke-dashoffset:76;animation:welcomeStroke 2s ease 0.8s forwards" />
          <rect x="4" y="4" width="72" height="72" rx="16" fill="none" stroke="url(#welcome-stroke-grad)" stroke-width="2" style="stroke-dasharray:272;stroke-dashoffset:272;animation:welcomeStroke 2s ease 0.3s forwards" />
          <defs>
            <linearGradient id="welcome-stroke-grad" x1="0" y1="0" x2="80" y2="80" gradientUnits="userSpaceOnUse">
              <stop stop-color="#4ECDC4" />
              <stop offset="1" stop-color="#A78BFA" />
            </linearGradient>
          </defs>
        </svg>

        <div style="display:flex;flex-direction:column;align-items:center;gap:8px">
          <h1
            style="font-family:'Space Grotesk',system-ui,sans-serif;font-size:clamp(42px,6vw,64px);font-weight:700;letter-spacing:-0.04em;line-height:1;background:linear-gradient(135deg,#ffffff 0%,#4ECDC4 30%,#A78BFA 70%,#ffffff 100%);background-size:200% 200%;animation:welcomeTextGrad 6s ease infinite;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text"
          >
            ScriptToScene
          </h1>
          <p
            style="font-family:'JetBrains Mono',monospace;font-size:14px;letter-spacing:0.35em;text-transform:uppercase;color:#4ECDC4;opacity:0;animation:welcomeFadeUp 0.8s ease 1s forwards"
          >
            STUDIO
          </p>
        </div>

        <div
          style="width:120px;height:1px;background:linear-gradient(90deg,transparent,rgba(78,205,196,0.8),transparent);opacity:0;animation:welcomeFadeUp 0.6s ease 1.4s forwards"
        ></div>

        <p
          id="welcome-quote"
          style="font-family:'DM Sans',system-ui,sans-serif;font-size:clamp(13px,1.5vw,15px);font-weight:400;color:#b8c8d8;max-width:520px;text-align:center;line-height:1.7;padding:0 24px;opacity:0;animation:welcomeFadeUp 0.8s ease 1.6s forwards"
        >
          {{ welcome.quote.value }}
        </p>

        <p
          style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:rgba(136,153,170,0.65);opacity:0;animation:welcomeFadeUp 0.6s ease 2s forwards"
        >
          Create. Align. Segment. Visualize.
        </p>

        <button
          id="welcome-enter-btn"
          class="welcome-enter-btn"
          @click="welcome.dismissWelcome()"
          style="margin-top:10px;padding:12px 40px;font-family:'Space Grotesk',system-ui,sans-serif;font-size:13px;font-weight:600;letter-spacing:0.15em;text-transform:uppercase;color:#0f1520;border:none;border-radius:12px;cursor:pointer;background:linear-gradient(135deg,#4ECDC4,#5edfd6);box-shadow:0 4px 30px rgba(78,205,196,0.45),inset 0 1px 0 rgba(255,255,255,0.25);opacity:0;animation:welcomeFadeUp 0.6s ease 2.4s forwards;transition:transform 0.2s,box-shadow 0.2s"
        >
          Enter Studio
        </button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.welcome-enter-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(78, 205, 196, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
}
</style>

<style>
@keyframes welcomeSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@keyframes welcomeDrift {
  0% { transform: translateX(0) translateY(0); }
  25% { transform: translateX(15px) translateY(-10px); }
  50% { transform: translateX(-10px) translateY(15px); }
  75% { transform: translateX(20px) translateY(5px); }
  100% { transform: translateX(0) translateY(0); }
}
@keyframes welcomeBar {
  0%, 100% { opacity: 0.3; transform: scaleY(0.6); }
  50% { opacity: 1; transform: scaleY(1); }
}
</style>
