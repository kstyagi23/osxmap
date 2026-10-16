# Gods Eye View and Meridian

## Purpose and Scope

This document consolidates the comparative study conducted on October 14, 2026. Gods Eye View is a separate project, not an extension of Meridian.

The study examined actual source code alongside documentation: rendering, data acquisition, selection, camera behavior, AI interfaces, persistence, application lifecycle, and potential reuse boundaries. Findings describe the inspected implementation, not guaranteed provider availability or future capabilities.

No application code was changed during the study. No dependencies were installed or development servers launched. Selected portable modules were exercised with in-memory inputs, and 22 local imagery fixture tests passed. Neither application received a live visual or performance evaluation.

**Central conclusion:** Gods Eye View makes the world feel alive. Meridian currently makes geography explorable. The most valuable lesson is connected interaction and continuity, not simply more layers or a tactical visual theme.

## 1. Product Identity

Gods Eye View is a local-first public-data exploration console with cinematic presentation. It connects global context, moving entities, individual targets, public cameras, environmental events, and authored scenes.

Meridian is a local, map-first geographic instrument. Its active strengths are place discovery, terrain inspection, building enrichment, source-backed geometry, route planning, geographic overlays, and a bounded AI control surface.

| Dimension | Gods Eye View | Meridian at Time of Study |
| --- | --- | --- |
| Product center | Observe and experience an active world | Explore places and understand geography |
| Main renderer | CesiumJS globe | MapLibre GL 5.24.0 |
| Geographic presentation | Globe, terrain, models, optional photorealistic 3D Tiles | Cartography, imagery, DEM terrain, extruded building footprints |
| Primary subjects | Moving entities, events, infrastructure, public signals | Places, buildings, roads, boundaries, routes, landscape |
| Time | Feed refreshes, reconstructed motion, weather replay, scene playback | Mostly static geography, route-calculation replay, fixed dated regional imagery |
| Camera experience | Aircraft tracking, cockpit, orbit, route dolly, authored tours | Geographic navigation, fit-to-result, terrain and view presets |
| AI interaction | Realtime voice, entity queries, scene/camera control, optional screenshots, MCP | Typed instructions, verified geographic references, overlays, routes, cited research |
| Persistence | Settings, scenes, share links, provider caches | SQLite workspace/caches plus browser camera, preferences, and overlays |
| Visual identity | Tactical, theatrical, telemetry-heavy | Restrained, cartographic, progressively hidden controls |

### Meridian's Active Scope

Meridian is currently Explore-only. Routes and saved places are utilities within the same map experience. Studio, population visualization, and general analytical dataset tools remain in parts of the repository and older documentation, but are retired from the active agent interface.

The retired names are removed from model schemas and absent from executable tool dispatch. This comparison therefore does not treat dormant analytical code as a shipped workflow.

References: [active tool registry](backend/agent_tools.py), [agent capability prompt](backend/agent.py), [current UI](UI/index.html).

## 2. Why Gods Eye View Is Compelling

Its appeal comes from several reinforcing mechanisms:

- Scale: move between Earth-wide context, a city, and an individual subject.
- Motion: aircraft, vessels, satellites, transit, weather, and trails create an active scene.
- Embodiment: a tracked aircraft becomes something to follow or experience from a cockpit.
- Connected discovery: a selected subject can expose nearby contacts or relevant cameras.
- Camera choreography: framing, easing, orbiting, lookahead, and authored movement make navigation experiential.
- Coherent presentation: shaders, telemetry, models, labels, and HUDs reinforce one product identity.

The key achievement is not placing many datasets on a map. It is turning data into subjects the user can experience.

Source inspection found deliberate tuning for low-speed aircraft jitter, heading transitions, camera lookahead, route banking, altitude changes, terrain clearance, cancellation, and model loading. These details contribute materially to perceived polish.

References: [camera verbs](gods-eye-view/src/cameraVerbs.js), [display-motion model](gods-eye-view/src/data/motionModel.js), [aircraft tracking](gods-eye-view/src/layers/flights/tracking.js), [scene director](gods-eye-view/src/scenes/director.js).

## 3. The Rendering Difference

### Appearance Versus Inspectable Features

Gods Eye View's most striking city views use Google Photorealistic 3D Tiles, accessed directly or through Cesium ion. These are textured 3D meshes, not ordinary footprint extrusions. Configured credentials and applicable provider access are required; the keyless baseline uses satellite imagery and terrain.

Meridian constructs city representation from building footprints and heights. Its source hierarchy includes OpenBuildingMap, OSM, and Overture. Missing heights are enriched through source floor counts, nearby references, range estimates, and deterministic neighborhood/footprint-based estimation. Provenance and confidence categories accompany the results.

