<script setup>
import { onMounted } from 'vue'
import MainLayout from './layouts/MainLayout.vue'
import ToastContainer from '@/shared/components/ToastContainer.vue'
import ActivitySnackbar from '@/shared/components/ActivitySnackbar.vue'
import WelcomeOverlay from '@/shared/components/WelcomeOverlay.vue'
import { useWelcomeOverlay } from '@/shared/composables/useWelcomeOverlay.js'

const welcome = useWelcomeOverlay()

onMounted(() => {
  welcome.initWelcome()
})
</script>

<template>
  <MainLayout />
  <WelcomeOverlay />
  <ToastContainer />
  <ActivitySnackbar />
</template>
