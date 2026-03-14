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
          style="position:absolute;inset:-50%;width:200%;height:200%;background:linear-gradient(135deg,#0a0e13 0%,#0f1a2a 15%,#132a35 25%,rgba(78,205,196,0.12) 35%,#0f1520 45%,#1a1535 55%,rgba(167,139,250,0.10) 65%,#0f1520 75%,rgba(78,205,196,0.08) 85%,#0a0e13 100%);background-size:200% 200%;animation:welcomeGradient 12s ease infinite"
        ></div>

        <div
          style="position:absolute;inset:0;background-image:linear-gradient(rgba(78,205,196,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(78,205,196,0.03) 1px,transparent 1px);background-size:60px 60px"
        ></div>

        <div
          style="position:absolute;top:20%;left:15%;width:300px;height:300px;border-radius:50%;background:radial-gradient(circle,rgba(78,205,196,0.08),transparent 70%);animation:welcomeFloat 8s ease-in-out infinite"
        ></div>
        <div
          style="position:absolute;bottom:20%;right:15%;width:250px;height:250px;border-radius:50%;background:radial-gradient(circle,rgba(167,139,250,0.06),transparent 70%);animation:welcomeFloat 10s ease-in-out infinite reverse"
        ></div>
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
          style="filter:drop-shadow(0 0 30px rgba(78,205,196,0.3))"
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
          style="width:120px;height:1px;background:linear-gradient(90deg,transparent,rgba(78,205,196,0.6),transparent);opacity:0;animation:welcomeFadeUp 0.6s ease 1.4s forwards"
        ></div>

        <p
          id="welcome-quote"
          style="font-family:'DM Sans',system-ui,sans-serif;font-size:clamp(13px,1.5vw,15px);font-weight:400;color:#8899aa;max-width:520px;text-align:center;line-height:1.7;padding:0 24px;opacity:0;animation:welcomeFadeUp 0.8s ease 1.6s forwards"
        >
          {{ welcome.quote.value }}
        </p>

        <p
          style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:rgba(136,153,170,0.4);opacity:0;animation:welcomeFadeUp 0.6s ease 2s forwards"
        >
          Create. Align. Segment. Visualize.
        </p>

        <button
          id="welcome-enter-btn"
          class="welcome-enter-btn"
          @click="welcome.dismissWelcome()"
          style="margin-top:10px;padding:12px 40px;font-family:'Space Grotesk',system-ui,sans-serif;font-size:13px;font-weight:600;letter-spacing:0.15em;text-transform:uppercase;color:#0f1520;border:none;border-radius:12px;cursor:pointer;background:linear-gradient(135deg,#4ECDC4,#5edfd6);box-shadow:0 4px 24px rgba(78,205,196,0.3),inset 0 1px 0 rgba(255,255,255,0.2);opacity:0;animation:welcomeFadeUp 0.6s ease 2.4s forwards;transition:transform 0.2s,box-shadow 0.2s"
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
