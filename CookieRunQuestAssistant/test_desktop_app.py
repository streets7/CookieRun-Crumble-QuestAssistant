import errno
import unittest
from unittest import mock

import desktop_app


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWindow:
    def __init__(self):
        self.events = type("Events", (), {"closed": Event()})()


class FakeWebview:
    def __init__(self):
        self.windows = []
        self.started = False

    def create_window(self, title, url, **options):
        self.windows.append((title, url, options))
        return FakeWindow()

    def start(self, **options):
        self.started = True


class FakeServer:
    def __init__(self):
        self.served = False
        self.shutdown_called = False
        self.closed = False

    def serve_forever(self):
        self.served = True

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.closed = True


class FakeWorker:
    def __init__(self):
        self.joined = False

    def join(self):
        self.joined = True


class DesktopAppTests(unittest.TestCase):
    def test_run_desktop_creates_one_local_window_without_browser(self):
        fake_webview = FakeWebview()
        fake_server = FakeServer()

        result = desktop_app.run_desktop(
            webview_module=fake_webview,
            server_factory=lambda: fake_server,
        )

        self.assertEqual(result, 0)
        self.assertTrue(fake_webview.started)
        self.assertEqual(len(fake_webview.windows), 1)
        self.assertEqual(fake_webview.windows[0][1], "http://127.0.0.1:8765/")
        self.assertTrue(fake_server.served)
        self.assertTrue(fake_server.shutdown_called)
        self.assertTrue(fake_server.closed)

    def test_duplicate_port_uses_existing_app_without_stopping_its_server(self):
        fake_webview = FakeWebview()
        port_error = OSError(errno.EADDRINUSE, "busy")

        with mock.patch.object(desktop_app, "existing_app_available", return_value=True):
            result = desktop_app.run_desktop(
                webview_module=fake_webview,
                server_factory=mock.Mock(side_effect=port_error),
            )

        self.assertEqual(result, 0)
        self.assertEqual(len(fake_webview.windows), 1)
        self.assertTrue(fake_webview.started)

    def test_shutdown_desktop_stops_engine_and_server_once(self):
        fake_server = FakeServer()
        fake_worker = FakeWorker()
        desktop_app.engine.STOP = False
        desktop_app.engine.SKIP_ACTION = True
        with mock.patch.dict(desktop_app.web_ui.STATE, {"worker": fake_worker}):
            desktop_app.shutdown_desktop(fake_server)
            desktop_app.shutdown_desktop(fake_server)

        self.assertTrue(desktop_app.engine.STOP)
        self.assertFalse(desktop_app.engine.SKIP_ACTION)
        self.assertTrue(fake_worker.joined)
        self.assertTrue(fake_server.shutdown_called)
        self.assertTrue(fake_server.closed)


if __name__ == "__main__":
    unittest.main()
