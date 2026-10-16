# Interesting Things to Build in Meridian

## Purpose

A curated feature list combining the complete [Meridian Live Earth Engineering Blueprint](Meridian_Live_Earth_Engineering_Blueprint.docx) with the inspected [Gods Eye View project](gods-eye-view/) and the earlier [comparison study](GODS_EYE_VIEW_COMPARISON.md).

The blueprint review covered all 13 sections, both appendices, its tables, and the architecture diagram. This list turns those engineering capabilities into experiences a user can actually enjoy. It is not an implementation commitment, a schedule, or permission to purchase services or assets.

Source snapshot: blueprint version 1.0, prepared October 14, 2026; Meridian revision `97f968b`; Gods Eye View revision `132b9e9`. Provider prices, rights, quotas, and current availability were not independently revalidated for this list.

**Product direction:** make Earth explorable in 3D, then observable over time. Borrow Gods Eye View's sense of continuity while preserving Meridian's map-first identity, inspectable geography, source transparency, and MapLibre foundation.

## What Meridian Already Has

Do not count these as new features:

- Satellite, Streets, Terrain, and elevation-colored Spectral views.
- Terrain relief, contours, sampled elevation, and single-destination landscape/camera presets.
- Building enrichment, estimated-height provenance, building and POI popups.
- Saved pins, measured areas, geographic overlays, and bounded AI map actions.
- Two-to-50-stop driving routes and an animation of the local routing calculation.
- Fullscreen and hide-controls viewing.
- City/country URL links and device-local camera/preferences persistence.
- One fixed, dated Bay Area NASA imagery scene.

The additions below are richer connections or genuinely new capabilities. Current route replay is not a camera flythrough; fixed imagery is not an acquisition browser; a building popup is not shared selected-feature context. Studio and general analytical dataset workflows are currently retired, so proposed science tools are new product work, not already accessible functionality.

## A. Signature Experiences

These are the strongest candidates for making Meridian immediately more compelling. The order reflects product appeal, not a strict engineering dependency order.

### 1. Watch Real Aircraft in 3D

See aircraft moving above the terrain, select one, inspect its trail and metadata, and optionally follow it from an overhead or chase view.

**First useful version:** one bounded-region position feed, timestamped details, trails, symbols at distance, and a small licensed pack of aircraft-class GLBs near the camera. The blueprint's release target includes at least five classes plus a generic fallback. A cockpit view is a later extension, not a prerequisite.

**Main needs:** live-data runtime, asset/type resolver, projection-aware transforms, camera ownership, and approved feed/asset rights. Label reconstructed motion and approximate models; do not invent a tail-specific livery. Airport schedules, gates, and flight status require separately licensed data, not inference from ADS-B positions.

**Basis:** blueprint sections 2.1, 3.1, 6, and 11; GEV aircraft tracking and cockpit.

### 2. Explore the ISS and Satellites

Find the ISS, inspect its orbit and ground track, discover the next pass over a selected place, and explore satellite groups.

**First useful version:** ISS/subsatellite position, ground track, pass prediction, and orbital-element epoch using CelesTrak plus SGP4. Extend to a physically placed 3D spacecraft after altitude, horizon, projection, and clipping behavior pass a rendering experiment.

**Main needs:** orbital propagation, time controls, and explicit predicted-position labeling. Meridian currently uses default Mercator; a convincing global orbital scene is not achieved merely by adding high-altitude markers. Preserve MapLibre while evaluating its projection-aware integration, rather than automatically replacing the engine.

**Basis:** blueprint sections 2.1, 3.1, and 7.2; GEV satellite orbit and pass implementation.

### 3. Fly Through a Route

Turn a planned drive into a cinematic journey: move along its geography, pause at stops, and explore nearby landmarks.

**First useful version:** a fixed-oblique camera tour along existing route geometry with play, pause, stop, reduced-motion behavior, and immediate manual interruption. It should work even when the route has no local search-edge replay.

**Main needs:** camera ownership and distance-based route sampling. Low-level terrain following, banking, and collision-aware framing come later. Approximate endpoint connectors must remain identifiable.

**Basis:** blueprint sections 2.1 and 3.3; GEV `fly_route` and camera verbs. Extends Meridian's existing routes, not its line animation alone.

### 4. Earth Time Machine

Choose a place and compare real imagery dates: a reservoir changing, a city expanding, a glacier retreating, or a landscape before and after an event.

**First useful version:** a bounded-area NASA CMR/GIBS acquisition browser with product/date cards, useful-coverage ranking, and an A/B swipe. Start with recent acquisitions; long historical discovery and derived change analysis are separate upgrades.

