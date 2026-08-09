import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/shared/api/client.js'
import { apiErrorText } from '@/shared/api/errors.js'
import { invalidateOptionSources } from '@/shared/composables/useOptionSources.js'
import { useSettings } from '@/features/settings/composables/useSettings.js'
import { AVAILABLE, UNAVAILABLE } from '../availability.js'

/**
 * The one frontend view of the provider catalog (step 12.1).
 *
 * `GET /api/providers` is authoritative: every provider list, label, capability,
 * availability state, and per-domain selection in the app is read from here.
 * Nothing about a provider is hardcoded in a component or in static frontend
 * data, so adding, removing, or relabeling a provider is a backend-only change.
 *
 * Two axes are kept apart, per contracts.md §21.5. **Availability** ships with
 * the catalog, costs nothing, and answers "can this be used?". **Health** costs
 * I/O, is requested explicitly, and is cached separately — it never gates
 * selection. The composable this store replaces conflated them by running a
 * validation round trip per selector render.
 */

const CATALOG_URL = '/api/providers'
// Provider packages are watched by the same dev reloader as node definitions,
// so provider edits arrive on the workflow reload stream (dev_reload.py).
const DEV_RELOAD_URL = '/api/workflow/dev-reload/events'

function healthKey(domain, providerId) {
  return `${domain}/${providerId}`
}

/**
 * Project an `excluded[]` entry onto the provider shape.
 *
 * A provider that failed discovery still has to render — silently dropping it
 * is how a broken folder becomes an unexplained missing dropdown entry. It is
 * the only source of the `unavailable` state (§21.4).
 */
function excludedAsProvider(exclusion, domain) {
  return {
    id: exclusion.id,
    label: exclusion.id,
    domain,
    aliases: [],
    capabilities: {},
    has_settings: false,
    availability: UNAVAILABLE,
    warnings: exclusion.message ? [exclusion.message] : [],
    reason_code: exclusion.reason_code,
  }
}

