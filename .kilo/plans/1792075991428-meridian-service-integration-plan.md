# Meridian Service Integration Plan

## Goal And Confirmed Decisions

Add every offering in `MERIDIAN_SERVICE_ACCESS.md` to Meridian's service catalogue, with real integrations or an explicit setup/permission blocker appropriate to the offering. Preserve the local-only Python backend and build-free MapLibre UI. Add an optional lazy-loaded Cesium globe/3D view, not a renderer migration.

- Verified commercially free, keyless offerings: enabled by default.
- Non-commercial free offerings: disabled; can be enabled in Settings after eligibility acknowledgement.
- Paid, trial, billing-enabled, or credential-required offerings: disabled; enabled explicitly in Settings after required credentials and acknowledgements are supplied. Credential requirements take precedence over commercial-free status.
- Unverified service/data/media rights: visible in Settings, activation blocked until exact permission and supported access are recorded. A checkbox or API key does not resolve an unverified grant.
- Downloads/self-hosted tools/assets: import, setup, or dependency workflows, not fictitious live API switches. Enabled means available, not already downloaded or installed.
- Credentials persist in backend-owned Windows DPAPI-protected local storage. Existing environment credentials are read-only configured sources; never copy them into browser storage.
- Billing-enabled integrations stop at conservative local product limits by default. Overage requires a separate explicit setting. Local counters cannot guarantee zero charges or account-wide limits; disclose this and recommend provider-side caps.
- Enabled means eligible for use. Requests begin only for visible layers, deliberate queries, selected entities, or explicit jobs. Do not poll all enabled providers at startup.

No application changes, purchases, registrations, credential tests, or live-provider verification are part of this planning task. The matrix is dated October 15, 2026; recheck exact products before enabling an integration during implementation.

## Existing Boundaries And Evidence

- `backend/server.py`: standard-library local HTTP server, SQLite caches/workspace, `SerialQueue`, Nominatim/Overpass queues, OSM road routing, OSRM fallback, building ingestion and agent integration. Keep existing routes; add provider modules instead of expanding the monolith for every service.
- `backend/config.py`: environment precedence, loopback requirement, backend-only model/SerpApi credentials. Preserve precedence: process environment, backend environment, root environment; saved settings credentials are fallback only.
- `backend/web_sources.py`: bounded public fetches and DNS-pinned connections. Reuse its safety design, but build a separate reviewed credential-aware transport; do not let arbitrary web-source reads gain credentials.
- `backend/raster_sources.py`: actual WorldPop/GeoTIFF extraction. Extend rather than replace verified observation extraction.
- `UI/index.html:14`, `UI/app.js:1890`: MapLibre GL JS 5.24.0 and OpenFreeMap. `UI/app.js:9-10` hardcodes Terrarium and classic Esri imagery; map mode currently defaults to satellite. Gate both hosted entitlements and select OpenFreeMap streets if no approved imagery source is available.
- `UI/map-actions.js`: bounded validated actions, source metadata, snapshots and undo. Keep the MapLibre contract; introduce explicit renderer capability checks rather than silently accepting unsupported Cesium actions.
- `UI/map-data.js`: geometry/time validation and visualization utilities. Use for static layers, not per-frame live entity storage.
- `backend/test_isolated.py`: temporary database, no environment loading/outbound HTTP. Extend isolation to secret storage and any new transports/dependencies.
- The shipped UI is Explore-oriented. Do not revive removed Studio navigation based on stale backend documentation; show scientific layers and bounded analysis through existing Explore/details workflows.

## 1. Build The Catalogue And Policy Model

Create proposed `backend/service_registry.py` and `backend/service_settings.py`. Use a single authoritative catalogue returned by the backend, not independently maintained browser and server policies.

Each product entry needs: stable provider/product ID; category; kind (`runtime`, `catalogue`, `download`, `self_hosted`, `asset`, `library`); feature capabilities; coverage; authentication schema; free/commercial/eligibility status; default enablement; official terms and verification date; attribution; separate data/media/service rights; permitted cache/stale/export/history behavior; endpoint origins; request/size/page limits; supported renderers; setup/dependency blockers. Separate offerings from the same company whenever terms/auth/billing differ.

Store user enablement, acknowledgements and product limits separately from immutable reviewed policy. Distinguish requested enablement from effective state: disabled, needs credentials, needs setup, permission blocked, incompatible renderer, ready, loading, fresh, stale, partial, quota exhausted, failed. Ready/health alone does not prove usable observations.