**Main needs:** imagery descriptors, cancellation, date/product provenance, and honest coverage/cloud reporting. Scene cloud percentage is not cloud percentage over the exact selected area. Do not label periodic imagery as live video.

**Basis:** blueprint sections 2.3, 3.3, and 7.1; GEV Recent Imagery. Its model/catalog/source boundary previously passed 22 local fixture tests without Cesium. This is a good early parallel win despite general science appearing later in the blueprint.

### 5. Click Anything, Then Ask About It

Click a building, peak, route segment, event, or aircraft and ask: "What is this?", "Why is it here?", or "Show me related places."

**First useful version:** connect the selected building, POI, or terrain point to a bounded selected-feature descriptor consumed by both the details UI and Meridian's existing assistant. Use verified source attributes and citations; do not imply the model knows unavailable facts.

**Main needs:** stable source/feature identity and selection lifecycle. Selection must not automatically change the selected city or add a route stop.

**Basis:** GEV shared subject context and query tools; blueprint selection/detail requirements. New connection between capabilities Meridian already has.

### 6. Discover What Is Nearby

From a selected subject, visit nearby viewpoints, airports, public cameras, landmarks, or other available entities without restarting a search.

**First useful version:** three relevant nearby POIs with distance, provenance, and a "visit next" action. Add live contacts only after those feeds exist.

**Main needs:** shared contextual queries and source-coverage status. Proximity does not prove affiliation, danger, relevance, or complete coverage; rankings should explain their basis.

**Basis:** GEV Contacts/proximity navigation and blueprint infrastructure/exploration layers. Extends Meridian's existing nearby search into a continuous selection-led experience.

### 7. Guided Geographic Stories

Open a short journey such as "How this valley formed", "Follow a river", "Explore a volcanic landscape", or "Watch the sky over this airport."

**First useful version:** three curated stops with camera framing, a small layer preset, captions, and an easy exit. Existing landscape destinations can supply the starting points.

**Main needs:** owned playback and readiness/cancellation handling. A complete scene editor or generated narration is not needed for the first release.

**Basis:** GEV packaged scenes and Director; blueprint presets, time, and exploration. Adds sequencing beyond Meridian's current destination buttons.

### 8. Save and Share an Exact View

Bookmark a discovery and reopen or share its camera, mode, selected layers, and applicable imagery date.

**First useful version:** a versioned camera/terrain/display permalink and named view bookmarks. Include stable provider/product references where supported.

**Main needs:** bounded serialization and startup precedence. A view link is not a shared local workspace or a recording of the original live observations. Portable overlays, routes, pins, and retained snapshots require explicit export formats and rights.

**Basis:** blueprint sections 3.3, 9, and 11; GEV share links and shot-state capture. Extends Meridian's city-only links and local persistence.

## B. Make Earth Feel Alive

| # | Experience | First Useful Version | Principal Gate / Basis |
| --- | --- | --- | --- |
| 9 | **Watch weather move across terrain** | One weather product with wind vectors or particles, forecast valid-time selection, and point inspection | Separate model issue time from valid time; validate field coverage. Blueprint 2.2/7.4; GEV wind/weather |
| 10 | **Follow rain and storms** | One region's radar timeline, visible coverage edge, and official storm/alert details | Observations, forecasts, and lightning density are different products; review rights before playback. Blueprint 2.2; GEV radar/cyclones |
| 11 | **Explore earthquakes in context** | USGS event markers with magnitude, depth, source time, revisions, and a bounded event timeline | Epicenter context is not a measured impact radius or warning service. Fault context can be added separately. Blueprint 2.2/7.4; GEV earthquakes |
| 12 | **Observe fires and smoke** | Timestamped FIRMS hotspots, available authoritative perimeters, and links to imagery | A hotspot is not automatically a confirmed fire; perimeter and smoke products have separate times. Blueprint 2.2/7.4; GEV fires/perimeters |
| 13 | **Compare air quality measurements and forecasts** | Nearby station cards with pollutant, unit, timestamp, and provider; optional separately labeled model grid | Never silently turn sparse sensors into a continuous measured surface. Blueprint 2.2/7.4; additional capability beyond the inspected GEV catalogue |
| 14 | **Look through a public camera** | Camera marker, timestamped still/authorized stream, original source link, and next/nearest navigation | Coverage and media rights vary. Missing footage must not be disguised with unrelated or synthetic imagery. Blueprint webcams; GEV CCTV |
| 15 | **Step into street imagery** | Open a nearby Mapillary image with capture date, attribution, and location | Check provider terms. GEV restricts embedded Google Street View to its compatible Google map stack; do not assume it is allowed beside Meridian's non-Google map. GEV Street Level |
| 16 | **Watch a city move** | Start with one city's GTFS-Realtime vehicles and static route context; add traffic-flow segments or GBFS availability as separate products | Road congestion is aggregate data, not the position of individual cars. Feed availability is agency/provider-specific. Blueprint 2.1/7.2/7.3; GEV transit/traffic/bikeshare |
| 17 | **Follow ships into a port** | One bounded AIS region, vessel cards, trails, port context, and one-shot focus | Continuous follow would be new Meridian work: inspected GEV vessels select/focus but do not continuously track the camera. AIS rights/coverage must be approved. Blueprint 2.1/7.2; GEV vessels |

