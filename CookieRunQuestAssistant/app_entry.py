#!/usr/bin/env python3
"""Desktop executable entry point for macOS and Windows bundles."""
import sys
import json
from pathlib import Path


def main():
    if "--self-test" in sys.argv:
        import quest_assistant as engine
        import web_ui
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        checks = {
            "version": web_ui.APP_VERSION,
            "assets": (root / "assets").is_dir(),
            "ocr": engine.VISION_OCR.is_file() or engine.VISION_OCR_WINDOWS.is_file(),
            "data_dir": str(web_ui.DATA_DIR),
        }
        print(json.dumps(checks, ensure_ascii=False))
        if not all(checks[key] for key in ("assets", "ocr")):
            raise SystemExit(2)
    else:
        from desktop_app import run_desktop
        raise SystemExit(run_desktop())


if __name__ == "__main__":
    main()
