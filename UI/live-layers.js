const EMPTY = () => ({ type: 'FeatureCollection', features: [] });

export function provenanceContent(feature, envelope = {}, doc = document) {
  const node = doc.createElement('div');
  const properties = feature?.properties || {};
  const provenance = envelope.provenance || {};
  const fields = {
    Entity: feature?.id ?? properties.entity_id ?? 'Unknown',
    Product: envelope.provider_id ?? envelope.product_id ?? envelope.source?.product_id ?? provenance.product_id ?? 'Unknown',
    Source: envelope.source?.name ?? provenance.source ?? 'Unknown',
    Observation: properties.observed_at ?? envelope.observed_at ?? provenance.observed_at ?? 'Unknown',
    Acquisition: envelope.acquired_at ?? provenance.acquired_at ?? 'Unknown',
    'Orbital epoch': properties.orbital_epoch ?? properties.epoch ?? provenance.orbital_epoch ?? 'Unknown',
    'Propagation time': properties.propagation_time ?? provenance.propagation_time ?? 'Unknown',
    Freshness: envelope.freshness ?? envelope.state ?? 'Unknown',
    Attribution: envelope.attribution ?? envelope.source?.attribution ?? provenance.attribution ?? 'Unknown',
    Licence: envelope.license ?? provenance.license ?? 'Unknown',
    Citation: provenance.citation ?? 'Unknown',
    'Altitude (m)': properties.altitude_m ?? 'Unknown',
    'Altitude reference': properties.altitude_reference ?? 'Unknown',
    'Forecast issue': properties.issue_time ?? provenance.issue_time ?? 'Unknown',
    'Forecast valid': properties.valid_time ?? provenance.valid_time ?? 'Unknown',
    Coverage: envelope.coverage ? (typeof envelope.coverage === 'string' ? envelope.coverage : JSON.stringify(envelope.coverage)) : 'Unknown',
  };
  if (envelope.partial || envelope.truncated) fields.Warning = 'Partial or truncated observations';
  for (const [label, value] of Object.entries(fields)) {
    const row = doc.createElement('p'); row.textContent = `${label}: ${String(value)}`; node.append(row);
  }
  return node;
}

