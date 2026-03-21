import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/pipeline',
  },
  {
    path: '/pipeline',
    name: 'pipeline',
    component: () => import('@/features/pipeline/views/PipelinePage.vue'),
    meta: { title: 'Pipeline', icon: 'rocket' },
  },
  {
    path: '/tts',
    name: 'tts',
    component: () => import('@/features/tts/views/TtsPage.vue'),
    meta: { title: 'Text to Speech', icon: 'mic' },
  },
  {
    path: '/timing',
    redirect: '/alignment',
  },
  {
    path: '/alignment',
    name: 'alignment',
    component: () => import('@/features/timing/views/TimingPage.vue'),
    meta: { title: 'Force Alignment', icon: 'clock' },
  },
  {
    path: '/segmenter',
    name: 'segmenter',
    component: () => import('@/features/segmenter/views/SegmenterPage.vue'),
    meta: { title: 'Scene Segmenter', icon: 'scissors' },
  },
  {
    path: '/scenes',
    name: 'scenes',
    component: () => import('@/features/scenes/views/ScenesPage.vue'),
    meta: { title: 'Scene Blueprint', icon: 'film' },
  },
  {
    path: '/assets',
    name: 'assets',
    component: () => import('@/features/assets/views/AssetsPage.vue'),
    meta: { title: 'Asset Manager', icon: 'image' },
  },
  {
    path: '/editor',
    name: 'editor',
    component: () => import('@/features/editor/views/EditorPage.vue'),
    meta: { title: 'Timeline Editor', icon: 'sliders' },
  },
  {
    path: '/export-library',
    name: 'export-library',
    component: () => import('@/features/export-library/views/ExportLibraryPage.vue'),
    meta: { title: 'Export Library', icon: 'archive' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/features/settings/views/SettingsPage.vue'),
    meta: { title: 'Settings', icon: 'settings' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  linkActiveClass: 'active',
  linkExactActiveClass: 'active',
})

export default router