export const useProviderCatalogStore = defineStore('providerCatalog', () => {
  // ── Catalog (backend-served, cached by content version) ────────────────
  const catalogVersion = ref(null)
  const domains = ref({})
  const loading = ref(false)
  const error = ref('')
  const devReloadEnabled = ref(false)
  // `domain/provider_id` -> the last HealthResult seen for that provider.
  const health = ref({})
  // `domain/provider_id` -> that provider's settings schema, or null when it
  // ships none. Cached because the node inspector asks per selected node.
  const schemas = ref({})

  let inFlight = null
  let devReloadSource = null

  const loaded = computed(() => catalogVersion.value !== null)
  const domainIds = computed(() => Object.keys(domains.value).sort())

  /**
   * Fetch the catalog, at most once per session unless forced.
   *
   * Concurrent callers share one request: three selectors mounting together
   * must not race three identical fetches. An unchanged `catalog_version` keeps
   * the existing objects rather than replacing them, so a forced refresh that
   * finds nothing new cannot churn every downstream computed.
   */
  async function loadCatalog({ force = false } = {}) {
    if (!force && catalogVersion.value !== null) return
    if (inFlight) return inFlight

    loading.value = true
    error.value = ''
    inFlight = api
      .get(CATALOG_URL)
      .then((data) => {
        devReloadEnabled.value = data.dev_reload_enabled === true
        const version = data.catalog_version ?? null
        if (version !== null && version === catalogVersion.value) return
        catalogVersion.value = version
        domains.value = data.domains || {}
        // A changed catalog version is the only thing that can change a
        // provider's settings schema — a reloaded package, a new version of
        // one. Dropping the cache here rather than on every settings save
        // avoids a refetch that a value write could never have invalidated.
        schemas.value = {}
      })
      .catch((err) => {
        error.value = apiErrorText(err, 'Failed to load providers')
      })
      .finally(() => {
        loading.value = false
        inFlight = null
      })
    return inFlight
  }

  function refresh() {
    return loadCatalog({ force: true })
  }

  // ── Domain grouping and lookup ─────────────────────────────────────────

  function domainEntry(domain) {
    return domains.value[domain] || null
  }

  function domainLabel(domain) {
    return domainEntry(domain)?.label || domain
  }

  function providersFor(domain) {
    return domainEntry(domain)?.providers || []
  }

  function excludedFor(domain) {
    return (domainEntry(domain)?.excluded || []).map((e) => excludedAsProvider(e, domain))
  }

  /** Every identity the domain knows about — registered first, then excluded. */
  function catalogEntriesFor(domain) {
    return [...providersFor(domain), ...excludedFor(domain)]
  }

  /**
   * Resolve an id through canonical id then alias.
   *
   * Deprecated provider identities are carried as aliases rather than a flag
   * (§20.1), so this is also how a legacy value stored before a rename still
   * points at the provider that replaced it.
   */
  function resolveProvider(domain, providerId) {
    if (!providerId) return null
    const list = providersFor(domain)
    return (
      list.find((p) => p.id === providerId) ||
      list.find((p) => (p.aliases || []).includes(providerId)) ||
      null
    )
  }

  function selectedId(domain) {
    return domainEntry(domain)?.selected ?? null
  }

  // ── The retired `app-config.json` selection keys (§24.3) ───────────────
  //
  // The catalog ships the *key name* per domain, so this file names no key and
  // no provider. Both helpers disappear when 16.1 stops serving the field.

  function legacySelectionKey(domain) {
    return domainEntry(domain)?.legacy_selection_key || null
  }

  /**
   * §24.3 rule 3 — read through to the legacy key for one release.
   *
   * The backend migration adopts the legacy value the first time a domain has
   * no explicit `selected_provider`, but a browser that loads before that
   * migration has run (or against a settings file it did not write) would
   * otherwise silently show the domain default instead of the provider the
   * user has been using. It is a *fallback*: an explicit `selected` always wins.
   */
  function legacySelectedId(domain) {
    const key = legacySelectionKey(domain)
    if (!key) return null
    return useSettings().settings.value[key] || null
  }

  /**
   * The value this provider is still spelled as on the legacy wire (§40.3,
   * output column) — what `POST /api/storyboard/grab` and friends compare
   * against until 16.1 removes the internal hop.
   *
   * A manifest lists its retired identities in `aliases`, so the first alias is
   * exactly that string; a provider that never had another name is already
   * canonical on the wire.
   */
  function legacyIdFor(domain, providerId) {
    const provider = resolveProvider(domain, providerId)
    if (!provider) return providerId || ''
    return (provider.aliases || [])[0] || provider.id
  }

  /**
   * The provider a domain will actually use, following the frozen precedence
   * chain (§24.1) for the rules a browser can evaluate: the stored selection,
   * the retired legacy key, then the domain default. The last two steps are the
   * recovery path for a selection whose provider was uninstalled — falling back
   * to a usable provider beats rendering an empty dropdown over a populated
   * domain.
   */
  function selectedProvider(domain) {
    const entry = domainEntry(domain)
    if (!entry) return null
    const list = entry.providers || []
    return (
      resolveProvider(domain, entry.selected) ||
      resolveProvider(domain, legacySelectedId(domain)) ||
      resolveProvider(domain, entry.default_provider) ||
      list.find((p) => p.availability === AVAILABLE) ||
      list[0] ||
      null
    )
  }

  function availabilityOf(domain, providerId) {
    const provider = resolveProvider(domain, providerId)
    if (provider) return provider.availability
    const excluded = excludedFor(domain).find((e) => e.id === providerId)
    return excluded ? UNAVAILABLE : null
  }

  function capabilitiesOf(domain, providerId) {
    return resolveProvider(domain, providerId)?.capabilities || {}
  }

  function supports(domain, providerId, capability) {
    return capabilitiesOf(domain, providerId)[capability] === true
  }

  // ── Health (explicit action only, cached apart from the catalog) ────────

  function healthFor(domain, providerId) {
    return health.value[healthKey(domain, providerId)] || null
  }

  function recordHealth(domain, providerId, result) {
    health.value = { ...health.value, [healthKey(domain, providerId)]: result }
    return result
  }

  /** Probe stored settings. Never throws: a failed probe *is* a health state. */
  async function checkHealth(domain, providerId) {
    try {
      const data = await api.get(`${CATALOG_URL}/${domain}/${providerId}/health`)
      return recordHealth(domain, providerId, data.health)
    } catch (err) {
      return recordHealth(domain, providerId, {
        status: 'fail',
        message: apiErrorText(err, 'Health check failed'),
      })
    }
  }

  /** Probe a candidate settings patch without saving it. */
  async function testProvider(domain, providerId, settings = {}) {
    const data = await api.post(`${CATALOG_URL}/${domain}/${providerId}/test`, { body: settings })
    return recordHealth(domain, providerId, data.health)
  }

  // ── Selection and settings writes ──────────────────────────────────────

  /**
   * One targeted write, not a read-modify-write of the whole settings document
   * (§24.2). Selection is non-blocking: a `needs_configuration` or failing
   * provider may be chosen, and the issues travel back so the caller can prompt.
   */
  async function selectProvider(domain, providerId) {
    if (selectedId(domain) === providerId) return { switched: false }

    const result = await api.put(`${CATALOG_URL}/${domain}/selection`, {
      body: { provider_id: providerId },
    })

    // The server answers with the canonical id — an alias is never stored.
    applySelection(domain, result)
    // Any dropdown resolved against this domain now has a different answer: a
    // context-free caller follows the selection (§23.4). Keeping the old list
    // is how one provider's voices end up offered for another provider's node.
    invalidateOptionSources({ domain })
    await mirrorLegacySelection(domain, result.selected)
    return {
      switched: true,
      availability: result.availability,
      needsConfiguration: result.availability !== AVAILABLE,
      issues: result.issues || [],
    }
  }

  /**
   * Keep the retired key in step until 16.1 deletes it.
   *
   * `usePipeline`, `useProviderTabs`, and `/api/pipeline/preflight` still read
   * it, so a selection made anywhere in the app has to land there too or the
   * two stores diverge on the next write — the exact failure §24.3 exists to
   * prevent. The legacy value is written, not the canonical id, because that is
   * what those readers put on the wire (§40.3).
   */
  async function mirrorLegacySelection(domain, providerId) {
    const key = legacySelectionKey(domain)
    if (!key) return
    try {
      await useSettings().update(key, legacyIdFor(domain, providerId))
    } catch {
      // A stale mirror is recoverable; a failed selection is not. The write
      // that matters already succeeded.
    }
  }

  function applySelection(domain, result) {
    const entry = domainEntry(domain)
    if (!entry) return
    const providers = (entry.providers || []).map((p) =>
      p.id === result.selected && result.availability
        ? { ...p, availability: result.availability }
        : p,
    )
    domains.value = {
      ...domains.value,
      [domain]: { ...entry, selected: result.selected, providers },
    }
  }

  function getProviderSettings(domain, providerId) {
    return api.get(`${CATALOG_URL}/${domain}/${providerId}/settings`)
  }

  // ── Settings schemas, cached per provider ──────────────────────────────
  //
  // The node inspector renders a per-run options form for whichever provider
  // the *node* selects, which is not necessarily the domain's selection, so it
  // cannot reuse `useDomainProvider`'s single-provider load. Concurrent asks
  // share one request: a workflow with three provider-backed nodes must not
  // fetch the same schema three times.

  const schemaRequests = new Map()

  function schemaFor(domain, providerId) {
    return schemas.value[healthKey(domain, providerId)] ?? null
  }

  async function loadProviderSchema(domain, providerId) {
    if (!domain || !providerId) return null
    const key = healthKey(domain, providerId)
    if (key in schemas.value) return schemas.value[key]
    if (schemaRequests.has(key)) return schemaRequests.get(key)

    const request = getProviderSettings(domain, providerId)
      .then((data) => data.schema || null)
      // A provider that is not installed, or ships no schema, has no form —
      // which is a state the inspector renders, not an error it reports. The
      // node stays inspectable either way (§23.3).
      .catch(() => null)
      .then((schema) => {
        schemas.value = { ...schemas.value, [key]: schema }
        schemaRequests.delete(key)
        return schema
      })
    schemaRequests.set(key, request)
    return request
  }

  /**
   * Save and re-read the catalog: filling in a required key flips availability
   * from `needs_configuration` to `available`, and that is not derivable here.
   */
  async function saveProviderSettings(domain, providerId, settings) {
    const result = await api.put(`${CATALOG_URL}/${domain}/${providerId}/settings`, {
      body: settings,
    })
    // Changing an API key changes what the provider can offer (§23.4).
    invalidateOptionSources({ domain })
    await refresh()
    return result
  }

  function validateProviderSettings(domain, providerId, settings = {}) {
    return api.post(`${CATALOG_URL}/${domain}/${providerId}/validate`, { body: settings })
  }

  // ── Unsaved drafts (one per provider, never containing a secret) ────────

  /**
   * Editing provider A, switching to B to compare, and coming back must not
   * silently discard A's edits — so a draft is keyed by provider and outlives
   * the modal. Secrets are stripped by the caller before they get here (§22.6).
   */
  const drafts = ref({})

  function draftFor(domain, providerId) {
    return drafts.value[healthKey(domain, providerId)] || null
  }

  function setDraft(domain, providerId, values) {
    drafts.value = { ...drafts.value, [healthKey(domain, providerId)]: { ...values } }
  }

  function clearDraft(domain, providerId) {
    const next = { ...drafts.value }
    delete next[healthKey(domain, providerId)]
    drafts.value = next
  }

  // ── Developer hot reload ───────────────────────────────────────────────

  /**
   * Refetch when the dev reloader republishes the catalog. The stream is shared
   * with the workflow node registry because one watcher covers both.
   */
  function watchCatalogReloads({ EventSourceImpl = globalThis.EventSource } = {}) {
    if (!devReloadEnabled.value || devReloadSource || !EventSourceImpl) return null
    devReloadSource = new EventSourceImpl(DEV_RELOAD_URL)
    devReloadSource.addEventListener('registry-reload', () => refresh())
    return devReloadSource
  }

  function closeCatalogReloads() {
    devReloadSource?.close()
    devReloadSource = null
  }

  return {
    catalogVersion,
    domains,
    loading,
    error,
    devReloadEnabled,
    health,
    loaded,
    domainIds,
    loadCatalog,
    refresh,
    domainEntry,
    domainLabel,
    providersFor,
    excludedFor,
    catalogEntriesFor,
    resolveProvider,
    selectedId,
    selectedProvider,
    legacySelectionKey,
    legacyIdFor,
    availabilityOf,
    capabilitiesOf,
    supports,
    healthFor,
    checkHealth,
    testProvider,
    selectProvider,
    getProviderSettings,
    schemas,
    schemaFor,
    loadProviderSchema,
    saveProviderSettings,
    validateProviderSettings,
    drafts,
    draftFor,
    setDraft,
    clearDraft,
    watchCatalogReloads,
    closeCatalogReloads,
  }
})