**Gods Eye View gives the appearance of a place. Meridian supplies editable, inspectable geographic features describing that place.**

A photogrammetric city does not automatically provide individually identified polygons suitable for building-level filtering and styling. Conversely, a footprint extrusion cannot reproduce the visual richness of textured photogrammetry.

References: [GEV photorealistic tiles](gods-eye-view/src/maps/google3d.js), [GEV viewer](gods-eye-view/src/app/viewer.js), [Meridian rendering and source pipeline](UI/app.js), [Meridian height estimation](backend/server.py).

### FLIR Is Not Spectral Terrain

GEV's FLIR/NVG modes are artistic post-processing. The thermal shader maps image luminance into thermal-looking values and includes a simulated temperature readout. It does not measure temperature.

Meridian's Spectral mode decodes Terrarium DEM pixels into elevation and applies an altitude palette. It represents a geographic quantity, but is not multispectral remote sensing or vegetation/material classification.

**GEV's FLIR changes how the world looks. Meridian's Spectral changes how elevation is represented.**

References: [thermal shader](gods-eye-view/src/styles/thermal.js), [spectral elevation decoding](UI/spectral-terrain.js).

## 4. Public Data and Presentation Semantics

GEV has genuine integrations across aviation, maritime, orbital, environmental, mobility, imagery, weather, cameras, radio, and infrastructure. Its layer catalog is broader than a simple globe demo.

However, the surveillance aesthetic must not be mistaken for measured or exhaustive intelligence.

| Capability | What the Inspected Implementation Actually Provides |
| --- | --- |
| Aircraft | Periodic source observations with reconstructed display motion between reports |
| Satellites | Positions propagated from orbital elements, not continuous sensor fixes |
| Traffic | Simulated individual dots along real roads; optional aggregate traffic-flow input |
| Detection overlay | Brackets/labels for registered scene objects, not computer vision over camera footage |
| CCTV | Public camera imagery on oriented planes with estimated poses, not precise projection onto building surfaces |
| FLIR/NVG | Visual shader effects, not thermal measurements |
| Infrastructure | Geographic inventories, not necessarily current operational status |
| Recent satellite imagery | Dated acquisitions and mosaics, not live satellite video |

Feed coverage can be partial, delayed, stale, unavailable, or dependent on optional credentials. An empty layer is not proof that nothing exists in the area.

References: [layer catalog](gods-eye-view/src/app/constructCatalog.js), [data sources and caveats](gods-eye-view/DATA_SOURCES.md), [traffic animation](gods-eye-view/src/layers/traffic/animation.js), [CCTV projection](gods-eye-view/src/layers/cctv/projection.js).

## 5. The Core Architectural Lesson

The strongest transferable interaction model is:

> Stable subject identity -> explicit selection intent -> controlled camera authority -> consistent displayed position -> contextual queries -> cancellation and cleanup that preserve newer user intent.

GEV implements this through cooperating owners rather than one universal controller. Newer source/domain boundaries are reusable, but much of its presentation runtime still assumes one Cesium viewer and one browser page.

### Selection, Focus, and Follow Are Different

These operations should not be conflated:

- Inspect: select a subject and expose its information.
- Focus: make one camera movement to frame it.
- Follow: maintain a camera relationship to a moving subject.
- Playback: temporarily execute an authored route or sequence.

Aircraft selection in GEV creates a tracked entity, frames it, requests enrichment and track history, and publishes subject context. Vessels currently select and request a one-time focus; they do not assign `viewer.trackedEntity` for continuous following.

This qualifies the broad description that GEV can "track anything": interaction behavior is entity-specific.

References: [aircraft tracking](gods-eye-view/src/layers/flights/tracking.js), [vessel selection](gods-eye-view/src/layers/vessels/selection.js), [world focus](gods-eye-view/src/worldFocus.js).

### Refreshing Data Must Not Reclaim Selection

GEV distinguishes selecting a subject from refreshing its registered context. A background poll or enrichment result can update metadata without resurrecting a subject the user has replaced.

Meridian currently has independent building, POI, terrain, and overlay inspection paths. Its `selected` location is a city/geographic anchor, not the clicked feature. The agent context does not reliably identify the building or POI currently being inspected.

A separate, bounded selected-feature descriptor would connect map inspection, contextual information, and the assistant. It should retain layer/source identity, stable feature identity, relevant geometry extent, bounded properties, and provenance.

It should not reset the selected city or route state merely because a feature was clicked.

References: [GEV context store](gods-eye-view/src/data/contextStore.js), [Meridian inspection and agent context](UI/app.js).

