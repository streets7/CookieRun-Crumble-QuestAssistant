"""Native desktop host for the existing local control interface."""
from __future__ import annotations

import errno
import threading
import urllib.request

import quest_assistant as engine
import web_ui


APP_TITLE = "쿠키런: 크럼블 퀘스트 도우미"
APP_URL = f"http://{web_ui.HOST}:{web_ui.PORT}/"


def existing_app_available(timeout=0.7):
    try:
        with urllib.request.urlopen(f"{APP_URL}status", timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def shutdown_desktop(server):
    if server is None or getattr(server, "_cqa_closed", False):
        return
    server._cqa_closed = True
    engine.SKIP_ACTION = False
    engine.STOP = True
    with web_ui.LOCK:
        worker = web_ui.STATE.get("worker")
    if worker is not None and worker is not threading.current_thread():
        worker.join()
    server.shutdown()
    server.server_close()


def run_desktop(webview_module=None, server_factory=None):
    if webview_module is None:
        import webview as webview_module

    if server_factory is None:
        server_factory = web_ui.create_server

    owns_server = True
    try:
        server = server_factory()
    except OSError as error:
        if getattr(error, "errno", None) not in (errno.EADDRINUSE, 48, 10048):
            raise
        if not existing_app_available():
            raise RuntimeError("프로그램 포트가 다른 앱에서 사용 중입니다.") from error
        server = None
        owns_server = False

    if server is not None:
        threading.Thread(target=server.serve_forever, name="cqa-local-server", daemon=True).start()

    window = webview_module.create_window(
        APP_TITLE,
        APP_URL,
        width=1180,
        height=860,
        min_size=(760, 620),
        text_select=True,
    )
    if owns_server:
        window.events.closed += lambda: shutdown_desktop(server)
    try:
        webview_module.start(debug=False)
    finally:
        if owns_server:
            shutdown_desktop(server)
    return 0

