const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// Isolated static ESM loader: imports are injected; no configured app or network.
function load(name, imports = {}, globals = {}) {
  const source = readFileSync(join(__dirname, name), 'utf8');
  const names = [...source.matchAll(/export (?:async )?(?:function|const) (\w+)/g)].map((match) => match[1]);
  const code = source.replace(/^import .*;\r?\n/gm, '').replace(/\bexport (?=(?:async )?(?:function|const))/g, '');
  const context = vm.createContext({ URL, AbortController, TextEncoder, TextDecoder, setTimeout, clearTimeout, console, ...imports, ...globals });
  return vm.runInContext(`${code}\n;({${names.join(',')}})`, context, { filename: name });
}
const response = (data, status = 200) => ({ ok: status < 400, status, headers: { get: () => null }, text: async () => JSON.stringify(data) });
const tick = () => new Promise((resolve) => setImmediate(resolve));

class Element {
  constructor(tag, doc) { this.tagName = tag; this.ownerDocument = doc; this.children = []; this.listeners = {}; this.attributes = {}; this.value = ''; this.hidden = false; }
  append(...nodes) { nodes.forEach((node) => { node.parent = this; this.children.push(node); }); }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((node) => node !== this); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  removeEventListener(type, listener) { this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== listener); }
  dispatch(type, event = {}) { for (const listener of this.listeners[type] || []) listener({ preventDefault() {}, ...event }); }
  querySelectorAll(selector) {
    const matches = (node) => selector.split(',').some((item) => item === node.tagName || (item === 'input[type="password"]' && node.tagName === 'input' && node.type === 'password') || (item === 'a[href]' && node.tagName === 'a' && node.href));
    return this.children.flatMap((node) => [...(matches(node) ? [node] : []), ...node.querySelectorAll(selector)]);
  }
  get options() { return this.children; }
  focus() { this.ownerDocument.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}
function documentFixture() {
  const doc = { hidden: false, listeners: {}, createElement(tag) { return new Element(tag, doc); },
    addEventListener: Element.prototype.addEventListener, removeEventListener: Element.prototype.removeEventListener, dispatch: Element.prototype.dispatch };
  doc.body = doc.createElement('body'); doc.head = doc.createElement('head'); return doc;
}
function mapFixture() {
  const sources = new Map(), layers = new Map(), container = { hidden: false };
  return { sources, layers, container, removed: 0, stopped: 0, calls: [],
    getSource: (id) => sources.get(id), getLayer: (id) => layers.get(id),
    addSource(id, spec) { sources.set(id, { data: spec.data, setData(data) { this.data = data; } }); },
    addLayer(spec) { layers.set(spec.id, spec); }, removeLayer(id) { layers.delete(id); }, removeSource(id) { sources.delete(id); },
    on() {}, off() {}, setLayoutProperty() {}, getContainer: () => container, getCenter: () => ({ lng: 12, lat: 34 }),
    getZoom: () => 7, getBearing: () => 10, getPitch: () => 20, stop() { this.stopped++; }, resize() {}, triggerRepaint() {},
    jumpTo(target) { this.calls.push(target); }, remove() { this.removed++; },
  };
}

test('service client uses revision, session CSRF and write-only credential bodies without persistence', async () => {
  const calls = []; let revision = 1;
  const { createServiceClient } = load('service-client.js', { API_BASE_URL: 'http://127.0.0.1:8787' }, { localStorage: { setItem() { assert.fail('Browser credential persistence'); } } });
  const client = createServiceClient({ fetch: async (url, options) => {
    calls.push({ url, ...options });
    if (options.method === 'GET') return response({ revision, csrfToken: 'session-token', services: [] });
    assert.equal(JSON.parse(options.body).revision, revision); revision++; return response({ revision });
  } });
  await client.settings();
  await Promise.all([client.replaceCredentials('weather.basic', { client_secret: 'write-only' }), client.update('weather.basic', { enabled: false })]);
  const writes = calls.filter((call) => call.method !== 'GET');
  assert.equal(writes.length, 2);
  for (const write of writes) { assert.equal(write.headers['X-Meridian-CSRF'], 'session-token'); assert.equal(write.credentials, 'include'); assert.equal(write.cache, 'no-store'); }
  assert.match(writes[0].url, /weather.basic\/credentials$/);
  assert.equal(JSON.parse(writes[0].body).credentials.client_secret, 'write-only');
  assert.ok(!JSON.stringify(client.snapshot).includes('write-only'));
});

