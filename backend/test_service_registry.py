"""Pure policy regression tests; the matrix is read only by this test fixture.

Run: python -B -m unittest backend.test_service_registry
No server/config imports, real credential reads, downloads or provider requests.
"""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import re
import unittest
from unittest import mock

from backend import service_registry as registry


# Independent explicit fixture: additions/removals in either document or policy
# must be consciously reviewed, not accepted by a dynamic runtime parser.
ROW_PRODUCTS = {
    "OpenFreeMap public hosting": ("openfreemap.public",),
    "OpenStreetMap data / Geofabrik extracts": ("osm.extracts",),
    "OSM standard raster tile server": ("osm.raster",),
    "Natural Earth": ("naturalearth.downloads",),
    "NASA GIBS / Worldview Snapshots": ("nasa.gibs", "nasa.worldview_snapshots"),
    "NASA CMR public metadata search": ("nasa.cmr",),
    "NASA Earthdata product downloads": ("nasa.earthdata_downloads",),
    "Copernicus Data Space STAC / OData catalogue": ("cdse.catalogue", "cdse.authenticated_search"),
    "Copernicus Sentinel product downloads": ("cdse.sentinel_downloads",),
    "CDSE Sentinel Hub processing": ("cdse.processing",),
    "Standalone Sentinel Hub / Planet": ("sentinel_hub.standalone",),
    "OpenTopography APIs": ("opentopography.personal", "opentopography.enterprise"),
    "Mapterhorn terrain": ("mapterhorn.hosted",),
    "Re:Earth Terrain": ("reearth.terrain",),
    "Mapzen Terrarium / AWS terrain tiles": ("mapzen.terrarium",),
    "OpenMapTiles self-hosted stack": ("openmaptiles.self_hosted",),
    "MapTiler Cloud free plan": ("maptiler.free",),
    "Esri classic World Imagery MapServer": ("esri.world_imagery",),
    "ArcGIS Location Platform basemaps": ("arcgis.basemaps",),
    "Google Photorealistic 3D Tiles": ("google.photorealistic_3d",),
    "Cesium ion Community": ("cesium.ion_community",),
    "Overture base/buildings/divisions/transportation": ("overture.base",),
    "Overture places/addresses": ("overture.places_addresses",),
    "OpenBuildingMap downloadable dataset": ("openbuildingmap.downloads",),
    "OpenBuildingMap hosted mirror/API": ("openbuildingmap.hosted",),
    "WorldPop open datasets/API": ("worldpop.public", "worldpop.high_limit"),
    "OpenInfraMap source data": ("openinframap.source_data",),
    "US Census geographic boundary files": ("census.boundaries",),
    "DataSF neighborhood boundaries": ("datasf.neighborhoods",),
    "Open-Meteo Weather / Air Quality": ("openmeteo.weather", "openmeteo.air_quality"),
    "OpenWeather basic Free plan": ("openweather.basic",),
    "OpenWeather One Call": ("openweather.one_call",),
    "NOAA / NWS weather API": ("noaa.nws",),
    "NOAA GFS on AWS": ("noaa.gfs",),
    "NOAA nowCOAST radar / lightning density": ("noaa.nowcoast",),
    "NHC advisories / NOAA SWPC": ("noaa.nhc", "noaa.swpc"),
    "ECMWF Open Data": ("ecmwf.open_data",),
    "RainViewer public API": ("rainviewer.public",),
    "OpenAQ": ("openaq.api",),
    "NASA FIRMS": ("nasa.firms",),
    "NASA EONET": ("nasa.eonet",),
    "USGS earthquake GeoJSON feeds": ("usgs.earthquakes",),
    "USGS WaterData API": ("usgs.waterdata",),
    "Macrostrat": ("macrostrat.api",),
    "NASA JPL Horizons API": ("nasa.horizons",),
    "Copernicus Marine": ("copernicus.marine",),
    "OpenSky REST": ("opensky.research", "opensky.authenticated", "opensky.operational"),
    "adsb.lol public API": ("adsblol.public",),
    "adsbdb API": ("adsbdb.api",),
    "ADS-B Exchange API": ("adsbexchange.community", "adsbexchange.enterprise"),
    "FlightAware AeroAPI": ("flightaware.personal", "flightaware.business"),
    "Aviationstack": ("aviationstack.free",),
    "CelesTrak GP": ("celestrak.gp", "celestrak.supgp"),
    "Space-Track": ("spacetrack.basic_ssa",),
    "AISstream": ("aisstream.websocket",),
    "MarineTraffic API": ("marinetraffic.contract",),
    "Launch Library 2 / TheSpaceDevs": ("thespacedevs.ll2", "thespacedevs.ll2_high_limit"),
    "FAA aircraft registry downloads": ("faa.registry",),
    "Mapillary licensed images": ("mapillary.licensed_images",),
    "Mapillary API/viewer": ("mapillary.api",),
    "Google Street View": ("google.street_view_static", "google.street_view_dynamic"),
    "Windy Webcams API": ("windy.webcams_free", "windy.webcams_professional"),
    "Radio Browser metadata/API": ("radiobrowser.metadata",),
    "Radio Browser linked streams/artwork": ("radiobrowser.linked_media",),
    "TfL JamCams": ("tfl.jamcams",),
    "Digitraffic Finland cameras": ("digitraffic.cameras",),
    "DriveBC HighwayCams catalogue": ("drivebc.catalogue", "drivebc.media"),
    "Ontario 511 cameras": ("ontario511.catalogue", "ontario511.media"),
    "Transport NSW LiveTraffic": ("nsw.catalogue", "nsw.media"),
    "Statens vegvesen Norway cameras": ("vegvesen.catalogue", "vegvesen.datex", "vegvesen.media"),
    "Open Calgary traffic cameras": ("calgary.cameras",),
    "Austin traffic cameras": ("austin.cameras",),
    "TxDOT cameras": ("txdot.cameras",),
    "Caltrans CWWP2": ("caltrans.cwwp2",),
    "DelDOT cameras": ("deldot.cameras",),
    "Tallinn cameras": ("tallinn.cameras",),
    "Tarktee / Transpordiamet": ("tarktee.cameras",),
    "Warendorf webcam": ("warendorf.webcam",),
    "GTFS / GTFS-Realtime": ("gtfs.specification", "gtfs.feeds"),
    "GBFS feeds, e.g. BCycle/Lyft": ("gbfs.specification", "gbfs.feeds"),
    "Entur open transit data": ("entur.open_data",),
    "TransLink Queensland": ("translink.queensland",),
    "MBTA / MassDOT": ("mbta.gtfs_rt", "mbta.v3"),
    "CapMetro": ("capmetro.feeds",),
    "Metro Transit": ("metrotransit.feeds",),
    "OVapi": ("ovapi.feeds",),
    "HSL": ("hsl.feeds",),
    "NIFC WFIGS fire perimeters": ("nifc.wfigs",),
    "InciWeb incident pages": ("inciweb.pages",),
    "GDELT DOC 2.0": ("gdelt.doc2",),
    "Google News RSS": ("google.news_rss",),
    "Nominatim public geocoder": ("nominatim.public",),
    "Photon public geocoder": ("photon.public",),
    "Overpass public instances": ("overpass.public",),
    "FOSSGIS routing / Overpass servers": ("fossgis.routing", "fossgis.overpass"),
    "OSRM self-hosted": ("osrm.self_hosted",),
    "Valhalla self-hosted": ("valhalla.self_hosted",),
    "GraphHopper hosted free plan": ("graphhopper.free",),
    "GraphHopper self-hosted engine": ("graphhopper.self_hosted",),
    "TomTom traffic/routing": ("tomtom.traffic", "tomtom.routing"),
    "HERE Traffic API": ("here.traffic",),
    "Google Geocoding / Routes Essentials": ("google.geocoding", "google.routes_essentials"),
    "Google Places": ("google.places",),
    "SerpApi search": ("serpapi.free", "serpapi.paid"),
    "OpenAI API / Realtime": ("openai.api", "openai.realtime"),
    "MapLibre GL JS": ("maplibre.library",),
    "Three.js": ("threejs.library",),
    "deck.gl": ("deckgl.library",),
    "CesiumJS": ("cesiumjs.library",),
    "Babylon.js": ("babylonjs.library",),
    "satellite.js": ("satellitejs.library",),
    "Blender / glTF": ("blender.tool", "gltf.format"),
    "Poly Haven downloadable assets": ("polyhaven.assets",),
    "Poly Haven live API": ("polyhaven.api",),
    "NASA 3D Resources": ("nasa.3d_assets",),
    "Sketchfab eligible free assets / Download API": ("sketchfab.assets", "sketchfab.download_api"),
    "TurboSquid selected free models": ("turbosquid.assets",),
    "CGTrader selected free models": ("cgtrader.assets", "cgtrader.approved_api"),
    "TeleGeography current cable dataset": ("telegeography.current_data",),
    "TeleGeography map screenshots/references": ("telegeography.screenshots",),
    "Historical cable snapshot bundled in GEV": ("gev.cable_snapshot",),
}