Resolve effective eligibility in this order: permission/access blockers, dependency/renderer blockers, explicit credential/billing/non-commercial opt-in, user disable override, then verified keyless commercial default. Environment keys never auto-enable a credentialed service on first migration. Gate every backend request, job, tile path and fallback using this policy, not just UI controls. No fallback into a disabled or incompatible provider.

Keep permission records maintained by reviewed application configuration or a supported permission-record workflow; arbitrary free-text claims from the browser/model must not change a blocked policy into approved. Record actual product/deployment scope, citation/document, review date, allowed operations and expiry where relevant.

Acceptance: a fixture covering every matrix row has exactly one or more explicit catalogue mappings; no unresolved row becomes effectively enabled; product pairs such as CDSE/Planet, Esri/ArcGIS, basic/One Call, CesiumJS/ion, GP/SupGP, and modern/legacy USGS remain separate.

## 2. Secure Settings And Credentials

Add an accessible Settings page/view within the current static application using proposed `UI/service-settings.js`, `UI/index.html` and existing design tokens in `UI/styles.css`. Group by category; provide search and enabled/configuration/blocked filters. Each service card shows offering, default/current state, features, coverage, auth type, quota/billing warning, terms, attribution and reason it cannot be enabled.

Support enable/disable, eligibility acknowledgement, write-only credential replacement/deletion, redacted configured status, product limits, provider priority and explicit connection tests. Do not test credentials merely by saving; disclose when a test consumes quota. Distinguish API keys, client IDs/secrets, scoped public tokens, bearer tokens, account logins and OAuth authorizations. Never present all of these as one interchangeable API-key field.

Proposed API boundaries: `GET /api/services`, `GET /api/settings/services`, `PUT /api/settings/services/{id}`, `PUT/DELETE /api/settings/services/{id}/credentials`, and `POST /api/settings/services/{id}/test`. Return version/revision and reject stale writes; credentials never appear in responses. Settings is separate from map workspace undo, clear-workspace, shared URLs and agent tools.

Implement proposed `backend/secret_store.py`: current-user Windows DPAPI, versioned encrypted records, atomic replacement, restrictive local permissions, deletion and corruption handling. Use temporary storage/test doubles in tests. On unavailable OS protection, refuse persistent saves; do not fall back to plaintext. DPAPI is not protection against code running as the same Windows user. Persist refresh credentials only when needed; keep short-lived access tokens in memory and serialize refresh.

Protect the local credential broker: exact trusted UI origins, strict Host validation against rebinding, session-bound CSRF token for Settings mutations, JSON-only bounded bodies, no wildcard CORS on secret/admin routes, no query-string credentials. Preserve loopback binding; provider credentials are not Meridian account authentication. Redact secrets from logs, exceptions, caches and agent context. Public browser tokens required by SDKs must be scoped/referrer-restricted and identified as public; expose only those through a dedicated capability, never server secrets.

Disabling/deleting a credential cancels pending work, invalidates token caches and closes live sockets. Remove live layers/media promptly; purge retained content where policy requires. Existing loaded/undo-restored restricted content must not bypass current rights checks.

## 3. Add Shared Provider Runtime

Create a small proposed `backend/providers/` package with shared transport/runtime and domain modules. Keep the current threading HTTP architecture for bounded requests; reuse the existing WebSocket/async infrastructure for an AIS connection manager rather than creating a new server framework.

- Fixed product IDs and typed bounded queries: viewport, time range, entity ID, selected dataset/band. No arbitrary provider URL or raw upstream query API. Self-hosted endpoints are explicit operator configuration, never model-controlled; allow local origins only for separately reviewed local engines, not public-fetch exceptions.
- HTTPS exact-origin allowlists, public DNS validation/pinning, redirect validation/refusal as required, credential scope per origin, TLS validation, bounded compressed/decompressed bytes, timeouts, bounded pages and subprocess arguments.
- Per-product/account admission, bounded queues, cancellation, singleflight, Retry-After/backoff, maximum stale age and cache eviction. Policy determines disk caching, not a generic TTL. Never serve indefinitely old imagery/traffic as current.
- Durable conservative quota counters with atomic reservations across tabs and restart, per-SKU windows/timezones, processing units as well as requests, and explicit uncertainty. Reserve estimated cost before requests; reconcile actual consumption if available. Account usage elsewhere remains unknown.
- Normalized envelopes: source/product/entity ID; source/license/citation; acquisition, observation, ingestion and update time; forecast issue/valid time; orbital epoch and propagation time; units, CRS/altitude reference; coverage/partial/truncated flags; freshness/errors; allowed presentation/export operations. Unknown remains unknown.
- Keep short-lived feeds out of workspace mutations/undo and routine disk history. Bounded selections use namespaced IDs; details and agent receive only inventory/provenance metadata.
- Downloads/processing use bounded explicit jobs with status, cancellation and temp cleanup. No automatic whole-world ingest. Heavy codecs/engines are optional pinned dependencies with missing-dependency status, never downloaded on application startup.