test('client rejects conflicts and oversized responses without echoing credential-bearing errors', async () => {
  const { createServiceClient } = load('service-client.js', { API_BASE_URL: 'http://localhost' });
  for (const apiBase of ['https://example.com', 'http://localhost@evil.test', 'http://127.0.0.1/?token=secret']) assert.throws(() => createServiceClient({ apiBase }), /loopback/);
  const client = createServiceClient({ fetch: async () => response({ secret: 'sensitive' }, 409) });
  await assert.rejects(client.settings(), /changed elsewhere/);
  const bounded = createServiceClient({ maxBytes: 3, fetch: async () => response({ large: 'payload' }) });
  await assert.rejects(bounded.catalogue(), /size limit/);
});

test('provider query sends session CSRF without settings revision and explicit test preserves query', async () => {
  const calls = [];
  const { createServiceClient } = load('service-client.js', { API_BASE_URL: 'http://127.0.0.1:8787' });
  const client = createServiceClient({ fetch: async (url, options) => {
    calls.push({ url, ...options });
    return response(options.method === 'GET' ? { revision: 3, csrfToken: 'bound-token', services: [] } : {});
  } });
  await client.query('noaa.nws', { latitude: 40, longitude: -74 });
  const query = calls.find((call) => call.url.endsWith('/query'));
  assert.equal(query.headers['X-Meridian-CSRF'], 'bound-token');
  assert.deepEqual(JSON.parse(query.body), { latitude: 40, longitude: -74 });
  await client.test('noaa.nws', { latitude: 40, longitude: -74 });
  const probe = calls.find((call) => call.url.endsWith('/test'));
  assert.deepEqual(JSON.parse(probe.body), { query: { latitude: 40, longitude: -74 }, revision: 3 });
  await client.submitJob('osm.extracts', { operation: 'import_geojson', source_id: 'reviewed', bbox: [1, 1, 2, 2] });
  await client.cancelJob('osm.extracts', 'abc123');
  const jobCalls = calls.filter((call) => call.url.includes('/jobs'));
  assert.equal(jobCalls.length, 2);
  assert.ok(jobCalls.every((call) => call.headers['X-Meridian-CSRF'] === 'bound-token'));
  assert.ok(jobCalls.every((call) => !Object.hasOwn(JSON.parse(call.body), 'revision')));
});

test('bounded streaming response cancels reader on overflow and releases lock', async () => {
  let cancelled = false, released = false;
  const { createServiceClient } = load('service-client.js', { API_BASE_URL: 'http://localhost' });
  const client = createServiceClient({ maxBytes: 3, fetch: async () => ({ ok: true, headers: { get: () => null }, body: { getReader: () => ({
    read: async () => ({ done: false, value: new Uint8Array(4) }), cancel: async () => { cancelled = true; }, releaseLock: () => { released = true; },
  }) } }) });
  await assert.rejects(client.catalogue(), /size limit/); assert.equal(cancelled, true); assert.equal(released, true);
});

