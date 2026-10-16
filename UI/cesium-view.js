export const CESIUM_VERSION = '1.123.0';
export const CESIUM_BASE_URL = `https://cdn.jsdelivr.net/npm/cesium@${CESIUM_VERSION}/Build/Cesium/`;
let assets;

// Load only on explicit globe entry. This loads CesiumJS, not ion services.
export function loadCesium({ document: doc = document, window: win = window } = {}) {
  if (assets) return assets;
  win.CESIUM_BASE_URL = CESIUM_BASE_URL;
  assets = new Promise((resolve, reject) => {
    const css = doc.createElement('link'); css.rel = 'stylesheet'; css.href = `${CESIUM_BASE_URL}Widgets/widgets.css`;
    const script = doc.createElement('script'); script.src = `${CESIUM_BASE_URL}Cesium.js`; script.async = true;
    let jsReady = false, cssReady = false;
    const complete = () => { if (jsReady && cssReady) { clearTimeout(timer); resolve(win.Cesium); } };
    const timer = setTimeout(() => fail(), 20000);
    const fail = () => { clearTimeout(timer); script.remove(); css.remove(); assets = null; reject(new Error('Pinned Cesium assets could not be loaded. MapLibre remains available.')); };
    css.onload = () => { cssReady = true; complete(); }; css.onerror = fail;
    script.onload = () => { if (!win.Cesium?.Viewer) { fail(); return; } jsReady = true; complete(); }; script.onerror = fail;
    doc.head.append(css, script);
  });
  return assets;
}

export function mapCameraTarget(map) {
  const center = map.getCenter();
  return { longitude: center.lng, latitude: center.lat, zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() };
}

export function createCesiumView({ Cesium, container, target, client, confirmDisclosure, onContextLost = () => {} }) {
  const viewer = new Cesium.Viewer(container, {
    baseLayer: false, terrainProvider: new Cesium.EllipsoidTerrainProvider(),
    animation: false, timeline: false, geocoder: false, baseLayerPicker: false,
    sceneModePicker: false, navigationHelpButton: false, homeButton: false,
    fullscreenButton: false, infoBox: false, selectionIndicator: false,
    requestRenderMode: true, maximumRenderTimeChange: Infinity,
    contextOptions: { webgl: { preserveDrawingBuffer: false } },
  });
  viewer.imageryLayers.removeAll();
  viewer.scene.globe.tileCacheSize = 64;
  viewer.clock.shouldAnimate = false;
  let semantic = { ...target }, destroyed = false;
  const canvas = viewer.scene.canvas;
  const lost = (event) => { event.preventDefault(); onContextLost(); };
  canvas.addEventListener('webglcontextlost', lost);
  function setTarget(value) {
    semantic = { ...value };
    const latitude = Math.max(-89.9, Math.min(89.9, value.latitude));
    const height = Math.max(20, 40075016.686 * Math.max(0.01, Math.cos(latitude * Math.PI / 180)) / (2 ** value.zoom));
    const destination = Cesium.Cartesian3.fromDegrees(value.longitude, latitude, height);
    viewer.camera.setView({ destination, orientation: { heading: Cesium.Math.toRadians(value.bearing || 0), pitch: Cesium.Math.toRadians((value.pitch || 0) - 90), roll: 0 } });
    viewer.scene.requestRender();
  }
  setTarget(target);
  const products = createCesiumProducts({ Cesium, viewer, client, confirmDisclosure });
  return {
    viewer, products, setTarget,
    getTarget() {
      const pixel = new Cesium.Cartesian2(canvas.clientWidth / 2, canvas.clientHeight / 2);
      const hit = viewer.camera.pickEllipsoid(pixel, viewer.scene.globe.ellipsoid);
      if (!hit) return { ...semantic };
      const position = Cesium.Cartographic.fromCartesian(hit);
      const latitude = Cesium.Math.toDegrees(position.latitude);
      const height = Math.max(20, viewer.camera.positionCartographic.height);
      return { longitude: Cesium.Math.toDegrees(position.longitude), latitude,
        zoom: Math.max(0, Math.min(22, Math.log2(40075016.686 * Math.max(0.01, Math.cos(position.latitude)) / height))),
        bearing: Cesium.Math.toDegrees(viewer.camera.heading), pitch: Math.max(0, Math.min(85, 90 + Cesium.Math.toDegrees(viewer.camera.pitch))) };
    },
    destroy() { if (destroyed) return; destroyed = true; products.destroy(); canvas.removeEventListener('webglcontextlost', lost); viewer.destroy(); },
  };
}
import { createCesiumProducts } from './cesium-products.js';