### Meridian's Current Click Semantics Need Care

Clicking a search-result marker currently adds a route stop, invalidates the current route, moves the camera, and opens the route utility, which switches to Streets. This is not a neutral focus action.

Building selection uses source IDs, while tile deduplication uses stronger composite identity. Style reloads and mode visibility also affect inspection highlights. Dynamic overlay picking must avoid triggering terrain inspection or pin creation from the same click.

Connected exploration should address these semantics rather than attaching more actions to existing popup handlers.

Reference: [Meridian application interaction paths](UI/app.js).

## 6. Camera and Pointer Ownership

### Revocable Camera Authority

GEV uses ownership tokens, navigation generations, and owner-specific cleanup to prevent old operations from interfering with new intent.

Deferred navigation can retain the current view while resolving a destination, then recheck authority before committing. Failed lookups need not destroy a valid current experience.

Meridian has useful guards for startup restoration, stale requests, route animation, overlay mutations, and undo. These do not yet constitute one camera-arbitration boundary. Manual camera movement can protect rollback without preventing a later agent `set_view` from moving the camera again.

Desired invariants for Meridian are:

- One continuous camera writer at a time.
- New explicit navigation invalidates older pending navigation.
- Old cleanup releases only its own owner.
- Playback/follow release does not unexpectedly jump to an overview.
- Animation frames are transient, not individual history entries.
- Terrain-mode side effects do not fight a camera-owning preset or tour.

References: [navigation policy](gods-eye-view/src/navigationPolicy.js), [arrival ownership](gods-eye-view/src/data/cameraArrival.js), [tracked camera](gods-eye-view/src/data/trackedCamera.js), [Meridian camera actions](UI/map-actions.js).

### Interruption Depends on Mode

| Mode | Appropriate Manual-Input Behavior |
| --- | --- |
| Ordinary feature inspection | Navigation can continue while selection remains meaningful |
| Ordinary aircraft follow | Dragging may orbit the followed subject rather than deselect it |
| Authored tour or route flythrough | Manual navigation stops playback |
| Cockpit | Dedicated controls and exit behavior apply; ordinary globe navigation is not equivalent |
| Deferred search/navigation | Newer user intent invalidates the pending result |

A universal "stop everything on pointer input" policy would lose this distinction.

GEV's pointer leases also prevent a tool that owns the click, such as drawing, from simultaneously activating ambient feature selection. Leases identify the exact owner instance so stale teardown cannot release a replacement tool.

References: [pointer ownership](gods-eye-view/src/data/inputOwnership.js), [tracking gestures](gods-eye-view/src/data/trackingClickGesture.js), [cockpit ownership](gods-eye-view/src/ui/cockpitTrackingController.js).

## 7. Observation, Presentation, and Freshness

| Concept | Meaning |
| --- | --- |
| Observation | What the provider reported, with its source timestamp |
| Presentation | How the application displays the subject between observations |
| Freshness | Whether information is current, stale, or of unknown age |
| Coverage | The geographic/source extent represented |
| Completeness | Whether the returned/accepted records fully represent the claimed snapshot |

GEV's normalized live contract preserves nullable altitude datums, source timestamps, units, and opaque references. Missing observation time is not substituted with response-receipt time.

For continuous movement, the camera and visual elements should consume coordinated display samples. GEV uses cached camera and visible-model accessors to avoid independently recomputing motion at incompatible render phases.

Meridian's existing tile freshness is cache-expiry status. It is not evidence that a building, road, or image was recently observed.

### Live Data Must Be Separate From Workspace Edits

Meridian's ordinary overlay updates participate in revision guards, history, and browser persistence. Treating every incoming position as an ordinary overlay edit would mix background observations with user intent.

The useful separation is:

- Durable, undoable configuration: style, filters, visibility, selected data product, authored geometry.
- Transient runtime state: incoming records, display positions, observation age, acquisition status, retry state.

The city tile worker is tailored to enrichment and deduplicates successful requests until reset. It is not a ready-made high-frequency feed scheduler.

References: [live-source contract](gods-eye-view/src/sources/live/contract.js), [aircraft normalization](gods-eye-view/src/sources/live/aircraft.js), [Meridian overlay transactions](UI/map-actions.js), [Meridian tile worker](UI/tile-worker.js).

## 8. Dated Imagery: The Strongest Reuse Opportunity

Meridian already displays a fixed, geographically bounded NASA GIBS scene. GEV adds a full acquisition-selection workflow around the same family of imagery services.

The workflow is:

