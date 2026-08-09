import { computed, ref, watch } from 'vue'
import { useProviderCatalogStore } from '../stores/providerCatalog.js'
import { effectiveSettings } from '@/shared/schema/providerSettings.js'

/**
 * One legacy page's view of one provider domain (step 12.4).
 *
 * The pages that predate the provider platform each answered three questions
 * for themselves: which provider is selected, what is it called on the wire,
 * and what is it configured with. They answered them from `useSettings`, from a
 * hardcoded list, and from `localStorage` respectively — three stores that could
 * disagree with the catalog and with each other. This answers all three from
 * `GET /api/providers` (contracts.md §24.3 rule 3), so a page keeps its own
 * layout and request shape while owning none of the provider knowledge.
 *
 * `withSettings` is opt-in because it costs a request per provider switch, and
 * only pages that put a configured value on the wire need it.
 */
export function useDomainProvider(domain, { withSettings = false } = {}) {
  const catalog = useProviderCatalogStore()

  const provider = computed(() => catalog.selectedProvider(domain))
  const providerId = computed(() => provider.value?.id || '')
  /** What the legacy routes still compare against (§40.3, output column). */
  const legacyId = computed(() => catalog.legacyIdFor(domain, providerId.value))
  const label = computed(() => provider.value?.label || providerId.value)
  /** The provider's own page, from its manifest — never a literal in a view. */
  const openUrl = computed(() => provider.value?.open_url || null)

  /** Declarative branching, the replacement for `if (provider === '…')`. */
  function supports(capability) {
    return catalog.supports(domain, providerId.value, capability)
  }

  // ── Configured values of the selected provider ─────────────────────────
  const schema = ref({})
  const settings = ref({})
  const settingsLoading = ref(false)

  async function loadSettings() {
    const id = providerId.value
    if (!id) {
      schema.value = {}
      settings.value = {}
      return
    }
    settingsLoading.value = true
    try {
      const data = await catalog.getProviderSettings(domain, id)
      // Guard against an out-of-order response for a provider that is no longer
      // selected: switching twice quickly must not leave the first one's values
      // on screen.
      if (providerId.value !== id) return
      schema.value = data.schema || {}
      settings.value = effectiveSettings(data.schema, data.settings)
    } catch {
      schema.value = {}
      settings.value = {}
    } finally {
      settingsLoading.value = false
    }
  }

  catalog.loadCatalog()
  if (withSettings) watch(providerId, loadSettings, { immediate: true })

  return {
    catalog,
    provider,
    providerId,
    legacyId,
    label,
    openUrl,
    supports,
    schema,
    settings,
    settingsLoading,
    loadSettings,
  }
}