test('failed Settings refresh retains last authoritative snapshot without a disabling callback', async () => {
  const doc = documentFixture();
  const snapshot = { revision: 4, services: [{ id: 'openfreemap.public', effective_enabled: true }] };
  let callbacks = 0;
  const client = { snapshot, catalogue: async () => { throw new Error('offline'); }, settings: async () => snapshot };
  const { initServiceSettings } = load('service-settings.js', { createServiceClient: () => client });
  const ui = initServiceSettings({ mount: doc.body, client, onChange: () => { callbacks++; } });
  assert.equal(await ui.refresh(), snapshot);
  assert.equal(callbacks, 0);
  ui.destroy();
});

test('live sources do not poll at startup; hidden tabs and immediate disable abort and clear data', async () => {
  const doc = documentFixture(), map = mapFixture(); let notify, calls = 0, signal;
  const client = { snapshot: { services: [{ id: 'aircraft', effective_enabled: true }] }, subscribe(fn) { notify = fn; return () => {}; },
    query: async (id, query, options) => { calls++; signal = options.signal; return { provider_id: id, state: 'fresh', features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [1, 2] }, properties: {} }] }; } };
  const { createLiveLayers } = load('live-layers.js');
  const live = createLiveLayers({ map, client, document: doc }); assert.equal(calls, 0);
  live.show('aircraft', { query: { bbox: [0, 0, 2, 3] } }); await tick(); assert.equal(calls, 1);
  assert.equal([...map.sources.values()][0].data.features.length, 1);
  doc.hidden = true; doc.dispatch('visibilitychange'); assert.equal([...map.sources.values()][0].data.features.length, 0);
  doc.hidden = false; doc.dispatch('visibilitychange'); await tick(); assert.equal(calls, 2);
  notify({ type: 'invalidate', id: 'aircraft' }); assert.equal([...map.sources.values()][0].data.features.length, 0);
  live.refresh(); await tick(); assert.equal(calls, 2);
  live.destroy(); assert.equal(map.sources.size, 0); assert.equal(map.removed, 0);
});

test('late live responses cannot resurrect hidden or disabled layers', async () => {
  const map = mapFixture(), doc = documentFixture(); let finish, requestSignal;
  const client = { snapshot: { services: [{ id: 'aircraft', effective_enabled: true }] }, subscribe: () => () => {},
    query(id, query, { signal }) { requestSignal = signal; return new Promise((resolve) => { finish = resolve; }); } };
  const { createLiveLayers } = load('live-layers.js'); const live = createLiveLayers({ map, client, document: doc });
  live.show('aircraft', { query: {} }); live.hide('aircraft'); assert.equal(requestSignal.aborted, true);
  finish({ data: { type: 'FeatureCollection', features: [{ id: 1 }] } }); await tick();
  assert.equal([...map.sources.values()][0].data.features.length, 0); live.destroy();
});

test('provenance popup uses text nodes and reports unknown instead of invented timestamps', () => {
  const doc = documentFixture(); const { provenanceContent } = load('live-layers.js');
  const popup = provenanceContent({ id: '<img onerror=alert(1)>' }, { provider_id: 'celestrak.gp', partial: true }, doc);
  const text = popup.children.map((node) => node.textContent).join('\n');
  assert.match(text, /<img onerror/); assert.match(text, /Observation: Unknown/); assert.match(text, /Partial/);
  assert.ok(popup.children.every((node) => node.tagName === 'p'));
});

test('renderer loads lazily, preserves original map, tears down globe and checks capabilities', async () => {
  const map = mapFixture(), container = { hidden: false }; let loads = 0, destroyed = 0; const active = [];
  const { createRendererController } = load('renderer-controller.js', { loadCesium: () => {}, createCesiumView: () => {}, mapCameraTarget: () => ({ longitude: 12, latitude: 34, zoom: 7 }) });
  const controller = createRendererController({ map, container, liveLayers: { setActive: (value) => active.push(value) },
    loadCesium: async () => { loads++; return {}; }, createView: () => ({ getTarget: () => ({ longitude: 5, latitude: 6, zoom: 4, pitch: 0, bearing: 0 }), destroy: () => destroyed++ }) });
  assert.equal(loads, 0); await controller.switchTo('cesium'); assert.equal(loads, 1); assert.equal(map.container.hidden, true);
  assert.equal(controller.hasCapability('globe'), true); assert.throws(() => controller.assertCapability('undo'), /Switch to MapLibre/);
  await controller.switchTo('maplibre'); assert.equal(destroyed, 1); assert.equal(map.container.hidden, false); assert.equal(map.removed, 0);
  assert.deepEqual(Array.from(map.calls[0].center), [5, 6]); assert.deepEqual(active, [false, true]); controller.destroy();
});

