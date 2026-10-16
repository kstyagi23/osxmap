const assert = require('node:assert/strict');
const test = require('node:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

const ION = 'cesium.ion_community';
const GOOGLE = 'google.photorealistic_3d';
const ROOT = 'https://tile.googleapis.com/v1/3dtiles/root.json';
let createCesiumProducts;
test.before(async () => {
  const source = readFileSync(join(__dirname, 'cesium-products.js'), 'utf8');
  ({ createCesiumProducts } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`));
});
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };

function fixture(t, overrides = {}) {
  const calls = [], primitives = new Set(), credits = new Set(), renders = new Set(), subscriptions = new Set();
  const tilesets = [];
  function tileset() {
    const value = { destroyed: 0, totalMemoryUsageInBytes: 0, isDestroyed() { return this.destroyed > 0; }, destroy() { this.destroyed++; } };
    tilesets.push(value); return value;
  }
  const Cesium = {
    Ion: { defaultAccessToken: 'untouched-default' },
    Credit: class { constructor(html, onScreen) { this.html = html; this.onScreen = onScreen; } },
    Resource: class { constructor(options) { Object.assign(this, options); } },
    Cesium3DTileset: {
      async fromIonAssetId(asset, options) { calls.push(['ion', asset, options]); return tileset(); },
      async fromUrl(resource, options) { calls.push(['google', resource, options]); return tileset(); },
    },
  };
  const viewer = { scene: {
    primitives: { add(value) { primitives.add(value); }, remove(value) { primitives.delete(value); value.destroy(); } },
    frameState: { creditDisplay: { addStaticCredit(value) { credits.add(value); }, removeStaticCredit(value) { credits.delete(value); } } },
    postRender: { addEventListener(callback) { renders.add(callback); return () => renders.delete(callback); } },
    requestRender() {},
  }, camera: new Proxy({}, { get() { throw new Error('Camera must not be accessed.'); } }) };
  const ready = () => ({ services: [ION, GOOGLE].map((id) => ({ id, state: 'ready', effective_enabled: true })) });
  const client = {
    async settings(options) { calls.push(['settings', options]); return ready(); },
    async browserToken(id, scope, options) {
      calls.push(['token', id, scope, options]);
      return { id, state: 'ready', browser_safe: true, token: 'short-lived.fixture',
        expires_at: new Date(Date.now() + 60000).toISOString(), scopes: scope.scopes,
        ...(id === ION ? { asset_id: scope.asset_id } : { endpoint: scope.endpoint }), attribution: 'Licensed <asset> & provider' };
    },
    subscribe(callback) { subscriptions.add(callback); return () => subscriptions.delete(callback); },
  };
  const confirmDisclosure = async (descriptor) => { calls.push(['consent', descriptor]); return true; };
  const api = createCesiumProducts({ Cesium, viewer, client, confirmDisclosure, ...overrides });
  t.after(() => api.destroy());
  return { api, calls, client, Cesium, viewer, primitives, credits, renders, subscriptions, tilesets, tileset, ready,
    emit(event) { for (const callback of subscriptions) callback(event); }, render() { for (const callback of renders) callback(); } };
}

test('import and construction do not load dependencies or call providers', (t) => {
  const f = fixture(t); assert.deepEqual(f.calls, []); assert.equal(f.primitives.size, 0);
});

test('ion requires backend then exact disclosure then scoped browser token, and preserves credits', async (t) => {
  const f = fixture(t);
  const status = await f.api.enable(ION, { assetId: 123, maximumScreenSpaceError: 0 });
  assert.deepEqual(status, { id: ION, state: 'active', active: true, reasons: [] });
  assert.deepEqual(f.calls.map((call) => call[0]), ['settings', 'consent', 'token', 'ion']);
  assert.equal(f.calls[0][1].renderer, 'cesium');
  const disclosure = f.calls[1][1];
  assert.equal(disclosure.id, ION); assert.equal(disclosure.asset_id, 123);
  assert.equal(disclosure.browserCredentialDisclosure, true); assert.equal(disclosure.queryCredentials, true);
  assert.equal(disclosure.persistentStorage, false); assert.equal(disclosure.exportAllowed, false);
  assert.deepEqual(f.calls[2][2], { renderer: 'cesium', scopes: ['assets:read'], asset_id: 123 });
  const options = f.calls[3][2];
  assert.equal(options.accessToken, 'short-lived.fixture'); assert.equal(options.maximumScreenSpaceError, 16);
  assert.equal(options.maximumCacheOverflowBytes, 0); assert.equal(options.showCreditsOnScreen, true);
  assert.equal(options.preloadWhenHidden, false); assert.equal(options.preloadFlightDestinations, false);
  assert.equal(f.Cesium.Ion.defaultAccessToken, 'untouched-default');
  assert.equal([...f.credits][0].html, 'Licensed &lt;asset&gt; &amp; provider');
  assert.equal([...f.credits][0].onScreen, true);
  assert(!JSON.stringify(status).includes('short-lived'));
});

test('Google uses only fixed root Resource query capability and Google exact scope', async (t) => {
  const f = fixture(t); assert.equal((await f.api.enable(GOOGLE)).state, 'active');
  assert.deepEqual(f.calls[2][2], { renderer: 'cesium', scopes: ['3d_tiles:read'], endpoint: ROOT });
  assert.equal(f.calls[3][1].url, ROOT);
  assert.deepEqual(f.calls[3][1].queryParameters, { key: 'short-lived.fixture' });
  assert.equal(f.calls[3][2].accessToken, undefined);
});

test('Google broker cannot redirect the capability to another URL or product scope', async (t) => {
  for (const patch of [{ endpoint: 'http://localhost/private' }, { endpoint: `${ROOT}?key=saved` }, { scopes: ['map_tiles:read'] }]) {
    const f = fixture(t), original = f.client.browserToken;
    f.client.browserToken = async (...args) => ({ ...await original(...args), ...patch });
    assert.equal((await f.api.enable(GOOGLE)).state, 'needs_setup');
    assert(!f.calls.some((call) => call[0] === 'google'));
  }
});

test('invented aliases, ArcGIS, arbitrary URLs, assets and credentials fail without calls', async (t) => {
  const f = fixture(t);
  for (const id of ['cesium.ion', 'google.map_tiles', 'arcgis.basemaps', 'esri.world_imagery']) {
    assert.equal((await f.api.enable(id)).state, 'permission_blocked');
  }
  for (const config of [{}, { assetId: -1 }, { assetId: '123' }, { assetId: 1.1 }, { assetId: Number.MAX_SAFE_INTEGER + 1 },
    { assetId: 1, url: 'http://localhost/private' }, { assetId: 1, accessToken: 'durable' }, { assetId: 1, maximumScreenSpaceError: Infinity }]) {
    assert.equal((await f.api.enable(ION, config)).state, 'needs_setup');
  }
  for (const config of [{ assetId: 1 }, { endpoint: ROOT }, { url: ROOT }, { token: 'saved' }]) {
    assert.equal((await f.api.enable(GOOGLE, config)).state, 'needs_setup');
  }
  assert.deepEqual(f.calls, []);
});

for (const state of ['needs_setup', 'disabled', 'needs_credentials', 'permission_blocked', 'incompatible_renderer', 'active']) {
  test(`backend ${state} never grants provider access`, async (t) => {
    const f = fixture(t); f.client.settings = async () => ({ services: [{ id: ION, state, effective_enabled: true }] });
    const response = await f.api.enable(ION, { assetId: 1 });
    assert.equal(response.active, false); assert(response.reasons.length); assert.deepEqual(f.calls, []);
  });
}

test('missing token broker returns needs_setup without disclosure or query fallback', async (t) => {
  const f = fixture(t); delete f.client.browserToken;
  f.client.query = () => { throw new Error('No durable credential route.'); };
  assert.equal((await f.api.enable(ION, { assetId: 1 })).state, 'needs_setup');
  assert.deepEqual(f.calls.map((call) => call[0]), ['settings']);
});

test('real client-style settings emission preserves the backend block reason', async (t) => {
  const f = fixture(t);
  f.client.settings = async () => {
    const settings = { services: [{ id: ION, state: 'incompatible_renderer', effective_enabled: false }] };
    f.emit({ type: 'settings', settings }); return settings;
  };
  assert.equal((await f.api.enable(ION, { assetId: 1 })).state, 'incompatible_renderer');
  assert.deepEqual(f.calls, []);
});

test('consent is strict explicit true and cannot be replaced by configuration', async (t) => {
  for (const consent of [undefined, async () => false, async () => 'true']) {
    const f = fixture(t, { confirmDisclosure: consent });
    assert.equal((await f.api.enable(GOOGLE)).state, 'disabled');
    assert.deepEqual(f.calls.map((call) => call[0]), ['settings']);
  }
});

test('broker rejects durable, mis-scoped, missing attribution or surplus credentials', async (t) => {
  for (const patch of [{ browser_safe: false }, { expires_at: new Date(Date.now() + 3600000).toISOString() },
    { expires_at: new Date(0).toISOString() }, { scopes: ['assets:write'] }, { scopes: ['assets:read', 'profile:read'] },
    { asset_id: 2 }, { id: GOOGLE }, { token: 'key&url=leak' }, { attribution: '' }, { server_secret: 'durable' }]) {
    const f = fixture(t); const token = f.client.browserToken;
    f.client.browserToken = async (...args) => ({ ...await token(...args), ...patch });
    const result = await f.api.enable(ION, { assetId: 1 });
    assert.equal(result.state, 'needs_setup'); assert.equal(f.primitives.size, 0);
    assert(!f.calls.some((call) => call[0] === 'ion'));
  }
});

test('disable aborts pending broker and late provider results destroy without attachment', async (t) => {
  const f = fixture(t), load = deferred();
  f.Cesium.Cesium3DTileset.fromIonAssetId = async () => load.promise;
  const pending = f.api.enable(ION, { assetId: 1 });
  while (!f.calls.some((call) => call[0] === 'token')) await Promise.resolve();
  await Promise.resolve(); await Promise.resolve();
  f.api.disable(ION); const value = f.tileset(); load.resolve(value);
  assert.equal((await pending).state, 'disabled'); assert.equal(value.destroyed, 1);
  assert.equal(f.primitives.size, 0); assert.equal(f.credits.size, 0);
  assert.equal(f.calls.find((call) => call[0] === 'token')[3].signal.aborted, true);
});

test('invalidation during consent cancels before requesting browser credentials', async (t) => {
  const consent = deferred(), f = fixture(t, { confirmDisclosure: () => consent.promise });
  const pending = f.api.enable(GOOGLE); await Promise.resolve(); await Promise.resolve();
  f.emit({ type: 'invalidate', id: GOOGLE }); consent.resolve(true);
  assert.equal((await pending).state, 'disabled');
  assert.deepEqual(f.calls.map((call) => call[0]), ['settings']);
});

test('late browser token after cancellation never invokes a tileset provider', async (t) => {
  const f = fixture(t), issued = deferred(), original = f.client.browserToken;
  f.client.browserToken = async (...args) => { const response = await original(...args); await issued.promise; return response; };
  const pending = f.api.enable(ION, { assetId: 1 });
  while (!f.calls.some((call) => call[0] === 'token')) await Promise.resolve();
  f.api.destroy(); issued.resolve();
  assert.equal((await pending).state, 'disabled');
  assert(!f.calls.some((call) => call[0] === 'ion'));
});

test('re-enabling the same product destroys replaced tileset and pending old results', async (t) => {
  const f = fixture(t); await f.api.enable(ION, { assetId: 1 });
  await f.api.enable(ION, { assetId: 2 });
  assert.equal(f.tilesets[0].destroyed, 1); assert.equal(f.primitives.size, 1); assert.equal(f.credits.size, 1);
  const late = deferred(); f.Cesium.Cesium3DTileset.fromIonAssetId = () => late.promise;
  const pending = f.api.enable(ION, { assetId: 3 });
  while (f.calls.filter((call) => call[0] === 'token').length < 3) await Promise.resolve();
  await Promise.resolve(); await Promise.resolve();
  f.Cesium.Cesium3DTileset.fromIonAssetId = async () => f.tileset();
  await f.api.enable(ION, { assetId: 4 });
  const old = f.tileset(); late.resolve(old);
  assert.equal((await pending).state, 'disabled'); assert.equal(old.destroyed, 1);
  assert.equal(f.primitives.size, 1); assert.equal(f.credits.size, 1);
});

test('bounded options, product count and actual GPU usage dispose resources', async (t) => {
  const f = fixture(t, { policy: { maxProducts: 1, maxGpuBytes: 8 * 1024 * 1024, minimumScreenSpaceError: 32 } });
  await f.api.enable(ION, { assetId: 1, maximumScreenSpaceError: 2 });
  assert.equal(f.calls[3][2].cacheBytes, 8 * 1024 * 1024); assert.equal(f.calls[3][2].maximumScreenSpaceError, 32);
  assert.equal((await f.api.enable(GOOGLE)).state, 'needs_setup');
  f.tilesets[0].totalMemoryUsageInBytes = 9 * 1024 * 1024; f.render();
  assert.equal(f.tilesets[0].destroyed, 1); assert.equal(f.primitives.size, 0);
  assert.equal(f.renders.size, 0); assert.equal(f.credits.size, 0);
});

test('settings revocation, repeated destroy, and provider failure cleanly redact errors', async (t) => {
  const f = fixture(t); await f.api.enable(GOOGLE);
  f.emit({ type: 'settings', settings: { services: [] } });
  assert.equal(f.tilesets[0].destroyed, 1); assert.equal(f.credits.size, 0);
  f.Cesium.Cesium3DTileset.fromUrl = async () => { throw new Error('private-token-in-url'); };
  const response = await f.api.enable(GOOGLE);
  assert.equal(response.state, 'needs_setup'); assert(!JSON.stringify(response).includes('private-token'));
  f.api.destroy(); f.api.destroy(); assert.equal(f.subscriptions.size, 0);
  assert.equal((await f.api.enable(GOOGLE)).state, 'disabled');
});

test('token expiration disposes active provider instead of silently refreshing', async (t) => {
  const f = fixture(t), original = f.client.browserToken;
  f.client.browserToken = async (...args) => ({ ...await original(...args), expires_at: new Date(Date.now() + 50).toISOString() });
  await f.api.enable(GOOGLE); await new Promise((resolve) => setTimeout(resolve, 80));
  assert.equal(f.primitives.size, 0); assert.equal(f.tilesets[0].destroyed, 1);
  assert.equal(f.calls.filter((call) => call[0] === 'token').length, 1);
});
