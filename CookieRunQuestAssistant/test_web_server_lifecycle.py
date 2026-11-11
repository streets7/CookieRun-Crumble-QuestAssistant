import unittest
from unittest import mock

import web_ui


class FakeServer:
    def __init__(self):
        self.served = False
        self.closed = False

    def serve_forever(self):
        self.served = True

    def server_close(self):
        self.closed = True


class WebServerLifecycleTests(unittest.TestCase):
    def test_create_server_binds_to_requested_localhost(self):
        sentinel = object()
        with mock.patch.object(web_ui, "ThreadingHTTPServer", return_value=sentinel) as server_class:
            server = web_ui.create_server("127.0.0.1", 0)

        self.assertIs(server, sentinel)
        server_class.assert_called_once_with(("127.0.0.1", 0), web_ui.Handler)

    def test_desktop_serve_does_not_open_browser_and_stops_engine(self):
        fake_server = FakeServer()
        web_ui.engine.STOP = False
        web_ui.engine.SKIP_ACTION = True
        with mock.patch.object(web_ui, "create_server", return_value=fake_server), mock.patch.object(
            web_ui.webbrowser, "open"
        ) as open_browser:
            web_ui.serve(open_browser=False)

        open_browser.assert_not_called()
        self.assertTrue(fake_server.served)
        self.assertTrue(fake_server.closed)
        self.assertTrue(web_ui.engine.STOP)
        self.assertFalse(web_ui.engine.SKIP_ACTION)


if __name__ == "__main__":
    unittest.main()
