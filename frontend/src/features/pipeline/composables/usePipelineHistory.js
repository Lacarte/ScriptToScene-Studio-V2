import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { ALL_STEPS } from '../constants/steps.js'

const jobs = ref([])
const lastCompletedProjectId = ref(null)
const lastCompletedExportFilename = ref(null)

async function loadHistory() {
  try {
    const data = await api.get('/api/pipeline/jobs')
    jobs.value = data
  } catch (e) {
    console.warn('[Pipeline] Failed to load history:', e.message)
    jobs.value = []
  }
}

function inferResumeStep(statuses = {}) {
  const stepIds = ALL_STEPS.map(step => step.id)
  for (const stepId of stepIds) {
    if (statuses?.[stepId] === 'stopped' || statuses?.[stepId] === 'running') {
      return stepId
    }
  }
  for (const stepId of stepIds) {
    if (!['done', 'skipped'].includes(statuses?.[stepId])) {
      return stepId
    }
  }
  return null
}

export function usePipelineHistory() {
  return {
    jobs: readonly(jobs),
    lastCompletedProjectId,
    lastCompletedExportFilename,
    loadHistory,
    inferResumeStep,

    // Internal mutable access for pipeline execution
    _jobs: jobs,
  }
}