Treat each row as an independently testable experience, not a requirement to enable every feed together. Begin with one excellent region or product before expanding coverage.

## C. Understand the Landscape

These use the blueprint's scientific direction to make Meridian distinctive, rather than merely imitating a public-feed console.

| # | Experience | First Useful Version | Principal Gate / Basis |
| --- | --- | --- | --- |
| 18 | **Read terrain like a geographer** | Draw a line and inspect an elevation profile; add slope and aspect over a bounded area | Current Spectral, contours, and point elevation already exist. New derivatives need resolution, nodata, and sampling disclosures. Blueprint 2.3/3.3 |
| 19 | **See what is visible from a peak** | Terrain-only viewshed from a selected point and observer height; line-of-sight between two points | DEM resolution and missing buildings/vegetation limit results. Not a safety or communications guarantee. Blueprint viewshed |
| 20 | **Move the Sun and Moon through time** | Sun direction, sunrise/sunset, day/night context, and date/location controls | Begin with astronomical calculations; terrain/building cast shadows need separate renderer/geometry validation. Fixed hillshade is not dynamic sunlight. Blueprint astronomy |
| 21 | **Explore a hiking journey** | A licensed trail or imported permitted path with distance, elevation gain, profile, and camera preview | Meridian currently plans driving routes. Walking/hiking route generation needs its own graph/profile and coverage; mapped trails do not guarantee safety or access. Blueprint outdoor/corridors |
| 22 | **Follow water from mountains to rivers** | One authoritative watershed/network plus available gauge cards and history | DEM-derived flow, measured gauges, and forecast flood extents must remain distinct; full watershed computation is bounded geoprocessing. Blueprint hydrology |
| 23 | **Watch snow and glaciers change** | Compare dated snow-cover/imagery products and an attributed glacier outline | Seasonal coverage, clouds, acquisition times, and resolution constrain conclusions. Blueprint snow/glaciers + imagery; GEV comparison interaction |
| 24 | **Explain geology and tectonics** | Source-backed rock units/faults around a selected landscape, with map scale and citations | Geological maps are regional and scale-dependent; do not invent uniform global detail. Blueprint geology/Macrostrat |
| 25 | **Explore the ocean as a moving system** | One region's sea-surface temperature or current forecast with depth/time metadata | Currents and waves are often model products; gridded processing and coverage need deliberate scope. Blueprint Copernicus Marine |
| 26 | **Compare settlement, lights, and land cover** | One dated night-lights or land-cover product with an exact legend, epoch, and comparison date | Population grids are estimates, not live census counts. Current general dataset workflows are retired; an active integration would be new work. Blueprint Earth science |
| 27 | **Discover aurora and space weather** | NOAA SWPC product cards and a source-labeled aurora probability layer where available | Probability is not guaranteed visibility; retain forecast/valid time and geographic limitations. Blueprint space weather |

Do not infer change attribution from an image difference alone. For example, changed color can result from clouds, season, sensor differences, or processing rather than a verified ecological event.

## D. Optional Experiments and Polish

These are interesting, but should not delay the first coherent experience.

