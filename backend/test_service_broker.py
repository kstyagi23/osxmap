import unittest
from .service_broker import BrokerError, LocalBroker


class BrokerTests(unittest.TestCase):
    def test_cross_site_document_navigation_does_not_authorize_api_access(self):
        broker = LocalBroker(8787)
        headers = {"Host": "127.0.0.1:8787", "Sec-Fetch-Site": "cross-site",
                   "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        broker.validate(headers, document_navigation=True)
        with self.assertRaises(BrokerError):
            broker.validate(headers)
        with self.assertRaises(BrokerError):
            broker.session(headers)
        with self.assertRaises(BrokerError):
            broker.validate(headers, mutation=True, document_navigation=True)
        for changes in ({"Host": "evil.test:8787"}, {"Origin": "http://evil.test"},
                        {"Sec-Fetch-Mode": "cors"}, {"Sec-Fetch-Dest": "iframe"},
                        {"Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Dest": "image"}):
            with self.subTest(changes=changes), self.assertRaises(BrokerError):
                broker.validate({**headers, **changes}, document_navigation=True)

    def test_session_csrf_and_origin(self):
        broker = LocalBroker(8787)
        headers = {"Host": "127.0.0.1:8787", "Origin": "http://127.0.0.1:8787", "Content-Type": "application/json"}
        token, cookie = broker.session(headers)
        headers.update({"Cookie": cookie.split(";", 1)[0], "X-Meridian-CSRF": token})
        broker.validate(headers, mutation=True)
        for changes in ({"Host": "evil.test:8787"}, {"Origin": "http://evil.test"}, {"Origin": "null"},
                        {"X-Meridian-CSRF": "wrong"}, {"Cookie": ""}, {"Content-Type": "text/plain"},
                        {"Sec-Fetch-Site": "cross-site"}, {"Origin": ""}):
            with self.subTest(changes=changes), self.assertRaises(BrokerError):
                broker.validate({**headers, **changes}, mutation=True)
        two, _ = broker.session({"Host": "127.0.0.1:8787"})
        with self.assertRaises(BrokerError):
            broker.validate({**headers, "X-Meridian-CSRF": two}, mutation=True)

    def test_no_wildcard_or_remote_origins(self):
        for origin in ("*", "http://evil.test", "http://localhost:8000/path", "http://u@localhost:8000"):
            with self.assertRaises(ValueError):
                LocalBroker(8787, (origin,))