For browser-direct tile/media SDK paths, enforce enablement before construction and teardown on disable, restrict public tokens, and document weaker local quota observability. Do not advertise hard local spend enforcement for third-party SDK requests that cannot be intercepted/countable; require provider caps or block until an acceptable control is available.

## 4. Add Renderer And Layer Lifecycles

Create proposed `UI/service-client.js`, `UI/live-layers.js`, `UI/renderer-controller.js`, and `UI/cesium-view.js`. Keep modules small and domain-based; no generic plugin framework is required.

MapLibre remains the default. Raster XYZ/WMTS/WMS overlays, ordinary GeoJSON and bounded live symbols use MapLibre. Cesium is separately loaded only when entering Globe/3D; vendor or pin its JS/CSS/workers/assets as an implementation dependency, independent of ion credentials. CesiumJS works with own/approved free data. No permanent simultaneous render loops: retain semantic view/layer state, dispose/pause inactive renderer, cap GPU/cache use and handle context loss.

Share geographic camera target, selected feature, enabled providers, layer identity/style and temporal selection. Convert camera coordinates explicitly; unsupported layer/action/terrain capabilities show a reason. Preserve existing route, drawing, snapshot and undo behavior; do not claim complete action parity before tests. MapLibre satellite positions may use truthful ground-track symbols; 3D orbital altitudes belong in Cesium.

One lifecycle per visible layer: load, refresh, select, hide, cancel and dispose. Suspend polling on hidden tabs/layers and stop on renderer switch unless another active consumer needs it. Use viewport/zoom limits, clustering, worker parsing where useful, bounded trails and reduced-motion fallbacks. No synthetic live data on missing credentials/outage. A map control enabling a layer is distinct from Settings enabling its provider.

Centralize attribution in map/details/settings and preserve required credits in permitted screenshots. Enforce media/data retention, export and map-combination restrictions per active product. Google Street View must not display beside a non-Google map when applicable terms prohibit it; a Cesium globe is not automatically a Google map. Use a permitted dedicated viewing context or retain an incompatibility blocker.

## 5. Complete Offering Coverage By Domain

Legend: **Default** = verified keyless commercial offering available by default; **Opt-in** = eligible non-commercial/incidental use; **Configure** = credentials/paid/trial setup, default off; **Blocked** = unresolved grant/access; **Import** = dataset/local engine/assets setup; **Library** = dependency, not provider access. Combined labels require all gates. Every name below corresponds to the matrix offering, not all products of that organization.

### Maps, Imagery, Terrain And Geography