test('renderer cancels pending entry and recovers construction failure', async () => {
  const map = mapFixture(); let resolve, creates = 0;
  const { createRendererController } = load('renderer-controller.js', { loadCesium: () => {}, createCesiumView: () => {}, mapCameraTarget: () => ({}) });
  const controller = createRendererController({ map, container: {}, loadCesium: () => new Promise((done) => { resolve = done; }), createView: () => { creates++; } });
  const entering = controller.switchTo('cesium'); await controller.switchTo('maplibre'); resolve({}); await entering; assert.equal(creates, 0);
  const failing = createRendererController({ map, container: {}, loadCesium: async () => ({}), createView: () => { throw new Error('WebGL'); } });
  await assert.rejects(failing.switchTo('cesium'), /WebGL/); assert.equal(map.container.hidden, false); assert.equal(failing.renderer, 'maplibre');
});

test('settings dialog is labelled, schema-specific write-only, explicit quota test, and restores focus', async () => {
  const doc = documentFixture(), opener = doc.createElement('button'); opener.focus(); let credentialValues, tests = 0;
  const snapshot = { services: [{ id: 'sample.oauth', state: 'needs_credentials', credentials: { configured: true, source: 'environment' }, reasons: ['Setup required'] }] };
  const client = { snapshot, catalogue: async () => ({ services: [{ id: 'sample.oauth', name: '<unsafe>', category: 'Weather', auth_fields: ['client_id', 'client_secret'], limits: { daily_requests: 5 }, acknowledgements: ['billing'] }] }), settings: async () => snapshot,
    replaceCredentials: async (id, values) => { credentialValues = values; }, test: async () => { tests++; }, update: async () => {}, deleteCredentials: async () => {} };
  const { initServiceSettings } = load('service-settings.js', { createServiceClient: () => client });
  let changed;
  const ui = initServiceSettings({ mount: doc.body, client, onChange: (value) => { changed = value; } });
  assert.equal(await ui.open(), snapshot);
  assert.equal(changed, snapshot);
  assert.equal(ui.dialog.open, true); assert.equal(ui.dialog.attributes['aria-labelledby'], 'service-settings-title');
  const passwords = ui.dialog.querySelectorAll('input[type="password"]'); assert.equal(passwords.length, 2); assert.ok(passwords.every((input) => input.value === ''));
  passwords[1].value = 'incomplete-secret'; passwords[1].parent.parent.parent.dispatch('submit'); await tick();
  assert.equal(credentialValues, undefined); assert.ok(passwords.every((input) => input.value === ''));
  passwords[0].value = 'new-client'; passwords[1].value = 'new-secret'; passwords[1].parent.parent.parent.dispatch('submit'); assert.equal(passwords[1].value, ''); await tick();
  assert.equal(credentialValues.client_secret, 'new-secret'); assert.equal(tests, 0);
  assert.ok(ui.dialog.querySelectorAll('button').some((button) => /consume provider quota/.test(button.textContent)));
  ui.dialog.dispatch('cancel'); assert.equal(ui.dialog.open, false); assert.equal(doc.activeElement, opener); ui.destroy();
});