| # | Idea | Smallest Sensible Slice | Why It Is Later / Basis |
| --- | --- | --- | --- |
| 28 | **Talk to Meridian and mark discoveries** | Voice access to existing verified navigation/context actions, then "Label this pin" or "Mark this area" with explicit save/clear controls | Typed agent navigation and geometry already exist; voice sessions, live-layer commands, direct drawing, and a durable notebook are additional work. GEV annotations kept until cleared are not saved audio notes. GEV voice/Draw |
| 29 | **Listen to the place** | A few local internet-radio stations with explicit play/stop, volume, and provider attribution | Optional ambience, not core geographic analysis; stream permissions and availability vary. GEV radio |
| 30 | **Receive aircraft locally** | Optional RTL-SDR receiver integration showing locally heard ADS-B with receiver provenance | Requires hardware, compatible WebUSB browser/context, radio engineering, and testing. Remote internet radio is not RF reception. GEV SDR |
| 31 | **Photorealistic city exploration** | An optional provider-approved 3D Tiles experiment with non-photorealistic fallback | A major integration/rights/performance gate, not a styling switch. Google 3D meshes are not individually editable building footprints or aircraft assets. Blueprint 3D strategy; GEV Google 3D |
| 32 | **Create geographic presentations** | Clean presentation mode, composition guides, named shot states, and permitted image exports | Meridian already hides controls. GEV recording mode adds safe frames, not an actual video recorder; video capture and data replay need separate implementation. GEV Director/recording controls; blueprint export |
| 33 | **Offer tasteful visual atmospheres** | One optional noir/CRT-style presentation preset with readable legends and attribution | Lower priority than data or interaction quality. Thermal-looking styling must never be presented as measured temperature; do not replace Meridian's elevation-based Spectral mode. GEV visual presets |

## Recommended First Releases

### Signature Release: Living Airspace

Build the blueprint's recognizable differentiator as one connected journey:

> Open the sky -> select an aircraft -> inspect its provenance and trail -> optionally follow -> explore ISS/ground tracks -> share the view.

Start with one approved aircraft source, a small licensed model pack, and a bounded satellite catalogue. Ship symbols/fallbacks and release controls before elaborate liveries or cockpit presentation. Full globe/orbital placement must pass its own rendering gate.

### Parallel Quick Wins: Exploration Continuity

Feature context, exact-view links, one three-stop landscape story, route camera preview, and recent imagery discovery can improve the existing map without waiting for every live provider agreement.

Their benefit is cumulative: selection becomes meaningful, camera movement becomes controllable, and discoveries become reproducible.

### Expansion: Live Earth, Then Science

Add a small number of excellent end-to-end feeds, beginning with suitable events/weather products. Introduce imagery/terrain science according to demonstrated user value and data coverage, not simply the number of APIs in the blueprint.

The first useful elevation profile or imagery comparison need not wait for an entire geoprocessing platform. Conversely, advanced watersheds, viewsheds, historical raster processing, and global model grids should not be treated as small UI toggles.

No calendar estimates are assigned here. Provider permission, asset procurement, projection experiments, and performance validation can dominate implementation time.

## Foundations That Make the Ideas Work

| Foundation | Required Behavior | Why It Matters |
| --- | --- | --- |
| **Layer registry** | Capabilities, source, geometry/data type, legend, coverage, timestamps, rights, and loading/empty/stale/error/disabled states | A reliable catalogue, not a long collection of unrelated switches |
| **Selected-feature state** | Stable namespaced identity, bounded properties, provenance, and refresh without reclaiming selection | Connects details, nearby discovery, and assistant queries |
| **Camera/pointer ownership** | Separate inspect/focus/follow/playback; mode-specific manual interruption; old cleanup cannot cancel a new owner | Prevents tours, tools, and late agent results from fighting the user |
| **Runtime data lane** | Keep feed records/display motion separate from persisted, undoable user layer settings | Incoming positions must not fill history or rewrite the workspace |
| **Temporal contract** | Observation time, source update, ingestion, forecast issue/valid time, acquisition time, and orbital epoch remain distinct | One timeline must not falsely imply that every layer has synchronized observed history |
| **Provider gateway** | Secret protection, payload validation, request coalescing, bounded retry/caching, coverage/status, quotas and spend visibility | Avoids duplicate upstream polling and uncontrolled paid requests |
| **3D asset pipeline** | Recorded browser-distribution rights, version/hash, axes/units/pivot, type mapping, LOD, selection and fallback tests | A marketplace preview or purchase does not automatically permit shipping downloadable GLBs |
| **Performance/accessibility gates** | Viewport filtering, GPU/texture budgets, lifecycle cleanup, integrated-GPU/mobile fallback, keyboard access, reduced motion | A cinematic map still needs to be usable on real devices |
| **Reproducible views and exports** | Record exact product/date/settings; distinguish current view from data snapshot; enforce export rights | Sharing presentation does not automatically share licensed source data |

Reuse the current backend and browser-module approach where practical. Redis, PostGIS, FastAPI, Node, TypeScript, and heavier raster pipelines in the blueprint are architectural options, not prerequisites or a mandate to rewrite Meridian.