// Live sources never enter map-actions snapshots, undo, or persisted workspace.
export function createLiveLayers({ map, client, document: doc = globalThis.document, Popup, onStatus = () => {}, maxLayers = 8, maxFeatures = 5000 } = {}) {
  const layers = new Map(); let active = true, disposed = false;
  const runnable = (entry) => !disposed && active && !doc?.hidden && entry.visible && entry.eligible;
  function clear(entry) {
    entry.generation += 1; entry.controller?.abort(); entry.controller = null;
    clearTimeout(entry.timer); entry.timer = null; entry.envelope = null;
    map.getSource(entry.source)?.setData(EMPTY()); entry.popup?.remove(); entry.popup = null;
    const records = doc.getElementById?.('service-record-details');
    records?.querySelector?.(`[data-service-record="${entry.id}"]`)?.remove();
    if (records && !records.children.length) records.hidden = true;
  }
  function install(entry) {
    if (!map.getSource(entry.source)) map.addSource(entry.source, { type: 'geojson', data: EMPTY(), cluster: true, clusterRadius: 45, clusterMaxZoom: 12 });
    if (!map.getLayer(entry.layer)) map.addLayer({ id: entry.layer, source: entry.source, type: 'circle', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': ['case', ['has', 'point_count'], 10, 4], 'circle-color': '#d0dac5', 'circle-stroke-color': '#263329', 'circle-stroke-width': 1 } });
    if (!map.getLayer(entry.area)) map.addLayer({ id: entry.area, type: 'fill', source: entry.source, filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#a7bd91', 'fill-opacity': 0.14 } });
    if (!map.getLayer(entry.outline)) map.addLayer({ id: entry.outline, type: 'line', source: entry.source, filter: ['!=', ['geometry-type'], 'Point'], paint: { 'line-color': '#a7bd91', 'line-width': 1.5 } });
  }
  async function refresh(entry) {
    if (!runnable(entry) || entry.controller) return;
    const generation = entry.generation, controller = new AbortController(); entry.controller = controller;
    onStatus({ id: entry.id, state: 'loading' });
    try {
      const query = typeof entry.query === 'function' ? entry.query(map) : entry.query;
      if (!query) return;
      const envelope = entry.predicted
        ? await client.predictions(query, [new Date().toISOString()], { signal: controller.signal })
        : await client.query(entry.id, query, { signal: controller.signal });
      if (!runnable(entry) || generation !== entry.generation) return;
      const data = envelope.data || (Array.isArray(envelope.features) ? { type: 'FeatureCollection', features: envelope.features } : null);
      if (data?.type !== 'FeatureCollection' || !Array.isArray(data.features) || data.features.length > maxFeatures) throw new Error('Invalid or oversized live GeoJSON.');
      entry.envelope = { ...envelope, data };
      install(entry); map.getSource(entry.source).setData(data);
      const { features, records, data: ignoredData, ...metadata } = envelope;
      onStatus({ ...metadata, id: entry.id, count: data.features.length });
      if (Array.isArray(records) && records.length) {
        const container = doc.getElementById?.('service-record-details');
        if (container) {
          const section = doc.createElement('section');
          section.dataset.serviceRecord = entry.id;
          container.querySelector?.(`[data-service-record="${entry.id}"]`)?.remove();
          const heading = doc.createElement('h3'); heading.textContent = `${entry.id} / ${records.length} metadata records`; section.append(heading);
          for (const record of records.slice(0, 20)) {
            const detail = doc.createElement('details'), title = doc.createElement('summary'), body = doc.createElement('pre');
            title.textContent = String(record.name || record.title || record.entity_id || record.id || 'Source record');
            body.textContent = JSON.stringify(record, null, 2); detail.append(title, body); section.append(detail);
          }
          container.append(section); container.hidden = false;
        }
      }
    } catch (error) {
      if (!controller.signal.aborted && generation === entry.generation) {
        // Unknown retention rights mean no stale browser retention on failure.
        entry.envelope = null; map.getSource(entry.source)?.setData(EMPTY());
        onStatus({ id: entry.id, state: 'failed', message: 'Live observations unavailable.' });
      }
    } finally {
      if (entry.controller === controller) entry.controller = null;
      if (runnable(entry) && generation === entry.generation) entry.timer = setTimeout(() => refresh(entry), entry.interval);
    }
  }
  function resume() { for (const entry of layers.values()) { clear(entry); if (runnable(entry)) refresh(entry); } }
  const visibility = () => resume(); doc?.addEventListener('visibilitychange', visibility);
  const style = () => { for (const entry of layers.values()) if (runnable(entry)) { install(entry); if (entry.envelope) map.getSource(entry.source).setData(entry.envelope.data); } };
  map.on?.('style.load', style);
  const unsubscribe = client.subscribe((event) => {
    if (event.type === 'invalidate') { const entry = layers.get(event.id); if (entry) { entry.eligible = false; clear(entry); } }
    if (event.type === 'settings') {
      for (const entry of layers.values()) {
        const service = event.settings.services?.find((item) => item.id === entry.id);
        const eligible = service?.effective_enabled === true;
        if (eligible !== entry.eligible) { entry.eligible = eligible; clear(entry); if (runnable(entry)) refresh(entry); }
      }
    }
  });
  return {
    show(id, { query, interval = 30000, predicted = false } = {}) {
      if (disposed) throw new Error('Live layers have been disposed.');
      let entry = layers.get(id);
      if (!entry) {
        if (layers.size >= maxLayers) throw new Error('Hide or remove a live layer before adding another.');
        const source = `meridian-live-${encodeURIComponent(id)}`;
        entry = { id, source, layer: `${source}-symbols`, area: `${source}-areas`, outline: `${source}-outlines`, generation: 0, eligible: client.snapshot?.services?.find((item) => item.id === id)?.effective_enabled === true };
        entry.click = (event) => {
          if (!runnable(entry) || !entry.envelope || !Popup || !event.features?.[0]) return;
          entry.popup?.remove();
          entry.popup = new Popup().setLngLat(event.lngLat).setDOMContent(provenanceContent(event.features[0], entry.envelope, doc)).addTo(map);
        };
        map.on?.('click', entry.layer, entry.click); layers.set(id, entry);
        map.on?.('click', entry.area, entry.click);
      }
      clear(entry); entry.visible = true; entry.query = query; entry.predicted = predicted; entry.interval = Number.isFinite(interval) ? Math.max(5000, Math.min(3600000, interval)) : 30000;
      install(entry); for (const layer of [entry.layer, entry.area, entry.outline]) map.setLayoutProperty?.(layer, 'visibility', 'visible'); refresh(entry);
    },
    hide(id) { const entry = layers.get(id); if (entry) { entry.visible = false; clear(entry); for (const layer of [entry.layer, entry.area, entry.outline]) if (map.getLayer(layer)) map.setLayoutProperty?.(layer, 'visibility', 'none'); } },
    remove(id) {
      const entry = layers.get(id); if (!entry) return;
      entry.visible = false; clear(entry); map.off?.('click', entry.layer, entry.click);
      map.off?.('click', entry.area, entry.click);
      for (const layer of [entry.layer, entry.area, entry.outline]) if (map.getLayer(layer)) map.removeLayer(layer);
      if (map.getSource(entry.source)) map.removeSource(entry.source);
      layers.delete(id);
    },
    setActive(value) { active = Boolean(value); resume(); },
    refresh() { resume(); },
    destroy() { if (disposed) return; disposed = true; unsubscribe(); doc?.removeEventListener('visibilitychange', visibility); map.off?.('style.load', style); for (const id of layers.keys()) this.remove(id); },
  };
}
