import { API_BASE_URL } from './config.js';

// Credentials are write-only. This client owns no browser persistence or policy.
export function createServiceClient({ apiBase = API_BASE_URL, fetch: fetcher = globalThis.fetch, timeout = 20000, maxBytes = 4000000 } = {}) {
  const base = new URL(apiBase);
  const host = base.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (!['http:', 'https:'].includes(base.protocol) || !['localhost', '127.0.0.1', '::1'].includes(host) || base.username || base.password || base.search || base.hash || !['', '/'].includes(base.pathname)) {
    throw new Error('Service Settings require a loopback API origin.');
  }
  const listeners = new Set();
  let revision, csrfToken, snapshot, queue = Promise.resolve();
  const emit = (event) => { for (const listener of listeners) listener(event); };
  const path = (id) => `/api/settings/services/${encodeURIComponent(id)}`;
  async function request(route, { method = 'GET', body, signal, mutation = false, csrf = false } = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) abort();
    signal?.addEventListener('abort', abort, { once: true });
    const timer = setTimeout(abort, timeout);
    try {
      const headers = { Accept: 'application/json' };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (csrf) {
        if (!csrfToken) throw new Error('Load Settings before querying services.');
        headers['X-Meridian-CSRF'] = csrfToken;
      }
      if (mutation) {
        if (!csrfToken || revision === undefined) throw new Error('Load Settings before changing services.');
        headers['X-Meridian-CSRF'] = csrfToken;
        body = { ...body, revision };
      }
      const response = await fetcher(`${base.origin}${route}`, {
        method, headers, credentials: 'include', cache: 'no-store', signal: controller.signal,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      if (Number(response.headers?.get('content-length')) > maxBytes) throw new Error('Service response exceeds the local size limit.');
      let data;
      if (response.body?.getReader) {
        const reader = response.body.getReader();
        const chunks = []; let size = 0;
        try {
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > maxBytes) { await reader.cancel(); throw new Error('Service response exceeds the local size limit.'); }
            chunks.push(value);
          }
        } finally { reader.releaseLock(); }
        const bytes = new Uint8Array(size); let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
        data = size ? JSON.parse(new TextDecoder().decode(bytes)) : {};
      } else {
        const text = await response.text();
        if (new TextEncoder().encode(text).length > maxBytes) throw new Error('Service response exceeds the local size limit.');
        data = text ? JSON.parse(text) : {};
      }
      if (!response.ok) {
        // Do not echo upstream messages, which could contain credentials.
        const error = new Error(response.status === 409 ? 'Settings changed elsewhere. Reload before saving.' : `Service request failed (${response.status}).`);
        error.status = response.status;
        throw error;
      }
      return data;
    } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
  }
  async function settings({ signal } = {}) {
    const data = await request('/api/settings/services', { signal });
    revision = data.revision; csrfToken = data.csrfToken; snapshot = data;
    emit({ type: 'settings', settings: data });
    return data;
  }
  function mutate(id, suffix, method, body = {}) {
    if (body.enabled === false || suffix === '/credentials') emit({ type: 'invalidate', id });
    const work = queue.then(async () => {
      if (!csrfToken) await settings();
      const result = await request(`${path(id)}${suffix}`, { method, body, mutation: true });
      if (result.revision !== undefined) revision = result.revision;
      await settings();
      return result;
    });
    queue = work.catch(() => {});
    return work;
  }
  return {
    get apiOrigin() { return base.origin; },
    catalogue: (options) => request('/api/services', options), settings,
    update: (id, changes) => mutate(id, '', 'PUT', changes),
    replaceCredentials: (id, credentials) => mutate(id, '/credentials', 'PUT', { credentials }),
    deleteCredentials: (id) => mutate(id, '/credentials', 'DELETE'),
    test: (id, query) => mutate(id, '/test', 'POST', { query }),
    predictions: async (query, times, { signal } = {}) => {
      if (!csrfToken) await settings({ signal });
      return request('/api/services/celestrak.gp/predictions', { method: 'POST', body: { query, times }, signal, csrf: true });
    },
    submitJob: async (id, job) => {
      if (!csrfToken) await settings();
      return request(`/api/services/${encodeURIComponent(id)}/jobs`, { method: 'POST', body: job, csrf: true });
    },
    jobStatus: (id, jobId) => request(`/api/services/${encodeURIComponent(id)}/jobs/${encodeURIComponent(jobId)}`),
    cancelJob: async (id, jobId) => {
      if (!csrfToken) await settings();
      return request(`/api/services/${encodeURIComponent(id)}/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE', body: {}, csrf: true });
    },
    query: async (id, query, { signal } = {}) => {
      if (!csrfToken) await settings({ signal });
      return request(`/api/services/${encodeURIComponent(id)}/query`, { method: 'POST', body: query, signal, csrf: true });
    },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    get snapshot() { return snapshot; },
  };
}