| Offerings | Implementation and initial state |
| --- | --- |
| OpenFreeMap public hosting | Default basemap; preserve attribution, best-effort notices and offline limits. |
| OSM/Geofabrik; Natural Earth | Default/Import regional extracts and boundary context with ODbL/public-domain provenance; no automatic bulk tile scraping. |
| OSM standard raster server | Default optional interactive basemap, never offline/prefetch backend; identification and attribution. |
| NASA GIBS/Worldview; CMR | Default unrestricted-product catalogue, bounded footprint/date search, acquisition cards, WMTS and permitted snapshots. Preserve full geometry and partial pagination. |
| NASA Earthdata downloads | Configure/Import account/token; collection-specific rights and bounded GeoTIFF jobs. |
| CDSE STAC/OData catalogue; Sentinel downloads; CDSE Sentinel Hub | Public discovery Default; authenticated search/download/processing Configure. OAuth refresh, per-product source notices, processing-unit/request quotas and explicit extent/resolution jobs. |
| Standalone Sentinel Hub/Planet | Configure separate 30-day NC trial/subscription entry and expiry; no substitution for CDSE. |
| OpenTopography APIs | Configure personal eligibility/key or Enterprise grant; terrain import and source licence gates. |
| Mapterhorn; Re:Earth; Mapzen Terrarium/AWS tiles | Blocked hosted commercial grant pending source/service review. Raster DEM/quantized-mesh adapters after approval; Re:Earth mesh uses Cesium. Keep own licensed terrain import fallback. |
| OpenMapTiles self-hosted | Import/setup vector tile stack and licence/hosting notices; no implicit hosted API. |
| MapTiler Cloud Free | Configure key and eligible NC/R&D purpose; production requires appropriate paid plan. |
| Classic Esri World Imagery | Blocked exact deployment entitlement; remove implicit/default direct tile and metadata-query access during migration. |
| ArcGIS Location Platform basemaps | Configure scoped token/OAuth; approved product style/tiles and allowance, separate from classic Esri. |
| Google Photorealistic 3D Tiles; Cesium ion Community | Configure separate billing/eligibility gates; Cesium mode, visible credits, storage/export constraints and conservative limits. |
| Overture base/buildings/divisions/transportation; places/addresses | Default/Import extend existing bounded DuckDB/file ingestion; per-theme/source notices. No production use of inspection PMTiles entitlement. |
| OpenBuildingMap downloads; hosted mirror/API | Downloads Default/Import existing pipeline; mirror Blocked until supported service rights. Do not infer mirror rights from ODbL downloads. |
| WorldPop | Default extend existing truthful year/resolution extraction; optional approved credential raises API limits but is Configure. |
| OpenInfraMap source data | Default/Import infrastructure from licensed OSM extracts; hosted exports/tiles separate setup/permission. |
| Census boundaries; DataSF neighborhoods | Blocked reuse verification, then explicit regional imports. |

### Weather, Hazards, Science And Astronomy

| Offerings | Implementation and initial state |
| --- | --- |
| Open-Meteo Weather/Air Quality; RainViewer | Opt-in NC/personal/educational endpoints with regional weather/radar adapters and coverage/time disclosure. |
| OpenWeather basic Free; One Call | Configure separate basic key and billed One Call subscription. Product-specific observations/forecast and local overage stops. |
| NOAA/NWS; NHC/SWPC | Default regional point/forecast/alerts, cyclone/advisory and probabilistic space-weather adapters; attribution/identifying headers and regional coverage. |
| NOAA GFS/AWS; ECMWF designated Open Data | Default/Import bounded forecast inventories/range requests and optional GRIB codec worker/job. Separate model issue/valid time and scalar/vector units. |
| nowCOAST | Blocked unresolved access/redistribution; fixed WMS products after review. Lightning density is not raw strikes. |
| OpenAQ; NASA FIRMS | Configure and Blocked where source/hosted scope unresolved. Station measurements vs modeled fields; real FIRMS detections, MAP_KEY quota/status and non-NASA layer review. |
| EONET; USGS earthquake feeds; USGS WaterData; Macrostrat | Blocked exact rights review; then metadata/events, revised quake depth/time, modern gauges and attributed regional geology. Optional WaterData key is Configure; do not inherit retiring WaterServices terms. |
| JPL Horizons | Blocked integration-policy resolution, then approved backend batch/cached workflow only; no prohibited direct embedding. Local Sun/Moon calculations need no Horizons call. |
| Copernicus Marine | Configure/Import account/Toolbox and bounded depth/time/model extraction. |

### Aircraft, Space And Maritime

| Offerings | Implementation and initial state |
| --- | --- |
| adsb.lol | Default bounded viewport aircraft states, ODbL attribution, truthful timestamps/coverage, SI normalization and capped observed trails. |
| OpenSky | Opt-in anonymous eligible research only; authenticated Configure. Operational Meridian features blocked without written grant even for nonprofits. |
| adsbdb | Blocked data/route publication rights; separate enrichment adapter, no unauthorized persistent route dataset. |
| ADS-B Exchange; FlightAware; Aviationstack | Configure separate paid Community/Enterprise, billed personal/business and NC Free offerings; product/eligibility limits. No invented free Exchange tier. |
| CelesTrak GP | Default standard GP with approved group allowlist, bounded fetch/cache and epoch-aged SGP4 prediction. SupGP/broader rights separate Blocked products. |
| Space-Track | Configure approved account/session and product-level redistribution; only eligible basic SSA products. |
| AISstream; MarineTraffic | Configure; AISstream reuse Blocked pending permission, MarineTraffic supported contract/trial only. Bounded server WebSocket snapshots/reconnect/TTL; received position time separate from connection status. |
| Launch Library 2 | Default bounded metadata/cache within 15/hour/IP; optional higher-rate token Configure, media separate, no invented ascent telemetry. |
| FAA registry | Blocked reuse, then Import daily bulk identity enrichment without claiming international coverage. |