1. Choose a bounded extent.
2. Query NASA CMR for Sentinel-2 HLS S30 and Landsat HLS L30 acquisitions.
3. Group granules into product/date candidates.
4. Assess footprint coverage and available cloud metadata.
5. Rank useful candidates rather than blindly choosing the newest date.
6. Display imagery with explicit product, date, resolution, and caveats.
7. Compare selected dates or imagery against the basemap.

### Verified Portable Boundary

| Module | Role | Dependency Characteristics |
| --- | --- | --- |
| [model.js](gods-eye-view/src/layers/recentImagery/model.js) | Products, extent validation, grouping, ranking, URL construction | No DOM, Cesium, or network imports |
| [catalog.js](gods-eye-view/src/layers/recentImagery/catalog.js) | CMR parsing and paginated acquisition | Imports model; fetch is injectable |
| [source.js](gods-eye-view/src/layers/recentImagery/source.js) | Catalog/thumbnail/tile adapter | Imports model and catalog; transport/builders replaceable |

These modules imported without Cesium. Local fixture tests verified extent validation, catalog pagination, ranking, imagery URL conventions, adapter routing, and cancellation.

The experiment also confirmed that ranking can choose an older clear candidate with useful coverage over a newer partial candidate.

### Caveats for Adaptation

- Coverage labeled `full` is assessed from four corners and the center, not exact polygon-union coverage.
- Cloud metadata is scene-level, not a precise cloud fraction for the selected extent.
- Unknown cloud must not be described as clear.
- Catalog truncation weakens certainty about the best available candidate.
- GIBS imagery uses provider-specific maximum zooms and has gaps and resolution limits.
- Extent validation rejects dateline-crossing and unsupported polar selections.
- The source trio does not by itself enforce the complete application's request/tile budget.
- Changing dates requires consistent descriptor, bounds, source recreation, attribution, fallback, and style-reload behavior, not only a tile-template change.

This is a strong fit for Meridian because it makes landscape exploration temporal without adopting a surveillance identity.

## 9. Practical Opportunities for Meridian

These are study recommendations, not implemented features or a committed roadmap.

| Opportunity | Existing Leverage | Main Work or Dependency |
| --- | --- | --- |
| Shared feature focus | Building/POI/terrain inspection and geographic overlays | Stable selection identity and click arbitration |
| Richer exploration presets | Existing terrain, Spectral, camera, and destination controls | Complete view descriptors and consistent history |
| Exact-view sharing | Saved camera and display preferences | Versioned URL validation and startup precedence |
| Selectable dated imagery | Existing GIBS raster source | Catalog lifecycle, descriptors, date selection, coverage/fallback UI |
| Route flythrough | Existing route geometry and cancellable replay scaffolding | Camera ownership, distance sampling, interruption, reduced motion |
| Bounded live feeds | GeoJSON rendering and provider adapters | Separate runtime data lane, freshness/coverage, transport and terms |

### Guided Exploration Before a Full Director

Meridian already has landscape destinations and camera presets. A richer preset can describe location, mode, terrain settings, relevant overlays, and a short explanation without introducing another workspace.

A multi-step tour needs an owned session with cancellation, resource readiness, and camera completion. GEV's adapter-based scene phases are a useful pattern, but its complete Director is substantially larger than Meridian needs for initial guided exploration.

Reference: [portable scene sequencing](gods-eye-view/src/director/playback.js).

### Route Replay Is Not Route Flythrough

Meridian's current replay draws explored search edges and progressively reveals route geometry. It does not move the camera. Routes lacking local search-edge history can still have valid geometry suitable for a flythrough.

A separate camera session should work from route geometry, bind to its revision, stop on manual navigation, respect reduced motion, and retain approximation caveats. Terrain-aware framing is additional work, especially with exaggeration and approximate endpoint connectors.

Reference: [Meridian route/replay implementation](UI/app.js).

### Sharing a View Is Not Sharing a Workspace

Camera, basemap, terrain, and display settings can be serialized into a bounded view link. This is a relatively small frontend capability.

A complete workspace includes browser overlays and backend pins, areas, and locally resolved route IDs. Those are not automatically available on another machine. Workspace sharing requires an explicit portable document/data format and provenance policy.

View links should override saved startup state without being overwritten by late Geo-IP or restoration results. Browser URL history and Meridian's action undo also need distinct semantics.

References: [Meridian saved state and startup](UI/app.js), [overlay persistence](UI/map-actions.js), [loopback configuration](UI/config.js).

## 10. What to Reuse and What to Rewrite

