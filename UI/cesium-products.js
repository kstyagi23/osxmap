const ION = 'cesium.ion_community';
const GOOGLE = 'google.photorealistic_3d';
const GOOGLE_ROOT = 'https://tile.googleapis.com/v1/3dtiles/root.json';
const MB = 1024 * 1024;
const STATES = new Set(['disabled', 'needs_setup', 'needs_credentials', 'permission_blocked', 'incompatible_renderer']);

// Injected dependencies only: importing this module loads no SDK or provider.
// Browser credentials live only in the provider resource until disposal, never in
// settings, workspace exports, camera state, or history. The broker is optional.
export function createCesiumProducts({ Cesium, viewer, client, confirmDisclosure, policy = {} } = {}) {
  const entries = new Map();
  const cap = (value, fallback, minimum) => Number.isFinite(value) ? Math.max(minimum, Math.min(fallback, value)) : fallback;
  const maxProducts = Math.floor(cap(policy.maxProducts, 2, 1));
  const maxGpuBytes = cap(policy.maxGpuBytes, 128 * MB, MB);
  const cacheBytes = Math.floor(Math.min(cap(policy.maxCacheBytes, 64 * MB, MB), maxGpuBytes / maxProducts));
  const minimumError = Number.isFinite(policy.minimumScreenSpaceError) ? Math.max(16, Math.min(64, policy.minimumScreenSpaceError)) : 16;
  let disposed = false;
  const result = (id, state, reason) => ({ id, state, active: state === 'active', reasons: reason ? [reason] : [] });
  const current = (entry) => !disposed && entries.get(entry.id) === entry && !entry.controller.signal.aborted;
  function release(entry) {
    entry.controller.abort(); clearTimeout(entry.timer); entry.removeRender?.();
    if (entry.creditAdded) viewer.scene.frameState.creditDisplay.removeStaticCredit(entry.credit);
    if (entry.tileset) {
      viewer.scene.primitives.remove(entry.tileset);
      if (!entry.tileset.isDestroyed()) entry.tileset.destroy();
    }
    viewer?.scene?.requestRender?.();
  }
  function disable(id) {
    const entry = entries.get(id);
    if (entry) { entries.delete(id); release(entry); }
    return result(id, 'disabled', 'Product is disabled.');
  }
  const unsubscribe = client?.subscribe?.((event) => {
    for (const entry of entries.values()) {
      if (event.type === 'invalidate' && event.id === entry.id) disable(entry.id);
      if (event.type === 'settings') {
        const state = event.settings?.services?.find((item) => item.id === entry.id);
        if (state?.state !== 'ready' || state.effective_enabled !== true) {
          entry.blockedState = STATES.has(state?.state) ? state.state : 'needs_setup';
          disable(entry.id);
        }
      }
    }
  });
  async function enable(id, configuration = {}) {
    if (disposed) return result(id, 'disabled', 'Product adapter has been destroyed.');
    if (id !== ION && id !== GOOGLE) return result(id, 'permission_blocked', 'Unsupported exact licensed product.');
    if (!configuration || typeof configuration !== 'object' || Array.isArray(configuration) ||
        Object.keys(configuration).some((key) => !['assetId', 'maximumScreenSpaceError'].includes(key)) ||
        (id === ION ? !Number.isSafeInteger(configuration.assetId) || configuration.assetId <= 0 : configuration.assetId !== undefined) ||
        (configuration.maximumScreenSpaceError !== undefined && !Number.isFinite(configuration.maximumScreenSpaceError))) {
      return result(id, 'needs_setup', 'Use a fixed positive ion asset ID or the fixed Google 3D endpoint; URLs and credentials are not configuration.');
    }
    disable(id);
    if (entries.size >= maxProducts) return result(id, 'needs_setup', 'Product memory budget is already allocated.');
    const entry = { id, controller: new AbortController() }; entries.set(id, entry);
    const cancelled = () => result(id, entry.blockedState || 'disabled', entry.blockedState
      ? 'Backend has not authorized this exact product for Cesium.' : 'Product load was cancelled.');
    const stop = (state, reason) => { if (current(entry)) disable(id); return result(id, state, reason); };
    try {
      if (typeof client?.settings !== 'function') return stop('needs_setup', 'Authoritative backend settings are unavailable.');
      const snapshot = await client.settings({ renderer: 'cesium', signal: entry.controller.signal });
      if (!current(entry)) return cancelled();
      const state = snapshot?.services?.find((item) => item.id === id);
      if (state?.state !== 'ready' || state.effective_enabled !== true) {
        return stop(STATES.has(state?.state) ? state.state : 'needs_setup', 'Backend has not authorized this exact product for Cesium.');
      }
      if (typeof client.browserToken !== 'function') return stop('needs_setup', 'A reviewed short-lived browser-token broker is not configured.');
      const credits = viewer?.scene?.frameState?.creditDisplay;
      if (!Cesium?.Cesium3DTileset || !Cesium?.Credit || !viewer?.scene?.primitives ||
          !viewer.scene.postRender?.addEventListener || !credits?.addStaticCredit || !credits?.removeStaticCredit ||
          (id === ION ? !Cesium.Cesium3DTileset.fromIonAssetId : !Cesium.Resource || !Cesium.Cesium3DTileset.fromUrl)) {
        return stop('needs_setup', 'Cesium tileset, attribution, and memory lifecycle support is required.');
      }
      const scope = id === ION ? { scopes: ['assets:read'], asset_id: configuration.assetId } : { scopes: ['3d_tiles:read'], endpoint: GOOGLE_ROOT };
      const disclosure = Object.freeze({
        id, renderer: 'cesium', product: id === ION ? 'Cesium ion Community' : 'Google Photorealistic 3D Tiles',
        scopes: Object.freeze([...scope.scopes]), ...(id === ION ? { asset_id: scope.asset_id } : { endpoint: GOOGLE_ROOT }),
        browserCredentialDisclosure: true, queryCredentials: true, paidOrRestricted: true,
        persistentStorage: false, exportAllowed: false,
        reason: 'The short-lived credential is visible to this browser and provider requests, including query URLs. Exact product licensing, billing, attribution and browser restrictions apply.',
      });
      if (typeof confirmDisclosure !== 'function' || await confirmDisclosure(disclosure) !== true) {
        return stop('disabled', 'Explicit browser credential disclosure consent is required.');
      }
      if (!current(entry)) return cancelled();
      // Only the broker may issue a browser-safe capability; saved server keys
      // and client configuration are deliberately not fallback token sources.
      let credential = await client.browserToken(id, { renderer: 'cesium', ...scope }, { signal: entry.controller.signal });
      if (!current(entry)) { credential = null; return cancelled(); }
      if (credential?.state !== 'ready') {
        const blocked = STATES.has(credential?.state) ? credential.state : 'needs_setup';
        credential = null; return stop(blocked, 'Browser-token broker has not authorized this product.');
      }
      const expires = Date.parse(credential.expires_at), now = Date.now();
      if (credential.id !== id || credential.browser_safe !== true || typeof credential.token !== 'string' ||
          !/^[A-Za-z0-9._~-]{1,4096}$/.test(credential.token) || !Number.isFinite(expires) || expires <= now || expires > now + 15 * 60 * 1000 ||
          !Array.isArray(credential.scopes) || credential.scopes.length !== 1 || credential.scopes[0] !== scope.scopes[0] ||
          (id === ION ? credential.asset_id !== scope.asset_id : credential.endpoint !== GOOGLE_ROOT) ||
          typeof credential.attribution !== 'string' || !credential.attribution.trim() || credential.attribution.length > 4096 ||
          Object.keys(credential).some((key) => !['id', 'state', 'browser_safe', 'token', 'expires_at', 'scopes', 'asset_id', 'endpoint', 'attribution'].includes(key))) {
        credential = null; return stop('needs_setup', 'Broker must issue an expiring browser-safe token restricted to the exact product and resource, with attribution.');
      }
      const escaped = credential.attribution.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
      entry.credit = new Cesium.Credit(escaped, true);
      const options = { maximumScreenSpaceError: Math.max(minimumError,
        Math.min(64, configuration.maximumScreenSpaceError ?? 24)), cacheBytes, maximumCacheOverflowBytes: 0,
        showCreditsOnScreen: true, preloadWhenHidden: false, preloadFlightDestinations: false };
      const token = credential.token;
      credential = null;
      entry.timer = setTimeout(() => { if (current(entry)) disable(id); }, expires - now);
      const tileset = id === ION
        ? await Cesium.Cesium3DTileset.fromIonAssetId(scope.asset_id, { ...options, accessToken: token })
        : await Cesium.Cesium3DTileset.fromUrl(new Cesium.Resource({ url: GOOGLE_ROOT, queryParameters: { key: token } }), options);
      if (!current(entry) || Date.now() >= expires) {
        if (!tileset.isDestroyed()) tileset.destroy();
        if (current(entry)) disable(id);
        return cancelled();
      }
      entry.tileset = tileset;
      viewer.scene.primitives.add(tileset); credits.addStaticCredit(entry.credit); entry.creditAdded = true;
      entry.removeRender = viewer.scene.postRender.addEventListener(() => {
        let bytes = 0;
        for (const item of entries.values()) {
          const usage = item.tileset?.totalMemoryUsageInBytes ?? 0;
          if (!Number.isFinite(usage) || usage < 0) { disable(id); return; }
          bytes += usage;
        }
        if (bytes > maxGpuBytes) disable(id);
      });
      viewer.scene.requestRender();
      return result(id, 'active');
    } catch {
      if (!current(entry)) return cancelled();
      return stop('needs_setup', 'Product could not be loaded safely.');
    }
  }
  return { enable, disable, destroy() {
    if (disposed) return;
    disposed = true; unsubscribe?.();
    for (const id of entries.keys()) disable(id);
  } };
}
