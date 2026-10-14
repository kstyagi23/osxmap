export const palette = Object.freeze([
  [-500, [8, 42, 50]], [0, [18, 62, 68]], [250, [25, 123, 128]],
  [750, [66, 206, 197]], [1500, [168, 205, 133]], [2500, [239, 180, 120]],
  [4000, [237, 121, 105]], [6000, [224, 244, 243]],
].map(([elevation, color]) => Object.freeze({ elevation, color: Object.freeze(color) })));

export function decodeTerrarium(red, green, blue) {
  return red * 256 + green + blue / 256 - 32768;
}

export function elevationColor(elevation) {
  if (typeof elevation !== 'number' || Number.isNaN(elevation)) throw new TypeError('Elevation must be a number.');
  if (elevation <= palette[0].elevation) return [...palette[0].color];
  for (let i = 1; i < palette.length; i++) {
    const low = palette[i - 1], high = palette[i];
    if (elevation <= high.elevation) {
      const fraction = (elevation - low.elevation) / (high.elevation - low.elevation);
      return low.color.map((channel, j) => Math.round(channel + (high.color[j] - channel) * fraction));
    }
  }
  return [...palette[palette.length - 1].color];
}

const TILE_URL = 'spectral://terrain/{z}/{x}/{y}';
const MAX_TILES = 64, MAX_BYTES = 16 * 1024 * 1024;
const registered = new WeakSet();

function checkAbort(signal) {
  if (signal?.aborted) throw signal.reason ?? new DOMException('Aborted', 'AbortError');
}

function abortable(promise, signal) {
  if (!signal) return promise;
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    promise.then(resolve, reject).finally(() => signal.removeEventListener('abort', abort));
  });
}

async function decodeImage(blob, signal) {
  if (typeof createImageBitmap === 'function') {
    // Avoid browser color conversion changing the encoded elevation channels.
    return createImageBitmap(blob, { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
  }
  const url = URL.createObjectURL(blob), image = new Image();
  try {
    await abortable(new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error('Cannot decode Terrarium PNG.'));
      image.src = url;
    }), signal);
    return image;
  } finally {
    image.onload = image.onerror = null;
    if (signal?.aborted) image.src = '';
    URL.revokeObjectURL(url);
  }
}

async function renderTile(blob, signal) {
  const image = await decodeImage(blob, signal);
  try {
    checkAbort(signal);
    const width = image.width, height = image.height;
    let canvas, context;
    if (typeof OffscreenCanvas === 'function') {
      canvas = new OffscreenCanvas(width, height);
      context = canvas.getContext('2d', { willReadFrequently: true });
    }
    if (!context && typeof document !== 'undefined') {
      canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      context = canvas.getContext('2d', { willReadFrequently: true });
    }
    if (!context) throw new Error('A browser 2D canvas is required for spectral terrain.');
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, width, height);
    for (let i = 0; i < pixels.data.length; i += 4) {
      const color = elevationColor(decodeTerrarium(pixels.data[i], pixels.data[i + 1], pixels.data[i + 2]));
      pixels.data.set(color, i);
    }
    context.putImageData(pixels, 0, 0);
    const png = typeof canvas.convertToBlob === 'function'
      ? await canvas.convertToBlob({ type: 'image/png' })
      : await new Promise((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error('Cannot encode spectral PNG.')), 'image/png'));
    checkAbort(signal);
    return await png.arrayBuffer();
  } finally {
    image.close?.();
  }
}

export function registerSpectralTerrain(maplibregl) {
  if (registered.has(maplibregl)) return TILE_URL;
  const cache = new Map();
  let bytes = 0;
  maplibregl.addProtocol('spectral', (params, abortController) => {
    const signal = abortController?.signal;
    const load = async () => {
      checkAbort(signal);
      const match = /^spectral:\/\/terrain\/(\d+)\/(\d+)\/(\d+)$/.exec(params.url);
      if (!match) throw new Error('Invalid spectral terrain tile URL.');
      const [, z, x, y] = match;
      if (+z > 22 || +x >= 2 ** +z || +y >= 2 ** +z) throw new Error('Invalid spectral terrain tile coordinates.');
      const key = `${+z}/${+x}/${+y}`;
      if (cache.has(key)) {
        const data = cache.get(key);
        cache.delete(key);
        cache.set(key, data);
        return { data: data.slice(0) };
      }
      const response = await fetch(`https://elevation-tiles-prod.s3.amazonaws.com/terrarium/${key}.png`, { signal });
      if (!response.ok) throw new Error(`Terrarium tile fetch failed: ${response.status} ${response.statusText}`);
      const data = await renderTile(await response.blob(), signal);
      checkAbort(signal);
      // Keep owned copies: MapLibre may transfer returned buffers to workers.
      if (data.byteLength <= MAX_BYTES) {
        if (cache.has(key)) { bytes -= cache.get(key).byteLength; cache.delete(key); }
        cache.set(key, data.slice(0));
        bytes += data.byteLength;
        while (cache.size > MAX_TILES || bytes > MAX_BYTES) {
          const oldest = cache.keys().next().value;
          bytes -= cache.get(oldest).byteLength;
          cache.delete(oldest);
        }
      }
      return { data };
    };
    return abortable(load(), signal);
  });
  registered.add(maplibregl);
  return TILE_URL;
}
