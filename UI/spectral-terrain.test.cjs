const assert = require('node:assert/strict');
const test = require('node:test');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

let terrain;
test.before(async () => {
  const source = readFileSync(join(__dirname, 'spectral-terrain.js'), 'utf8');
  terrain = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
});

function globals(t, values) {
  for (const [key, value] of Object.entries(values)) {
    const old = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
    t.after(() => old ? Object.defineProperty(globalThis, key, old) : delete globalThis[key]);
  }
}

function fixture(t, { documentCanvas = false, size = 8 } = {}) {
  const state = { fetched: [], closed: 0, encoded: [], options: [] };
  class Canvas {
    getContext(type) {
      assert.equal(type, '2d');
      return {
        drawImage() {},
        getImageData: () => ({ data: new Uint8ClampedArray([128, 0, 0, 255, 133, 220, 0, 128]) }),
        putImageData: (pixels) => state.encoded.push([...pixels.data]),
      };
    }
    convertToBlob(options) {
      assert.equal(options.type, 'image/png');
      return Promise.resolve({ arrayBuffer: async () => new ArrayBuffer(size) });
    }
    toBlob(callback, type) {
      assert.equal(type, 'image/png');
      callback({ arrayBuffer: async () => new ArrayBuffer(size) });
    }
  }
  globals(t, {
    fetch: async (url, options) => { state.fetched.push({ url, options }); return { ok: true, blob: async () => new Blob() }; },
    createImageBitmap: async (blob, options) => { state.options.push(options); return { width: 2, height: 1, close: () => state.closed++ }; },
    OffscreenCanvas: documentCanvas ? undefined : Canvas,
    document: { createElement: (name) => { assert.equal(name, 'canvas'); const canvas = new Canvas(); canvas.convertToBlob = undefined; return canvas; } },
  });
  const library = { addProtocol(name, handler) { assert.equal(name, 'spectral'); state.handler = handler; state.registrations = (state.registrations || 0) + 1; } };
  state.url = terrain.registerSpectralTerrain(library);
  state.library = library;
  state.load = (tile = '0/0/0', controller = new AbortController()) => state.handler({ url: `spectral://terrain/${tile}` }, controller);
  return state;
}

test('Terrarium decoding includes negative, zero, fractional and high real elevations', () => {
  for (const [rgb, expected] of [[[0, 0, 0], -32768], [[126, 12, 0], -500], [[128, 0, 0], 0], [[128, 0, 128], .5], [[133, 220, 0], 1500], [[151, 112, 0], 6000], [[255, 255, 255], 32767.99609375]]) {
    assert.equal(terrain.decodeTerrarium(...rgb), expected);
  }
});

test('fixed palette thresholds map exactly, are immutable and clamp out-of-range elevations', () => {
  assert.deepEqual(terrain.palette.map((stop) => stop.elevation), [-500, 0, 250, 750, 1500, 2500, 4000, 6000]);
  assert(Object.isFrozen(terrain.palette));
  for (const stop of terrain.palette) {
    assert(Object.isFrozen(stop));
    assert(Object.isFrozen(stop.color));
    assert.deepEqual(terrain.elevationColor(stop.elevation), stop.color);
  }
  assert.deepEqual(terrain.elevationColor(-Infinity), [8, 42, 50]);
  assert.deepEqual(terrain.elevationColor(-32768), [8, 42, 50]);
  assert.deepEqual(terrain.elevationColor(Infinity), [224, 244, 243]);
  assert.deepEqual(terrain.elevationColor(9000), [224, 244, 243]);
  const color = terrain.elevationColor(0); color[0] = 255;
  assert.deepEqual(terrain.elevationColor(0), [18, 62, 68]);
  assert.throws(() => terrain.elevationColor(NaN), TypeError);
  assert.throws(() => terrain.elevationColor('750'), TypeError);
});

test('every interval interpolates continuously rather than selecting discrete bands', () => {
  for (let i = 1; i < terrain.palette.length; i++) {
    const low = terrain.palette[i - 1], high = terrain.palette[i];
    assert.deepEqual(terrain.elevationColor((low.elevation + high.elevation) / 2), low.color.map((value, j) => Math.round((value + high.color[j]) / 2)));
    assert.deepEqual(terrain.elevationColor(high.elevation - .0001), high.color);
    assert.deepEqual(terrain.elevationColor(low.elevation + .0001), low.color);
  }
});

