"""Small, failure-safe GitHub stable release checker."""
from __future__ import annotations

import json
import re
import urllib.request


def parse_version(value):
    match = re.search(r"\d+(?:\.\d+)*", str(value))
    return tuple(int(part) for part in match.group(0).split(".")) if match else ()


def select_platform_asset(release, platform_name):
    platform_name = str(platform_name).lower()
    if platform_name in ("darwin", "mac", "macos"):
        required_suffix = ".dmg"
    elif platform_name in ("windows", "win32", "win"):
        required_suffix = "-setup.exe"
    else:
        return None
    for asset in release.get("assets", []):
        name = str(asset.get("name", "")).lower()
        if name.endswith(required_suffix):
            return asset
    return None


def check_latest_release(api_url, current_version, platform_name, timeout=3.0):
    unavailable = {
        "status": "unavailable",
        "update_available": False,
        "current_version": current_version,
    }
    try:
        request = urllib.request.Request(
            api_url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "CookieRunQuestAssistant"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            release = json.loads(response.read().decode("utf-8"))
        if not isinstance(release, dict):
            return unavailable
        latest = str(release.get("tag_name", ""))
        if release.get("prerelease") or not parse_version(latest):
            return {**unavailable, "status": "current", "latest_version": latest}
        update_available = parse_version(latest) > parse_version(current_version)
        asset = select_platform_asset(release, platform_name)
        return {
            "status": "update" if update_available else "current",
            "update_available": update_available,
            "current_version": current_version,
            "latest_version": latest,
            "download_url": (asset or {}).get("browser_download_url") or release.get("html_url", ""),
        }
    except Exception:
        return unavailable

