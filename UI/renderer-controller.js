import { loadCesium, createCesiumView, mapCameraTarget } from './cesium-view.js';

export const RENDERER_CAPABILITIES = Object.freeze({
  maplibre: Object.freeze(['camera', 'workspace', 'drawing', 'routing', 'undo', 'geojson', 'live_symbols', 'raster']),
  cesium: Object.freeze(['camera', 'globe']),
});

// Globe initially supports camera/ellipsoid only. Workspace editing, drawing,
// routes, live layers, terrain and export must stay in MapLibre until implemented.
export function createRendererController({ map, container, liveLayers, client, confirmDisclosure, loadCesium: loader = loadCesium,
  createView = createCesiumView, onChange = () => {} } = {}) {
  const mapContainer = map.getContainer();
  let renderer = 'maplibre', view, generation = 0, disposed = false;
  const wasHidden = mapContainer.hidden;
  container.hidden = true;
  function restore() {
    view?.destroy(); view = null; container.hidden = true;
    mapContainer.hidden = wasHidden; map.resize(); map.triggerRepaint?.(); liveLayers?.setActive(true); renderer = 'maplibre';
  }
  async function switchTo(next) {
    if (!['maplibre', 'cesium'].includes(next)) throw new Error('Unknown renderer.');
    if (disposed) throw new Error('Renderer controller has been disposed.');
    const ticket = ++generation;
    if (next === 'maplibre') {
      const target = view?.getTarget(); restore();
      if (target) map.jumpTo({ center: [target.longitude, target.latitude], zoom: target.zoom, bearing: target.bearing, pitch: target.pitch });
      onChange(renderer); return renderer;
    }
    if (renderer === 'cesium') return renderer;
    const Cesium = await loader();
    if (disposed || ticket !== generation) return renderer;
    const target = mapCameraTarget(map);
    // Stop transitions and hide, but never remove the original map/undo owner.
    liveLayers?.setActive(false); map.stop(); mapContainer.hidden = true; container.hidden = false;
    try {
      view = createView({ Cesium, container, target, client, confirmDisclosure, onContextLost: () => { switchTo('maplibre').catch(() => {}); } });
      renderer = 'cesium'; onChange(renderer); return renderer;
    } catch (error) { restore(); onChange(renderer); throw error; }
  }
  return {
    switchTo,
    get renderer() { return renderer; },
    enableProduct(id, configuration) { return view?.products?.enable(id, configuration) || Promise.resolve({ state: 'needs_setup', reasons: ['Open the optional Globe before configuring 3D products.'] }); },
    hasCapability(action) { return RENDERER_CAPABILITIES[renderer].includes(action); },
    assertCapability(action) { if (!this.hasCapability(action)) throw new Error(`${action} is not supported in ${renderer}. Switch to MapLibre to use this action.`); },
    destroy() { if (disposed) return; disposed = true; generation += 1; restore(); },
  };
}