for (const documentCanvas of [false, true]) test(`protocol decodes DEM and returns PNG ArrayBuffer via ${documentCanvas ? 'document' : 'Offscreen'} canvas`, async (t) => {
  const state = fixture(t, { documentCanvas });
  assert.equal(state.url, 'spectral://terrain/{z}/{x}/{y}');
  assert.equal(terrain.registerSpectralTerrain(state.library), state.url);
  assert.equal(state.registrations, 1);
  const controller = new AbortController();
  const result = await state.load('0/0/0', controller);
  assert(result.data instanceof ArrayBuffer);
  assert.equal(result.data.byteLength, 8);
  assert.equal(state.fetched[0].url, 'https://elevation-tiles-prod.s3.amazonaws.com/terrarium/0/0/0.png');
  assert.equal(state.fetched[0].options.signal, controller.signal);
  assert.deepEqual(state.options[0], { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
  assert.deepEqual(state.encoded[0], [18, 62, 68, 255, 168, 205, 133, 128]);
  assert.equal(state.closed, 1);
  new Uint8Array(result.data)[0] = 99;
  assert.equal(new Uint8Array((await state.load()).data)[0], 0);
  assert.equal(state.fetched.length, 1);
});

test('HTTP, network and malformed tile errors propagate without caching failures', async (t) => {
  const state = fixture(t);
  globalThis.fetch = async () => ({ ok: false, status: 404, statusText: 'Not Found' });
  await assert.rejects(state.load(), /404 Not Found/);
  const failure = new Error('network offline');
  globalThis.fetch = async () => { throw failure; };
  await assert.rejects(state.load(), (error) => error === failure);
  await assert.rejects(state.load('1/2/0'), /coordinates/);
  await assert.rejects(state.load('0/0/0?url=https://example.org'), /URL/);
});

test('Image fallback revokes its object URL and still renders decoded DEM pixels', async (t) => {
  const state = fixture(t, { documentCanvas: true });
  const revoked = [];
  class Image {
    width = 2;
    height = 1;
    set src(value) { if (value) queueMicrotask(() => this.onload?.()); }
  }
  globals(t, {
    createImageBitmap: undefined, Image,
    URL: { createObjectURL: () => 'blob:dem-test', revokeObjectURL: (url) => revoked.push(url) },
  });
  assert((await state.load()).data instanceof ArrayBuffer);
  assert.deepEqual(revoked, ['blob:dem-test']);
  assert.deepEqual(state.encoded[0], [18, 62, 68, 255, 168, 205, 133, 128]);
});

test('image decode and PNG encoding errors propagate', async (t) => {
  const state = fixture(t, { documentCanvas: true });
  const failure = new Error('corrupt PNG');
  globalThis.createImageBitmap = async () => { throw failure; };
  await assert.rejects(state.load(), (error) => error === failure);
  globalThis.createImageBitmap = async () => ({ width: 2, height: 1, close: () => state.closed++ });
  const createCanvas = globalThis.document.createElement;
  globalThis.document.createElement = (name) => {
    const canvas = createCanvas(name);
    canvas.toBlob = (callback) => callback(null);
    return canvas;
  };
  await assert.rejects(state.load(), /Cannot encode spectral PNG/);
  assert.equal(state.closed, 1);
});

test('aborted requests reject even from cache or while image decoding is pending', async (t) => {
  const state = fixture(t);
  await state.load();
  const aborted = new AbortController(); aborted.abort();
  await assert.rejects(state.load('0/0/0', aborted), { name: 'AbortError' });
  let finish;
  globalThis.createImageBitmap = () => new Promise((resolve) => { finish = resolve; });
  const controller = new AbortController(), pending = state.load('1/0/0', controller);
  // Let fetch and blob resolution reach the non-cancellable browser decoder.
  await new Promise(setImmediate);
  controller.abort();
  await assert.rejects(pending, { name: 'AbortError' });
  finish({ width: 2, height: 1, close: () => state.closed++ });
  await new Promise(setImmediate);
  assert.equal(state.closed, 2, 'late decoded images are released');
  globalThis.createImageBitmap = async () => ({ width: 2, height: 1, close() {} });
  await state.load('1/0/0');
  assert.equal(state.fetched.length, 3, 'aborted work was not cached');
});

test('LRU cache is bounded by tile count and refreshes cache hits', async (t) => {
  const state = fixture(t);
  for (let x = 0; x < 64; x++) await state.load(`7/${x}/0`);
  await state.load('7/0/0');
  await state.load('7/64/0');
  await state.load('7/0/0');
  assert.equal(state.fetched.length, 65);
  await state.load('7/1/0');
  assert.equal(state.fetched.length, 66);
});

test('cache also evicts tiles when its byte budget is reached', async (t) => {
  const state = fixture(t, { size: 9 * 1024 * 1024 });
  await state.load('1/0/0');
  await state.load('1/1/0');
  await state.load('1/0/0');
  assert.equal(state.fetched.length, 3);
});
