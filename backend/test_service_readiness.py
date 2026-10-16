"""Offline readiness coverage and fail-closed inventory regressions."""

from dataclasses import FrozenInstanceError
import inspect
import json
import unittest
from unittest import mock

from backend import service_readiness as reviewed
from backend import service_registry as registry


class ServiceReadinessTests(unittest.TestCase):
    def test_exact_catalogue_coverage_and_fixed_reviewed_groups(self):
        ids = [product_id for group in reviewed._GROUPS for product_id in group[0]]
        self.assertEqual(len(ids), 152)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(registry.PRODUCTS))
        self.assertEqual(set(reviewed.REVIEWED_ENTRIES), set(registry.PRODUCTS))
        for product_id, entry in reviewed.REVIEWED_ENTRIES.items():
            with self.subTest(product_id=product_id):
                self.assertIsInstance(entry.setup_steps, tuple)
                self.assertEqual(len(entry.setup_steps), 2)
                self.assertGreater(len(entry.setup_steps[0]), 60)
                self.assertGreater(len(entry.setup_steps[1]), 60)
                self.assertNotIn("implementation pending", " ".join(entry.setup_steps).lower())
                self.assertNotIn("not connected by this catalogue", " ".join(entry.setup_steps))
                self.assertEqual(entry.dependencies, registry.PRODUCTS[product_id].dependencies)
                self.assertEqual(entry.capabilities, registry.PRODUCTS[product_id].capabilities)

    def test_shape_json_safety_and_missing_inventory_for_every_product(self):
        keys = {"implementation_status", "setup_steps", "blockers", "capabilities", "live_tested"}
        for product_id in registry.PRODUCTS:
            with self.subTest(product_id=product_id):
                result = reviewed.readiness(product_id, set(), set())
                self.assertEqual(set(result), keys)
                self.assertIs(result["live_tested"], False)
                self.assertTrue(result["blockers"])
                self.assertIn(result["implementation_status"], {"needs_setup", "permission_blocked"})
                self.assertEqual(json.loads(json.dumps(result)), result)

    def test_inventory_does_not_clear_any_authoritative_permission_blocker(self):
        installed = {key for product in registry.PRODUCTS.values() for key in product.dependencies}
        for product_id, product in registry.PRODUCTS.items():
            with self.subTest(product_id=product_id):
                result = reviewed.readiness(product_id, installed, set(registry.PRODUCTS))
                if product.permission_blockers:
                    self.assertEqual(result["implementation_status"], "permission_blocked")
                    for blocker in product.permission_blockers:
                        self.assertIn(blocker, result["blockers"])
                self.assertIs(result["live_tested"], False)
                state = registry.effective_state(product_id,
                    {"enabled": True, "acknowledged": list(product.acknowledgements),
                     "permission": "approved", "grant": True}, True,
                    dependencies={key: True for key in installed})
                if product.permission_blockers:
                    self.assertFalse(state["effective_enabled"])
                    self.assertEqual(state["state"], "permission_blocked")

    def test_review_is_immutable_and_results_are_detached(self):
        entry = reviewed.REVIEWED_ENTRIES["openfreemap.public"]
        with self.assertRaises(TypeError):
            reviewed.REVIEWED_ENTRIES["fake.product"] = entry
        with self.assertRaises(FrozenInstanceError):
            entry.setup_steps = ()
        before = registry.catalogue()
        result = reviewed.readiness("openfreemap.public", set(), set())
        result["setup_steps"].clear()
        result["blockers"].append("fake permission")
        result["capabilities"].clear()
        self.assertEqual(registry.catalogue(), before)
        self.assertEqual(reviewed.readiness("openfreemap.public", set(), set())["setup_steps"], list(entry.setup_steps))

    def test_unknown_ids_and_settings_shaped_inventory_never_fall_back(self):
        for product_id in ("unknown.product", "openfreeMap.public", "openfreemap", "", None):
            with self.subTest(product_id=product_id), self.assertRaises(KeyError):
                reviewed.readiness(product_id, set(), set())
        for inventory in ({"adapter:openfreemap.public": True}, ["adapter:openfreemap.public"], True, None):
            with self.subTest(inventory=inventory), self.assertRaises(TypeError):
                reviewed.readiness("openfreemap.public", inventory, set())
            with self.subTest(paths=inventory), self.assertRaises(TypeError):
                reviewed.readiness("openfreemap.public", set(), inventory)
        self.assertEqual(tuple(inspect.signature(reviewed.readiness).parameters),
                         ("product_id", "installed", "configured_paths"))

    def test_optional_software_missing_is_honest(self):
        software = ("maplibre.library", "threejs.library", "deckgl.library", "cesiumjs.library",
                    "babylonjs.library", "satellitejs.library", "blender.tool", "gltf.format")
        for product_id in software:
            with self.subTest(product_id=product_id):
                self.assertEqual(reviewed.readiness(product_id, set(), set())["implementation_status"], "needs_setup")
                # Supplying a product name is not installing its dependency.
                self.assertEqual(reviewed.readiness(product_id, {product_id}, set())["implementation_status"], "needs_setup")
                installed = set(registry.PRODUCTS[product_id].dependencies)
                self.assertEqual(reviewed.readiness(product_id, installed, set())["implementation_status"], "loaded_dependency")

    def test_documented_download_prerequisites_are_not_executable_importers(self):
        for product_id in ("osm.extracts", "naturalearth.downloads", "polyhaven.assets", "mapillary.licensed_images",
                           "noaa.gfs", "ecmwf.open_data", "copernicus.marine", "telegeography.screenshots"):
            with self.subTest(product_id=product_id):
                result = reviewed.readiness(product_id, set(), {product_id})
                self.assertEqual(result["implementation_status"], "needs_setup")
                self.assertTrue(any("Missing workflow:" in blocker for blocker in result["blockers"]))
                result = reviewed.readiness(product_id, set(registry.PRODUCTS[product_id].dependencies), set())
                self.assertEqual(result["implementation_status"], "connected_workflow")
                self.assertIs(result["live_tested"], False)

    def test_explicit_self_hosted_and_schedule_configuration(self):
        for product_id in ("openmaptiles.self_hosted", "osrm.self_hosted", "valhalla.self_hosted",
                           "graphhopper.self_hosted", "entur.open_data", "translink.queensland"):
            with self.subTest(product_id=product_id):
                installed = set(registry.PRODUCTS[product_id].dependencies)
                self.assertEqual(reviewed.readiness(product_id, installed, set())["implementation_status"], "needs_setup")
                # Arbitrary paths/URLs and permission-looking strings do not match product IDs.
                self.assertEqual(reviewed.readiness(product_id, installed, {"https://example.com", "approved", "C:/feed"})["implementation_status"], "needs_setup")
                self.assertIn(reviewed.readiness(product_id, installed, {product_id})["implementation_status"],
                              {"connected_workflow", "connected_adapter"})

    def test_google_display_gates_and_public_viewer_restrictions(self):
        google_ids = ("google.street_view_static", "google.street_view_dynamic", "google.geocoding",
                      "google.routes_essentials", "google.places")
        for product_id in google_ids:
            with self.subTest(product_id=product_id):
                result = reviewed.readiness(product_id, set(registry.PRODUCTS[product_id].dependencies), {product_id})
                self.assertEqual(result["implementation_status"], "permission_blocked")
                self.assertTrue(result["blockers"])
        for product_id in ("txdot.cameras", "deldot.cameras", "tallinn.cameras", "warendorf.webcam"):
            with self.subTest(product_id=product_id):
                text = " ".join(reviewed.REVIEWED_ENTRIES[product_id].setup_steps)
                self.assertIn("deep", text)
                self.assertIn("view", text)

    def test_separate_offerings_have_specific_access_roles_and_formats(self):
        expectations = {
            "cdse.processing": ("sh.dataspace.copernicus.eu", "processing-unit"),
            "sentinel_hub.standalone": ("services.sentinel-hub.com", "expiry"),
            "opentopography.personal": ("individual", "GeoTIFF"),
            "opentopography.enterprise": ("Enterprise", "contract"),
            "noaa.gfs": ("GRIB2", "issue/valid"),
            "noaa.nowcoast": ("WMS", "density"),
            "reearth.terrain": ("quantized-mesh", "Cesium"),
            "mapzen.terrarium": ("Terrarium", "PNG"),
            "spacetrack.basic_ssa": ("session", "OMM/TLE"),
            "vegvesen.datex": ("DATEX II XML", "credential"),
            "sketchfab.download_api": ("OAuth2", "ZIP/glTF"),
            "telegeography.current_data": ("contract", "not interactive-map scraping"),
            "telegeography.screenshots": ("reference images", "do not embed"),
            "gev.cable_snapshot": ("historical", "existence is not permission"),
        }
        for product_id, terms in expectations.items():
            with self.subTest(product_id=product_id):
                text = " ".join(reviewed.REVIEWED_ENTRIES[product_id].setup_steps)
                for term in terms:
                    self.assertIn(term, text)

    def test_pure_resolution_without_files_network_or_environment(self):
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem access")), \
                mock.patch("socket.create_connection", side_effect=AssertionError("network access")), \
                mock.patch.dict("os.environ", {}, clear=True):
            for product_id in registry.PRODUCTS:
                reviewed.readiness(product_id, frozenset(), frozenset())


if __name__ == "__main__":
    unittest.main()