test('settings master/detail lists the complete catalogue and defaults to a free available service', async () => {
  const doc = documentFixture();
  const products = Array.from({ length: 151 }, (_, index) => ({ id: `service.${index}`, name: `Service ${index}`, category: index % 2 ? 'Weather' : 'Maps', auth_fields: index === 0 ? ['token'] : [] }));
  const snapshot = { services: products.map((product, index) => ({ id: product.id, state: index === 1 ? 'available' : 'needs_setup', effective_enabled: index === 1 })) };
  const client = { snapshot, catalogue: async () => ({ services: products }), settings: async () => snapshot };
  const { initServiceSettings } = load('service-settings.js', { createServiceClient: () => client });
  const ui = initServiceSettings({ mount: doc.body, client, presentation: 'page' }); await ui.refresh();
  const rows = () => ui.dialog.querySelectorAll('button').filter((node) => node.attributes['data-service-id']);
  assert.equal(ui.dialog.tagName, 'section'); assert.equal(rows().length, 151);
  assert.equal(rows().find((node) => node.attributes['aria-pressed'] === 'true').attributes['data-service-id'], 'service.1');
  assert.equal(ui.dialog.querySelectorAll('article').length, 1); assert.equal(ui.dialog.querySelectorAll('form').length, 1);
  await ui.open('service.5');
  assert.equal(rows().find((node) => node.attributes['aria-pressed'] === 'true').attributes['data-service-id'], 'service.5');
  rows()[0].dispatch('click');
  const secret = ui.dialog.querySelectorAll('input[type="password"]')[0]; secret.value = 'do-not-retain';
  rows()[1].dispatch('click'); assert.equal(secret.value, '');
  const search = ui.dialog.querySelectorAll('input').find((node) => node.type === 'search'); search.value = 'Service 150'; search.dispatch('input'); assert.equal(rows().length, 1);
  search.value = 'no matches'; search.dispatch('input'); assert.equal(rows().length, 0);
  ui.close(); assert.equal(ui.dialog.hidden, true); await ui.open(); assert.equal(ui.dialog.hidden, false); assert.equal(ui.dialog.open, undefined); ui.destroy();
});

test('permission-blocked enablement is disabled and omitted from updates even if checked programmatically', async () => {
  const doc = documentFixture(); let patch;
  const snapshot = { services: [{ id: 'blocked', state: 'permission_blocked', requested_enabled: false }] };
  const client = { snapshot, catalogue: async () => ({ services: [{ id: 'blocked', category: 'Maps', limits: { daily_requests: 10 } }] }), settings: async () => snapshot, update: async (id, changes) => { patch = changes; } };
  const { initServiceSettings } = load('service-settings.js', { createServiceClient: () => client });
  const ui = initServiceSettings({ mount: doc.body, client }); await ui.open();
  const checkbox = ui.dialog.querySelectorAll('input').find((node) => node.type === 'checkbox'); assert.equal(checkbox.disabled, true);
  checkbox.checked = true; ui.dialog.querySelectorAll('form')[0].dispatch('submit'); await tick();
  assert.equal(Object.hasOwn(patch, 'enabled'), false); assert.equal(patch.limits.daily_requests, 10); ui.destroy();
});

test('connection test has a human location preset, validates coordinates, and keeps JSON optional', async () => {
  const doc = documentFixture(); let query, tests = 0;
  const snapshot = { services: [{ id: 'weather', state: 'available', effective_enabled: true }] };
  const client = { snapshot, catalogue: async () => ({ services: [{ id: 'weather', category: 'Weather' }] }), settings: async () => snapshot, test: async (id, value) => { query = value; tests++; } };
  const { initServiceSettings } = load('service-settings.js', { createServiceClient: () => client });
  const ui = initServiceSettings({ mount: doc.body, client }); await ui.open();
  const probe = () => ui.dialog.querySelectorAll('button').find((node) => /may consume provider quota/.test(node.textContent));
  const latitude = ui.dialog.querySelectorAll('input').find((node) => node.parent.children[0].textContent === 'Latitude');
  latitude.value = '100'; probe().dispatch('click'); await tick(); assert.equal(tests, 0);
  latitude.value = '40'; probe().dispatch('click'); await tick();
  assert.equal(tests, 1); assert.equal(query.latitude, 40); assert.equal(query.longitude, -74.006); assert.equal(query.limit, 5);
  assert.equal(ui.dialog.querySelectorAll('textarea')[0].value, ''); ui.destroy();
});

