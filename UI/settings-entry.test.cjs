const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');

function run(page = false) {
  const calls = [], listeners = new Map(), events = [];
  const mount = { replaceChildren() { calls.push('clear'); } };
  const client = { id: 'shared-client' };
  const settings = { client, open() { calls.push('open'); } };
  const window = { location: { hash: '' }, dispatchEvent(event) { events.push(event); } };
  const document = { readyState: 'complete', getElementById(id) {
    if (id === 'settings-page-content') return page ? mount : null;
    if (id === 'service-settings-open') return { addEventListener(type, callback) { listeners.set(type, callback); } };
  } };
  const source = readFileSync(join(__dirname, 'settings-entry.js'), 'utf8').replace(/^import .*;\r?\n/gm, '');
  let options;
  vm.runInNewContext(source, { window, document, createServiceClient: () => client,
    initServiceSettings(value) { options = value; return settings; },
    CustomEvent: class { constructor(type, values) { this.type = type; this.detail = values.detail; } } });
  return { calls, listeners, events, window, settings, options, mount, client };
}

test('dedicated Settings page initializes without map globals or external SDKs', () => {
  const fixture = run(true);
  assert.equal(fixture.options.presentation, 'page');
  assert.equal(fixture.options.mount, fixture.mount);
  assert.equal(fixture.options.client, fixture.client);
  assert.deepEqual(fixture.calls, ['clear', 'open']);
  const html = readFileSync(join(__dirname, 'settings.html'), 'utf8');
  assert.match(html, /settings-entry\.js/);
  assert.doesNotMatch(html, /maplibre|cesium|app\.js/);
});

test('map Settings launcher remains independently wired with no MapLibre or WebGL', () => {
  const fixture = run();
  assert.equal(fixture.window.MERIDIAN_SETTINGS, fixture.settings);
  fixture.listeners.get('click')();
  assert.deepEqual(fixture.calls, ['open']);
  const snapshot = { services: [{ id: 'openfreemap.public', effective_enabled: true }] };
  fixture.options.onChange(snapshot);
  assert.equal(fixture.window.MERIDIAN_SERVICE_STATE, snapshot);
  assert.equal(fixture.events[0].type, 'meridian:service-settings');
  assert.equal(fixture.events[0].detail, snapshot);
});

test('map startup is no longer delayed by a service settings request', () => {
  const source = readFileSync(join(__dirname, 'app.js'), 'utf8');
  const startup = source.slice(source.lastIndexOf("window.addEventListener('DOMContentLoaded'"));
  assert.doesNotMatch(startup, /await client\.settings\(/);
  assert.match(startup, /new CityExplorer\(\)/);
  assert.match(startup, /Service Settings remains available/);
  const html = readFileSync(join(__dirname, 'index.html'), 'utf8');
  assert.match(html, /href="\.\/settings\.html"/);
  assert.match(html, /id="live-layers-open"/);
  assert.ok(html.indexOf('settings-entry.js') < html.indexOf('src="./app.js'));
});

test('Settings page mobile shell is content-sized and toolbar actions stay above search', () => {
  const settingsCss = readFileSync(join(__dirname, 'service-settings.css'), 'utf8');
  assert.match(settingsCss, /\.service-settings\.ss-shell\.ss-page\s*\{[^}]*height:\s*auto;[^}]*overflow:\s*visible/);
  const mapCss = readFileSync(join(__dirname, 'styles.css'), 'utf8');
  assert.match(mapCss, /\.app-actions\s*\{[^}]*z-index:\s*30/);
  assert.match(mapCss, /\.floating-search\s*\{[^}]*z-index:\s*25/);
});
