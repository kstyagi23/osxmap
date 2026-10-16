"""Reviewed service policy, not a provider transport or runtime matrix parser.

No environment, credentials, clock, filesystem or network is consulted here.
``settings`` is product-local mutable intent, never evidence of permission.
Dependency flags are supplied by reviewed application code, not browser settings.
"""

from dataclasses import asdict, dataclass
from types import MappingProxyType


VERSION = "2026-10-15.1"
VERIFIED_ON = "2026-10-15"


@dataclass(frozen=True)
class Product:
    id: str
    provider_id: str
    name: str
    matrix_row: str
    category: str
    kind: str
    capabilities: tuple
    coverage: str
    authentication: tuple
    credential_required: bool
    free_status: str
    commercial_status: str
    eligibility: str
    default_enabled: bool
    terms: tuple
    verification_date: str
    attribution: str
    data_rights: str
    media_rights: str
    service_rights: str
    cache_policy: str
    stale_policy: str
    export_policy: str
    history_policy: str
    endpoint_origins: tuple
    limits: tuple
    renderers: tuple
    acknowledgements: tuple
    permission_blockers: tuple
    setup_blockers: tuple
    dependencies: tuple
    implementation_status: str
    auth_fields: tuple
    environment: tuple
    billing: bool


# Explicit reviewed row mappings. Policy codes: D verified keyless commercial;
# C credentials; N restricted opt-in; B unresolved rights; P paid; T NC trial;
# CN credentialed NC. A code never overrides a row's additional blocker.
# Fields: exact display label, IDs, category, kind, policy, auth, official URL,
# origin, capability, coverage, rights/eligibility notes.
_ROWS = (
    ("OpenFreeMap public hosting", "openfreemap.public", "maps", "runtime", "D", "none", "https://openfreemap.org/tos/", "https://tiles.openfreemap.org", "basemap", "global", "Commercial public hosting with attribution; best effort; offline limits apply."),
    ("OpenStreetMap data / Geofabrik extracts", "osm.extracts", "maps", "download", "D", "none", "https://www.openstreetmap.org/copyright", "https://download.geofabrik.de", "regional_extract", "global regional files", "ODbL attribution and database obligations; editing/upload separate."),
    ("OSM standard raster tile server", "osm.raster", "maps", "runtime", "D", "identifying_headers", "https://operations.osmfoundation.org/policies/tiles/", "https://tile.openstreetmap.org", "basemap", "global", "Interactive viewing only; no offline, prefetch or bulk; visible attribution; no SLA."),
    ("Natural Earth", "naturalearth.downloads", "maps", "download", "D", "none", "https://www.naturalearthdata.com/about/terms-of-use/", "", "boundaries", "global", "Public-domain downloads."),
    ("NASA GIBS / Worldview Snapshots", "nasa.gibs nasa.worldview_snapshots", "imagery", "runtime", "D", "none", "https://nasa-gibs.github.io/gibs-api-docs/", "https://gibs.earthdata.nasa.gov", "imagery", "global product-dependent", "Unrestricted NASA products only; third-party products require separate review."),
    ("NASA CMR public metadata search", "nasa.cmr", "imagery", "catalogue", "D", "none", "https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html", "https://cmr.earthdata.nasa.gov", "discovery", "global public records", "Public discovery only; restricted records and dataset reuse separate."),
    ("NASA Earthdata product downloads", "nasa.earthdata_downloads", "imagery", "download", "C", "account bearer_token", "https://urs.earthdata.nasa.gov/documentation/for_users/data_access", "https://urs.earthdata.nasa.gov", "raster_import", "collection-dependent", "Exact collection rights required; account/login is not a CMR API key."),
    ("Copernicus Data Space STAC / OData catalogue", "cdse.catalogue cdse.authenticated_search", "imagery", "catalogue", "D", "none", "https://documentation.dataspace.copernicus.eu/APIs/STAC.html", "https://catalogue.dataspace.copernicus.eu", "discovery", "Sentinel public metadata", "Sentinel discovery under free full open terms; other collections separate."),
    ("Copernicus Sentinel product downloads", "cdse.sentinel_downloads", "imagery", "download", "C", "account bearer_token", "https://documentation.dataspace.copernicus.eu/APIs/OData.html#product-download", "https://download.dataspace.copernicus.eu", "raster_import", "Sentinel", "Sentinel source notices and fair-use/download quotas."),
    ("CDSE Sentinel Hub processing", "cdse.processing", "imagery", "runtime", "C", "account oauth_client bearer_token", "https://documentation.dataspace.copernicus.eu/Quotas.html", "https://sh.dataspace.copernicus.eu", "raster_processing", "eligible Sentinel products", "10,000 requests and 10,000 processing units/month; source and service terms."),
    ("Standalone Sentinel Hub / Planet", "sentinel_hub.standalone", "imagery", "runtime", "T", "account oauth_client bearer_token", "https://www.sentinel-hub.com/faq/", "https://services.sentinel-hub.com", "raster_processing", "plan-dependent", "30-day non-commercial trial, not permanent free entitlement; subscription separate."),
    ("OpenTopography APIs", "opentopography.personal opentopography.enterprise", "terrain", "download", "CN", "api_key", "https://opentopography.org/developers", "https://portal.opentopography.org", "terrain_import", "dataset-dependent", "Individual eligibility/quota; commercial software needs paid Enterprise key; dataset rights separate."),
    ("Mapterhorn terrain", "mapterhorn.hosted", "terrain", "runtime", "B", "none", "https://mapterhorn.com/attribution", "https://tiles.mapterhorn.com", "terrain", "source-dependent", "Blanket hosted commercial grant unverified; source licences require review."),
    ("Re:Earth Terrain", "reearth.terrain", "terrain", "runtime", "B", "none", "https://terrain.reearth.land/", "https://terrain.reearth.land", "quantized_mesh", "source-dependent", "Best-effort hosting; source and hosted commercial scope unverified."),
    ("Mapzen Terrarium / AWS terrain tiles", "mapzen.terrarium", "terrain", "runtime", "B", "none", "https://registry.opendata.aws/terrain-tiles/", "https://s3.amazonaws.com", "terrain", "source-dependent", "Unsigned public reads; blanket commercial source/service grant unverified."),
    ("OpenMapTiles self-hosted stack", "openmaptiles.self_hosted", "maps", "self_hosted", "D", "none", "https://github.com/openmaptiles/openmaptiles/blob/master/LICENSE.md", "", "vector_tiles", "operator data", "BSD/CC BY/ODbL obligations; hosting costs yours; no free hosted API."),
    ("MapTiler Cloud free plan", "maptiler.free", "maps", "runtime", "CN", "api_key", "https://www.maptiler.com/terms/cloud/#FreePlan", "https://api.maptiler.com", "basemap", "global", "5,000 sessions / 100,000 requests monthly; NC or commercial R&D only, not commercial production."),
    ("Esri classic World Imagery MapServer", "esri.world_imagery", "imagery", "runtime", "B", "none", "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer", "https://services.arcgisonline.com", "basemap", "global", "Reachability is not entitlement; third-party deployment rights unverified."),
    ("ArcGIS Location Platform basemaps", "arcgis.basemaps", "maps", "runtime", "C", "account scoped_public_token oauth", "https://location.arcgis.com/help/licensing-and-attribution/", "https://basemapstyles-api.arcgis.com", "basemap", "product-dependent", "Authenticated platform licence and attribution; allowance varies; not classic Living Atlas entitlement."),
    ("Google Photorealistic 3D Tiles", "google.photorealistic_3d", "imagery", "runtime", "P", "api_key billing_project", "https://developers.google.com/maps/documentation/tile/policies", "https://tile.googleapis.com", "3d_tiles", "provider coverage", "1,000 monthly billable events; paid overage; storage/export/attribution restrictions."),
    ("Cesium ion Community", "cesium.ion_community", "terrain", "runtime", "CN", "account access_token", "https://cesium.com/platform/cesium-ion/pricing/", "https://api.cesium.com", "3d_tiles", "asset-dependent", "10 GB storage / 15 GB monthly streaming; personal/unfunded education and evaluation eligibility, not blanket commercial production."),
    ("Overture base/buildings/divisions/transportation", "overture.base", "maps", "download", "D", "none", "https://docs.overturemaps.org/attribution/", "", "regional_extract", "global themes", "ODbL and source notices; inspection PMTiles not production hosting entitlement."),
    ("Overture places/addresses", "overture.places_addresses", "maps", "download", "D", "none", "https://docs.overturemaps.org/attribution/", "", "regional_extract", "source-dependent", "Only sources whose exact licences permit use; no single blanket licence."),
    ("OpenBuildingMap downloadable dataset", "openbuildingmap.downloads", "maps", "download", "D", "none", "https://www.openbuildingmap.org/", "", "buildings", "dataset coverage", "GeoPackage downloads under ODbL; attribution/database duties."),
    ("OpenBuildingMap hosted mirror/API", "openbuildingmap.hosted", "maps", "runtime", "B", "unknown", "", "", "buildings", "unknown", "Hosted offer, auth and service rights unverified; download licence is not mirror entitlement."),
    ("WorldPop open datasets/API", "worldpop.public worldpop.high_limit", "maps", "catalogue", "D", "none", "https://www.worldpop.org/faq/", "https://www.worldpop.org", "population", "dataset year/resolution coverage", "CC BY 4.0; public REST up to 1,000/day; approved key above that."),
    ("OpenInfraMap source data", "openinframap.source_data", "maps", "download", "D", "none", "https://openinframap.org/about", "", "infrastructure", "OSM coverage", "ODbL raw extracts only; turnkey exports may cost; no hosted tile/API entitlement."),
    ("US Census geographic boundary files", "census.boundaries", "maps", "download", "B", "none", "https://www.census.gov/geographies/mapping-files.html", "", "boundaries", "United States", "Public downloads; exact dataset reuse grant not reverified."),
    ("DataSF neighborhood boundaries", "datasf.neighborhoods", "maps", "download", "B", "endpoint_dependent", "https://data.sfgov.org/Geographic-Locations-and-Boundaries/Analysis-Neighborhoods/p5b7-5n3h/about_data", "", "boundaries", "San Francisco", "Official grant not reverified; portal availability and GEV PDDL report are not clearance."),
    ("Open-Meteo Weather / Air Quality", "openmeteo.weather openmeteo.air_quality", "weather", "runtime", "N", "none", "https://open-meteo.com/en/terms", "https://api.open-meteo.com", "forecast", "product coverage", "Free hosted non-commercial only; CC BY data does not waive hosted terms; paid endpoint separate."),
    ("OpenWeather basic Free plan", "openweather.basic", "weather", "runtime", "C", "account api_key", "https://openweathermap.org/faq", "https://api.openweathermap.org", "weather", "product coverage", "Product-limited Free; commercial API permission with attribution/credit conditions."),
    ("OpenWeather One Call", "openweather.one_call", "weather", "runtime", "P", "account api_key subscription", "https://openweathermap.org/faq", "https://api.openweathermap.org", "forecast", "product coverage", "Separate pay-as-you-call subscription; 1,000/day allowance; automatic billable overage."),
    ("NOAA / NWS weather API", "noaa.nws", "weather", "runtime", "D", "identifying_headers", "https://www.weather.gov/documentation/services-web-api", "https://api.weather.gov", "weather_alerts", "United States service coverage", "Agency content free for any purpose; notices and third-party exceptions; User-Agent required."),
    ("NOAA GFS on AWS", "noaa.gfs", "weather", "download", "D", "none", "https://registry.opendata.aws/noaa-gfs-bdp-pds/", "https://noaa-gfs-bdp-pds.s3.amazonaws.com", "forecast_import", "global model", "Designated NOAA data no use restrictions; own compute separate; issue and valid times distinct."),
    ("NOAA nowCOAST radar / lightning density", "noaa.nowcoast", "weather", "runtime", "B", "unknown", "https://www.nauticalcharts.noaa.gov/learn/nowcoast.html", "", "radar_lightning_density", "product coverage", "Fee/quota/auth and blanket redistribution unverified; density is not raw strikes."),
    ("NHC advisories / NOAA SWPC", "noaa.nhc noaa.swpc", "weather", "runtime", "D", "none", "https://www.nhc.noaa.gov/aboutrss.shtml", "https://www.nhc.noaa.gov", "advisories", "agency product coverage", "Agency-authored feeds under NWS policy; third-party products separate."),
    ("ECMWF Open Data", "ecmwf.open_data", "weather", "download", "D", "none", "https://www.ecmwf.int/en/forecasts/datasets/open-data", "", "forecast_import", "designated global products", "CC BY 4.0 only designated open distribution, not every ECMWF API."),
    ("RainViewer public API", "rainviewer.public", "weather", "runtime", "N", "none", "https://www.rainviewer.com/api/transition-faq.html", "https://api.rainviewer.com", "radar", "provider coverage", "Personal/educational grant only; commercial permission/offering unverified."),
    ("OpenAQ", "openaq.api", "science", "runtime", "B", "account api_key", "https://docs.openaq.org/about/terms", "https://api.openaq.org", "station_measurements", "station coverage", "Hosted commercial grant unverified; source licences vary; competing service restrictions."),
    ("NASA FIRMS", "nasa.firms", "hazards", "runtime", "B", "map_key", "https://firms.modaps.eosdis.nasa.gov/api/", "https://firms.modaps.eosdis.nasa.gov", "fire_detections", "layer-dependent", "NASA-led unrestricted data permits reuse with credit; hosted/non-NASA scope needs confirmation; archives may require Earthdata."),
    ("NASA EONET", "nasa.eonet", "hazards", "catalogue", "B", "none", "https://eonet.gsfc.nasa.gov/docs/v3", "https://eonet.gsfc.nasa.gov", "events", "public metadata coverage", "NASA metadata policy does not clear blanket hosted/media or linked-source rights."),
    ("USGS earthquake GeoJSON feeds", "usgs.earthquakes", "hazards", "runtime", "B", "none", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php", "https://earthquake.usgs.gov", "earthquakes", "feed coverage", "Exact feed/contributed-content reuse licence not independently verified."),
    ("USGS WaterData API", "usgs.waterdata", "science", "runtime", "B", "optional_api_key", "https://api.waterdata.usgs.gov/", "https://api.waterdata.usgs.gov", "gauges", "United States stations", "Modern hosted/data reuse unverified; optional api.data.gov key raises limits; not legacy terms."),
    ("Macrostrat", "macrostrat.api", "science", "runtime", "B", "none", "https://macrostrat.org/api/v2/meta", "https://macrostrat.org", "geology", "regional data coverage", "CC BY 4.0 data; hosted commercial entitlement/quota/fee scope unverified."),
    ("NASA JPL Horizons API", "nasa.horizons", "science", "runtime", "B", "identifying_headers", "https://ssd-api.jpl.nasa.gov/doc/horizons.html", "https://ssd.jpl.nasa.gov", "ephemerides", "solar system", "Direct website integration prohibited; commercial entitlement unverified; serialized requests/caching/backoff."),
    ("Copernicus Marine", "copernicus.marine", "science", "download", "C", "account", "https://marine.copernicus.eu/user-corner/service-commitments-and-licence", "", "marine_import", "model/depth/time coverage", "No-cost commercial data with licence/acknowledgement; account/Toolbox, not a separate API key."),
    ("OpenSky REST", "opensky.research opensky.authenticated opensky.operational", "aircraft", "runtime", "N", "none", "https://opensky-network.org/about/terms-of-use", "https://opensky-network.org", "aircraft_states", "receiver coverage", "Nonprofit research/education only; operational systems need written licence even for nonprofits."),
    ("adsb.lol public API", "adsblol.public", "aircraft", "runtime", "D", "none", "https://www.adsb.lol/docs/open-data/api/", "https://api.adsb.lol", "aircraft_states", "receiver coverage", "ODbL commercial permission; attribution/database duties; dynamic limits."),
    ("adsbdb API", "adsbdb.api", "aircraft", "runtime", "B", "none", "https://www.adsbdb.com/", "https://api.adsbdb.com", "aircraft_enrichment", "dataset coverage", "Data rights unverified; route publication/copying needs permission; MIT code is not route licence."),
    ("ADS-B Exchange API", "adsbexchange.community adsbexchange.enterprise", "aircraft", "runtime", "P", "api_key", "https://www.adsbexchange.com/community/developer-hub/", "", "aircraft_states", "contract coverage", "No durable general free tier; paid Community non-commercial, Enterprise agreement commercial."),
    ("FlightAware AeroAPI", "flightaware.personal flightaware.business", "aircraft", "runtime", "P", "account api_key", "https://www.flightaware.com/commercial/aeroapi/", "https://aeroapi.flightaware.com", "aircraft_enrichment", "plan coverage", "Personal/academic $5 allowance ($10 feeders), beyond billable; business requires Standard/Premium."),
    ("Aviationstack", "aviationstack.free", "aircraft", "runtime", "CN", "account api_key", "https://aviationstack.com/product", "https://api.aviationstack.com", "aircraft_enrichment", "plan coverage", "100 monthly Free requests; personal/non-commercial only; paid commercial plan separate."),
    ("CelesTrak GP", "celestrak.gp celestrak.supgp", "space", "runtime", "D", "none", "https://celestrak.org/NORAD/documentation/gp-data-formats.php", "https://celestrak.org", "orbital_elements", "approved standard GP groups", "Standard basic-data redistribution with citation; caching limits; SupGP rights separate."),
    ("Space-Track", "spacetrack.basic_ssa", "space", "download", "C", "approved_account session", "https://www.space-track.org/documentation", "https://www.space-track.org", "orbital_import", "approved basic SSA", "Basic SSA redistribution with citation only; broader products need approval/review."),
    ("AISstream", "aisstream.websocket", "maritime", "runtime", "B", "account api_key", "https://aisstream.io/documentation", "wss://stream.aisstream.io", "vessel_states", "receiver coverage", "Free advertised service; commercial/republication data grant unverified; server-side socket."),
    ("MarineTraffic API", "marinetraffic.contract", "maritime", "runtime", "P", "api_key contract", "https://servicedocs.marinetraffic.com/", "", "vessel_states", "contract coverage", "Paid service-specific agreement; complimentary trial only by agreement/internal business; no general free production."),
    ("Launch Library 2 / TheSpaceDevs", "thespacedevs.ll2 thespacedevs.ll2_high_limit", "space", "catalogue", "D", "none", "https://thespacedevs.com/llapi", "https://ll.thespacedevs.com", "launch_metadata", "published launch coverage", "15/hour/IP; broad data-use terms; avoid unchanged raw passthrough; linked media separate."),
    ("FAA aircraft registry downloads", "faa.registry", "aircraft", "download", "B", "none", "https://www.faa.gov/licenses_certificates/aircraft_certification/aircraft_registry/releasable_aircraft_download", "", "identity_import", "United States registry", "Public daily bulk access; dataset republication/commercial grant not verified."),
    ("Mapillary licensed images", "mapillary.licensed_images", "cameras", "asset", "D", "none", "https://help.mapillary.com/hc/en-us/articles/115001770409-Licenses", "", "street_images", "eligible copies", "CC BY-SA 4.0 attribution and ShareAlike for adaptations; hosted API separate."),
    ("Mapillary API/viewer", "mapillary.api", "cameras", "runtime", "B", "registered_app client_token", "https://help.mapillary.com/hc/en-us/articles/8348198426396-Mapillary-FAQ", "https://graph.mapillary.com", "street_images", "provider coverage", "Free company use advertised; full contractual API restrictions unverified."),
    ("Google Street View", "google.street_view_static google.street_view_dynamic", "cameras", "runtime", "P", "api_key billing_project", "https://developers.google.com/maps/documentation/streetview/usage-and-billing", "https://maps.googleapis.com", "street_images", "provider coverage", "Static 10,000 / Dynamic 5,000 monthly events; paid above; non-Google map-combination restrictions."),
    ("Windy Webcams API", "windy.webcams_free windy.webcams_professional", "cameras", "runtime", "B", "private_api_key", "https://account.windy.com/agreements/windy-webcams-api-terms-of-use", "https://api.windy.com", "webcams", "provider coverage", "Free institutional eligibility unresolved; paid Professional does not remove media/publication/paywall restrictions."),
    ("Radio Browser metadata/API", "radiobrowser.metadata", "radio", "catalogue", "D", "identifying_headers", "https://docs.radio-browser.info/", "", "station_metadata", "directory coverage", "Public-domain dedicated metadata only; descriptive User-Agent requested; mirrors need reviewed origins."),
    ("Radio Browser linked streams/artwork", "radiobrowser.linked_media", "radio", "runtime", "B", "endpoint_dependent", "https://docs.radio-browser.info/", "", "playback", "rightsholder-dependent", "Directory licence grants no music, broadcast or artwork rights."),
    ("TfL JamCams", "tfl.jamcams", "cameras", "runtime", "C", "registered_access_token", "https://tfl.gov.uk/corporate/terms-and-conditions/transport-data-service", "https://api.tfl.gov.uk", "camera_images", "London", "Image grant verified with branding/freshness/attribution; no cropping; registered token."),
    ("Digitraffic Finland cameras", "digitraffic.cameras", "cameras", "runtime", "D", "identifying_headers", "https://www.digitraffic.fi/en/terms-of-service/", "https://tie.digitraffic.fi", "camera_images", "Finland", "CC BY 4.0 camera data/images; attribution/modification notices; identification recommended."),
    ("DriveBC HighwayCams catalogue", "drivebc.catalogue drivebc.media", "cameras", "catalogue", "D", "none", "https://catalogue.data.gov.bc.ca/api/3/action/package_show?id=bc-highwaycams", "https://catalogue.data.gov.bc.ca", "camera_catalogue", "British Columbia", "OGL-BC catalogue only; linked media and separate camera API unverified."),
    ("Ontario 511 cameras", "ontario511.catalogue ontario511.media", "cameras", "catalogue", "C", "api_key", "https://data.ontario.ca/dataset/traffic-cameras", "", "camera_catalogue", "Ontario", "OGL-Ontario catalogue only; linked media not automatically licensed; 511 key/cost verification needed."),
    ("Transport NSW LiveTraffic", "nsw.catalogue nsw.media", "cameras", "catalogue", "C", "gateway_credentials", "https://opendata.transport.nsw.gov.au/data/dataset/live-traffic-cameras", "", "camera_catalogue", "New South Wales", "CC BY 4.0 catalogue; media reuse unverified; endpoint-specific gateway credentials."),
    ("Statens vegvesen Norway cameras", "vegvesen.catalogue vegvesen.datex vegvesen.media", "cameras", "catalogue", "D", "none", "https://dataut.vegvesen.no/en/dataset/webkamera", "", "camera_catalogue", "Norway", "NLOD catalogue only; linked images unverified; WFS registration optional, DATEX credentials required."),
    ("Open Calgary traffic cameras", "calgary.cameras", "cameras", "runtime", "B", "unknown", "https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa", "", "camera_images", "Calgary", "Portal verification blocked; dataset/media licence unverified; general site licence not clearance."),
    ("Austin traffic cameras", "austin.cameras", "cameras", "runtime", "B", "unknown", "https://data.austintexas.gov/Transportation-and-Mobility/Traffic-Cameras/b4k4-adkb", "", "camera_images", "Austin", "Dataset/media rights and endpoint access unverified."),
    ("TxDOT cameras", "txdot.cameras", "cameras", "runtime", "B", "unknown", "https://www.txdot.gov/discover/live-traffic-cameras.html", "", "camera_images", "Texas", "Viewing only; reuse and public API contract unverified."),
    ("Caltrans CWWP2", "caltrans.cwwp2", "cameras", "runtime", "B", "none", "https://cwwp2.dot.ca.gov/documentation/cctv/cctv.htm", "https://cwwp2.dot.ca.gov", "camera_images", "California", "Owned information generally public domain; camera/third-party media scope unverified."),
    ("DelDOT cameras", "deldot.cameras", "cameras", "runtime", "B", "unknown", "https://deldot.gov/map/index.shtml", "", "camera_images", "Delaware", "Public viewing only; reuse and API contract unverified."),
    ("Tallinn cameras", "tallinn.cameras", "cameras", "runtime", "B", "unknown", "https://ristmikud.tallinn.ee/", "", "camera_images", "Tallinn", "Public viewing only; reuse and API contract unverified."),
    ("Tarktee / Transpordiamet", "tarktee.cameras", "cameras", "runtime", "B", "unknown", "https://tarktee.transpordiamet.ee/", "", "camera_images", "Estonia", "Camera-media grant and endpoint access unverified."),
    ("Warendorf webcam", "warendorf.webcam", "cameras", "runtime", "B", "unknown", "https://www.warendorf.de/de/impressum/", "", "camera_images", "Warendorf", "Website viewing only; written permission beyond statutory exceptions; no API contract."),
    ("GTFS / GTFS-Realtime", "gtfs.specification gtfs.feeds", "transit", "library", "D", "none", "https://gtfs.org/getting-started/publish/", "", "transit_format", "per agency", "Free specification grants no operator data rights; per-agency feed licence/auth required."),
    ("GBFS feeds, e.g. BCycle/Lyft", "gbfs.specification gbfs.feeds", "transit", "library", "D", "none", "https://gbfs.org/documentation/data-policy/", "", "bikeshare_format", "per system", "Free specification; actual feed licence and operator auth vary."),
    ("Entur open transit data", "entur.open_data", "transit", "runtime", "D", "identifying_headers", "https://developer.entur.no/terms-of-service", "https://api.entur.io", "transit", "Norway", "NLOD 2.0 source terms/attribution; ET-Client-Name required."),
    ("TransLink Queensland", "translink.queensland", "transit", "runtime", "D", "none", "https://translink.com.au/about-translink/open-data", "", "transit", "Queensland", "CC BY 4.0 plus agency terms/attribution; no authentication."),
    ("MBTA / MassDOT", "mbta.gtfs_rt mbta.v3", "transit", "runtime", "B", "none", "https://www.mbta.com/developers/gtfs-realtime", "https://api-v3.mbta.com", "transit", "Massachusetts", "Governing developer licence unverified; V3 key distinct from GTFS-RT."),
    ("CapMetro", "capmetro.feeds", "transit", "runtime", "B", "endpoint_dependent", "https://www.capmetro.org/developertools", "", "transit", "Austin", "Agency grant unverified; endpoint-specific authentication."),
    ("Metro Transit", "metrotransit.feeds", "transit", "runtime", "B", "endpoint_dependent", "https://svc.metrotransit.org/", "https://svc.metrotransit.org", "transit", "agency coverage", "Agency grant unverified; endpoint-specific authentication."),
    ("OVapi", "ovapi.feeds", "transit", "runtime", "B", "endpoint_dependent", "https://gtfs.ovapi.nl/README", "https://gtfs.ovapi.nl", "transit", "Netherlands feed coverage", "Agency grant unverified; endpoint-specific authentication."),
    ("HSL", "hsl.feeds", "transit", "runtime", "B", "endpoint_dependent", "https://www.hsl.fi/en/hsl/open-data", "", "transit", "Helsinki", "Agency grant/auth unverified; documentation blocked."),
    ("NIFC WFIGS fire perimeters", "nifc.wfigs", "events", "runtime", "B", "none", "https://www.arcgis.com/sharing/rest/content/items/d1c32af3212341869b3c810f1a215824?f=pjson", "https://www.arcgis.com", "fire_perimeters", "agency coverage", "Informational accuracy/non-legal-use disclaimer; express commercial licence not established."),
    ("InciWeb incident pages", "inciweb.pages", "events", "catalogue", "B", "none", "https://inciweb.wildfire.gov/", "https://inciweb.wildfire.gov", "incident_links", "agency coverage", "Viewing/source links only; automated republication/media rights and API entitlement unverified."),
    ("GDELT DOC 2.0", "gdelt.doc2", "news", "catalogue", "D", "none", "https://www.gdeltproject.org/about.html#termsofuse", "https://api.gdeltproject.org", "news_metadata", "indexed coverage", "Project data commercial/government use with citation/link; publisher articles/media separate."),
    ("Google News RSS", "google.news_rss", "news", "runtime", "N", "none", "https://www.google.com/intl/en_us/terms_google_news.html", "https://news.google.com", "news_metadata", "feed coverage", "Personal non-commercial only; publisher rights separate; no commercial fallback."),
    ("Nominatim public geocoder", "nominatim.public", "routing", "runtime", "D", "identifying_headers", "https://operations.osmfoundation.org/policies/nominatim/", "https://nominatim.openstreetmap.org", "submitted_geocoding", "OSM coverage", "Max 1/second; no autocomplete; caching/attribution/switchability; self-host/pay for scale."),
    ("Photon public geocoder", "photon.public", "routing", "runtime", "B", "none", "https://github.com/komoot/photon", "https://photon.komoot.io", "geocoding", "OSM coverage", "Reasonable-use demo; explicit hosted commercial grant unverified; no SLA."),
    ("Overpass public instances", "overpass.public", "routing", "runtime", "B", "endpoint_dependent", "https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances", "", "osm_query", "operator coverage", "OSM data rights do not grant operator-specific hosted permission."),
    ("FOSSGIS routing / Overpass servers", "fossgis.routing fossgis.overpass", "routing", "runtime", "N", "identifying_headers", "https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/", "", "routing", "operator coverage", "Eligible incidental use only; not substantial commercial offering; routing max 1/second."),
    ("OSRM self-hosted", "osrm.self_hosted", "routing", "self_hosted", "D", "none", "https://raw.githubusercontent.com/Project-OSRM/osrm-backend/master/LICENSE.TXT", "", "routing", "operator data", "BSD-2-Clause plus OSM data obligations; own server policy/cost."),
    ("Valhalla self-hosted", "valhalla.self_hosted", "routing", "self_hosted", "D", "none", "https://github.com/valhalla/valhalla/blob/master/COPYING", "", "routing", "operator data", "MIT plus data licence; own hosting costs."),
    ("GraphHopper hosted free plan", "graphhopper.free", "routing", "runtime", "CN", "api_key", "https://www.graphhopper.com/pricing/", "https://graphhopper.com", "routing", "plan coverage", "500 credits/day; non-commercial only; paid hosted or self-hosting separate."),
    ("GraphHopper self-hosted engine", "graphhopper.self_hosted", "routing", "self_hosted", "D", "none", "https://raw.githubusercontent.com/graphhopper/graphhopper/master/LICENSE.txt", "", "routing", "operator data", "Apache-2.0 plus data obligations; not hosted Free plan."),
    ("TomTom traffic/routing", "tomtom.traffic tomtom.routing", "routing", "runtime", "B", "api_key", "https://docs.tomtom.com/legal/terms-and-conditions", "https://api.tomtom.com", "traffic_routing", "SKU coverage", "Traffic 200,000 tiles / 20,000 segments monthly; other SKUs separate; free-commercial terms unverified."),
    ("HERE Traffic API", "here.traffic", "routing", "runtime", "B", "api_key oauth", "https://www.here.com/get-started/pricing", "", "traffic", "plan coverage", "Free start/trial advertised; exact production entitlement unverified; commercial plans exist."),
    ("Google Geocoding / Routes Essentials", "google.geocoding google.routes_essentials", "routing", "runtime", "P", "api_key oauth billing_project", "https://developers.google.com/maps/documentation/routes/policies", "https://maps.googleapis.com", "geocoding_routing", "SKU coverage", "10,000 monthly events per listed SKU; paid overage; display/storage restrictions."),
    ("Google Places", "google.places", "routing", "runtime", "P", "api_key billing_project", "https://developers.google.com/maps/billing-and-pricing/pricing", "https://places.googleapis.com", "place_search", "SKU coverage", "SKU-specific allowances; product/display/retention restrictions; not unlimited search."),
    ("SerpApi search", "serpapi.free serpapi.paid", "search", "runtime", "B", "api_key", "https://serpapi.com/legal", "https://serpapi.com", "search", "engine coverage", "250/month Free; explicit free-commercial grant unverified; third-party content/resale not cleared."),
    ("OpenAI API / Realtime", "openai.api openai.realtime", "ai", "runtime", "P", "server_api_key", "https://developers.openai.com/api/docs/pricing", "https://api.openai.com", "inference", "model capabilities", "Paid API policies; no durable general free tier; ChatGPT subscription not API credits; Realtime client ephemeral token only."),
    ("MapLibre GL JS", "maplibre.library", "software", "library", "D", "none", "https://raw.githubusercontent.com/maplibre/maplibre-gl-js/main/LICENSE.txt", "", "map_renderer", "library", "BSD-3-Clause retain notices; no hosted data entitlement."),
    ("Three.js", "threejs.library", "software", "library", "D", "none", "https://raw.githubusercontent.com/mrdoob/three.js/dev/LICENSE", "", "3d_library", "library", "MIT retain notices; no asset/service entitlement."),
    ("deck.gl", "deckgl.library", "software", "library", "D", "none", "https://raw.githubusercontent.com/visgl/deck.gl/master/LICENSE", "", "visualization_library", "library", "MIT retain notices; optional component."),
    ("CesiumJS", "cesiumjs.library", "software", "library", "D", "none", "https://cesium.com/platform/cesiumjs/", "", "globe_renderer", "library", "Apache-2.0 independent of ion Community eligibility; own data requires no ion token."),
    ("Babylon.js", "babylonjs.library", "software", "library", "D", "none", "https://raw.githubusercontent.com/BabylonJS/Babylon.js/master/license.md", "", "3d_library", "library", "Apache-2.0 notices; optional engine."),
    ("satellite.js", "satellitejs.library", "software", "library", "D", "none", "https://raw.githubusercontent.com/shashwatak/satellite-js/develop/LICENSE.md", "", "orbital_propagation", "library", "MIT; orbital source rights separate; predictions are not observed positions."),
    ("Blender / glTF", "blender.tool gltf.format", "software", "library", "D", "none", "https://www.blender.org/about/license/", "", "asset_tooling", "tool/format", "Blender GPL distribution duties; authored output not automatically GPL; glTF royalty-free format; asset rights separate."),
    ("Poly Haven downloadable assets", "polyhaven.assets", "assets", "asset", "D", "none", "https://polyhaven.com/license", "", "asset_import", "selected assets", "CC0 including self-hosted redistribution; explicit downloads only."),
    ("Poly Haven live API", "polyhaven.api", "assets", "catalogue", "D", "identifying_headers", "https://raw.githubusercontent.com/Poly-Haven/Public-API/master/ToS.md", "https://api.polyhaven.com", "asset_catalogue", "catalogue coverage", "Separate API terms; visible provider credit; identifying User-Agent/Referer."),
    ("NASA 3D Resources", "nasa.3d_assets", "assets", "asset", "B", "none", "https://www.nasa.gov/nasa-brand-center/images-and-media/", "", "asset_import", "per asset", "Per-asset/media/IP review; third-party copyright, logos, endorsement/person rights separate."),
    ("Sketchfab eligible free assets / Download API", "sketchfab.assets sketchfab.download_api", "assets", "asset", "B", "account", "https://sketchfab.com/developers/download-api", "", "asset_import", "per model", "Exact model licence/extraction rights; NC not commercial, ND limits adaptation; API app/end-user OAuth2 separate."),
    ("TurboSquid selected free models", "turbosquid.assets", "assets", "asset", "B", "account", "https://blog.turbosquid.com/turbosquid-3d-model-license/", "", "asset_import", "per model", "Exact model/Editorial terms; downloadable GLB/custom WebGL distribution not automatic; no free catalogue API."),
    ("CGTrader selected free models", "cgtrader.assets cgtrader.approved_api", "assets", "asset", "B", "account", "https://help.cgtrader.com/hc/en-us/articles/360015122437-Can-I-commercially-use-a-free-model", "", "asset_import", "per model", "Seller licence, Incorporated Products/extraction protection/IP review; Editorial limited; approved API key/OAuth separate."),
    ("TeleGeography current cable dataset", "telegeography.current_data", "assets", "download", "P", "contract", "https://www2.telegeography.com/license-geocoded-map-data", "", "cable_import", "contract dataset", "No verified free raw data even students; paid negotiated licence/contract delivery, not public API."),
    ("TeleGeography map screenshots/references", "telegeography.screenshots", "assets", "asset", "D", "none", "https://www2.telegeography.com/license-telegeography-map", "", "map_reference", "specified maps", "CC BY-SA 4.0 attribution/ShareAlike; not raw data; interactive map not embeddable."),
    ("Historical cable snapshot bundled in GEV", "gev.cable_snapshot", "assets", "download", "B", "none", "gods-eye-view/DATA_SOURCES.md", "", "cable_import", "historical snapshot", "Authentic bundled CC BY-NC-SA provenance unverified; no commerce without separate permission; never copy by existence alone."),
)


# Product differences are explicit; no provider-wide inferred permissions.
_OVERRIDES = {
    "cdse.catalogue": {"origin": "https://stac.dataspace.copernicus.eu"},
    "openweather.basic": {"auth": "api_key"},
    "openweather.one_call": {"auth": "api_key subscription"},
    "cdse.authenticated_search": {"policy": "C", "auth": "account bearer_token"},
    "opentopography.enterprise": {"policy": "P", "auth": "enterprise_api_key", "ack": ("contract_scope", "dataset_scope")},
    "worldpop.high_limit": {"policy": "C", "auth": "approved_api_key"},
    "opensky.authenticated": {"policy": "CN", "auth": "oauth_client bearer_token"},
    "opensky.operational": {"policy": "B", "auth": "oauth_client bearer_token", "notes": "Written operational deployment licence required even for nonprofits."},
    "adsbexchange.community": {"policy": "P", "auth": "rapidapi_key", "ack": ("billing", "non_commercial")},
    "adsbexchange.enterprise": {"policy": "P", "auth": "enterprise_api_key", "ack": ("billing", "contract_scope")},
    "flightaware.personal": {"ack": ("billing", "personal_academic")},
    "flightaware.business": {"ack": ("billing", "business_subscription")},
    "celestrak.supgp": {"policy": "B", "notes": "Supplemental owner/operator data commercial and broader redistribution rights unverified; standard GP grant does not apply.", "coverage": "supplemental owner/operator data"},
    "thespacedevs.ll2_high_limit": {"policy": "C", "auth": "access_token"},
    "drivebc.media": {"policy": "B", "kind": "runtime", "capability": "camera_images"},
    "ontario511.media": {"policy": "B", "kind": "runtime", "capability": "camera_images"},
    "nsw.media": {"policy": "B", "kind": "runtime", "capability": "camera_images"},
    "vegvesen.datex": {"policy": "C", "auth": "account", "kind": "runtime"},
    "vegvesen.media": {"policy": "B", "kind": "runtime", "capability": "camera_images"},
    "gtfs.feeds": {"policy": "B", "kind": "catalogue", "auth": "endpoint_dependent", "capability": "transit_feed"},
    "gbfs.feeds": {"policy": "B", "kind": "catalogue", "auth": "endpoint_dependent", "capability": "bikeshare_feed"},
    "mbta.v3": {"auth": "api_key"},
    "serpapi.paid": {"policy": "P", "ack": ("billing", "paid_scope"), "blockers": ("Exact paid deployment/service scope must be reviewed; purchasing a plan or checking paid_scope does not clear third-party content/resale rights.",), "notes": "Separate paid service, not the 250-search Free grant; exact paid scope needs review; no publisher content or resale grant inferred."},
    "cesium.ion_community": {"ack": ("community_eligibility",)},
    "maptiler.free": {"ack": ("non_commercial_or_research_development",)},
    "sketchfab.download_api": {"kind": "download", "auth": "registered_app end_user_oauth"},
    "cgtrader.approved_api": {"kind": "catalogue", "auth": "approved_api_key oauth"},
    "gltf.format": {"notes": "Royalty-free glTF format, not Blender GPL or an asset licence.", "terms": "https://www.khronos.org/gltf/"},
    "windy.webcams_professional": {"auth": "private_api_key subscription"},
    "nasa.worldview_snapshots": {"origin": "https://wvs.earthdata.nasa.gov", "capability": "imagery_snapshot"},
    "noaa.swpc": {"origin": "https://services.swpc.noaa.gov", "terms": "https://www.swpc.noaa.gov/content/data-access", "capability": "space_weather"},
    "openmeteo.air_quality": {"origin": "https://air-quality-api.open-meteo.com", "capability": "air_quality"},
    "google.routes_essentials": {"origin": "https://routes.googleapis.com", "capability": "routing"},
    "google.geocoding": {"capability": "geocoding"},
    "google.street_view_dynamic": {"origin": "https://maps.googleapis.com", "capability": "street_view_viewer"},
    "openai.realtime": {"capability": "realtime_inference"},
    "tomtom.traffic": {"capability": "traffic"},
    "tomtom.routing": {"capability": "routing"},
    "fossgis.overpass": {"capability": "osm_query"},
}

_EXTRA_ROWS = (
    ("Legacy USGS WaterServices (procurement note)", "usgs.waterservices_legacy", "science", "runtime", "B", "none", "https://waterservices.usgs.gov/", "https://waterservices.usgs.gov", "gauges", "legacy United States stations", "Retires February 22, 2027; no legacy permission/quota transfer to modern WaterData; legacy access/reuse must be reviewed separately."),
)

_RENDERERS = {
    "reearth.terrain": ("cesium",),
    "google.photorealistic_3d": ("cesium",),
    "cesium.ion_community": ("cesium",),
    "google.street_view_static": ("dedicated_google_view",),
    "google.street_view_dynamic": ("dedicated_google_view",),
}

_LIMITS = {
    "cdse.catalogue": (("requests_hour", 60),),
    "openweather.basic": (("requests_hour", 60),),
    "openmeteo.weather": (("requests_hour", 60),),
    "openmeteo.air_quality": (("requests_hour", 60),),
    "rainviewer.public": (("requests_hour", 60),),
    "openai.api": (("requests_day", 20),),
    "serpapi.paid": (("requests_month", 100),),
    "cdse.processing": (("requests_month", 10000), ("processing_units_month", 10000)),
    "maptiler.free": (("sessions_month", 5000), ("requests_month", 100000)),
    "worldpop.public": (("requests_day", 1000),),
    "openweather.one_call": (("included_calls_day", 1000),),
    "thespacedevs.ll2": (("requests_hour_ip", 15),),
    "aviationstack.free": (("requests_month", 100),),
    "graphhopper.free": (("credits_day", 500),),
    "serpapi.free": (("searches_month", 250),),
    "google.photorealistic_3d": (("included_events_month", 1000),),
    "google.street_view_static": (("included_events_month", 10000),),
    "google.street_view_dynamic": (("included_events_month", 5000),),
    "google.geocoding": (("included_events_month_sku", 10000),),
    "google.routes_essentials": (("included_events_month_sku", 10000),),
    "tomtom.traffic": (("tiles_month", 200000), ("segments_month", 20000)),
    "cesium.ion_community": (("storage_gb", 10), ("streaming_gb_month", 15)),
    "nominatim.public": (("requests_second", 1),),
    "fossgis.routing": (("requests_second", 1),),
}

_AUTH_FIELDS = {
    "account": ("username", "password"), "approved_account": ("username", "password"),
    "bearer_token": ("bearer_token",), "oauth_client": ("client_id", "client_secret"),
    "oauth": ("client_id", "client_secret", "refresh_token"),
    "api_key": ("api_key",), "server_api_key": ("api_key",),
    "enterprise_api_key": ("api_key",), "approved_api_key": ("api_key",),
    "rapidapi_key": ("api_key",), "private_api_key": ("api_key",),
    "map_key": ("map_key",), "access_token": ("access_token",),
    "registered_access_token": ("access_token",), "scoped_public_token": ("public_token",),
    "client_token": ("client_token",), "registered_app": ("client_id",),
    "end_user_oauth": ("client_id", "client_secret", "refresh_token"),
    "session": ("session_token",), "gateway_credentials": ("api_key",),
}


def _build():
    products, mappings = {}, {}
    for label, ids, category, kind, policy, auth, terms, origin, capability, coverage, notes in _ROWS + _EXTRA_ROWS:
        mappings[label] = tuple(ids.split())
        for product_id in mappings[label]:
            override = _OVERRIDES.get(product_id, {})
            code = override.get("policy", policy)
            product_kind = override.get("kind", kind)
            auth_fields = tuple(override.get("auth", auth).split())
            credentialed = any(field not in ("none", "identifying_headers", "optional_api_key") for field in auth_fields)
            description = override.get("notes", notes)
            restricted = code in ("N", "CN", "T")
            acknowledgements = override.get("ack", ("non_commercial",) if restricted else ("billing",) if code == "P" else ())
            if product_id == "opensky.research" or product_id == "opensky.authenticated":
                acknowledgements = ("research_education",)
            if product_id == "rainviewer.public":
                acknowledgements = ("personal_educational",)
            if product_id == "google.news_rss":
                acknowledgements = ("personal_non_commercial",)
            if product_id.startswith("fossgis."):
                acknowledgements = ("incidental_use",)
            # Source selection is a release gate, not a generic browser claim.
            blocker = override.get("blockers", (description,) if code == "B" else ())
            if product_id == "nasa.earthdata_downloads":
                blocker = ("Exact selected collection rights must be reviewed.",)
            dependency = ("library:" if product_kind == "library" else "workflow:" if product_kind in ("download", "asset", "self_hosted") else "adapter:") + product_id
            product = Product(
                id=product_id, provider_id=product_id.split(".")[0],
                name=label if len(mappings[label]) == 1 else label + " [" + product_id.split(".")[1] + "]",
                matrix_row=label, category=category, kind=product_kind,
                capabilities=(override.get("capability", capability),), coverage=override.get("coverage", coverage),
                authentication=auth_fields, credential_required=credentialed,
                free_status="paid with product-specific allowance or contract" if code == "P" else "30-day trial" if code == "T" else "unverified offering or scope" if code == "B" else "free under stated conditions; own hosting costs separate",
                commercial_status="unverified" if code == "B" else "not eligible under this restricted offering" if restricted else "conditional under exact offering terms",
                eligibility=description, default_enabled=code == "D" and not credentialed,
                terms=(override.get("terms", terms),) if override.get("terms", terms) else (), verification_date=VERIFIED_ON,
                attribution=description, data_rights=description,
                media_rights=description if "images" in capability or product_kind == "asset" else "No linked or third-party media grant; review separately.",
                service_rights=description,
                cache_policy="no offline/prefetch/bulk" if product_id == "osm.raster" else "bounded caching only after operation-specific policy review; no blanket disk permission",
                stale_policy="never represent stale content as current; maximum stale age must be reviewed per adapter",
                export_policy="blocked pending operation-specific review" if blocker else "exact data/media licence only; no blanket export entitlement",
                history_policy="no routine live-feed disk history; explicit retention requires product review",
                endpoint_origins=(override.get("origin", origin),) if override.get("origin", origin) else (),
                limits=(("max_response_bytes", 8 * 1024 * 1024), ("max_pages", 1), ("timeout_seconds", 20), ("provider_quota_verified", product_id in _LIMITS)) + _LIMITS.get(product_id, ()),
                renderers=_RENDERERS.get(product_id, ("maplibre", "cesium")),
                acknowledgements=acknowledgements, permission_blockers=blocker,
                setup_blockers=("Reviewed " + dependency + " implementation is not connected by this catalogue.",),
                dependencies=(dependency,), implementation_status="dependency_pending" if product_kind == "library" else "workflow_pending" if product_kind in ("download", "asset", "self_hosted") else "adapter_pending",
                auth_fields=tuple(dict.fromkeys(field for method in auth_fields for field in _AUTH_FIELDS.get(method, ()))),
                environment=(("api_key", "OPENAI_API_KEY"),) if product_id.startswith("openai.") else (("api_key", "SERP_API_KEY"),) if product_id.startswith("serpapi.") else (),
                billing=code == "P",
            )
            if product_id in products:
                raise ValueError("Duplicate reviewed product ID: " + product_id)
            products[product_id] = product
    return MappingProxyType(products), MappingProxyType(mappings)


PRODUCTS, MATRIX_ROWS = _build()


def get_product(product_id):
    """Return immutable policy; unknown IDs raise KeyError."""
    return PRODUCTS[product_id]


def catalogue():
    """Return detached JSON-safe policy records. No credentials or user intent."""
    records = []
    for product in PRODUCTS.values():
        record = asdict(product)
        for key, value in tuple(record.items()):
            if isinstance(value, tuple):
                record[key] = list(value)
        record["environment"] = dict(product.environment)
        record["limits"] = dict(product.limits)
        records.append(record)
    return records


def effective_state(product, settings, configured, renderer="maplibre", dependencies=None):
    """Resolve eligibility, not observations, health or quota admission.

    Only exact True enables a flag. Acknowledgements are identifiers in a list
    or tuple; arbitrary permission records and expiry claims are not accepted.
    Expiring eligibility needs a reviewed application dependency workflow before
    activation. Unknown IDs and malformed inputs fail closed without side effects.
    ``dependencies`` maps immutable dependency IDs to exact bool readiness.
    """
    product_id = product.id if isinstance(product, Product) else product
    policy = PRODUCTS.get(product_id) if isinstance(product_id, str) else None
    settings_valid = isinstance(settings, dict)
    values = settings if settings_valid else {}
    enable_override = values.get("enabled")
    requested = (policy.default_enabled if policy else False) if enable_override is None else enable_override
    requested = requested is True
    result = {"id": product_id if isinstance(product_id, str) else None,
              "requested_enabled": requested, "effective_enabled": False,
              "state": "permission_blocked", "reasons": []}
    if policy is None or isinstance(product, Product) and product != policy:
        result["reasons"] = ["Unknown or non-authoritative product policy."]
        return result
    if policy.permission_blockers:
        result["reasons"] = list(policy.permission_blockers)
        return result
    if renderer not in policy.renderers:
        result.update(state="incompatible_renderer", reasons=["Product is not supported in this renderer."])
        return result
    readiness = dependencies if isinstance(dependencies, dict) else {}
    missing = [key for key in policy.dependencies if readiness.get(key) is not True]
    if missing:
        result.update(state="needs_setup", reasons=["Missing reviewed implementation/dependency: " + key for key in missing])
        return result
    if not settings_valid or enable_override is not None and type(enable_override) is not bool:
        result.update(state="disabled", reasons=["Malformed product enablement settings."])
        return result
    # Configured environment credentials never supply explicit user opt-in.
    if (policy.credential_required or policy.acknowledgements) and values.get("enabled") is not True:
        result.update(state="disabled", reasons=["Explicit product opt-in required."])
        return result
    if policy.credential_required and configured is not True:
        result.update(state="needs_credentials", reasons=["Required product authentication is not configured."])
        return result
    acknowledged = values.get("acknowledged", ())
    if not isinstance(acknowledged, (list, tuple)) or any(not isinstance(item, str) for item in acknowledged):
        acknowledged = ()
    missing_ack = [key for key in policy.acknowledgements if key not in acknowledged]
    if missing_ack:
        result.update(state="disabled", reasons=["Eligibility acknowledgement required: " + key for key in missing_ack])
        return result
    if policy.id == "sentinel_hub.standalone" and readiness.get("eligibility:sentinel_hub.standalone_trial_valid") is not True:
        result.update(state="needs_setup", reasons=["Reviewed unexpired 30-day trial eligibility required; subscription is a separate offering."])
        return result
    if not requested:
        result.update(state="disabled", reasons=["Disabled by user."])
        return result
    result.update(state="ready", effective_enabled=True, reasons=[])
    return result