test('page refresh failure retains loaded controls and offers the actual backend Settings origin', async () => {
  const doc = documentFixture(); let offline = false, changes = 0;
  const snapshot = { services: [{ id: 'available', state: 'available', effective_enabled: true }] };
  const client = { apiOrigin: 'http://127.0.0.1:8787', snapshot, catalogue: async () => { if (offline) throw new Error('offline'); return { services: [{ id: 'available' }] }; }, settings: async () => snapshot };
  const { initServiceSettings } = load('service-settings.js', { createServiceClient: () => client });
  const ui = initServiceSettings({ mount: doc.body, client, presentation: 'page', onChange: () => { changes++; } }); await ui.refresh(); offline = true;
  assert.equal(await ui.refresh(), snapshot); assert.equal(changes, 1);
  assert.equal(ui.dialog.querySelectorAll('button').filter((node) => node.attributes['data-service-id']).length, 1);
  const link = ui.dialog.querySelectorAll('a[href]').find((node) => node.textContent === 'Open backend Settings');
  assert.equal(link.href, 'http://127.0.0.1:8787/settings.html'); assert.equal(link.parent.hidden, false); ui.destroy();
});

test('Cesium assets load only on request and use one pinned JS/CSS/assets release', async () => {
  const doc = documentFixture(), win = {};
  const { loadCesium, CESIUM_BASE_URL } = load('cesium-view.js');
  assert.equal(doc.head.children.length, 0);
  const pending = loadCesium({ document: doc, window: win });
  const [css, script] = doc.head.children;
  assert.ok(css.href.startsWith(CESIUM_BASE_URL)); assert.ok(script.src.startsWith(CESIUM_BASE_URL)); assert.equal(win.CESIUM_BASE_URL, CESIUM_BASE_URL);
  assert.match(CESIUM_BASE_URL, /cesium@1\.123\.0/);
  win.Cesium = { Viewer() {} }; css.onload(); script.onload(); assert.equal(await pending, win.Cesium);
});

test('Cesium ellipsoid view has no implicit imagery or ion and tears down viewer', () => {
  const doc = documentFixture(), container = doc.createElement('div'); let options, destroyed = 0, removedImagery = 0;
  const canvas = doc.createElement('canvas');
  const Cesium = { Viewer: function (node, config) {
    options = config; this.imageryLayers = { removeAll: () => removedImagery++ }; this.scene = { canvas, globe: {}, requestRender() {} };
    this.clock = {}; this.camera = { setView() {}, pickEllipsoid: () => null }; this.destroy = () => destroyed++;
  }, EllipsoidTerrainProvider: function () {}, Cartesian3: { fromDegrees: (...values) => values }, Cartesian2: function () {}, Math: { toRadians: (value) => value * Math.PI / 180 } };
  const { createCesiumView } = load('cesium-view.js', { createCesiumProducts: () => ({ destroy() {} }) });
  const target = { longitude: 12, latitude: 34, zoom: 7, bearing: 0, pitch: 0 };
  const view = createCesiumView({ Cesium, container, target });
  assert.equal(options.baseLayer, false); assert.ok(options.terrainProvider instanceof Cesium.EllipsoidTerrainProvider);
  assert.equal(options.requestRenderMode, true); assert.equal(removedImagery, 1); assert.equal(view.viewer.clock.shouldAnimate, false);
  assert.equal(view.getTarget().latitude, 34); view.destroy(); view.destroy(); assert.equal(destroyed, 1);
});
