/**
 * Typed API client wrapping fetch.
 * All backend calls go through this module.
 */

const BASE_URL = ''

async function request(method, path, { body, params } = {}) {
  const url = new URL(path, window.location.origin)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, v)
    })
  }

  const opts = {
    method,
    headers: {},
  }

  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  const res = await fetch(`${BASE_URL}${url.pathname}${url.search}`, opts)

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${method} ${path} → ${res.status}: ${text}`)
  }

  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return res.json()
  }
  return res.text()
}

export const api = {
  get:    (path, opts) => request('GET', path, opts),
  post:   (path, opts) => request('POST', path, opts),
  put:    (path, opts) => request('PUT', path, opts),
  patch:  (path, opts) => request('PATCH', path, opts),
  delete: (path, opts) => request('DELETE', path, opts),
}