### Cameras, Street Imagery And Radio

| Offerings | Implementation and initial state |
| --- | --- |
| Mapillary licensed copies; API/viewer | Default/Import eligible CC BY-SA images with capture dates/credits. API Configure client token and Blocked unresolved API restrictions until reviewed. |
| Google Street View; Windy Webcams | Configure credentials/billing or Free tier; Street View map-combination gate, Windy unresolved eligibility/media operations Blocked. Expiring URLs are not permanent media. |
| Radio Browser metadata; linked streams/artwork | Default geolocated metadata, bounded mirrors/cache; linked broadcasts/artwork Blocked until rightsholder scope established. Explicit playback only; disclose direct broadcaster connection, no autoplay or presumed music licence. |
| TfL JamCams; Digitraffic | TfL Configure registered token; Digitraffic Default licensed images. Real capture cadence/freshness, TfL no cropping/branding compliance. |
| DriveBC; Ontario 511; Transport NSW; Norway Vegvesen | Catalogue adapters where catalogue grant verified; linked media Blocked. Ontario/NSW/DATEX credential paths Configure and price/access checks as applicable. |
| Calgary; Austin; TxDOT; Caltrans CWWP2; DelDOT; Tallinn; Tarktee; Warendorf | Blocked unresolved dataset/media/access scope; source-specific registered catalogue/media adapters only after review. Warendorf requires applicable permission. No generic proxy to arbitrary camera URLs. |

### Transit, Events, Search And Routing

| Offerings | Implementation and initial state |
| --- | --- |
| GTFS/GTFS-RT; GBFS including BCycle/Lyft | Library/spec parser plus per-feed catalogue/permission setup. Feed format is not a data grant; join schedules for verified mode/route identity rather than guesses. |
| Entur; Queensland TransLink | Default supported open feeds, required identification, protobuf validation, regional vehicles and status. |
| MBTA/MassDOT; CapMetro; Metro Transit; OVapi; HSL | Blocked agency terms until reviewed; credentials Configure where needed (MBTA V3 distinct from GTFS-RT). |
| WFIGS/NIFC; InciWeb | Blocked express reuse/republication scope; then separately dated perimeters and source-linked incidents with accuracy disclaimers. |
| GDELT DOC 2.0; Google News RSS | GDELT Default metadata/citations, publisher media separate; Google News Opt-in personal NC and never implicit commercial fallback. |
| Nominatim public | Default exact submitted lookup; fix existing external typeahead to local cache only or an approved self-hosted/contracted autocomplete provider. Global <=1 request/second, caching and switchability. |
| Photon public; Overpass instances | Blocked hosted permission/operator-policy review; explicit origins/pacing and source ODbL. Own reviewed engines can be configured separately. |
| FOSSGIS routing/Overpass | Opt-in compliant eligible/incidental usage only, blocked for substantial commercial dependency. Do not equate public router availability with self-hosted software rights. |
| OSRM; Valhalla; GraphHopper self-hosted | Import/setup optional local engines with versions/data coverage and bounded routing interfaces; retain existing local Dijkstra default. |
| GraphHopper hosted Free | Configure key plus NC eligibility, separate paid offering. |
| TomTom; HERE | Configure credentials and exact plan/product entitlement; unresolved hosted grants Blocked. Bounded traffic tile/segment lifecycle, genuine timestamps, no simulated live substitute. |
| Google Geocoding/Routes Essentials/Places | Configure per-product billing/scoped auth and field masks; display/retention/export gates and independent usage windows. |
| SerpApi | Configure existing transport, explicit enablement and Blocked unresolved free-commercial scope; reviewed paid scope separately. Recheck existing place/research fallbacks. |
| OpenAI API/Realtime | Configure paid backend credentials; preserve validated tool allowlist, optional explicit mic permission and ephemeral browser Realtime token. No ChatGPT/Codex subscription inference or free API promise. |