| Category | Assessment |
| --- | --- |
| Pure source normalization and contracts | Strong reuse candidates; retain units, timestamps, provenance, and validation |
| Recent imagery model/catalog/source | Verified renderer-independent boundary |
| Portable scene sequencing | Useful adapter pattern; application must honor cancellation |
| Ownership principles | Reimplement in application-scoped Meridian services |
| GEV provider middleware | Node-specific and endpoint-specific; not directly usable inside Meridian's Python backend |
| Full motion model | Numeric policies are useful, but the module imports Cesium |
| Aircraft entities/models and ENU camera frames | Rewrite for MapLibre or an explicitly chosen rendering adapter |
| Page-global context/readout owners | Do not import unchanged as a general multi-map service |
| Full cockpit, Director, and application shell | High coupling and scope; not a minimal integration |

Declared package exports demonstrate boundaries, not a published stable SDK. The inspected package is marked private. Default source factories can also depend on GEV-specific `/api/*` routes and response headers even when their record contracts are portable.

Camera schemas require adaptation: GEV's authored poses use ellipsoidal altitude, downward-looking pitch conventions, heading, and roll. They cannot simply be passed as Meridian's center/zoom/pitch/bearing configuration.

References: [package exports](gods-eye-view/package.json), [code boundaries](gods-eye-view/docs/CODE-BOUNDARIES.md), [default live sources](gods-eye-view/src/sources/live/standalone.js), [portable camera schema](gods-eye-view/src/director/camera.js).

## 11. Licensing and Operational Constraints

GEV's code is MIT-licensed. Copying substantial code requires retaining its copyright and permission/warranty notice. MIT does not automatically license bundled datasets, imagery, models, or provider access.

The narrow recent-imagery trio imports no NonCommercial event packs or submarine-cable datasets. Broader copying requires a fresh dependency and asset review.

| Source or Asset | Important Distinction Recorded in the Project |
| --- | --- |
| NASA imagery | Public-domain data described in source documentation; retain GIBS acknowledgement and attribution; service access is a separate concern |
| NOAA weather | Public products/disclaimers and provider credits; derived lightning density is not raw Vaisala detections |
| ECMWF wind | CC BY 4.0 plus ECMWF terms, attribution, modification notice, and disclaimer |
| OpenSky | Noncommercial research/education terms; operational or commercial use may require agreement |
| adsb.lol | ODbL data obligations, separate from application code licensing |
| adsbdb enrichment | No general service license documented; route-data reuse has explicit permission restrictions |
| Google 3D Tiles | Proprietary access, credentials, quotas, billing, and attribution requirements |
| Bundled cables/event assets | Some NonCommercial carveouts; not covered by the MIT code grant |

Public availability and keyless endpoints do not establish unrestricted deployment rights. This is a source-documentation assessment, not legal clearance or verification of current provider terms.

Both projects are primarily local applications, not authenticated multi-user production platforms. GEV's substantial integration and presentation polish should not be confused with safety-grade operational intelligence or guaranteed performance. Its published performance baseline is hardware-specific and cannot predict the user's Windows environment.

References: [license](gods-eye-view/LICENSE), [data terms](gods-eye-view/DATA_SOURCES.md), [third-party notices](gods-eye-view/THIRD_PARTY_NOTICES.md), [security posture](gods-eye-view/SECURITY.md), [performance baseline](gods-eye-view/docs/PERFORMANCE.md).

## 12. Validation Record

Executed locally without installing dependencies or making provider requests:

- Imported the recent-imagery model, catalog, and source adapter without Cesium.
- Exercised extent validation, empty catalog behavior, URL generation, and coverage-aware ranking with in-memory inputs.
- Imported aircraft normalization without Cesium and verified separate barometric/ellipsoid altitude and unknown/stale timestamp semantics with synthetic observations.
- Imported scene sequencing without a renderer and exercised phase order/final release using an injected in-memory adapter.
- Ran the following existing fixture suites, with 22 tests passing and zero failures:

```powershell
node --test src/layers/recentImagery/model.test.mjs src/layers/recentImagery/catalog.test.mjs src/layers/recentImagery/source.test.mjs
```

Not verified: full application tests, live provider reliability, browser rendering, accessibility playtests, Windows GPU performance, integration into Meridian, or current external licensing/access terms.

## Final Direction

The opportunity is not "make Meridian look like Gods Eye View."

It is to give Meridian comparable continuity:

> Select something. Understand it. Move through it. Compare it over time. Share the view.

Preserve Meridian's map-first identity, MapLibre foundation, inspectable geometry, grounded actions, and provenance. Borrow GEV's interaction quality, camera ownership, contextual continuity, and selected portable domain logic.

The most important architectural separation is between user intent, transient data, and presentation. Once those are explicit, richer exploration can feel immersive without becoming unpredictable or misleading.