class CatalogueTests(unittest.TestCase):
    def test_every_matrix_row_has_exact_explicit_mapping(self):
        matrix = Path(__file__).resolve().parents[1] / "MERIDIAN_SERVICE_ACCESS.md"
        labels = []
        for line in matrix.read_text(encoding="utf-8").splitlines():
            if not line.startswith("| "):
                continue
            cell = line.split("|")[1].strip()
            if cell in ("Service", "---"):
                continue
            labels.append(re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cell))
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(set(labels), set(ROW_PRODUCTS))
        self.assertEqual(len(labels), 121)
        for label, ids in ROW_PRODUCTS.items():
            self.assertEqual(registry.MATRIX_ROWS[label], ids, label)
            for product_id in ids:
                self.assertEqual(registry.get_product(product_id).matrix_row, label)
        self.assertEqual(set(registry.PRODUCTS), {pid for ids in ROW_PRODUCTS.values() for pid in ids} | {"usgs.waterservices_legacy"})

    def test_immutable_and_detached_json_catalogue(self):
        with self.assertRaises(TypeError):
            registry.PRODUCTS["fake"] = registry.get_product("openfreemap.public")
        with self.assertRaises(FrozenInstanceError):
            registry.get_product("openfreemap.public").default_enabled = False
        with self.assertRaises(TypeError):
            registry.MATRIX_ROWS["fake"] = ()
        records = registry.catalogue()
        json.dumps(records)
        records[0]["dependencies"].append("injected")
        self.assertNotIn("injected", registry.get_product(records[0]["id"]).dependencies)

    def test_rich_fields_and_truthful_pending_implementations(self):
        for product in registry.PRODUCTS.values():
            with self.subTest(product=product.id):
                for field in ("category", "kind", "capabilities", "coverage", "authentication", "free_status", "commercial_status", "eligibility", "attribution", "data_rights", "media_rights", "service_rights", "cache_policy", "stale_policy", "export_policy", "history_policy", "limits", "renderers", "setup_blockers", "dependencies", "implementation_status"):
                    self.assertTrue(getattr(product, field), field)
                self.assertEqual(product.verification_date, "2026-10-15")
                self.assertFalse(product.default_enabled and product.credential_required)
                self.assertFalse(product.default_enabled and product.permission_blockers)
                self.assertIn(product.implementation_status, ("adapter_pending", "workflow_pending", "dependency_pending"))

    def test_separate_product_policies(self):
        pairs = (("cdse.processing", "sentinel_hub.standalone"), ("esri.world_imagery", "arcgis.basemaps"), ("openweather.basic", "openweather.one_call"), ("cesiumjs.library", "cesium.ion_community"), ("celestrak.gp", "celestrak.supgp"), ("usgs.waterdata", "usgs.waterservices_legacy"), ("serpapi.free", "serpapi.paid"), ("drivebc.catalogue", "drivebc.media"), ("gtfs.specification", "gtfs.feeds"))
        for left, right in pairs:
            self.assertNotEqual(registry.get_product(left), registry.get_product(right))
        self.assertTrue(registry.get_product("celestrak.gp").default_enabled)
        self.assertTrue(registry.get_product("celestrak.supgp").permission_blockers)
        self.assertTrue(registry.get_product("serpapi.free").permission_blockers)
        self.assertTrue(registry.get_product("serpapi.paid").billing)
        self.assertTrue(registry.get_product("serpapi.paid").permission_blockers)
        self.assertIn("February 22, 2027", registry.get_product("usgs.waterservices_legacy").eligibility)