### Software And Assets

| Offerings | Implementation and initial state |
| --- | --- |
| MapLibre; Three.js; deck.gl; CesiumJS; Babylon.js; satellite.js; Blender/glTF | Library/tool catalogue with licence notices. Retain MapLibre; add Cesium/satellite.js as needed. Three/deck/Babylon are optional capability-dependent components, not mandatory competing renderers; do not import all at startup. |
| Poly Haven downloads/API | Default CC0 Import plus separately credited bounded API catalogue; explicit asset download. |
| NASA 3D Resources | Import eligible per-asset/media/IP review; no blanket logo/endorsement permission. |
| Sketchfab free assets/Download API | Import per-model licence and extraction rights; OAuth/app credentials Configure for API, not one shared API key. |
| TurboSquid; CGTrader selected free assets | Import exact seller/model licence and extraction-protection approval; no invented catalogue API. Approved CGTrader API Configure. |
| TeleGeography current raw data; screenshots/references; GEV historical cable snapshot | Current data Configure supported negotiated contract/delivery, not free. Specified screenshots Default/Import CC BY-SA, not interactive embedding. Historical NC snapshot Opt-in plus provenance Blocked until authentic grant confirmed. |

Asset manifest: provenance, exact licence/proof, attribution, content hash, allowed distribution/export, units/axes/pivot, bounding size and LOD. Models are optional visual representations, not source measurements or proof of identity. Use simple procedural aircraft/vessel/satellite symbols until real assets are approved. Never copy GEV bundled assets/data solely because files exist there.

## 6. Reuse GEV Patterns Without Copying Its Risks

Reference paths below are relative to `gods-eye-view/`. Port concepts and pure normalization into Python/browser modules; do not embed its Node/Vite backend or import Cesium-specific layers into MapLibre. Inspect applicable code/dependency/data licences before copying.

- `server/providers/aircraft/{opensky,adsb-lol,tracks,enrichment}.js`, `src/sources/live/aircraft.js`: SI/altitude/timestamp normalization, singleflight and region fallback. Replace OpenSky-first default with eligible adsb.lol; fix enrichment pacing/size/cache rights.
- `server/providers/space/{celestrak,launch-library}.js`, `src/layers/satellites/tracking.js`: epoch/propagation separation and shared frame time. Add group allowlist, body cap, bounded cache and maximum stale age.
- `src/layers/recentImagery/{source,catalog,model}.js`: bounded CMR/GIBS search and acquisition cards. Preserve complete multipolygon geometry and centralized quota admission.
- `server/providers/wind/{gfs,ifs}.js`, `weather.js`, `cyclones.js`: ranged GRIB, units and forecast time distinctions. Do not copy unapproved nowCOAST entitlement or equate lightning density with raw detections.
- `server/providers/vessels/{ais-live,ais-store}.js`: server-side AIS connection/store. Apply permission gates, observation TTL and cancellation.
- `server/providers/{transit,gbfs}.js`, `src/data/transitFeeds.js`: pinned feeds, protobuf and regional lifecycle. Correct default rights assumptions, GBFS singleflight and exact-origin validation including userinfo/ports.
- `server/providers/cctv/`, `radio/`: registered source IDs and bounded catalogues. Use radio's stronger DNS-pinned transport pattern; impose media body caps even without Content-Length, license images independently and never reuse browser-like bypasses.
- `server/providers/{firms,firePerimeters,traffic}.js`: source-specific parsing/limits. Fix unlimited-age traffic stale retention and do not treat local daily counters as account monthly quotas.
- `server/providers/regional/{weather,news}.js`: locality normalization only; do not copy Open-Meteo/Google News hardcoded primary defaults.
- `src/maps/{google3d,imagery,terrain}.js`: Cesium factories/credits only after policy gate; reduce GEV's very large tileset memory settings for desktop/mobile defaults.
- `server/providers/openai/realtime.js`: ephemeral-token flow, not experimental Codex credential reuse or camera-screenshot transmission without explicit consent.

## 7. Delivery And Migration Order

