# Meridian Service Access and Free-Use Matrix

## Scope and Meaning

Prepared October 15, 2026 from the [engineering blueprint](Meridian_Live_Earth_Engineering_Blueprint.docx), [feature ideas](MERIDIAN_FEATURE_IDEAS.md), Gods Eye View's integrations, and current official documentation/terms. This is a procurement and engineering reference, not legal clearance or a service-availability guarantee.

- **Free** describes a no-charge service, quota, trial, dataset, or software licence. It does not include your hosting/compute costs.
- **Non-Commercial use** and **Commercial Use** describe permission under the specified free offering. Paid production options and restrictions are stated explicitly.
- **Yes, conditional** means attribution, data-licence, fair-use, or product-specific obligations still apply.
- **Unverified** means an explicit grant could not be confirmed. It does not mean permission is prohibited, and must not be treated as permission granted.
- **API Key** identifies required authentication. Account login, OAuth credentials, bearer tokens, app-identifying headers, and secret API keys are different things.
- Dataset licences do not grant unlimited use of every server hosting the data. A public endpoint does not prove commercial, caching, export, or redistribution rights.

Official source links are attached to the relevant service names and qualifications. No account registrations, purchases, authenticated API calls, or model downloads were performed.

## Maps, Imagery, Terrain, and Geographic Data

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [OpenFreeMap public hosting](https://openfreemap.org/) | Yes; best-effort public map hosting | Yes; attribution and service terms | Yes; explicitly permitted, with attribution | No key or registration |
| [OpenStreetMap data / Geofabrik extracts](https://www.openstreetmap.org/copyright) | Yes; [public downloads](https://www.geofabrik.de/data/download.html) | Yes; ODbL | Yes; ODbL attribution and database obligations | No for extracts; editing/upload services separate |
| [OSM standard raster tile server](https://operations.osmfoundation.org/policies/tiles/) | No-charge access, limited capacity | Yes for policy-compliant interactive viewing | Conditional; no SLA, no offline/prefetch/bulk use; not an unlimited production backend | No; identifying headers and visible attribution |
| [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) | Yes; public-domain downloads | Yes | Yes; public domain | No |
| [NASA GIBS / Worldview Snapshots](https://nasa-gibs.github.io/gibs-api-docs/) | Yes; public imagery services | Yes for unrestricted products | Yes for unrestricted NASA data; [third-party/product exceptions](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance) | No for public imagery/snapshots |
| [NASA CMR public metadata search](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) | Yes; throttling applies | Yes | Yes for public discovery; dataset reuse rights are separate | No for public records; token for restricted records |
| [NASA Earthdata product downloads](https://urs.earthdata.nasa.gov/documentation/for_users/data_access) | Yes for open data | Dataset-dependent | Yes for unrestricted NASA-led products; other collections need separate checks | Usually Earthdata account/login or bearer token, not a CMR key |
| [Copernicus Data Space STAC / OData catalogue](https://documentation.dataspace.copernicus.eu/APIs/STAC.html) | Yes | Yes | Yes for Sentinel discovery/data under [free, full, open terms](https://dataspace.copernicus.eu/terms-and-conditions); other collections separate | Public metadata ordinarily anonymous; some search modes authenticated |
| [Copernicus Sentinel product downloads](https://documentation.dataspace.copernicus.eu/APIs/OData.html#product-download) | Yes; fair-use/download quotas | Yes for eligible products | Yes for Sentinel data with source notices | CDSE account and bearer token |
| [CDSE Sentinel Hub processing](https://documentation.dataspace.copernicus.eu/Quotas.html) | 10,000 requests and 10,000 processing units/month for general users | Yes within quota | Yes; [commercial services may be built on top](https://documentation.dataspace.copernicus.eu/FAQ.html), subject to source and service terms | CDSE account, OAuth client ID/secret and access token |
| [Standalone Sentinel Hub / Planet](https://www.sentinel-hub.com/faq/#which-pricing-plan-activated-during-30-days-trial-there-difference-account-if-i-subscribe) | 30-day trial; not a verified permanent free tier | Trial use | No commercial trial use; subscription required | Account and OAuth credentials/token |
| [OpenTopography APIs](https://opentopography.org/developers) | Free personal key, eligibility and quotas | Yes within access rules | Commercial-software integration requires paid Enterprise key; dataset reuse is separate | Required; free individual key or paid Enterprise key |
| [Mapterhorn terrain](https://mapterhorn.com/data-access) | Public tiles/downloads | Conditional on [source licences](https://mapterhorn.com/attribution) | Source-dependent; blanket hosted commercial permission unverified | No key in documented public routes |
| [Re:Earth Terrain](https://terrain.reearth.land/) | Yes; best-effort hosting | Conditional on source licences | Source-dependent; blanket hosted commercial grant unverified | No key or signup |
| [Mapzen Terrarium / AWS terrain tiles](https://registry.opendata.aws/terrain-tiles/) | Yes; unsigned public S3 reads | Conditional on source licences/credits | Source-dependent; blanket commercial grant unverified; review [terrain attribution/licences](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) | No AWS account or key for public access |
| [OpenMapTiles self-hosted stack](https://github.com/openmaptiles/openmaptiles/blob/master/LICENSE.md) | Software/schema free; hosting costs yours | Yes under code/schema/data licences | Yes under BSD/CC BY/ODbL obligations; not free hosted API access | No inherent key |
| [MapTiler Cloud free plan](https://www.maptiler.com/cloud/pricing/) | 5,000 map sessions / 100,000 API requests/month; counting varies | Yes | [Not commercial production](https://www.maptiler.com/terms/cloud/#FreePlan); commercial R&D allowed; paid plan for deployment | Required; own account/key |
| [Esri classic World Imagery MapServer](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer) | Public keyless endpoint exists; unrestricted free entitlement unverified | Third-party deployment rights unverified | Unverified; reachability is not permission | No token technically required by this endpoint |
| [ArcGIS Location Platform basemaps](https://location.arcgis.com/help/) | Monthly allowance; e.g. 2 million tiles / 1,000 sessions, product-dependent | Yes under authenticated service terms | Yes within allowance and [platform licence](https://location.arcgis.com/help/licensing-and-attribution/); not every Living Atlas/classic service | Scoped API-key token or OAuth; account |
| [Google Photorealistic 3D Tiles](https://developers.google.com/maps/billing-and-pricing/pricing) | 1,000 billable events/month on verified global schedule; paid overage | Yes under platform terms | Yes within allowance; [storage/export/attribution restrictions](https://developers.google.com/maps/documentation/tile/policies) | API key and billing-enabled project |
| [Cesium ion Community](https://cesium.com/platform/cesium-ion/pricing/) | Individual quota: 10 GB storage / 15 GB monthly streaming | Eligible personal/unfunded educational use | Evaluation allowed; not blanket free commercial production permission; revenue/funding/integration eligibility matters | Account and ion access token |
| [Overture base/buildings/divisions/transportation](https://docs.overturemaps.org/attribution/) | Yes; public files | Yes; ODbL and source notices | Yes; ODbL obligations | No for [public cloud files](https://docs.overturemaps.org/getting-data/cloud-sources/) |
| [Overture places/addresses](https://docs.overturemaps.org/attribution/) | Yes; public files | Yes under source-specific licences | Yes where source terms permit; no single blanket licence | No for public files |
| [OpenBuildingMap downloadable dataset](https://www.openbuildingmap.org/) | Public GeoPackage downloads | Yes; ODbL | Yes; ODbL obligations | No key documented for downloads |
| OpenBuildingMap hosted mirror/API | Unverified service offer | Unverified service rights | Unverified service rights; download licence does not grant unlimited mirror access | Unverified |
| [WorldPop open datasets/API](https://www.worldpop.org/faq/) | Yes; public data and bounded API | Yes; CC BY 4.0 | Yes; commercial use expressly permitted with attribution | [No up to 1,000 REST calls/day](https://www.worldpop.org/sdi/api_rate_limits/); approved key above that |
| [OpenInfraMap source data](https://openinframap.org/about) | OSM-derived data free; turnkey exports may cost | Yes; ODbL | Yes under source data licence; no blanket hosted tile/API entitlement | No for raw OSM extracts; export service separate |
| [US Census geographic boundary files](https://www.census.gov/geographies/mapping-files.html) | Public government files | Download access public; exact reuse grant not reverified | Exact dataset grant not reverified in this review | No for public downloads |
| [DataSF neighborhood boundaries](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Analysis-Neighborhoods/p5b7-5n3h/about_data) | Public-data listing; verification blocked | GEV reports PDDL; official dataset grant not reverified | Not reverified; do not infer from portal availability | Dataset/API dependent |

## Weather, Hazards, Science, and Astronomy

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [Open-Meteo Weather / Air Quality](https://open-meteo.com/en/terms) | Free hosted endpoint; non-commercial only, rate limits | Yes within definition/limits | No free hosted commercial use; paid subscription. CC BY data licence does not waive API terms | None for Free; customer key for paid endpoint |
| [OpenWeather basic Free plan](https://openweathermap.org/faq) | Yes; product-limited free plan | Yes with attribution | Yes; commercial API use expressly permitted, product/credit conditions | Account/API key |
| [OpenWeather One Call](https://openweathermap.org/faq) | 1,000 calls/day allowance on separate billed subscription | Yes under subscription terms | Yes under subscription terms; overages automatically billable | Account/API key and pay-as-you-call subscription |
| [NOAA / NWS weather API](https://www.weather.gov/documentation/services-web-api) | Yes; rate-limited public API | Yes; [free for any purpose](https://www.weather.gov/disclaimer) for applicable agency content | Yes; agency-content use, notices and third-party exceptions | No current key; identifying User-Agent required |
| [NOAA GFS on AWS](https://registry.opendata.aws/noaa-gfs-bdp-pds/) | Yes; public data retrieval | Yes | Yes; [NOAA states no use restrictions](https://www.noaa.gov/big-data-project-frequently-asked-questions); own cloud compute separate | No for public retrieval |
| [NOAA nowCOAST radar / lightning density](https://www.nauticalcharts.noaa.gov/learn/nowcoast.html) | Public viewer/WMS; explicit fee/quota terms unverified | Public application use supported | Commercial-mariner use supported; blanket redistribution rights unverified | Complete auth policy unverified; help page blocked |
| [NHC advisories](https://www.nhc.noaa.gov/aboutrss.shtml) / [NOAA SWPC](https://www.swpc.noaa.gov/content/data-access) | Public feeds | Yes for agency-authored content | Yes for agency-authored content under NWS policy; third-party products separate | No key documented for public feeds |
| [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data) | Yes for designated Open Data distribution | Yes; CC BY 4.0 | Yes; designated open products, terms/attribution; not every ECMWF API | No for anonymous open files/cloud retrieval |
| [RainViewer public API](https://www.rainviewer.com/api/transition-faq.html) | Personal/educational public access | Personal/educational only verified | Not covered by public grant; separate commercial permission needed, offering/pricing unverified | No for public API |
| [OpenAQ](https://docs.openaq.org/about/terms) | Free account/API within rate limits | Source-specific licences/attribution and hosted terms | Blanket free-commercial grant unverified; source licences vary and competing service uses restricted | Free account/API key required |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/) | Free, transaction-limited API | NASA product sharing with credit; layer-specific exceptions | NASA-led unrestricted data allows commercial reuse under [NASA guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance); hosted/API and non-NASA layer scope needs confirmation | Free FIRMS MAP_KEY; separate archives may need Earthdata Login |
| [NASA EONET](https://eonet.gsfc.nasa.gov/docs/v3) | Public metadata API | NASA metadata sharing; linked sources separate | NASA metadata reuse under general policy; blanket hosted-service/media rights unverified | No key in documented v3 public API |
| [USGS earthquake GeoJSON feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php) | Public programmatic feeds | Source/reuse scope not independently reverified | Agency data generally open; exact feed/contributed-content licence not verified because reuse policy unavailable | No in public summary-feed protocol |
| [USGS WaterData API](https://api.waterdata.usgs.gov/) | Public anonymous access; key raises limits | Public access; modern reuse terms unverified | Modern hosted/data reuse scope not independently verified | Optional email-issued api.data.gov key |
| [Macrostrat](https://macrostrat.org/api/v2/meta) | Public API; explicit service quota/fee terms unverified | Data: CC BY 4.0 | Data: yes with attribution; hosted-commercial entitlement unverified | No key documented for public routes |
| [NASA JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | Public [fair-use service](https://ssd-api.jpl.nasa.gov/doc/) | Subject to fair-use integration limits | Commercial entitlement unverified; direct website embedding prohibited by API policy | No key; identifying User-Agent, serialized requests, caching/backoff |
| [Copernicus Marine](https://marine.copernicus.eu/user-corner/service-commitments-and-licence) | Yes; account/Toolbox access | Yes with licence/acknowledgement | Yes; no-cost commercial use subject to licence/attribution | Free account credentials, not a separate API key |

## Aircraft, Satellites, Maritime, and Launches

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [OpenSky REST](https://openskynetwork.github.io/opensky-api/rest.html) | Limited anonymous/account credit quotas | [Nonprofit research/education only by default](https://opensky-network.org/about/terms-of-use); operational apps need written licence even if nonprofit | No under free default grant; written licence required | Anonymous latest states: none; authenticated access: OAuth2 credentials/bearer token |
| [adsb.lol public API](https://www.adsb.lol/docs/open-data/api/) | Yes; public API, dynamic limits | Yes; ODbL | Yes; ODbL explicitly includes commercial use, attribution/database duties | No key documented for current public API |
| [adsbdb API](https://www.adsbdb.com/) | Public free GET access | Data licence unverified; route publication/copying needs permission | Data rights unverified; MIT code licence does not license route dataset | No key for documented public GET routes |
| [ADS-B Exchange API](https://www.adsbexchange.com/community/developer-hub/) | No durable general free API tier verified | No verified free tier; paid Community is non-commercial | No verified free commercial tier; paid Enterprise agreement | RapidAPI key for Community; issued key for Enterprise |
| [FlightAware AeroAPI](https://www.flightaware.com/commercial/aeroapi/) | Personal monthly allowance up to $5, $10 for feeders; usage beyond billable | Personal/academic tier, not every nonprofit use | Free Personal allowance not business; paid Standard/Premium for business/B2B | Account and `x-apikey` |
| [Aviationstack](https://aviationstack.com/product) | 100 requests/month on Free | Yes; personal/non-commercial | No on Free; paid commercial plan | Account/API key |
| [CelesTrak GP](https://celestrak.org/NORAD/documentation/gp-data-formats.php) | Yes; public orbital files, caching limits | Standard basic-data redistribution with citation; SupGP separate | Standard basic-data redistribution not NC-limited; broader/SupGP commercial rights unverified | No for public downloads |
| [Space-Track](https://www.space-track.org/documentation) | No-charge approved-account access | Basic SSA redistribution with citation; other products need approval | Basic-data redistribution approved without NC condition; broader products/rights need review | Approved account, credentials/session; no conventional key documented |
| [AISstream](https://aisstream.io/documentation) | Free WebSocket service advertised | Data reuse licence unverified | Commercial/republication rights unverified | GitHub account and API key; server-side connection |
| [MarineTraffic API](https://servicedocs.marinetraffic.com/) | Paid/sales-supported; complimentary trial only by agreement | No general free public-app grant; trial agreement controls | No general free production grant; paid contract; trial internal-business only | Service-specific API key |
| [Launch Library 2 / TheSpaceDevs](https://thespacedevs.com/llapi) | 15 calls/hour/IP on production free API | Yes under broad [TSD data-use terms](https://raw.githubusercontent.com/TheSpaceDevs/Tutorials/main/faqs/faq_TSD.md) | Yes within same quota/terms; avoid unchanged raw passthrough as requested; linked media separate | None at free quota; token for higher rate |
| [FAA aircraft registry downloads](https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download) | Yes; public daily bulk download | Download access established; broad reuse grant not verified | Dataset-specific republication/commercial grant not verified in checked pages | No for bulk download |

## Cameras, Street Imagery, and Radio

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [Mapillary licensed images](https://help.mapillary.com/hc/en-us/articles/115001770409-Licenses) | Yes | Yes; CC BY-SA 4.0 | Yes; attribution and ShareAlike for adaptations | None for licensed copies; hosted API separate |
| [Mapillary API/viewer](https://help.mapillary.com/hc/en-us/articles/8348198426396-Mapillary-FAQ) | Free company/all-use access advertised | Conditional on API terms | Free company use advertised; full contractual API restrictions not verified | Registered application/client token |
| [Google Street View](https://developers.google.com/maps/documentation/streetview/usage-and-billing) | Static 10,000 / Dynamic 5,000 monthly events; paid above | Conditional platform use | Yes within allowance; not open imagery and [map-combination restrictions](https://cloud.google.com/maps-platform/terms) | API key, enabled API and billing |
| [Windy Webcams API](https://api.windy.com/webcams) | Restricted Free tier | Conditional private/application use | Free commercial/institutional eligibility unverified; paid Professional also has [media restrictions](https://account.windy.com/agreements/windy-webcams-api-terms-of-use) | Registered private key |
| [Radio Browser metadata/API](https://docs.radio-browser.info/) | Yes | Yes; public-domain station metadata | Yes for dedicated metadata, not linked streams/artwork | No; descriptive User-Agent requested |
| Radio Browser linked streams/artwork | Station-dependent | Rightsholder-specific | Rightsholder-specific; not granted by directory licence | Station-dependent |
| [TfL JamCams](https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service) | Yes | Yes; image/branding/freshness conditions | Yes including JamCam images; no cropping, attribution | [Registered access token required](https://tfl.gov.uk/info-for/open-data-users/unified-api) |
| [Digitraffic Finland cameras](https://www.digitraffic.fi/en/terms-of-service/) | Yes | Yes; CC BY 4.0 camera data/images | Yes with attribution/modification notices | No; identifying header recommended |
| [DriveBC HighwayCams catalogue](https://catalogue.data.gov.bc.ca/api/3/action/package_show?id=bc-highwaycams) | Yes for catalogue | OGL-BC catalogue; linked media unverified | OGL-BC catalogue; linked media unverified | No key documented for catalogue; camera API separate |
| [Ontario 511 cameras](https://data.ontario.ca/dataset/traffic-cameras) | Catalogue free; API cost not verified | OGL-Ontario catalogue; media scope unverified | Licensed catalogue yes; linked images/streams not automatically licensed | [Key required for 511 API](https://511on.ca/developers/doc) |
| [Transport NSW LiveTraffic](https://opendata.transport.nsw.gov.au/data/dataset/live-traffic-cameras) | Public catalogue | CC BY 4.0 catalogue; media scope unverified | Catalogue yes; unrestricted camera-media reuse unverified | Endpoint-specific; gateway credentials |
| [Statens vegvesen Norway cameras](https://dataut.vegvesen.no/en/dataset/webkamera) | Open catalogue/services | NLOD catalogue; linked-image licence unverified | NLOD catalogue yes; linked media unverified | WFS registration optional; DATEX credentials required |
| [Open Calgary traffic cameras](https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa) | Public portal | Dataset/media licence unverified; portal verification blocked | Unverified; general site licence is not portal clearance | Unverified |
| [Austin traffic cameras](https://data.austintexas.gov/Transportation-and-Mobility/Traffic-Cameras/b4k4-adkb) | Public portal | Dataset/media licence unverified | Unverified | Unverified |
| [TxDOT cameras](https://www.txdot.gov/discover/live-traffic-cameras.html) | Public viewing | Reuse unverified | Reuse unverified | No public API contract verified |
| [Caltrans CWWP2](https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm) | Public exports/viewing | Owned information generally public domain; camera media scope unverified | Applicable public-domain information yes; media/third-party rights unverified | No key documented for exports |
| [DelDOT cameras](https://deldot.gov/map/index.shtml) | Public viewing | Reuse unverified | Reuse unverified | No API contract verified |
| [Tallinn cameras](https://ristmikud.tallinn.ee/) | Public viewing | Reuse unverified | Reuse unverified | No API contract verified |
| [Tarktee / Transpordiamet](https://tarktee.transpordiamet.ee/) | Public viewing/catalogue | Camera-media grant unverified | Camera-media grant unverified | Endpoint access unverified |
| [Warendorf webcam](https://www.warendorf.de/de/impressum/) | Official website viewing | Reuse beyond statutory exceptions needs written permission | No free reuse grant; written permission beyond exceptions | No for viewing; no API contract verified |

## Transit and Bikeshare

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [GTFS / GTFS-Realtime](https://gtfs.org/getting-started/publish/) | Free specification; feed access varies | Per-agency data licence | Per-agency licence; format grants no operator-data rights | Agency/endpoint-dependent |
| [GBFS feeds, e.g. BCycle/Lyft](https://gbfs.org/documentation/data-policy/) | Free specification; systems vary | Per-system licence/terms | Per-system licence; inspect actual feed licence | Operator-dependent |
| [Entur open transit data](https://developer.entur.no/terms-of-service) | Yes | Yes; NLOD 2.0 | Yes with source terms/attribution | No for open services; `ET-Client-Name` required |
| [TransLink Queensland](https://translink.com.au/about-translink/open-data) | Yes | Yes; CC BY 4.0 plus agency terms | Yes with source terms/attribution | No authentication required |
| [MBTA / MassDOT](https://www.mbta.com/developers/gtfs-realtime) | Published feeds; free V3 key | Governing developer licence; grant unverified in this review | Grant unverified; governing PDF not parsed | GTFS-RT key not documented; V3 key for full limits |
| [CapMetro](https://www.capmetro.org/developertools) | Published feeds | Agency grant unverified here | Agency grant unverified here | Endpoint-specific |
| [Metro Transit](https://svc.metrotransit.org/) | Published feeds | Agency grant unverified here | Agency grant unverified here | Endpoint-specific |
| [OVapi](https://gtfs.ovapi.nl/README) | Published feeds | Agency grant unverified here | Agency grant unverified here | Endpoint-specific |
| [HSL](https://www.hsl.fi/en/hsl/open-data) | Published feeds | Agency grant unverified here | Agency grant unverified here | Endpoint-specific; docs blocked |

## Event Context and News

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [NIFC WFIGS fire perimeters](https://www.arcgis.com/sharing/rest/content/items/d1c32af3212341869b3c810f1a215824?f=pjson) | Yes; public feature service | Ordinary informational use subject to accuracy/non-legal-use disclaimer | No NC prohibition stated; express commercial licence not established | No for public query endpoint |
| [InciWeb incident pages](https://inciweb.wildfire.gov/) | Public viewing/source links | Linked information public; automated republication terms not reverified | Unverified for republication; do not infer media rights from public pages | No for viewing; no public API entitlement verified |
| [GDELT DOC 2.0](https://www.gdeltproject.org/about.html#termsofuse) | Yes; public project data | Yes with citation/link | Yes; commercial/government use expressly permitted; publisher articles/media separate | No |
| [Google News RSS](https://www.google.com/intl/en_us/terms_google_news.html) | No-charge feeds | Personal non-commercial use | No under stated personal/non-commercial terms | No; linked publisher content has separate rights |

## Geocoding, Routing, Traffic, and AI

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [Nominatim public geocoder](https://operations.osmfoundation.org/policies/nominatim/) | Yes for light, policy-compliant use | Yes; max 1 request/second; no autocomplete | Conditional; same limits, caching, attribution, switchability; self-host/pay for scale | No; app identification required |
| [Photon public geocoder](https://photon.komoot.io/) | Yes; reasonable-use demo | Yes under fair use | Explicit hosted commercial grant unverified; no NC ban in [public policy](https://github.com/komoot/photon), no SLA | No |
| [Overpass public instances](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances) | Many no-charge instances; operator-dependent | Operator-policy-dependent | OSM data permits commerce; hosted permission is operator-specific | Usually no; instance-specific |
| [FOSSGIS routing / Overpass servers](https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/) | Community access | Yes with policy compliance | Not when service is a substantial part of the commercial offering; incidental use only within restrictions | No; routing max 1 request/second, identifying headers |
| [OSRM self-hosted](https://raw.githubusercontent.com/Project-OSRM/osrm-backend/master/LICENSE.TXT) | Free software; hosting costs yours | Yes; BSD-2-Clause plus data licence | Yes; licence notices and OSM data obligations | None inherent; your server policy |
| [Valhalla self-hosted](https://github.com/valhalla/valhalla/blob/master/COPYING) | Free software; hosting costs yours | Yes; MIT plus data licence | Yes; licence notices and data obligations | None inherent |
| [GraphHopper hosted free plan](https://www.graphhopper.com/pricing/) | 500 credits/day on verified pricing page | Yes; non-commercial only | No on free plan; paid hosted plan or self-hosting | Required |
| [GraphHopper self-hosted engine](https://raw.githubusercontent.com/graphhopper/graphhopper/master/LICENSE.txt) | Free software; hosting costs yours | Yes; Apache-2.0 plus data licence | Yes; code and data obligations; separate from hosted free plan | None inherent |
| [TomTom traffic/routing](https://docs.tomtom.com/pricing/) | Traffic: 200,000 tile / 20,000 segment requests monthly; other SKUs separate | Free quota offered; service terms apply | Free-commercial permission unverified because current [Docs terms](https://docs.tomtom.com/legal/terms-and-conditions) did not render; obtain confirmation | Required |
| [HERE Traffic API](https://www.here.com/get-started/pricing) | Free start/trial advertised; exact current entitlement unverified | Subject to plan terms | Free production entitlement unverified; commercial plans exist | API key or OAuth, endpoint-dependent |
| [Google Geocoding / Routes Essentials](https://developers.google.com/maps/billing-and-pricing/pricing) | 10,000 monthly events per listed SKU; paid overage | Yes under platform terms | Yes within applicable allowance; [display/storage restrictions](https://developers.google.com/maps/documentation/routes/policies) | API key or supported OAuth; billing project |
| [Google Places](https://developers.google.com/maps/billing-and-pricing/pricing) | SKU-specific allowances, not unlimited place search | Yes under platform terms | Yes within allowance; product/display/retention terms apply | Required; billing-enabled account |
| [SerpApi search](https://serpapi.com/pricing) | 250 searches/month on free plan | Subject to [service terms](https://serpapi.com/legal) | Explicit free-commercial grant unverified; no NC-only clause found; third-party content/resale rights not cleared | Required |
| [OpenAI API / Realtime](https://developers.openai.com/api/docs/pricing) | No durable general free inference tier advertised | No general free inference tier; paid use subject to policies | No general free inference tier; paid use; ChatGPT subscription does not include API credits | Required; server credentials, ephemeral tokens for suitable client sessions |

## 3D Software and Assets

Software rows describe the library licence, not free terrain, tiles, models, or a hosted service.

| Service | Free | Non-Commercial use | Commercial Use | API Key |
| --- | --- | --- | --- | --- |
| [MapLibre GL JS](https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/LICENSE.txt) | Yes; library | Yes; BSD-3-Clause | Yes; retain notices | No for engine |
| [Three.js](https://raw.githubusercontent.com/mrdoob/three.js/dev/LICENSE) | Yes; library | Yes; MIT | Yes; retain notices | No |
| [deck.gl](https://raw.githubusercontent.com/visgl/deck.gl/master/LICENSE) | Yes; library | Yes; MIT | Yes; retain notices | No for library |
| [CesiumJS](https://cesium.com/platform/cesiumjs/) | Yes; engine | Yes; Apache-2.0 | Yes; independent of ion free-plan eligibility | No for engine/own data; ion token separate |
| [Babylon.js](https://raw.githubusercontent.com/BabylonJS/Babylon.js/master/license.md) | Yes; engine | Yes; Apache-2.0 | Yes; licence/notice obligations | No |
| [satellite.js](https://raw.githubusercontent.com/shashwatak/satellite-js/develop/LICENSE.md) | Yes; library | Yes; MIT | Yes; orbital source rights separate | No |
| [Blender](https://www.blender.org/about/license/) / [glTF](https://www.khronos.org/gltf/) | Yes; tool / royalty-free format | Yes | Yes; Blender GPL distribution duties, authored output not automatically GPL; asset rights separate | No |
| [Poly Haven downloadable assets](https://polyhaven.com/license) | Yes | Yes; CC0 | Yes, including self-hosted asset redistribution | No |
| [Poly Haven live API](https://polyhaven.com/our-api) | Yes; current separate API policy | Yes | Yes under [API terms](https://raw.githubusercontent.com/Poly-Haven/Public-API/master/ToS.md); visible provider credit required | No key; app-identifying User-Agent/Referer |
| [NASA 3D Resources](https://science.nasa.gov/3d-resources/) | Public downloadable assets | Conditional on asset/media notices | Conditional on [NASA media rules](https://www.nasa.gov/nasa-brand-center/images-and-media/); third-party copyright, logos, endorsement/person rights separate | No for public downloads |
| [Sketchfab eligible free assets / Download API](https://sketchfab.com/developers/download-api) | Selected owner-enabled models | Exact asset licence applies | CC0/BY/BY-SA permitted; NC not commercial; ND limits adaptations; rights vary by model | Download account; API needs app credentials/end-user OAuth2 |
| [TurboSquid selected free models](https://blog.turbosquid.com/turbosquid-3d-model-license/) | Selected $0 assets | Permitted uses under exact licence; Editorial restrictions | Conditional; plain downloadable GLB/custom WebGL distribution not automatically allowed; seek approval | Account for downloads; no free catalogue API verified |
| [CGTrader selected free models](https://help.cgtrader.com/hc/en-us/articles/360015122437-Can-I-commercially-use-a-free-model) | Selected assets | Seller-selected licence | Royalty Free models allow commercial Incorporated Products; extraction protection/IP restrictions; Editorial limited | Download account; approved API requires key/OAuth2 |
| [TeleGeography current cable dataset](https://www2.telegeography.com/license-geocoded-map-data) | No current free raw-data offer verified | No verified free underlying data, including students | No verified free raw-data grant; paid negotiated licence | Contract delivery; no public API entitlement verified |
| [TeleGeography map screenshots/references](https://www2.telegeography.com/license-telegeography-map) | Yes; specified maps, not raw dataset | Yes; CC BY-SA 4.0 | Yes; attribution/ShareAlike; interactive map not embeddable | No |
| Historical cable snapshot bundled in GEV | Existing files under [bundled notice](gods-eye-view/DATA_SOURCES.md); current upstream grant not reverified | Conditional on authentic CC BY-NC-SA grant | No under NC terms without separate permission | No for bundled files |

## Strong Free Commercial Candidates

These have affirmative source/service permissions under the stated offering, subject to their respective obligations. They are a shortlist, not blanket approval of all products from each organization.

- Maps and geographic data: OpenFreeMap, OSM/Geofabrik, Natural Earth, Overture source files, OpenBuildingMap downloads, WorldPop.
- Imagery: unrestricted NASA GIBS products, Sentinel data/CDSE processing within quota; review individual non-NASA and non-Sentinel products.
- Weather: NOAA/NWS, GFS, designated ECMWF Open Data, OpenWeather basic Free, and Copernicus Marine.
- Aircraft and space context: adsb.lol under ODbL; Launch Library 2 metadata within quota. Standard orbital/basic SSA redistribution has its own narrower grant.
- Cameras and transit: TfL JamCams, Digitraffic images, Entur, and TransLink Queensland under their respective data/media terms.
- Assets/software: Poly Haven CC0 downloads and documented API offering; MapLibre, Three.js, deck.gl, CesiumJS, Babylon.js, satellite.js, and self-hosted routing engines.
- Other context: GDELT project data and Radio Browser station metadata, not automatically linked articles, broadcasts, music, or artwork.

Free-plan exclusions or unresolved rights include OpenSky operational use, Open-Meteo commercial hosting, MapTiler commercial production, GraphHopper hosted commerce, RainViewer commercial use, adsbdb data, AISstream data, and many linked camera-media sources.

## Procurement Notes

- OpenTopography's free individual key is not permission to embed one shared key in a commercial application. Review dataset eligibility separately.
- CDSE's free processing quota and the standalone Sentinel Hub/Planet trial are different offerings with different commercial permissions.
- OpenFreeMap permits free commercial hosting; offline downloads have additional limits in its [service terms](https://openfreemap.org/tos/).
- Overture's prebuilt inspection PMTiles are not a production hosting entitlement. Generate permitted production tiles from the licensed data.
- Mapterhorn, Re:Earth, and Terrarium combine source datasets. A downstream code licence or simplified attribution label does not override every upstream data licence.
- Google global free allowances are product-specific billable events, not necessarily HTTP requests. Billing must be configured, overages can incur costs, and regional pricing differs.
- CesiumJS is freely usable commercially; Cesium ion Community is a separately restricted hosted plan. Funded research, government, revenue/funding thresholds, and external commercial integration may require paid permission.
- Free or purchased marketplace models may still prohibit extractable browser GLBs. Review models, liveries, logos, CDN distribution, derivative textures, and proof of rights individually.
- OpenSky's current terms are narrower than generic "non-commercial" access: operational systems require a written licence even for nonprofits. Its FAQ and terms are not perfectly aligned; use the controlling terms for approval.
- CelesTrak standard GP/basic SSA redistribution and supplemental owner/operator data are not interchangeable licences. Keep SupGP product permissions separate.
- GEV's adsbdb, AISstream, and municipal camera integrations do not prove a commercial data/media grant. adsbdb's route source expressly restricts copying/publication without permission.
- Google non-EEA terms prohibit Street View imagery beside non-Google maps on the same screen. EEA rules differ; a free allowance does not waive these display restrictions.
- Windy Free institutional eligibility is unresolved; its API terms restrict redistribution, publishing graphics containing webcam images, and implementing Free solely behind a paywall. Paid Professional does not remove all media restrictions.
- Camera catalogue licences do not automatically license linked snapshots or video. TfL and Digitraffic grants were verified for images; many other sources remain catalogue-only or unverified.
- Radio Browser's public-domain dedication covers station metadata, not music/broadcast rights. GTFS and GBFS formats do not supply a blanket licence for every operator feed.
- Open-Meteo's returned CC BY data is not permission to use its free hosted endpoint commercially. OpenAQ and Macrostrat also require distinguishing source-data licences from hosted-service terms.
- nowCOAST lightning products are derived density, not a licence to redistribute raw lightning detections. Forecast issue/valid times and observation times remain distinct regardless of licence.
- [Legacy USGS WaterServices](https://waterservices.usgs.gov/) is scheduled to retire February 22, 2027. Its usage wording and quotas must not be transferred to the modern WaterData API; use the modern endpoint's current key/limit documentation.
- Horizons' API fair-use policy restricts direct website integration. A public endpoint should not be embedded in Meridian without resolving the applicable integration restrictions.
- The table does not approve emergency, aviation, safety, navigation, or other regulated deployment claims.

## Verification Limits

Verification used current official pages where retrievable. Some JavaScript-only, unavailable, or ambiguous terms could not be established; those rows are labeled unverified. Provider quotas/terms may change after October 15, 2026. Recheck the exact product and deployment model before launch.

Application code, provider credentials, and the Word blueprint were not modified.