class EffectiveStateTests(unittest.TestCase):
    def state(self, product_id, settings=None, configured=False, renderer="maplibre", ready=True):
        product = registry.get_product(product_id)
        dependencies = {key: True for key in product.dependencies} if ready else None
        return registry.effective_state(product_id, settings or {}, configured, renderer, dependencies)

    def test_default_and_user_disable(self):
        self.assertTrue(self.state("openfreemap.public")["effective_enabled"])
        self.assertEqual(self.state("openfreemap.public", {"enabled": False})["state"], "disabled")
        self.assertEqual(self.state("openfreemap.public", ready=False)["state"], "needs_setup")
        self.assertTrue(self.state("openfreemap.public", {"enabled": None})["effective_enabled"])

    def test_credentials_never_auto_enable_even_environment_migration(self):
        for configured in (False, True):
            self.assertEqual(self.state("openweather.basic", configured=configured)["state"], "disabled")
        self.assertEqual(self.state("openweather.basic", {"enabled": True})["state"], "needs_credentials")
        self.assertTrue(self.state("openweather.basic", {"enabled": True}, True)["effective_enabled"])

    def test_restricted_and_paid_acknowledgements(self):
        self.assertFalse(self.state("openmeteo.weather", {"enabled": True})["effective_enabled"])
        self.assertTrue(self.state("openmeteo.weather", {"enabled": True, "acknowledged": ["non_commercial"]})["effective_enabled"])
        self.assertFalse(self.state("openai.api", {"enabled": True}, True)["effective_enabled"])
        self.assertTrue(self.state("openai.api", {"enabled": True, "acknowledged": ["billing"]}, True)["effective_enabled"])
        self.assertFalse(self.state("openmeteo.weather", {"enabled": True, "acknowledged": {"non_commercial": "expired"}})["effective_enabled"])

    def test_all_permission_blockers_cannot_be_overridden(self):
        for product in registry.PRODUCTS.values():
            if not product.permission_blockers:
                continue
            with self.subTest(product=product.id):
                values = {"enabled": True, "acknowledged": list(product.acknowledgements), "permission_approved": True, "permission_record": "I have rights"}
                dependencies = {key: True for key in product.dependencies}
                result = registry.effective_state(product, values, True, product.renderers[0], dependencies)
                self.assertEqual(result["state"], "permission_blocked")
                self.assertFalse(result["effective_enabled"])

    def test_precedence_and_renderer(self):
        self.assertEqual(self.state("esri.world_imagery", {"enabled": False}, renderer="unknown", ready=False)["state"], "permission_blocked")
        self.assertEqual(self.state("google.photorealistic_3d", {"enabled": True}, ready=False)["state"], "incompatible_renderer")
        self.assertEqual(self.state("openweather.basic", {"enabled": True}, ready=False)["state"], "needs_setup")
        for renderer in ("maplibre", "cesium"):
            self.assertEqual(self.state("google.street_view_static", {"enabled": True}, True, renderer)["state"], "incompatible_renderer")

    def test_trial_requires_reviewed_unexpired_eligibility(self):
        values = {"enabled": True, "acknowledged": ["non_commercial"], "trial_valid": True}
        product = registry.get_product("sentinel_hub.standalone")
        dependencies = {key: True for key in product.dependencies}
        self.assertEqual(registry.effective_state(product, values, True, dependencies=dependencies)["state"], "needs_setup")
        dependencies["eligibility:sentinel_hub.standalone_trial_valid"] = True
        self.assertTrue(registry.effective_state(product, values, True, dependencies=dependencies)["effective_enabled"])

    def test_malformed_unknown_and_forged_policies_fail_closed(self):
        for value in ("yes", 1, [], {}):
            self.assertFalse(self.state("openfreemap.public", {"enabled": value})["effective_enabled"])
        for product in ("missing", None, [], replace(registry.get_product("esri.world_imagery"), permission_blockers=())):
            self.assertFalse(registry.effective_state(product, {"enabled": True}, True)["effective_enabled"])
        product = registry.get_product("openfreemap.public")
        self.assertFalse(registry.effective_state(product, None, True, dependencies={key: True for key in product.dependencies})["effective_enabled"])
        self.assertFalse(registry.effective_state(product, {}, False, dependencies={key: 1 for key in product.dependencies})["effective_enabled"])
        self.assertFalse(self.state("openweather.basic", {"enabled": True}, configured=1)["effective_enabled"])

    def test_pure_no_io_no_mutation_no_health_claims(self):
        values = {"enabled": True, "acknowledged": []}
        product = registry.get_product("openfreemap.public")
        dependencies = {key: True for key in product.dependencies}
        with mock.patch("builtins.open", side_effect=AssertionError("No file reads")), mock.patch("socket.socket", side_effect=AssertionError("No network")):
            first = registry.effective_state(product, values, False, dependencies=dependencies)
            second = registry.effective_state(product, values, False, dependencies=dependencies)
            registry.catalogue()
        self.assertEqual(first, second)
        self.assertEqual(values, {"enabled": True, "acknowledged": []})
        self.assertEqual(dependencies, {key: True for key in product.dependencies})
        self.assertEqual(first["state"], "ready")
        self.assertNotIn("observations", first)


if __name__ == "__main__":
    unittest.main()