1. Catalogue, policy tests, Settings, DPAPI storage, local broker security and quota/runtime foundation. All matrix offerings visible with truthful implementation/setup status; a catalogue entry alone is not a completed adapter.
2. Route existing OpenFreeMap/OSM/Overture/OpenBuildingMap/WorldPop/SerpApi/OpenAI/terrain/imagery through policy. Preserve stored workspace and caches, version settings migrations, gate existing environment keys, fix Nominatim autocomplete, and fall back to approved streets/flat terrain without deleting user work.
3. First end-to-end slice: adsb.lol live symbols/details, CelesTrak predicted tracks, LL2 launches, NOAA/NWS, GDELT, Digitraffic, Entur/Queensland and bounded NASA imagery. Add shared source/time/selection/attribution UI before additional adapters.
4. Authenticated and NC slices: basic OpenWeather, CDSE, FIRMS where rights verified, TfL, Mapillary where API cleared, Open-Meteo/RainViewer opt-in; then remaining paid/enrichment/transit/camera/traffic providers when supported access and grants permit. Each adapter needs fixtures and disable/quota tests before activation.
5. Explicit download/processing/engine/asset workflows, GFS/ECMWF and scientific products; validate optional dependencies and bounded jobs. No blanket portal scraping to fill catalogue gaps.
6. Lazy Cesium mode and renderer switching using own/approved data first; then configured ion/Google 3D. Validate semantic parity/fallback and restricted media contexts before enabling paid 3D capabilities.
7. Complete each remaining catalogue row with reviewed adapter/import/setup or documented permission/access blocker. Maintain an exhaustive coverage test and visible status; do not declare a blocked service integrated or a trial production-ready.

Public hosting, Meridian user accounts/tenancy, multi-machine credential sync, legal clearance, continuous global archives, safety-grade navigation/aviation, turnkey local SDR hardware, and building a new general-purpose analytics product are out of scope. Remote deployment requires a separate authenticated architecture; never relax the loopback restriction as a shortcut.

## Validation And Release Gates

- Run existing `python -B -m backend.test_isolated` and `node --test UI/map-actions.test.cjs UI/app.test.cjs UI/map-data.test.cjs UI/spectral-terrain.test.cjs`; extend the isolated runner for new suites and transports. Do not import the configured server casually or read real credentials during tests.
- Policy truth table: free/keyless, credentialed-free, NC, paid/trial, unresolved, missing assets/engine, renderer mismatch, expired acknowledgement, disabled fallback and existing environment-key migration. Matrix coverage includes software/download/public-viewing rows.
- Secret tests: DPAPI round-trip with isolated current-user storage, corruption/decrypt failure, restart, replace/delete, environment precedence, no plaintext/log/response/browser/agent leakage, cross-origin/CSRF/Host rejection and revision conflicts.
- Transport tests: malicious host/redirect/port/userinfo, credential forwarding, compressed oversized bodies, malformed JSON/CSV/PBF/GRIB, provider 401/429/5xx, token refresh races, bounded paging/queue/singleflight, cancellation and maximum stale expiry.
- Quota tests: concurrent tabs, restart reservations, failed/ambiguous billable requests, request-vs-event-vs-processing-unit counts, window boundaries, exhausted quotas and explicit overage setting. SDK paths disclose/count what is actually enforceable.
- Fixture semantics: aircraft altitude/age/units, predicted orbit epoch, AIS position age, forecast issue/valid times, revised earthquakes, thermal detections vs perimeters, camera capture cadence, GTFS differential rejection/schedule joins, GBFS partial feeds, raster NoData/zero/year/CRS and attribution.
- UI tests: accessible Settings focus/keyboard/mobile layout, write-only inputs and status, render-switch teardown, hidden-tab pause, rapid enable/disable/credential replacement, no startup polling storm, offline/failure states, preserved map actions/undo, prohibited export/media combinations and current-policy checks on restored layers.
- Manual desktop/mobile checks: lazy renderer asset loading, WebGL failure/context loss, memory/LOD budgets, globe/dateline/polar/altitude behavior, terrain elevation references, reduced motion, visible credits and usable fallback map.
- Live smoke tests are explicit per-provider opt-in after credentials/terms verification; bounded requests only, never CI registrations/purchases/model downloads. Label test quota consumption and record product/date. Do not promise current service availability from fixtures.

No open user design decisions remain. Exact vendor grants, unsupported APIs, and optional codec/install choices are per-service release blockers with visible status, not grounds to invent access or silently weaken the confirmed rules.