Typed natural-language navigation and map operations already exist. Future voice/layer discovery should target known, validated capabilities, not model-invented endpoints, arbitrary scripts, or unrestricted media fetches.

## Trust and Scope Rules

- Preserve source times and unknown values; received now does not mean observed now.
- Show incomplete/stale coverage even if the animation looks smooth.
- Limit extrapolation and make reconstructed motion distinguishable from new observations.
- Separate source coordinates and altitude datums from rendered placement; course is not always nose heading.
- Never substitute synthetic footage or unrelated imagery without an explicit label.
- Do not call orbital predictions, traffic simulations, forecast grids, or FLIR shaders direct measurements.
- Do not turn public-data exploration into an emergency, aviation, navigation, or safety-grade claim.
- Check display, caching, retention, playback, screenshot/export, browser-asset, and commercial rights separately.
- A shared time slider must disclose unsupported times, gaps, and whether retained history actually exists.
- Keep the UI contextual and progressively hidden; more features should not mean permanent dashboard clutter.

## Source Map

| Topic | Blueprint | Gods Eye View / Meridian Evidence |
| --- | --- | --- |
| Aircraft, cockpit, model truth | 2.1, 3.1, 6, 7.2, 11 | [tracking](gods-eye-view/src/layers/flights/tracking.js), [cockpit ownership](gods-eye-view/src/ui/cockpitTrackingController.js), [live contract](gods-eye-view/src/sources/live/contract.js) |
| ISS/orbital exploration | 2.1, 3.1, 7.2 | [satellite orbits](gods-eye-view/src/layers/satellites/orbits.js) |
| Route journeys and guided stories | 2.1, 3.3 | [camera verbs](gods-eye-view/src/cameraVerbs.js), [recipes](gods-eye-view/src/scenes/recipes.js), [portable playback](gods-eye-view/src/director/playback.js) |
| Context and nearby discovery | 2, 4, 5 | [context store](gods-eye-view/src/data/contextStore.js), [proximity engine](gods-eye-view/src/data/militaryAwarenessEngine.js) |
| Recent imagery | 2.3, 3.3, 7.1 | [model](gods-eye-view/src/layers/recentImagery/model.js), [catalog](gods-eye-view/src/layers/recentImagery/catalog.js), [source](gods-eye-view/src/layers/recentImagery/source.js) |
| Weather, events, mobility | 2.1, 2.2, 7.2-7.4 | [catalog assembly](gods-eye-view/src/app/constructCatalog.js), [source assembly](gods-eye-view/src/standalone/layerSources.js), [data-source terms](gods-eye-view/DATA_SOURCES.md) |
| Public cameras and street imagery | 2.2, 7.4 | [CCTV controls](gods-eye-view/src/ui/cctvBindings.js), [Mapillary](gods-eye-view/src/layers/streetLevel/providers/mapillary/index.js), [Google compatibility policy](gods-eye-view/src/layers/streetLevel/providers/google/index.js) |
| Scientific tools and outdoor exploration | 2.3, 3.3, 7.5, 11 | Blueprint-led new capabilities; [current Spectral implementation](UI/spectral-terrain.js) is elevation coloring, not the advanced analysis suite |
| Voice, radio, receiver | 4, 6, 9 for shared foundations | [Draw](gods-eye-view/src/annotations/drawTool.js), [annotation lifetime](gods-eye-view/src/annotations/annotationEngine.js), [radio](gods-eye-view/src/layers/radio/playback.js), [SDR](gods-eye-view/src/sdr/controller.js) |
| View sharing and presentation | 3.3, 9, 11 | [share links](gods-eye-view/src/sharelink.js), [recording controls](gods-eye-view/src/ui/recordingControls.js), [visual presets](gods-eye-view/src/ui/visualPresets.js) |
| Current Meridian baseline | Existing implementation, not blueprint claims | [application](UI/app.js), [map actions](UI/map-actions.js), [current agent scope](backend/agent.py), [UI documentation](UI/README.md) |
| Rights and operational limits | 8-13 and appendices | [code license](gods-eye-view/LICENSE), [data terms](gods-eye-view/DATA_SOURCES.md), [security](gods-eye-view/SECURITY.md), [comparison caveats](GODS_EYE_VIEW_COMPARISON.md) |

**Recommended product combination:** live 3D aircraft and ISS for spectacle; contextual selection, camera journeys, and exact views for continuity; dated imagery and terrain science for Meridian's distinctive depth.
