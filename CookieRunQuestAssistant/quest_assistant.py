#!/usr/bin/env python3
"""Supervised CookieRun: Crumble quest assistant for BlueStacks.

The assistant uses BlueStacks' bundled local ADB. It intentionally stops on
unknown draw currency and caps the number of cycles. No detection-evasion or
background concealment is implemented.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image
from PIL import ImageChops, ImageStat


IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"


def find_bluestacks_adb() -> Path:
    """Locate the bundled BlueStacks ADB on macOS and Windows."""
    configured = os.environ.get("CQA_ADB_PATH", "").strip()
    candidates = [Path(configured)] if configured else []
    if IS_WINDOWS:
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(variable, "").strip()
            if base:
                candidates.extend((
                    Path(base) / "BlueStacks_nxt" / "HD-Adb.exe",
                    Path(base) / "BlueStacks" / "HD-Adb.exe",
                ))
        candidates.extend((
            Path(r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"),
            Path(r"C:\Program Files\BlueStacks\HD-Adb.exe"),
        ))
    else:
        candidates.append(Path("/Applications/BlueStacks.app/Contents/MacOS/hd-adb"))
    system_adb = shutil.which("adb")
    if system_adb:
        candidates.append(Path(system_adb))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0] if candidates else Path("adb")


ADB = find_bluestacks_adb()
ADB_SERIAL = None
GAME_PACKAGE = "com.devsisters.cc"
GAME_ACTIVITY = "com.devsisters.plugin.OvenUnityPlayerActivity"
DEVICE_SCREENSHOT = "/sdcard/codex_quest_assistant.png"
WIDTH, HEIGHT = 1080, 1920
DEVICE_WIDTH, DEVICE_HEIGHT = WIDTH, HEIGHT

# Coordinates measured from the supplied 1080 x 1920 recording.
QUEST_PANEL = (900, 1060)
TEN_DRAW = (575, 1565)
BOTTOM_X = (540, 1845)
AUTO_BUTTON = (415, 1725)
AUTO_START = (540, 1690)
EQUIPMENT_TUTORIAL_DONT_SHOW = (812, 1348)
BAG_FIRST_ITEM = (160, 1160)
ITEM_MINUS = (225, 708)
ITEM_USE = (540, 850)
EQUIPMENT_ACTION = (723, 1300)
BOSS_SUMMON_BUTTON = (540, 305)
BOSS_MOVE_SECONDS = 4.0
BOSS_CORNER_MOVE_SECONDS = 6.0
BOSS_D_MOVE_ENABLED = False
BOSS_AS_MOVE_ENABLED = False
BOSS_CONTROL_LOCK = threading.RLock()
BOSS_MOVEMENT_REVISION = 0
# Boss attempts start from preset 5. A summon button that reappears means the
# previous attempt did not clear the quest, so the next preset is tried once.
COOKIE_NAV_BUTTON = (80, 1835)
COOKIE_PRESET_BUTTONS = {
    1: (55, 520),
    2: (140, 520),
    3: (225, 520),
    4: (310, 520),
    5: (405, 520),
}
COOKIE_PRESET_NAMES = {
    1: "전투력",
    2: "단일보스",
    3: "아픈단일",
    4: "다수보스",
    5: "아픈다수",
}
BOSS_PRESET_SEQUENCE = (5, 2, 3)
SLEEP_CROWN_FALLBACK = (540, 950)
SLEEP_CHARACTER_TARGET = (540, 1420)
LEVEL_UP_TAP = (540, 1730)

# Challenge dungeon coordinates measured from the current 1080 x 1920 UI.
DUNGEON_NAV = (390, 1815)
CHALLENGE_TAB = (220, 1695)
CHALLENGE_ROWS = {
    "crumble": (540, 650),
    "arena": (540, 960),
    "implant": (540, 1270),
}
CRUMBLE_START = (540, 1535)
ARENA_ENTER = (820, 1430)
ARENA_CHALLENGE = (540, 1425)
ARENA_REFRESH = (920, 1425)
ARENA_RESULT_CONTINUE = (540, 1730)
IMPLANT_START = (540, 1550)
IMPLANT_CONTINUOUS = (800, 1545)
IMPLANT_NEXT_FLOOR = (540, 1490)

# Daily dungeon coordinates. The first three rows are visible at the top of
# the list. Research Stone and Rune Crystal are selected after one controlled
# upward scroll so the click never lands on a different dungeon card.
DAILY_TAB = (620, 1695)
DAILY_ROWS_TOP = {
    "exp": (540, 610),
    "coin": (540, 950),
    "dough": (540, 1290),
}
DAILY_ROWS_SCROLLED = {
    "research_stone": (540, 820),
    "rune_crystal": (540, 1170),
}
DAILY_START = (540, 1550)
DAILY_CONTINUOUS = (800, 1545)
DAILY_ACHIEVEMENT = (1000, 770)
DAILY_NEXT_DUNGEON = (1000, 620)
DAILY_CLAIM_ALL = (540, 1690)
DAILY_EXIT_CONTINUE = (325, 1685)
DAILY_EXIT_CONFIRM = (750, 1685)
DAILY_ORDER = ("exp", "coin", "dough", "research_stone", "rune_crystal")

STOP = False
SKIP_ACTION = False
FAST_SCREENSHOT_AVAILABLE = None
EQUIPMENT_SESSION = False
EQUIPMENT_PENDING_UNTIL = 0.0
TAP_SETTLE = 0.60
SCREEN_POLL = 0.55
QUEST_SCREEN_POLL = 0.15
QUEST_COMPLETION_POLL = 0.45
QUEST_COMPLETION_IDLE_POLL = 0.80
QUEST_COMPLETION_FAST_WINDOW = 20.0
TIMEOUT_DRAW = 35
TIMEOUT_EQUIPMENT = 90
TIMEOUT_MONSTER = 180
TIMEOUT_BAG = 30
TIMEOUT_STAGE = 300
MAX_EQUIPMENT_COMPARISONS = 200
# Auto opens ten pieces per run. The old six-second fixed delay added roughly
# thirty seconds to every 50-piece quest even when the battle screen was ready.
# Screen classification still gates every tap, so a short settle is sufficient.
EQUIPMENT_BATCH_SETTLE = 1.25
EQUIPMENT_AUTO_RETRY = 1.0
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSETS = RESOURCE_DIR / "assets"
VISION_OCR = RESOURCE_DIR / ("vision_ocr.exe" if IS_WINDOWS else "vision_ocr")
VISION_OCR_WINDOWS = RESOURCE_DIR / "vision_ocr_windows.ps1"
QUEST_TEMPLATES = {}
SPECIAL_STAGE_TEMPLATES = []
QUEST_TEMPLATE_BITS = {}
ERROR_REPORTER = None
PROGRESS_REPORTER = None
ARENA_DECISION_REPORTER = None
LAST_FOREGROUND_CHECK = None
LAST_FOREGROUND_RESULT = None
FOREGROUND_CHECK_INTERVAL = 2.5
AUTO_RELAUNCH_GAME = True


class SafeStop(RuntimeError):
    pass


class SkipAction(SafeStop):
    """Leave the current top-level checklist action and continue the run."""

    pass


class GameRelaunched(SafeStop):
    """Abort the current action after recovering the game from Android Home."""

    pass


def on_signal(_signum, _frame):
    global STOP
    STOP = True


def adb(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    if not adb_available():
        raise SafeStop("BlueStacks 내부 연결 도구(ADB)를 찾지 못했습니다.")
    command = [str(ADB)]
    if ADB_SERIAL and args and args[0] not in ("devices", "connect", "start-server"):
        command.extend(("-s", ADB_SERIAL))
    command.extend(args)
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0,
    )


def adb_bytes(*args: str) -> bytes:
    if not adb_available():
        raise SafeStop("BlueStacks 내부 연결 도구(ADB)를 찾지 못했습니다.")
    command = [str(ADB)]
    if ADB_SERIAL and args and args[0] not in ("devices", "connect", "start-server"):
        command.extend(("-s", ADB_SERIAL))
    command.extend(args)
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0,
    ).stdout


def adb_available() -> bool:
    return ADB.is_file() or shutil.which(str(ADB)) is not None


def _windows_bluestacks_adb_ports() -> list[int]:
    if not IS_WINDOWS:
        return []
    roots = [os.environ.get("PROGRAMDATA", ""), os.environ.get("APPDATA", "")]
    ports = []
    for root in filter(None, roots):
        for filename in ("BlueStacks_nxt/bluestacks.conf", "BlueStacks/bluestacks.conf"):
            path = Path(root) / filename
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in re.findall(r'adb_port="?(\d+)"?', text):
                port = int(match)
                if 1 <= port <= 65535 and port not in ports:
                    ports.append(port)
    return ports


def ensure_adb_connection() -> str:
    """Return the selected device and connect BlueStacks 5 when necessary."""
    global ADB_SERIAL
    if not adb_available():
        raise SafeStop(f"BlueStacks ADB를 찾지 못했습니다: {ADB}")
    ADB_SERIAL = None
    try:
        output = adb("devices").stdout
    except subprocess.SubprocessError as error:
        raise SafeStop("BlueStacks ADB를 실행하지 못했습니다.") from error
    devices = re.findall(r"^([^\s]+)\s+device\s*$", output, re.MULTILINE)
    if not devices and IS_WINDOWS:
        for port in _windows_bluestacks_adb_ports() or [5555]:
            try:
                adb("connect", f"127.0.0.1:{port}")
            except subprocess.SubprocessError:
                continue
        output = adb("devices").stdout
        devices = re.findall(r"^([^\s]+)\s+device\s*$", output, re.MULTILINE)
    if not devices:
        message = "BlueStacks와 게임을 실행해 주세요."
        if IS_WINDOWS:
            message += " BlueStacks 설정 > 고급에서 Android 디버그 브리지(ADB)를 켜 주세요."
        raise SafeStop(message)
    ADB_SERIAL = devices[0]
    return ADB_SERIAL


def foreground_package() -> str | None:
    """Return the currently resumed Android package without guessing the launcher."""
    try:
        output = adb("shell", "dumpsys", "activity", "activities").stdout
    except (SafeStop, subprocess.SubprocessError):
        return None
    match = re.search(
        r"(?:topResumedActivity|mResumedActivity)=.*?\s([A-Za-z0-9._]+)/",
        output,
    )
    return match.group(1) if match else None


def game_is_foreground(force: bool = False) -> bool | None:
    global LAST_FOREGROUND_CHECK, LAST_FOREGROUND_RESULT
    now = time.monotonic()
    if (
        not force and LAST_FOREGROUND_CHECK is not None
        and now - LAST_FOREGROUND_CHECK < FOREGROUND_CHECK_INTERVAL
    ):
        return LAST_FOREGROUND_RESULT
    LAST_FOREGROUND_CHECK = now
    package = foreground_package()
    LAST_FOREGROUND_RESULT = None if package is None else package == GAME_PACKAGE
    return LAST_FOREGROUND_RESULT


def game_memory_mb() -> float | None:
    """Return CookieRun's total PSS when Android exposes it."""
    try:
        output = adb("shell", "dumpsys", "meminfo", GAME_PACKAGE).stdout
    except (SafeStop, subprocess.SubprocessError):
        return None
    match = re.search(r"TOTAL PSS:\s*([\d,]+)", output)
    if match is None:
        match = re.search(r"^\s*TOTAL\s+([\d,]+)", output, re.MULTILINE)
    if match is None:
        return None
    return int(match.group(1).replace(",", "")) / 1024


def trim_bluestacks_memory() -> tuple[float | None, float | None]:
    """Ask the foreground game to release memory and clear cached Android apps."""
    if game_is_foreground(force=True) is not True:
        raise SafeStop("BlueStacks에서 쿠키런 게임 화면을 먼저 전면에 띄워 주세요.")
    before = game_memory_mb()
    adb("shell", "am", "send-trim-memory", GAME_PACKAGE, "RUNNING_CRITICAL")
    adb("shell", "am", "kill-all")
    time.sleep(0.8)
    after = game_memory_mb()
    return before, after


def check_stop():
    global SKIP_ACTION
    if STOP:
        raise SafeStop("사용자가 긴급정지했습니다.")
    if SKIP_ACTION:
        SKIP_ACTION = False
        raise SkipAction("사용자가 다음 행동으로 이동했습니다.")


def set_device_size(width: int, height: int):
    global DEVICE_WIDTH, DEVICE_HEIGHT
    if width <= 0 or height <= 0:
        raise SafeStop(f"올바르지 않은 게임 화면 크기입니다: {width}x{height}")
    DEVICE_WIDTH, DEVICE_HEIGHT = width, height


def configure_device_size(wm_output: str | None = None) -> tuple[int, int]:
    """Read the current emulator size while keeping 1080x1920 as reference coordinates."""
    output = wm_output if wm_output is not None else adb("shell", "wm", "size").stdout
    matches = re.findall(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", output)
    if not matches:
        matches = re.findall(r"(\d+)x(\d+)", output)
    if not matches:
        raise SafeStop(f"BlueStacks 화면 크기를 확인하지 못했습니다: {output.strip()}")
    width, height = map(int, matches[-1])
    set_device_size(width, height)
    return width, height


def scaled_point(point: tuple[int, int]) -> tuple[int, int]:
    x, y = point
    return (
        max(0, min(DEVICE_WIDTH - 1, round(x * DEVICE_WIDTH / WIDTH))),
        max(0, min(DEVICE_HEIGHT - 1, round(y * DEVICE_HEIGHT / HEIGHT))),
    )


def tap(point: tuple[int, int], label: str, dry_run: bool):
    check_stop()
    x, y = scaled_point(point)
    print(f"  클릭: {label}")
    if not dry_run:
        adb("shell", "input", "tap", str(x), str(y))
    time.sleep(TAP_SETTLE)


def tap_without_settle(point: tuple[int, int], label: str):
    """Tap and return immediately when the following key input is time-critical."""
    check_stop()
    x, y = scaled_point(point)
    print(f"  클릭: {label}")
    adb("shell", "input", "tap", str(x), str(y))


def hold_bluestacks_keys(keys: tuple[str, ...], seconds: float, label: str):
    """Only hold an explicitly enabled combination; always release on cancellation."""
    check_stop()
    quoted_keys = tuple(keys)
    with BOSS_CONTROL_LOCK:
        if not boss_movement_enabled(quoted_keys):
            print("  체크하지 않은 보스 이동: 키보드 입력을 건너뜁니다.")
            return
        revision = BOSS_MOVEMENT_REVISION
        seconds = max(0.5, min(float(seconds), 15.0))
    if IS_WINDOWS:
        return _hold_bluestacks_keys_windows(quoted_keys, seconds, label, revision)
    if not IS_MACOS:
        raise SafeStop("Unsupported operating system for BlueStacks keyboard input.")
    down_lines = "\n".join(f'key down "{key}"' for key in quoted_keys)
    up_lines = "\n".join(f'key up "{key}"' for key in reversed(quoted_keys))
    script = f'''tell application "System Events"
if not (frontmost of process "BlueStacks") then error "BlueStacks is not frontmost"
{down_lines}
delay {seconds:.2f}
{up_lines}
end tell'''
    process = None
    failure = None
    try:
        # Focus separately, then recheck the selection before sending ANY key.
        subprocess.run(
            ["/usr/bin/osascript", "-e", 'tell application "BlueStacks" to activate'],
            check=True, text=True, capture_output=True, timeout=3,
        )
        time.sleep(0.15)
        check_stop()
        with BOSS_CONTROL_LOCK:
            if revision != BOSS_MOVEMENT_REVISION or not boss_movement_enabled(quoted_keys):
                print("  보스 이동 설정 변경: 키보드 입력을 취소합니다.")
                return
            process = subprocess.Popen(
                ["/usr/bin/osascript", "-e", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        print(f"  이동: {label} ({seconds:g}초)")
        deadline = time.monotonic() + seconds + 3
        while process.poll() is None:
            check_stop()
            with BOSS_CONTROL_LOCK:
                cancelled = revision != BOSS_MOVEMENT_REVISION or not boss_movement_enabled(quoted_keys)
            if cancelled:
                print("  보스 이동 체크 변경: 누르던 키를 해제합니다.")
                return
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("보스 이동", seconds + 3)
            time.sleep(0.05)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, "보스 이동")
    except (OSError, subprocess.SubprocessError) as error:
        failure = error
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
            except (OSError, subprocess.SubprocessError) as error:
                # Even child-process cleanup failure must not skip key release.
                failure = error
            cleanup = 'tell application "System Events"\n' + up_lines + '\nend tell'
            try:
                subprocess.run(
                    ["/usr/bin/osascript", "-e", cleanup],
                    check=True, text=True, capture_output=True, timeout=3,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise SafeStop("방향키 해제 실패: 실행을 중단합니다. BlueStacks에서 누르던 키를 직접 눌렀다 떼고 손쉬운 사용 권한을 확인하세요.") from error
    if failure is not None:
        raise SafeStop(
            "BlueStacks 방향키 입력에 실패했습니다. "
            "게임 창과 macOS 손쉬운 사용 키보드 제어 권한을 확인하세요."
        ) from failure


def _hold_bluestacks_keys_windows(
    keys: tuple[str, ...], seconds: float, label: str, revision: int
):
    """Focus BlueStacks and hold selected movement keys on Windows."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def collect(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if "bluestacks" in title.value.lower():
                found.append(hwnd)
                return False
            return True

        user32.EnumWindows(collect, 0)
        if not found:
            raise SafeStop("BlueStacks game window was not found on Windows.")
        user32.ShowWindow(found[0], 9)
        if not user32.SetForegroundWindow(found[0]):
            raise SafeStop("Could not focus the BlueStacks window.")
        time.sleep(0.15)
        check_stop()
        with BOSS_CONTROL_LOCK:
            if revision != BOSS_MOVEMENT_REVISION or not boss_movement_enabled(keys):
                print("  Boss movement setting changed; keyboard input cancelled.")
                return
        key_codes = {"a": 0x41, "s": 0x53, "d": 0x44}
        codes = [key_codes[key.lower()] for key in keys]
        for code in codes:
            user32.keybd_event(code, 0, 0, 0)
        print(f"  Movement: {label} ({seconds:g}s)")
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            check_stop()
            with BOSS_CONTROL_LOCK:
                if revision != BOSS_MOVEMENT_REVISION or not boss_movement_enabled(keys):
                    print("  Boss movement setting changed; held keys released.")
                    return
            time.sleep(0.05)
    except SafeStop:
        raise
    except (AttributeError, OSError, ValueError) as error:
        raise SafeStop("BlueStacks movement-key input failed on Windows.") from error
    finally:
        if "user32" in locals() and "codes" in locals():
            for code in reversed(codes):
                user32.keybd_event(code, 0, 0x0002, 0)


def swipe(start: tuple[int, int], end: tuple[int, int], label: str, duration_ms: int = 450):
    check_stop()
    start_x, start_y = scaled_point(start)
    end_x, end_y = scaled_point(end)
    print(f"  스크롤: {label}")
    adb(
        "shell", "input", "swipe",
        str(start_x), str(start_y), str(end_x), str(end_y), str(duration_ms),
    )
    time.sleep(1.0)


def _capture_screenshot() -> Image.Image:
    global FAST_SCREENSHOT_AVAILABLE
    image = None
    if FAST_SCREENSHOT_AVAILABLE is not False:
        try:
            payload = adb_bytes("exec-out", "screencap", "-p")
            if len(payload) < 1024:
                raise OSError("빠른 스크린샷 데이터가 비어 있습니다.")
            image = Image.open(io.BytesIO(payload)).convert("RGB")
            FAST_SCREENSHOT_AVAILABLE = True
        except (OSError, subprocess.SubprocessError):
            FAST_SCREENSHOT_AVAILABLE = False
    if image is None:
        with tempfile.TemporaryDirectory(prefix="cookie_quest_") as temp_dir:
            local = Path(temp_dir) / "screen.png"
            adb("shell", "screencap", "-p", DEVICE_SCREENSHOT)
            adb("pull", DEVICE_SCREENSHOT, str(local))
            image = Image.open(local).convert("RGB")
    set_device_size(*image.size)
    if image.size != (WIDTH, HEIGHT):
        image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    return image.copy()


def _game_content_visible(image: Image.Image) -> bool:
    if screen_state(image) != "unknown":
        return True
    return any((
        challenge_menu_visible(image), arena_home_visible(image),
        arena_opponents_visible(image), crumble_dungeon_visible(image),
        implant_tower_visible(image), daily_menu_visible(image),
        daily_detail_visible(image), dungeon_battle_visible(image),
    ))


def relaunch_game(timeout: int = 180):
    """Start CookieRun again and wait until a real game screen is rendered."""
    global LAST_FOREGROUND_CHECK, LAST_FOREGROUND_RESULT
    print("  게임 이탈 감지: Android 바탕화면에서 쿠키런을 다시 실행합니다.")
    adb(
        "shell", "am", "start", "-n",
        f"{GAME_PACKAGE}/{GAME_ACTIVITY}",
    )
    LAST_FOREGROUND_CHECK = None
    LAST_FOREGROUND_RESULT = None
    deadline = time.monotonic() + timeout
    foreground_confirmed = False
    while time.monotonic() < deadline:
        check_stop()
        foreground = game_is_foreground(force=True)
        if foreground:
            foreground_confirmed = True
            image = _capture_screenshot()
            if _game_content_visible(image):
                state = screen_state(image)
                print(f"  게임 재실행 성공: {state if state != 'unknown' else '게임 화면'} 확인")
                raise GameRelaunched("게임이 다시 실행되어 현재 작업을 처음부터 재시도합니다.")
        time.sleep(2.0 if foreground_confirmed else 1.0)
    if foreground_confirmed:
        raise SafeStop("쿠키런을 다시 실행했지만 제한시간 안에 게임 화면을 확인하지 못했습니다.")
    raise SafeStop("쿠키런 앱을 다시 실행했지만 전면 실행 상태를 확인하지 못했습니다.")


def screenshot() -> Image.Image:
    check_stop()
    foreground = game_is_foreground()
    if foreground is False:
        if AUTO_RELAUNCH_GAME:
            relaunch_game()
        raise SafeStop(
            "쿠키런 앱이 종료되었거나 Android 바탕화면으로 이동했습니다. "
            "게임 종료 시 자동 재실행이 꺼져 있습니다."
        )
    image = _capture_screenshot()
    if sleep_mode_visible(image):
        return wake_sleep_mode(image)
    return image


def pixel_fraction(image: Image.Image, box, predicate) -> float:
    crop = image.crop(box).resize((80, 80))
    pixels = list(crop.getdata())
    return sum(1 for pixel in pixels if predicate(*pixel)) / len(pixels)


def image_difference(first: Image.Image, second: Image.Image, box=None) -> float:
    if box:
        first, second = first.crop(box), second.crop(box)
    first = first.convert("RGB").resize((90, 160))
    second = second.convert("RGB").resize((90, 160))
    stat = ImageStat.Stat(ImageChops.difference(first, second))
    return sum(stat.mean) / (3 * 255)


def sleep_crown_position(image: Image.Image) -> tuple[int, int] | None:
    """Locate the moving red-and-gold crown in the sleep-mode screen."""
    small = image.convert("RGB").resize((270, 480))
    pixels = small.load()
    candidates = []
    for y in range(170, 295):
        for x in range(80, 190):
            r, g, b = pixels[x, y]
            if r > 165 and g < 125 and r > g * 1.7 and r > b * 1.5:
                candidates.append((x, y))
    if len(candidates) < 10:
        return None
    # Score compact 24x24 reference-coordinate bins. This ignores scattered
    # damage numbers and selects the densest gold object nearest screen center.
    bins = {}
    for x, y in candidates:
        key = (x // 6, y // 6)
        bins[key] = bins.get(key, 0) + 1
    best_key, best_count = max(
        bins.items(),
        key=lambda item: item[1] - 0.010 * ((item[0][0] * 6 - 135) ** 2 + (item[0][1] * 6 - 238) ** 2),
    )
    if best_count < 4:
        return None
    bx, by = best_key
    nearby = [
        (x, y) for x, y in candidates
        if abs(x // 6 - bx) <= 1 and abs(y // 6 - by) <= 1
    ]
    if not nearby:
        return None
    center_x = round(sum(x for x, _ in nearby) / len(nearby) * 4)
    center_y = round(sum(y for _, y in nearby) / len(nearby) * 4)
    return center_x, center_y


def sleep_mode_visible(image: Image.Image) -> bool:
    """Identify the crown-drag screen on both bright and dark stages."""
    crown = sleep_crown_position(image)
    if crown is None or not (450 <= crown[0] <= 630 and 870 <= crown[1] <= 1030):
        return False
    sleep_menu_teal = pixel_fraction(
        image, (0, 1780, 1080, 1915),
        lambda r, g, b: g > 55 and b > 55 and g > r * 1.15 and b > r * 1.15,
    )
    return sleep_menu_teal > 0.12


def wake_sleep_mode(first: Image.Image) -> Image.Image:
    """Drag the moving crown down to the character and resume the game."""
    print("  절전 모드 감지: 움직이는 왕관을 아래 캐릭터로 끌어내립니다.")
    image = first
    for attempt in range(1, 4):
        check_stop()
        crown = sleep_crown_position(image) or SLEEP_CROWN_FALLBACK
        swipe(
            crown, SLEEP_CHARACTER_TARGET,
            f"절전 모드 해제 - 왕관을 캐릭터로 이동 ({attempt}/3)",
            duration_ms=900,
        )
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            check_stop()
            image = _capture_screenshot()
            if not sleep_mode_visible(image):
                print("  절전 모드 해제 성공: 기존 작업 화면을 다시 확인합니다.")
                return image
            time.sleep(0.5)
    raise SafeStop("절전 모드 왕관을 캐릭터로 옮겼지만 화면이 해제되지 않았습니다.")


def equipment_compare_visible(image: Image.Image) -> bool:
    """Require both dark comparison cards and a visible shared action button."""
    dark = lambda r, g, b: r < 85 and g < 105 and b < 115
    cyan = lambda r, g, b: g > 105 and b > 100 and g > r * 1.25
    orange = lambda r, g, b: r > 165 and 55 < g < 190 and b < 100 and r > b * 1.7
    left_card = pixel_fraction(image, (35, 700, 525, 1200), dark)
    right_card = pixel_fraction(image, (555, 760, 1050, 1250), dark)
    action_cyan = pixel_fraction(image, (540, 1235, 1015, 1370), cyan)
    action_orange = pixel_fraction(image, (540, 1235, 1015, 1370), orange)
    return (
        left_card > 0.70
        and right_card > 0.70
        and (action_cyan > 0.14 or action_orange > 0.18)
    )


def equipment_auto_running_visible(image: Image.Image) -> bool:
    """Detect the Auto-already-running information sheet."""
    teal = lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1
    cyan = lambda r, g, b: g > 105 and b > 100 and g > r * 1.25
    orange = lambda r, g, b: r > 165 and 40 < g < 190 and b < 100
    dark = lambda r, g, b: r < 55 and g < 115 and b < 135
    dialog_teal = pixel_fraction(image, (20, 1380, 1060, 1710), teal)
    stop_cyan = pixel_fraction(image, (100, 1610, 525, 1750), cyan)
    organize_orange = pixel_fraction(image, (550, 1610, 970, 1750), orange)
    message_dark = pixel_fraction(image, (80, 1430, 1000, 1610), dark)
    return (
        bottom_x_visible(image)
        and dialog_teal > 0.65
        and stop_cyan > 0.45
        and organize_orange > 0.35
        and message_dark > 0.45
    )


def equipment_auto_tutorial_visible(image: Image.Image) -> bool:
    """Detect Santa Cookie's Auto-organize tutorial over the result sheet."""
    if not equipment_auto_running_visible(image):
        return False
    white = lambda r, g, b: min(r, g, b) > 180 and max(r, g, b) - min(r, g, b) < 70
    red = lambda r, g, b: r > 120 and r > g * 1.4 and r > b * 1.25
    speech_bubble = pixel_fraction(image, (450, 1040, 760, 1230), white)
    santa_cookie = pixel_fraction(image, (400, 1160, 670, 1450), red)
    return speech_bubble > 0.20 and santa_cookie > 0.06


def dismiss_equipment_auto_tutorial():
    """Disable today's repeating tutorial and close it back to Auto results."""
    tap(
        EQUIPMENT_TUTORIAL_DONT_SHOW,
        "장비 Auto 안내 - 오늘 그만보기 체크",
        dry_run=False,
    )
    time.sleep(0.25)
    tap(BOTTOM_X, "장비 Auto 안내창 닫기", dry_run=False)


def equipment_auto_result_visible(image: Image.Image) -> bool:
    """Detect the ten-item Auto result sheet with Organize and trash buttons."""
    teal = lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1
    cyan = lambda r, g, b: g > 105 and b > 100 and g > r * 1.25
    orange = lambda r, g, b: r > 165 and 40 < g < 190 and b < 100
    warm_icon = lambda r, g, b: r > 150 and g > 70 and b < 130
    panel_teal = pixel_fraction(image, (0, 1180, 1080, 1710), teal)
    organize_orange = pixel_fraction(image, (330, 1620, 750, 1750), orange)
    trash_cyan = pixel_fraction(image, (900, 1610, 1070, 1760), cyan)
    result_icons = pixel_fraction(image, (40, 1290, 1040, 1610), warm_icon)
    return (
        bottom_x_visible(image)
        and panel_teal > 0.48
        and organize_orange > 0.40
        and trash_cyan > 0.25
        and result_icons > 0.12
    )


def tssr_reveal_visible(image: Image.Image) -> bool:
    """Detect the full-screen TSSR cookie reveal that says to tap the screen.

    The reveal has no normal bottom navigation or close X.  Its red/brown art
    previously satisfied the broad battle-color check, causing quest detection
    to run repeatedly against a screen that contains no quest card.
    """
    white = lambda r, g, b: min(r, g, b) > 180 and max(r, g, b) - min(r, g, b) < 70
    cyan_badge = lambda r, g, b: g > 100 and b > 120 and b > r * 1.1 and g > r * 1.1
    teal_panel = lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1
    prompt_white = pixel_fraction(image, (350, 1690, 730, 1770), white)
    rarity_badge = pixel_fraction(image, (90, 1430, 320, 1640), cyan_badge)
    bottom_navigation_white = pixel_fraction(image, (0, 1780, 1080, 1920), white)
    lower_teal_panel = pixel_fraction(image, (0, 900, 1080, 1700), teal_panel)
    return (
        prompt_white > 0.030
        and rarity_badge > 0.100
        and bottom_navigation_white < 0.025
        and (lower_teal_panel < 0.080 or (lower_teal_panel < 0.30 and rarity_badge > 0.18 and prompt_white > 0.05))
    )


def level_up_visible(image: Image.Image) -> bool:
    """Detect both the old and the brighter Crumble Level Up overlays."""
    level_cyan = pixel_fraction(
        image, (0, 740, 1080, 960),
        lambda r, g, b: g > 100 and b > 95 and g > r * 1.25,
    )
    level_dark = pixel_fraction(
        image, (0, 950, 1080, 1750),
        lambda r, g, b: r < 75 and g < 95 and b < 100,
    )
    level_green = pixel_fraction(
        image, (380, 810, 720, 950),
        lambda r, g, b: g > 150 and r < 150 and b < 150,
    )
    level_prompt = pixel_fraction(
        image, (300, 1660, 780, 1790),
        lambda r, g, b: min(r, g, b) > 170 and max(r, g, b) - min(r, g, b) < 55,
    )
    # The newer overlay leaves more of the bright battle scene visible, so its
    # lower section is only about 31% dark (the old variant exceeded 55%).
    # Retain the three distinctive cyan/green/prompt signals before accepting
    # the lower dark threshold to avoid confusing a normal battle with it.
    return (
        level_cyan > 0.35
        and level_green > 0.03
        and level_prompt > 0.01
        and (level_dark > 0.25 or (level_cyan > 0.60 and level_green > 0.10))
    )


def screen_state(image: Image.Image) -> str:
    teal = lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1
    orange = lambda r, g, b: r > 165 and 40 < g < 190 and b < 90
    gold = lambda r, g, b: r > 155 and g > 95 and b < 80 and r > b * 1.7
    teal_center = pixel_fraction(image, (0, 250, 1080, 1450), teal)
    teal_low = pixel_fraction(image, (0, 900, 1080, 1700), teal)
    use_orange = pixel_fraction(image, (150, 650, 930, 950), orange)
    auto_start_orange = pixel_fraction(image, (300, 1580, 780, 1780), orange)
    reward_gold = pixel_fraction(image, (0, 250, 1080, 1050), gold)
    battle_brown = pixel_fraction(
        image, (0, 1350, 1080, 1800),
        lambda r, g, b: r > 30 and r > g * 1.15 and g < 120 and b < 100,
    )
    if level_up_visible(image):
        return "level_up"
    # New lower-sheet Auto dialog: the battle remains visible above the teal
    # panel, while the large orange Start button stays at the original center.
    if (
        0.12 < teal_center < 0.50
        and teal_low > 0.45
        and auto_start_orange > 0.20
    ):
        return "auto_dialog"
    if teal_center > 0.70 and teal_low > 0.70 and use_orange > 0.12:
        return "item_dialog"
    if teal_center > 0.70 and teal_low > 0.70 and auto_start_orange > 0.14:
        return "auto_dialog"
    if equipment_auto_result_visible(image):
        return "equipment_auto_result"
    if equipment_auto_tutorial_visible(image):
        return "equipment_auto_tutorial"
    if equipment_auto_running_visible(image):
        return "equipment_auto_running"
    # Check equipment comparison only after the Auto and item sheets. Expanded
    # Auto option rows also contain two dark columns and cyan controls, which
    # otherwise resemble the comparison cards.
    if equipment_compare_visible(image):
        return "equipment_compare"
    if teal_low > 0.70 and teal_center < 0.70 and bottom_x_visible(image):
        return "bag"
    if teal_center > 0.70 and teal_low > 0.70 and bottom_x_visible(image):
        return "draw_result"
    if teal_center < 0.40 and 0.20 < teal_low < 0.55 and auto_start_orange > 0.08 and bottom_x_visible(image):
        return "gacha"
    # Run this narrowly scoped detector only after all normal teal dialogs and
    # draw screens.  This prevents their centered Start/Draw text from being
    # mistaken for the TSSR "tap the screen" prompt.
    if tssr_reveal_visible(image):
        return "tssr_reveal"
    if teal_low < 0.08 and reward_gold > 0.012 and bottom_x_visible(image):
        return "reward"
    if teal_low < 0.28 and not bottom_x_visible(image) and battle_brown > 0.35:
        return "battle"
    # Some stages (for example Implant Tower) use blue/gray backgrounds rather
    # than the usual brown oven palette. Once the equipment comparison is gone,
    # a verified completed quest card is sufficient to resume as battle.
    if quest_complete(image):
        return "battle"
    if sleep_mode_visible(image):
        return "sleep_mode"
    return "unknown"


def wait_for_state(expected: str, timeout: int = 15, previous=None) -> Image.Image:
    print(f"  확인: {expected} 화면 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    unknown_close_frames = 0
    unknown_close_taps = 0
    while time.monotonic() < deadline:
        check_stop()
        current = screenshot()
        state = screen_state(current)
        if expected == "battle" and state == "unknown" and bottom_x_visible(current):
            unknown_close_frames += 1
            if unknown_close_frames >= 2 and unknown_close_taps < 3:
                tap(BOTTOM_X, "전투 복귀 중 확인된 팝업 X 닫기", dry_run=False)
                unknown_close_taps += 1
                unknown_close_frames = 0
                time.sleep(0.7)
                continue
        else:
            unknown_close_frames = 0
        if state == "equipment_auto_tutorial":
            dismiss_equipment_auto_tutorial()
            continue
        if state == "level_up":
            tap(LEVEL_UP_TAP, "레벨업 화면 - 화면을 탭하세요", dry_run=False)
            continue
        if state == "tssr_reveal":
            tap(LEVEL_UP_TAP, "TSSR 쿠키 등장 화면 넘기기", dry_run=False)
            continue
        if expected == "battle" and state == "equipment_compare":
            print("  실제 장비 비교 화면을 연속 확인한 뒤 공통 좌표를 처리합니다.")
            current = resolve_equipment_comparisons(current, state)
            state = screen_state(current)
        changed = previous is None or image_difference(previous, current) > 0.025
        if state == expected and changed:
            print(f"  성공: {expected} 화면 확인")
            return current
        time.sleep(SCREEN_POLL)
    raise SafeStop(f"예상 화면을 확인하지 못했습니다: {expected}")


def wait_for_states(expected: tuple[str, ...], timeout: int = 15, previous=None) -> tuple[Image.Image, str]:
    names = ", ".join(expected)
    print(f"  확인: {names} 중 하나 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_stop()
        current = screenshot()
        state = screen_state(current)
        if state == "equipment_auto_tutorial":
            dismiss_equipment_auto_tutorial()
            continue
        if state == "level_up":
            tap(LEVEL_UP_TAP, "레벨업 화면 - 화면을 탭하세요", dry_run=False)
            continue
        if state == "tssr_reveal":
            tap(LEVEL_UP_TAP, "TSSR 쿠키 등장 화면 넘기기", dry_run=False)
            continue
        changed = previous is None or image_difference(previous, current) > 0.025
        if state in expected and changed:
            print(f"  성공: {state} 화면 확인")
            return current, state
        time.sleep(SCREEN_POLL)
    raise SafeStop(f"예상 화면을 확인하지 못했습니다: {names}")


def _text_mask(image: Image.Image) -> set[int]:
    image = image.convert("RGB").resize((352, 230)).crop((70, 35, 350, 165)).resize((140, 65))
    return {
        index for index, (r, g, b) in enumerate(image.getdata())
        if min(r, g, b) > 145 and max(r, g, b) - min(r, g, b) < 100
    }


def _load_quest_templates():
    if QUEST_TEMPLATES:
        return
    SPECIAL_STAGE_TEMPLATES.clear()
    QUEST_TEMPLATE_BITS.clear()
    for name in ("pet", "equipment", "monster", "bag", "stage", "cookie"):
        variants = []
        for path in sorted(ASSETS.glob(f"quest_{name}*.png")):
            mask = _text_mask(Image.open(path))
            variants.append(mask)
            if name == "stage" and "one_shot" in path.stem:
                # The quest sequence number changes continuously (for example
                # 7748 -> 7922).  It is not part of the quest type, so compare
                # these special cards with that text area removed.
                SPECIAL_STAGE_TEMPLATES.append(_without_quest_sequence(mask))
        if variants:
            QUEST_TEMPLATES[name] = variants


def _without_quest_sequence(mask: set[int]) -> set[int]:
    """Remove the changing number from '퀘스트 N까지 한 번에 클리어 하기'."""
    return {
        index for index in mask
        if not (55 <= index % 140 <= 102 and 17 <= index // 140 <= 40)
    }


def _mask_bits(mask: set[int]) -> int:
    """Pack the 140x65 quest-text mask into one fast comparison integer."""
    bits = 0
    for index in mask:
        bits |= 1 << index
    return bits


def _popcount(value: int) -> int:
    """Count set bits on the Python 3.9 runtime bundled with macOS."""
    return bin(value).count("1")


_QUEST_MASK_WIDTH = 140
_QUEST_MASK_HEIGHT = 65
_QUEST_FULL_BITS = (1 << (_QUEST_MASK_WIDTH * _QUEST_MASK_HEIGHT)) - 1
_QUEST_HORIZONTAL_KEEP = {}
for _quest_dx in range(-8, 9):
    if _quest_dx > 0:
        _QUEST_HORIZONTAL_KEEP[_quest_dx] = sum(
            ((1 << (_QUEST_MASK_WIDTH - _quest_dx)) - 1) << (row * _QUEST_MASK_WIDTH)
            for row in range(_QUEST_MASK_HEIGHT)
        )
    elif _quest_dx < 0:
        _quest_amount = -_quest_dx
        _QUEST_HORIZONTAL_KEEP[_quest_dx] = sum(
            ((1 << (_QUEST_MASK_WIDTH - _quest_amount)) - 1)
            << (row * _QUEST_MASK_WIDTH + _quest_amount)
            for row in range(_QUEST_MASK_HEIGHT)
        )


def _shift_mask_bits(bits: int, dx: int, dy: int) -> int:
    """Shift a packed 140x65 mask without wrapping pixels across rows."""
    if dx > 0:
        bits = (bits & _QUEST_HORIZONTAL_KEEP[dx]) << dx
    elif dx < 0:
        amount = -dx
        bits = (bits & _QUEST_HORIZONTAL_KEEP[dx]) >> amount
    if dy > 0:
        bits <<= dy * _QUEST_MASK_WIDTH
    elif dy < 0:
        bits >>= -dy * _QUEST_MASK_WIDTH
    return bits & _QUEST_FULL_BITS


def _shifted_bit_masks(mask: set[int]) -> list[tuple[int, int]]:
    bits = _mask_bits(mask)
    shifted = []
    for dx in range(-8, 9):
        for dy in range(-6, 7):
            moved = _shift_mask_bits(bits, dx, dy)
            shifted.append((moved, _popcount(moved)))
    return shifted


def _aligned_bit_score(shifted_samples: list[tuple[int, int]], template: set[int]) -> float:
    cache_key = id(template)
    cached = QUEST_TEMPLATE_BITS.get(cache_key)
    if cached is None:
        cached = (_mask_bits(template), len(template))
        QUEST_TEMPLATE_BITS[cache_key] = cached
    template_bits, template_count = cached
    return max(
        2 * _popcount(sample_bits & template_bits)
        / (sample_count + template_count + 1)
        for sample_bits, sample_count in shifted_samples
    )


def detect_quest(image: Image.Image, assume_battle: bool = False) -> tuple[str, float]:
    _load_quest_templates()
    if not assume_battle and screen_state(image) != "battle":
        return "unknown", 0.0
    panel = image.crop((704, 960, 1080, 1206))
    sample = _text_mask(panel)
    shifted_samples = _shifted_bit_masks(sample)

    scores = []
    for name, templates in QUEST_TEMPLATES.items():
        score = max(_aligned_bit_score(shifted_samples, template) for template in templates)
        if name == "stage" and SPECIAL_STAGE_TEMPLATES:
            stable_sample = _without_quest_sequence(sample)
            stable_shifted = _shifted_bit_masks(stable_sample)
            stable_score = max(
                _aligned_bit_score(stable_shifted, template)
                for template in SPECIAL_STAGE_TEMPLATES
            )
            score = max(score, stable_score)
        scores.append((score, name))
    scores.sort(reverse=True)
    # Live quest cards can vary slightly with animation and resolution scaling.
    # Accept a moderate match only when it still clearly beats the runner-up.
    if not scores or scores[0][0] < 0.50:
        return "unknown", scores[0][0] if scores else 0.0
    if len(scores) > 1 and scores[0][0] - scores[1][0] < 0.05:
        return "unknown", scores[0][0]
    return scores[0][1], scores[0][0]


def tap_and_expect(point, label: str, expected: str, timeout: int = 15) -> Image.Image:
    before = screenshot()
    tap(point, label, dry_run=False)
    return wait_for_state(expected, timeout=timeout, previous=before)


def retry_tap_until_state(
    point, label: str, source: str, expected: str, timeout: int = 30, max_taps: int = 5
) -> Image.Image:
    """Retry a close tap only while the original screen is still visible.

    High-grade draw animations can temporarily ignore X. Unknown/transition frames
    are only observed; they are never tapped, preventing a delayed double click.
    """
    print(f"  확인: {label} 후 {expected} 화면 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    taps = 0
    equipment_interruptions = 0
    reward_interruptions = 0
    next_tap_at = 0.0
    unknown_close_frames = 0
    unknown_close_taps = 0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if expected == "battle" and state == "unknown" and bottom_x_visible(image):
            unknown_close_frames += 1
            if unknown_close_frames >= 2 and unknown_close_taps < 3:
                tap(BOTTOM_X, "전투 복귀 중 확인된 팝업 X 닫기", dry_run=False)
                unknown_close_taps += 1
                unknown_close_frames = 0
                time.sleep(0.7)
                continue
        else:
            unknown_close_frames = 0
        if state == "level_up":
            print("  퀘스트 판별 전 레벨업 화면을 넘깁니다.")
            tap(LEVEL_UP_TAP, "레벨업 화면 - 화면을 탭하세요", dry_run=False)
            continue
        if state == "tssr_reveal":
            tap(LEVEL_UP_TAP, "TSSR 쿠키 등장 화면 넘기기", dry_run=False)
            next_tap_at = time.monotonic() + 1.0
            continue
        if state == "reward":
            if not bottom_x_visible(image):
                time.sleep(0.45)
                continue
            reward_interruptions += 1
            if reward_interruptions > 3:
                raise SafeStop(f"{label} 도중 보상 획득 팝업이 반복해서 나타났습니다.")
            tap(
                BOTTOM_X,
                f"{label} 도중 보상 획득 팝업 닫기 ({reward_interruptions}/3)",
                dry_run=False,
            )
            # The original quest-card tap was consumed by the reward overlay.
            # Once battle returns, retry the intended action from its first tap.
            taps = 0
            next_tap_at = 0.0
            deadline += 5
            continue
        if state == "equipment_compare":
            equipment_interruptions += 1
            if equipment_interruptions > 5:
                raise SafeStop(f"{label} 도중 장착/판매 팝업이 반복해서 나타났습니다.")
            print(f"  {label} 도중 장착/판매 팝업을 처리합니다.")
            resolve_started = time.monotonic()
            image = resolve_equipment_comparisons(image, state)
            # Popup processing must not consume the timeout for the original
            # quest action.  Once battle returns, retry that action from the
            # beginning with a fresh tap allowance.
            deadline += time.monotonic() - resolve_started
            state = screen_state(image)
            if state == expected:
                print(f"  성공: {label} 완료, {expected} 화면 확인")
                return image
            if state == source:
                print(f"  팝업 처리 후 {source} 화면 복귀: {label}을 다시 시도합니다.")
                taps = 0
                next_tap_at = 0.0
                continue
        if state == expected:
            print(f"  성공: {label} 완료, {expected} 화면 확인")
            return image
        now = time.monotonic()
        if state == source and taps < max_taps and now >= next_tap_at:
            taps += 1
            tap(point, f"{label} ({taps}/{max_taps})", dry_run=False)
            next_tap_at = time.monotonic() + 2.5
        else:
            time.sleep(0.55)
    raise SafeStop(f"{label} 후 {expected} 화면을 확인하지 못했습니다.")


def close_draw_result_verified(timeout: int = 50, max_taps: int = 8) -> Image.Image:
    """Close normal and high-grade draw result variants safely.

    High-grade cookie results are sometimes classified as unknown because their
    animation changes the teal panel.  A stable, visible bottom X is therefore
    accepted as a closeable result even when the general screen classifier does
    not call it draw_result.
    """
    print(f"  확인: 고급 포함 뽑기 결과 닫기 후 gacha·battle 화면 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    taps = 0
    visible_frames = 0
    battle_frames = 0
    next_tap_at = 0.0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state == "gacha":
            print("  성공: 뽑기 결과 닫기 완료, gacha 화면 확인")
            return image
        if state == "battle":
            battle_frames += 1
            if battle_frames >= 2:
                print("  성공: 뽑기 결과와 뽑기 화면이 함께 닫혀 battle 화면까지 복귀했습니다.")
                return image
            time.sleep(0.35)
            continue
        battle_frames = 0
        if state == "tssr_reveal":
            tap(LEVEL_UP_TAP, "TSSR 쿠키 등장 화면 넘기기", dry_run=False)
            visible_frames = 0
            next_tap_at = time.monotonic() + 1.0
            continue

        x_visible = bottom_x_visible(image)
        closeable = state == "draw_result" or (state == "unknown" and x_visible)
        visible_frames = visible_frames + 1 if closeable else 0
        now = time.monotonic()
        if visible_frames >= 2 and taps < max_taps and now >= next_tap_at:
            taps += 1
            tap(BOTTOM_X, f"고급 포함 뽑기 결과 닫기 ({taps}/{max_taps})", dry_run=False)
            visible_frames = 0
            next_tap_at = time.monotonic() + 1.5
        else:
            time.sleep(0.45)
    raise SafeStop("고급 포함 뽑기 결과를 닫고 gacha 또는 battle 화면으로 돌아가지 못했습니다.")


def wait_for_bag_open_result(timeout: int = 25) -> tuple[Image.Image, str]:
    """Accept known bag results plus new reward variants that still expose X."""
    print(f"  확인: 상자 열기 결과 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    closeable_unknown_frames = 0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state in ("reward", "bag", "battle"):
            print(f"  성공: 상자 열기 후 {state} 화면 확인")
            return image, state
        if state == "unknown" and bottom_x_visible(image):
            closeable_unknown_frames += 1
            if closeable_unknown_frames >= 2:
                print("  성공: 새 보상 연출 화면과 하단 X 확인")
                return image, "reward_variant"
        else:
            closeable_unknown_frames = 0
        time.sleep(0.65)
    raise SafeStop("상자 열기 후 보상·가방·전투 화면을 확인하지 못했습니다.")


def close_bag_reward_verified(timeout: int = 35, max_taps: int = 5) -> tuple[Image.Image, str]:
    """Close any reward variant and verify that bag or battle is really visible."""
    print(f"  확인: 상자 보상 닫기 후 가방·전투 화면 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    taps = 0
    next_tap_at = 0.0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state in ("bag", "battle"):
            print(f"  성공: 상자 보상 닫기 완료, {state} 화면 확인")
            return image, state
        now = time.monotonic()
        closeable = state == "reward" or (state == "unknown" and bottom_x_visible(image))
        if closeable and taps < max_taps and now >= next_tap_at:
            taps += 1
            tap(BOTTOM_X, f"상자 보상 닫기 ({taps}/{max_taps})", dry_run=False)
            next_tap_at = time.monotonic() + 2.5
        else:
            time.sleep(0.55)
    raise SafeStop("상자 보상 X를 닫은 후 가방·전투 화면을 확인하지 못했습니다.")


def wait_detect_quest(
    timeout: int = 12, exclude=None, require_incomplete: bool = False,
    initial_image: Image.Image | None = None,
) -> tuple[Image.Image, str, float]:
    deadline = time.monotonic() + timeout
    best_name, best_score = "unknown", 0.0
    low_confidence_name = None
    low_confidence_count = 0
    pending_image = initial_image
    while time.monotonic() < deadline:
        check_stop()
        image = pending_image if pending_image is not None else screenshot()
        pending_image = None
        state = screen_state(image)
        if state == "equipment_auto_tutorial":
            print("  퀘스트 판별 전 장비 Auto 안내창을 닫습니다.")
            dismiss_equipment_auto_tutorial()
            continue
        if state == "tssr_reveal":
            print("  퀘스트 판별 전 TSSR 쿠키 등장 화면을 넘깁니다.")
            tap(LEVEL_UP_TAP, "TSSR 쿠키 등장 화면 넘기기", dry_run=False)
            continue
        if state == "equipment_compare":
            print("  퀘스트 판별 중 실제 장비 비교 화면을 처리합니다.")
            image = resolve_equipment_comparisons(image, state)
            state = screen_state(image)
        if state == "battle":
            if repeat_equipment_reward_visible(image):
                return image, "equipment_repeat", 0.0
            name, score = detect_quest(image, assume_battle=True)
            if score > best_score:
                best_name, best_score = name, score
            valid_name = name != "unknown" and (exclude is None or name != exclude)
            valid_completion = not require_incomplete or not quest_complete(image)
            if valid_name and valid_completion:
                # Preserve v14.19 stability: accept a weaker match only after
                # the same quest is seen in three consecutive battle frames.
                if score >= 0.56:
                    return image, name, score
                if name == low_confidence_name:
                    low_confidence_count += 1
                else:
                    low_confidence_name = name
                    low_confidence_count = 1
                required_frames = 2 if score >= 0.52 else 3
                if low_confidence_count >= required_frames:
                    print(f"  낮은 신뢰도 교차 확인: {name} {low_confidence_count}회 연속 ({score:.2f})")
                    return image, name, score
            else:
                low_confidence_name = None
                low_confidence_count = 0
        time.sleep(QUEST_SCREEN_POLL)
    raise SafeStop(f"현재 퀘스트를 여러 화면에서 판별하지 못했습니다(최고 {best_score:.2f}).")


def quest_complete(image: Image.Image) -> bool:
    # A completed quest card gains a bright yellow glow around its outer edge.
    # Keep quest-name recognition separate: this function decides only whether
    # the already identified quest is complete.
    yellow = lambda r, g, b: r > 220 and g > 160 and b < 100
    yellow_top = pixel_fraction(image, (690, 990, 1080, 1035), yellow)
    yellow_left = pixel_fraction(image, (680, 990, 735, 1160), yellow)
    yellow_right = pixel_fraction(image, (1035, 990, 1080, 1160), yellow)
    yellow_bottom = pixel_fraction(image, (690, 1120, 1080, 1170), yellow)
    yellow_sides = sum(
        value > threshold
        for value, threshold in (
            (yellow_left, 0.14),
            (yellow_right, 0.07),
            (yellow_bottom, 0.12),
        )
    )
    yellow_complete = yellow_top > 0.18 and yellow_sides >= 2

    # Retain the narrow progress-bar check as a fallback for older stage themes
    # whose yellow edge animation is hidden by battle effects for a frame.
    progress_fraction = pixel_fraction(
        image,
        (820, 1070, 1070, 1150),
        lambda r, g, b: r > 165 and g > 105 and b < 95 and r > b * 1.7,
    )
    # Battle effects can make every outer edge yellow while 0/10 remains white.
    # Require the yellow completed progress digits inside the card as well.
    yellow_progress = pixel_fraction(
        image, (900, 1098, 985, 1134),
        lambda r, g, b: r > 200 and g > 145 and b < 110,
    )
    return (yellow_complete or progress_fraction > 0.20) and yellow_progress > 0.06


def one_shot_quest_visible(image: Image.Image) -> bool:
    """Recognize the purple '퀘스트 N까지 한 번에 클리어 하기' reward card.

    The sequence number changes continuously and is intentionally ignored.  The
    stable magenta card body and cyan rim distinguish it from the six ordinary
    quest cards.
    """
    if screen_state(image) != "battle":
        return False
    card = (690, 990, 1080, 1165)
    magenta = pixel_fraction(
        image, card,
        lambda r, g, b: r > 130 and b > 120 and r > g * 1.25,
    )
    cyan = pixel_fraction(
        image, card,
        lambda r, g, b: g > 125 and b > 145 and b > r * 1.05,
    )
    return magenta > 0.08 and cyan > 0.08


def bottom_x_visible(image: Image.Image) -> bool:
    fraction = pixel_fraction(
        image,
        (455, 1740, 625, 1920),
        lambda r, g, b: r > 165 and 45 < g < 155 and b < 55,
    )
    return fraction > 0.035


def boss_summon_ready(image: Image.Image) -> bool:
    """Recognize the red/orange boss summon button at the top center."""
    if screen_state(image) != "battle":
        return False
    fraction = pixel_fraction(
        image,
        (390, 250, 700, 355),
        lambda r, g, b: r > 180 and g < 120 and b < 90,
    )
    return fraction > 0.28


def cookie_preset_screen_visible(image: Image.Image) -> bool:
    """Recognize the cookie roster screen containing battle presets 1-5."""
    upper_teal = pixel_fraction(
        image, (0, 300, 1080, 590),
        lambda r, g, b: g > 90 and b > 90 and b > r * 1.15 and g > r * 1.05,
    )
    lower_teal = pixel_fraction(
        image, (0, 1450, 1080, 1760),
        lambda r, g, b: g > 90 and b > 90 and b > r * 1.15 and g > r * 1.05,
    )
    preset_row = pixel_fraction(
        image, (0, 490, 470, 565),
        lambda r, g, b: g > 100 and b > 90 and max(g, b) > r * 1.05,
    )
    return upper_teal > 0.45 and lower_teal > 0.55 and preset_row > 0.40


def select_battle_preset(number: int):
    """Open the cookie roster, select one preset, and safely return to battle."""
    if number not in BOSS_PRESET_SEQUENCE:
        return False
    point = COOKIE_PRESET_BUTTONS.get(number)
    if point is None:
        raise SafeStop(f"지원하지 않는 전투 프리셋입니다: {number}번")

    preset_label = f"{number}번 [{COOKIE_PRESET_NAMES[number]}]"
    tap(COOKIE_NAV_BUTTON, f"보스 재도전 - 왼쪽 아래 쿠키 메뉴 열기 ({preset_label} 프리셋)", dry_run=False)
    deadline = time.monotonic() + 12
    open_attempts = 1
    next_open_at = time.monotonic() + 2.0
    image = screenshot()
    while time.monotonic() < deadline and not cookie_preset_screen_visible(image):
        check_stop()
        if screen_state(image) == "battle" and open_attempts < 3 and time.monotonic() >= next_open_at:
            tap(COOKIE_NAV_BUTTON, "쿠키 프리셋 메뉴 다시 열기", dry_run=False)
            open_attempts += 1
            next_open_at = time.monotonic() + 2.0
        time.sleep(0.45)
        image = screenshot()
    if not cookie_preset_screen_visible(image):
        raise SafeStop("쿠키 전투 프리셋 화면을 확인하지 못했습니다.")

    with BOSS_CONTROL_LOCK:
        selected = number in BOSS_PRESET_SEQUENCE
        if selected:
            check_stop()
            x, y = scaled_point(point)
            adb("shell", "input", "tap", str(x), str(y))
    if selected:
        print(f"  클릭: 쿠키 전투 프리셋 {preset_label} 선택")
        time.sleep(TAP_SETTLE)
    tap(BOTTOM_X, f"프리셋 {preset_label} 적용 후 쿠키 화면 닫기", dry_run=False)
    wait_for_state("battle", timeout=15)
    print(f"  전투 프리셋 적용 완료: {preset_label}" if selected else "  체크 해제된 프리셋 선택을 취소했습니다.")
    return selected


def _stage_number_from_text(text: str) -> tuple[int, int] | None:
    """Extract a world-stage pair such as 43-5 from OCR text."""
    # Vision can read the short hyphen over a bright boss panel as an
    # underscore (for example 56_23), so accept that equivalent separator.
    match = re.search(r"(\d{1,3})\s*[-_–—~]\s*(\d{1,3})", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _ocr_region(image: Image.Image, box) -> str:
    """Read a small game text region with the bundled platform OCR helper."""
    if not VISION_OCR.is_file() and not (IS_WINDOWS and VISION_OCR_WINDOWS.is_file()):
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="cookie_stage_ocr_") as temp_dir:
            target = Path(temp_dir) / "region.png"
            crop = image.crop(box)
            crop.resize(
                (crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS
            ).save(target)
            command = [str(VISION_OCR), str(target)]
            if IS_WINDOWS:
                command = [
                    "powershell.exe", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File",
                    str(VISION_OCR_WINDOWS), str(target),
                ]
            result = subprocess.run(
                command,
                check=False,
                text=True,
                encoding="utf-8",
                errors="ignore",
                capture_output=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0,
            )
            return result.stdout if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def stage_numbers(image: Image.Image) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Return (quest stage, current stage) only for the incomplete boss check."""
    quest_text = _ocr_region(image, (790, 1015, 1080, 1105))
    return _stage_number_from_text(quest_text), current_stage_number(image)


def current_stage_number(image: Image.Image) -> tuple[int, int] | None:
    """Read the current stage from the expanded boss panel with an old-UI fallback."""
    # The current stage moved down into the expanded boss-summon panel.  Keep
    # the old progress-bar crop as a fallback for stages using the former UI.
    for box in ((300, 300, 800, 440), (265, 285, 570, 350)):
        number = _stage_number_from_text(_ocr_region(image, box))
        if number is not None:
            return number
    return None


def _orange_button_fraction(image: Image.Image, box=(300, 1430, 780, 1620)) -> float:
    return pixel_fraction(
        image, box,
        lambda r, g, b: r > 165 and 45 < g < 190 and b < 100 and r > b * 1.7,
    )


def challenge_menu_visible(image: Image.Image) -> bool:
    gold_row = pixel_fraction(
        image, (0, 450, 1080, 760),
        lambda r, g, b: r > 160 and g > 110 and b < 110 and r > b * 1.5,
    )
    purple_row = pixel_fraction(
        image, (0, 760, 1080, 1090),
        lambda r, g, b: r > 100 and b > 100 and b > g * 1.15,
    )
    teal_low = pixel_fraction(
        image, (0, 1450, 1080, 1760),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    return gold_row > 0.20 and purple_row > 0.18 and teal_low > 0.62


def crumble_dungeon_visible(image: Image.Image) -> bool:
    gold_top = pixel_fraction(
        image, (0, 100, 1080, 600),
        lambda r, g, b: r > 160 and g > 110 and b < 110 and r > b * 1.5,
    )
    teal_low = pixel_fraction(
        image, (0, 1450, 1080, 1760),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    return gold_top > 0.30 and teal_low > 0.65 and not challenge_menu_visible(image)


def wagle_arena_opponents_visible(image):
    if not isinstance(image, Image.Image):
        return False
    gold = pixel_fraction(image, (220, 900, 650, 1000),
                          lambda r, g, b: r > 170 and 85 < g < 190 and b < 95)
    purple = pixel_fraction(image, (700, 170, 1040, 320),
                            lambda r, g, b: b > 95 and r > g * 1.15 and b > g * 1.2)
    footer = pixel_fraction(image, (300, 1640, 1000, 1750),
                            lambda r, g, b: g > 70 and b > 70 and r < g * .8)
    return gold > .45 and purple > .45 and footer > .65


def wagle_arena_home_visible(image):
    if not isinstance(image, Image.Image):
        return False
    with Image.open(ASSETS / "wagle_title.png") as reference:
        return image_difference(image.crop((300, 80, 800, 200)), reference) < .08


def arena_action_point(image, action):
    if action == "enter":
        return (820, 1550) if wagle_arena_home_visible(image) else ARENA_ENTER
    point = ARENA_CHALLENGE if action == "challenge" else ARENA_REFRESH
    return (point[0], point[1] + 112) if wagle_arena_opponents_visible(image) else point


def arena_home_visible(image: Image.Image) -> bool:
    if wagle_arena_home_visible(image):
        return True
    neutral_top = pixel_fraction(
        image, (0, 100, 1080, 600),
        lambda r, g, b: abs(r - g) < 30 and abs(g - b) < 30 and 80 < r < 190,
    )
    teal_low = pixel_fraction(
        image, (0, 1450, 1080, 1760),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    return neutral_top > 0.12 and teal_low > 0.70 and _orange_button_fraction(image) > 0.10


def arena_opponents_visible(image: Image.Image) -> bool:
    if wagle_arena_opponents_visible(image):
        return True
    pink_top = pixel_fraction(
        image, (0, 100, 1080, 600),
        lambda r, g, b: r > 130 and b > 80 and r > g * 1.3,
    )
    teal_low = pixel_fraction(
        image, (0, 1450, 1080, 1760),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    return pink_top > 0.35 and teal_low > 0.75 and _orange_button_fraction(image) > 0.16


def _arena_number(text: str, power: bool = False) -> int | None:
    """Parse arena OCR such as 498.44K, 1.03M, 2,207, or 2.713."""
    compact = re.sub(r"\s+", "", text or "").upper()
    if power:
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*([KMB])", compact)
        if not match:
            return None
        number = float(match.group(1).replace(",", "."))
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2)]
        return round(number * multiplier)
    groups = re.findall(r"\d+", compact)
    if not groups:
        return None
    # Vision sometimes reads the thousands comma as a decimal point.
    joined = "".join(groups)
    return int(joined) if joined else None


def _ocr_arena_power(image: Image.Image, box) -> str:
    """Read normal white power text and the yellow stronger-opponent variant."""
    text = _ocr_region(image, box)
    if not VISION_OCR.is_file() and not (IS_WINDOWS and VISION_OCR_WINDOWS.is_file()):
        return text
    try:
        crop = image.crop(box).convert("RGB")
        mask = Image.new("RGB", crop.size, "black")
        source, target_pixels = crop.load(), mask.load()
        yellow_pixels = 0
        for y in range(crop.height):
            for x in range(crop.width):
                r, g, b = source[x, y]
                if r > 135 and g > 75 and b < 100 and r > b * 1.5:
                    target_pixels[x, y] = (255, 255, 255)
                    yellow_pixels += 1
        # A stronger opponent's power is yellow.  Generic OCR can mix nearby
        # labels into it (for example "1k27M"), so prefer the colour-isolated
        # reading whenever a meaningful yellow number is present.
        yellow_fraction = yellow_pixels / max(1, crop.width * crop.height)
        if yellow_fraction < 0.015 and _arena_number(text, power=True) is not None:
            return text
        with tempfile.TemporaryDirectory(prefix="cookie_arena_power_") as temp_dir:
            target = Path(temp_dir) / "power.png"
            mask.resize(
                (mask.width * 4, mask.height * 4), Image.Resampling.LANCZOS
            ).save(target)
            command = [str(VISION_OCR), str(target)]
            if IS_WINDOWS:
                command = [
                    "powershell.exe", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File",
                    str(VISION_OCR_WINDOWS), str(target),
                ]
            result = subprocess.run(
                command, check=False, text=True,
                encoding="utf-8", errors="ignore", capture_output=True, timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0,
            )
            masked_text = result.stdout if result.returncode == 0 else ""
            return masked_text if _arena_number(masked_text, power=True) is not None else text
    except (OSError, subprocess.SubprocessError):
        return text


def arena_match_values(image: Image.Image) -> tuple[int | None, int | None, int | None, int | None]:
    offset = 55 if wagle_arena_opponents_visible(image) else 0
    def box(x1, y1, x2, y2):
        return (x1, y1 + offset, x2, y2 + offset)
    opponent_power = _arena_number(_ocr_arena_power(image, box(520, 170, 760, 270)), power=True)
    opponent_trophies = _arena_number(_ocr_region(image, box(760, 180, 1015, 260)))
    my_power = _arena_number(_ocr_region(image, box(155, 845, 410, 930)), power=True)
    my_trophies = _arena_number(_ocr_region(image, box(410, 845, 650, 930)))
    return opponent_power, opponent_trophies, my_power, my_trophies


def arena_opponent_counter(image: Image.Image) -> tuple[int, int] | None:
    offset = 112 if wagle_arena_opponents_visible(image) else 0
    counter_box = (870, 1570, 965, 1610) if offset else (890, 1460, 1010, 1515)
    text = _ocr_region(image, counter_box)
    digits = "".join(re.findall(r"\d", text))
    if len(digits) < 2 or digits[-1] != "5":
        return None
    current = int(digits[0])
    return (current, 5) if 0 <= current <= 5 else None


def arena_next_opponent_available(image: Image.Image) -> bool:
    counter = arena_opponent_counter(image)
    return arena_opponents_visible(image) and counter is not None and counter[0] < counter[1]


def arena_free_refresh_available(image: Image.Image) -> bool:
    """Allow refresh only after Next Opponent is exhausted and no cost is shown."""
    counter = arena_opponent_counter(image)
    if counter is None or counter[0] < counter[1]:
        return False
    refresh_teal = pixel_fraction(
        image, (790, 1370, 1045, 1470),
        lambda r, g, b: g > 105 and b > 100 and g > r * 1.2,
    )
    refresh_text = _ocr_region(image, (780, 1330, 1070, 1515))
    number_groups = re.findall(r"\d+", refresh_text)
    counter_digits = f"{counter[0]}1{counter[1]}"
    other_numbers = [group for group in number_groups if group != counter_digits]
    return (
        arena_opponents_visible(image)
        and refresh_teal > 0.30
        and not other_numbers
    )


def _arena_match_description(values) -> str:
    opponent_power, opponent_trophies, my_power, my_trophies = values
    def power_label(value):
        if value is None:
            return "판독 실패"
        return f"{value / 1_000_000:.2f}M" if value >= 1_000_000 else f"{value / 1_000:.2f}K"
    return (
        f"내 전투력 {power_label(my_power)} / 상대 {power_label(opponent_power)}, "
        f"내 트로피 {my_trophies if my_trophies is not None else '판독 실패'} / "
        f"상대 {opponent_trophies if opponent_trophies is not None else '판독 실패'}"
    )


def implant_tower_visible(image: Image.Image) -> bool:
    blue_top = pixel_fraction(
        image, (0, 100, 1080, 600),
        lambda r, g, b: b > 100 and b > r * 1.1 and b > g * 0.85,
    )
    teal_low = pixel_fraction(
        image, (0, 1450, 1080, 1760),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    return (
        blue_top > 0.18
        and teal_low > 0.68
        and _orange_button_fraction(image) > 0.22
        and not arena_opponents_visible(image)
    )


def dungeon_action_available(image: Image.Image) -> bool:
    return _orange_button_fraction(image) > 0.14


def implant_continuous_enabled(image: Image.Image) -> bool:
    yellow = pixel_fraction(
        image, (740, 1480, 830, 1560),
        lambda r, g, b: r > 175 and g > 145 and b < 100,
    )
    return implant_tower_visible(image) and yellow > 0.08


def daily_tab_active(image: Image.Image) -> bool:
    teal = pixel_fraction(
        image, (410, 1640, 850, 1780),
        lambda r, g, b: g > 100 and b > 100 and g > r * 1.25 and b > r * 1.15,
    )
    # Compressed/scaled BlueStacks frames lower the cyan fraction to about
    # 0.40, while the selected Daily tab still remains visually unambiguous.
    return teal > 0.38 and bottom_x_visible(image)


def daily_achievement_visible(image: Image.Image) -> bool:
    teal_center = pixel_fraction(
        image, (0, 250, 1080, 1450),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    # Reward animations sometimes cover the selected daily-tab strip, so the
    # large teal achievement panel itself is the stable signal.
    return teal_center > 0.80 and bottom_x_visible(image)


def daily_clear_visible(image: Image.Image) -> bool:
    brown = pixel_fraction(
        image, (0, 250, 1080, 1700),
        lambda r, g, b: r > 45 and r > g * 1.25 and g < 125 and b < 100,
    )
    next_button = _orange_button_fraction(image, (150, 1400, 850, 1640))
    # A Research Stone battle is also mostly brown and the quest card at the
    # lower right contains orange.  The actual CRISPY CLEAR page is much more
    # uniformly brown and has a large centered orange next-stage button.
    return brown > 0.70 and next_button > 0.45 and bottom_x_visible(image)


def dungeon_exit_confirm_visible(image: Image.Image) -> bool:
    cyan_left = pixel_fraction(
        image, (100, 1600, 520, 1760),
        lambda r, g, b: g > 105 and b > 100 and g > r * 1.25,
    )
    orange_right = pixel_fraction(
        image, (540, 1600, 960, 1760),
        lambda r, g, b: r > 165 and 45 < g < 190 and b < 100 and r > b * 1.7,
    )
    dark_prompt = pixel_fraction(
        image, (90, 1430, 990, 1610),
        lambda r, g, b: r < 90 and g < 130 and b < 145,
    )
    return (
        cyan_left > 0.35
        and orange_right > 0.35
        and dark_prompt > 0.55
        and bottom_x_visible(image)
    )


def daily_detail_visible(image: Image.Image) -> bool:
    if daily_achievement_visible(image) or daily_clear_visible(image):
        return False
    return daily_tab_active(image) and _orange_button_fraction(image) > 0.25


def daily_detail_screen(image: Image.Image) -> bool:
    """Recognize a Daily detail page even after its start button turns gray."""
    if daily_achievement_visible(image) or daily_clear_visible(image):
        return False
    if daily_detail_visible(image):
        return True
    if not daily_tab_active(image):
        return False
    teal_center = pixel_fraction(
        image, (0, 250, 1080, 1450),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    # The list menu is a large teal sheet (>= 0.20). Detail pages keep the
    # dungeon illustration and party cards, so this remains below that even
    # when the key/ad action button is disabled.
    return teal_center < 0.20


def daily_start_available(image: Image.Image) -> bool:
    return (
        daily_detail_screen(image)
        and _orange_button_fraction(image, (300, 1430, 780, 1620)) > 0.18
    )


def daily_menu_visible(image: Image.Image) -> bool:
    if daily_achievement_visible(image) or daily_clear_visible(image):
        return False
    teal_center = pixel_fraction(
        image, (0, 250, 1080, 1450),
        lambda r, g, b: g > 65 and b > 65 and g > r * 1.2 and b > r * 1.1,
    )
    return (
        daily_tab_active(image)
        and 0.20 < teal_center < 0.65
        and _orange_button_fraction(image) < 0.12
    )


def daily_continuous_enabled(image: Image.Image) -> bool:
    yellow = pixel_fraction(
        image, (740, 1480, 830, 1560),
        lambda r, g, b: r > 175 and g > 145 and b < 100,
    )
    return daily_detail_screen(image) and yellow > 0.075


def daily_achievement_available(image: Image.Image) -> bool:
    bright_pink = pixel_fraction(
        image, (1040, 700, 1080, 780),
        lambda r, g, b: r > 220 and g < 105 and b > 75 and r > b * 1.1,
    )
    return daily_detail_screen(image) and bright_pink > 0.08


def daily_claim_all_available(image: Image.Image) -> bool:
    orange = _orange_button_fraction(image, (250, 1620, 830, 1780))
    return daily_achievement_visible(image) and orange > 0.18


def dungeon_battle_visible(image: Image.Image) -> bool:
    if any((
        challenge_menu_visible(image), crumble_dungeon_visible(image),
        arena_home_visible(image), arena_opponents_visible(image),
        implant_tower_visible(image), daily_menu_visible(image),
        daily_detail_visible(image), daily_achievement_visible(image),
        daily_clear_visible(image),
    )):
        return False
    equipment_area = pixel_fraction(
        image, (0, 1230, 1080, 1740),
        lambda r, g, b: r > 30 and r > g * 1.12 and g < 135 and b < 115,
    )
    return equipment_area > 0.23


def tower_clear_visible(image: Image.Image) -> bool:
    brown = pixel_fraction(
        image, (0, 250, 1080, 1700),
        lambda r, g, b: r > 45 and r > g * 1.25 and g < 125 and b < 100,
    )
    return (
        brown > 0.43
        and _orange_button_fraction(image, (150, 1350, 850, 1620)) > 0.12
        and bottom_x_visible(image)
    )


def crumble_result_visible(image: Image.Image) -> bool:
    brown = pixel_fraction(
        image, (0, 250, 1080, 1700),
        lambda r, g, b: r > 45 and r > g * 1.25 and g < 125 and b < 100,
    )
    return brown > 0.28 and bottom_x_visible(image) and not tower_clear_visible(image)


def arena_result_visible(image: Image.Image) -> bool:
    if any((arena_home_visible(image), arena_opponents_visible(image), dungeon_battle_visible(image))):
        return False
    lower_action = _orange_button_fraction(image, (180, 1450, 900, 1780))
    return bottom_x_visible(image) or lower_action > 0.12


def arena_victory_visible(image: Image.Image) -> bool:
    """Detect the full-screen WIN result before its slower generic result UI."""
    win_yellow = pixel_fraction(
        image, (300, 450, 850, 800),
        lambda r, g, b: r > 190 and g > 115 and b < 80 and r > b * 2,
    )
    tap_prompt = pixel_fraction(
        image, (350, 1690, 730, 1775),
        lambda r, g, b: min(r, g, b) > 175 and max(r, g, b) - min(r, g, b) < 75,
    )
    return win_yellow > 0.25 and tap_prompt > 0.045


def arena_rank_change_visible(image: Image.Image) -> bool:
    """Detect the tap-to-continue promotion/demotion page after a result."""
    if any((
        arena_home_visible(image), arena_opponents_visible(image),
        dungeon_battle_visible(image), arena_victory_visible(image),
    )):
        return False
    tap_prompt = pixel_fraction(
        image, (320, 1640, 770, 1805),
        lambda r, g, b: min(r, g, b) > 170 and max(r, g, b) - min(r, g, b) < 80,
    )
    return tap_prompt > 0.025


def arena_static_tap_result_visible(image: Image.Image, previous: Image.Image | None) -> bool:
    """Fallback for a defeat page that still resembles the arena battle.

    Defeat leaves the teams visible behind a dark overlay, so the normal battle
    detector can remain true. Require the bottom tap prompt and a nearly static
    full screen; live arena battles animate well above this difference limit.
    """
    if previous is None or any((
        arena_home_visible(image), arena_opponents_visible(image),
        arena_victory_visible(image),
    )):
        return False
    tap_prompt = pixel_fraction(
        image, (320, 1640, 770, 1805),
        lambda r, g, b: min(r, g, b) > 170 and max(r, g, b) - min(r, g, b) < 80,
    )
    return tap_prompt > 0.025 and image_difference(previous, image) < 0.012


def _static_dungeon_result_visible(image: Image.Image, previous: Image.Image | None) -> bool:
    """Fallback for redesigned clear pages: require a stable screen and action UI."""
    if previous is None or not bottom_x_visible(image):
        return False
    if any((
        challenge_menu_visible(image), crumble_dungeon_visible(image),
        arena_home_visible(image), arena_opponents_visible(image),
        implant_tower_visible(image), daily_menu_visible(image),
        daily_detail_visible(image), daily_achievement_visible(image),
        dungeon_exit_confirm_visible(image),
    )):
        return False
    lower_action = _orange_button_fraction(image, (150, 1350, 900, 1700))
    return lower_action > 0.12 and image_difference(previous, image) < 0.018


def _service_quest_during_daily_dungeon(image: Image.Image) -> bool:
    """Use daily-dungeon battle idle time without waiting on passive quests."""
    if daily_clear_visible(image) or not dungeon_battle_visible(image):
        return False
    quest, confidence = detect_quest(image, assume_battle=True)
    if quest == "unknown" or confidence < 0.56:
        return False
    if one_shot_quest_visible(image):
        print("  일일 던전 대기 중 한번에 클리어 퀘스트를 처리합니다.")
        verified_one_shot_reward()
        return True
    if quest_complete(image):
        print(f"  일일 던전 대기 중 완료 퀘스트 보상 처리: {quest} ({confidence:.2f})")
        claim_reward_verified(quest)
        return True
    if quest == "pet":
        print("  일일 던전 대기 중 펫 뽑기 퀘스트를 진행합니다.")
        return bool(verified_draw("pet"))
    if quest == "cookie":
        print("  일일 던전 대기 중 쿠키 뽑기 퀘스트를 진행합니다.")
        return bool(verified_draw("cookie"))
    if quest == "equipment":
        print("  일일 던전 대기 중 장비 뽑기 퀘스트를 진행합니다.")
        verified_equipment()
        return True
    if quest == "bag":
        print("  일일 던전 대기 중 가방 퀘스트를 진행합니다.")
        return bool(verified_bag())
    # Monster and stage quests advance naturally during the dungeon battle.
    return False


def _wait_dungeon_completion(
    label: str,
    result_predicate,
    return_predicate,
    timeout: int,
    service_quests: bool = False,
) -> tuple[Image.Image, str]:
    """Accept a verified result page or an already returned preparation page."""
    print(f"  확인: {label} 종료 신호 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    fallback_at = time.monotonic() + 3.0
    previous = None
    result_frames = 0
    return_frames = 0
    fallback_frames = 0
    next_quest_check_at = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        if dungeon_exit_confirm_visible(image):
            tap(DAILY_EXIT_CONTINUE, f"{label} 전투 계속하기", dry_run=False)
            previous = None
            result_frames = return_frames = fallback_frames = 0
            time.sleep(0.8)
            continue
        if result_predicate(image):
            result_frames += 1
            if result_frames >= 2:
                print(f"  성공: {label} 결과 화면 확인")
                return image, "result"
        else:
            result_frames = 0
        if time.monotonic() >= fallback_at and return_predicate(image):
            return_frames += 1
            if return_frames >= 2:
                print(f"  성공: {label} 준비 화면 자동 복귀 확인")
                return image, "returned"
        else:
            return_frames = 0
        if time.monotonic() >= fallback_at and _static_dungeon_result_visible(image, previous):
            fallback_frames += 1
            if fallback_frames >= 2:
                print(f"  성공: {label} 정지 결과 화면 교차 확인")
                return image, "result"
        else:
            fallback_frames = 0
        now = time.monotonic()
        if service_quests and now >= next_quest_check_at and dungeon_battle_visible(image):
            service_started = time.monotonic()
            try:
                if _service_quest_during_daily_dungeon(image):
                    deadline += time.monotonic() - service_started
                    previous = None
                    result_frames = return_frames = fallback_frames = 0
            except SafeStop as error:
                if STOP or isinstance(error, SkipAction):
                    raise
                print(f"  일일 던전 중 퀘스트 처리를 보류합니다: {error}")
                service_quests = False
            next_quest_check_at = time.monotonic() + 2.0
            continue
        previous = image
        time.sleep(0.4)
    raise SafeStop(f"제한시간 안에 확인하지 못했습니다: {label} 종료")


def draw_currency(image: Image.Image) -> str:
    # Cost icon on the 10-draw button. Cyan/blue means crystals; cream/yellow
    # means the ticket seen in the user's recording.
    icon = image.crop((430, 1510, 515, 1618)).resize((100, 100))
    pixels = list(icon.getdata())
    cyan = sum(1 for r, g, b in pixels if b > 125 and g > 105 and b > r * 1.25)
    ticket = sum(1 for r, g, b in pixels if r > 155 and g > 125 and b < 125)
    total = len(pixels)
    if cyan / total > 0.025:
        return "crystal"
    if ticket / total > 0.025:
        return "ticket"
    return "unknown"


def quest_completion_poll_interval(started: float) -> float:
    """Poll completed cards quickly, then ease off during long battles."""
    if time.monotonic() - started < QUEST_COMPLETION_FAST_WINDOW:
        return QUEST_COMPLETION_POLL
    return QUEST_COMPLETION_IDLE_POLL


def wait_until(description: str, predicate, timeout: int, interval=None):
    print(f"  대기: {description} (최대 {timeout}초)")
    started = time.monotonic()
    deadline = started + timeout
    equipment_interruptions = 0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state == "equipment_compare":
            equipment_interruptions += 1
            if equipment_interruptions > 5:
                raise SafeStop(f"{description} 대기 중 장착/판매 팝업이 반복해서 나타났습니다.")
            print(f"  {description} 대기 중 장착/판매 팝업을 처리합니다.")
            resolve_started = time.monotonic()
            image = resolve_equipment_comparisons(image, state)
            # Preserve the quest's original waiting time while the popup stack
            # is being cleared.
            deadline += time.monotonic() - resolve_started
        if predicate(image):
            return image
        time.sleep(interval if interval is not None else quest_completion_poll_interval(started))
    raise SafeStop(f"제한시간 안에 확인하지 못했습니다: {description}")


def wait_equipment_completion(timeout: int) -> Image.Image:
    print(f"  대기: equipment 완료 표시 또는 지연 장착/판매 팝업 (최대 {timeout}초)")
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state == "equipment_compare":
            image = resolve_equipment_comparisons(image, state)
            continue
        if state == "equipment_auto_result":
            resolve_equipment_auto_result(image)
            continue
        if state == "equipment_auto_tutorial":
            dismiss_equipment_auto_tutorial()
            time.sleep(0.45)
            continue
        if state == "equipment_auto_running":
            tap_and_expect(
                BOTTOM_X, "Auto 실행 중 안내창 닫기", "battle", timeout=12
            )
            continue
        if state == "battle" and quest_complete(image):
            return image
        time.sleep(quest_completion_poll_interval(started))
    raise SafeStop("제한시간 안에 확인하지 못했습니다: equipment 완료 표시")


def wait_draw_completion(quest_name: str, timeout: int) -> tuple[Image.Image, bool]:
    """Wait for a draw quest to complete, or confirm it already advanced.

    A high-grade pet/cookie animation can return to battle after the short
    yellow completion glow has already disappeared.  In that case the next
    quest card is visible and there is no reward left to tap.  Accept that
    transition only after the same *different* quest is recognized in three
    consecutive battle frames, so a single noisy OCR frame never causes a
    reward click to be skipped.
    """
    print(f"  대기: {quest_name} 완료 표시 또는 다음 퀘스트 전환 (최대 {timeout}초)")
    started = time.monotonic()
    deadline = started + timeout
    next_candidate = None
    next_frames = 0
    equipment_interruptions = 0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state == "equipment_compare":
            equipment_interruptions += 1
            if equipment_interruptions > 5:
                raise SafeStop(
                    f"{quest_name} 완료 확인 중 장착/판매 팝업이 반복해서 나타났습니다."
                )
            print(f"  {quest_name} 완료 확인 중 장착/판매 팝업을 처리합니다.")
            resolve_started = time.monotonic()
            image = resolve_equipment_comparisons(image, state)
            deadline += time.monotonic() - resolve_started
            state = screen_state(image)
        if state == "battle":
            if quest_complete(image):
                return image, False
            name, confidence = detect_quest(image, assume_battle=True)
            if name not in ("unknown", quest_name) and confidence >= 0.56:
                if name == next_candidate:
                    next_frames += 1
                else:
                    next_candidate, next_frames = name, 1
                if next_frames >= 3:
                    print(
                        f"  {quest_name} 완료 표시가 지나간 뒤 다음 퀘스트 전환 확인: "
                        f"{name} ({confidence:.2f})"
                    )
                    return image, True
            else:
                next_candidate, next_frames = None, 0
        else:
            next_candidate, next_frames = None, 0
        time.sleep(quest_completion_poll_interval(started))
    raise SafeStop(f"제한시간 안에 확인하지 못했습니다: {quest_name} 완료 표시")


def close_if_visible(label: str, dry_run: bool):
    if dry_run:
        print(f"  확인 예정: {label}의 하단 X")
        return
    image = screenshot()
    if not bottom_x_visible(image):
        raise SafeStop(f"{label}: 하단 중앙 X를 찾지 못했습니다.")
    tap(BOTTOM_X, f"{label} 닫기 X", dry_run=False)


def claim_completed(label: str, dry_run: bool, timeout: int):
    if dry_run:
        print(f"  확인 예정: {label} 완료 패널")
        return
    wait_until(f"{label} 퀘스트 완료", quest_complete, timeout)
    tap(QUEST_PANEL, f"{label} 퀘스트 완료/보상", dry_run=False)
    time.sleep(1.2)


def draw_quest(kind: str, dry_run: bool):
    print(f"\n[{kind} 10회 뽑기]")
    tap(QUEST_PANEL, f"{kind} 퀘스트 패널(자동 이동)", dry_run)
    if not dry_run:
        time.sleep(1.5)
        currency = draw_currency(screenshot())
        print(f"  비용 판별: {currency}")
        if currency == "crystal":
            raise SafeStop(f"{kind} 뽑기가 크리스탈 비용으로 표시되어 중단합니다.")
        if currency != "ticket":
            raise SafeStop(f"{kind} 뽑기 비용을 10회권으로 확정하지 못해 중단합니다.")
    else:
        print("  확인 예정: 10회 버튼이 뽑기권인지 판별")
    tap(TEN_DRAW, f"{kind} 10회권 사용", dry_run)
    if not dry_run:
        time.sleep(2.0)
    close_if_visible(f"{kind} 결과", dry_run)
    close_if_visible(f"{kind} 뽑기 창", dry_run)
    claim_completed(kind, dry_run, timeout=TIMEOUT_DRAW)


def equipment_quest(dry_run: bool):
    print("\n[오븐 장비 15개]")
    tap(QUEST_PANEL, "장비 퀘스트 패널(자동 이동)", dry_run)
    time.sleep(1.0)
    tap(AUTO_BUTTON, "Auto", dry_run)
    time.sleep(0.8)
    tap(AUTO_START, "자동 열기 시작", dry_run)
    claim_completed("장비 15개", dry_run, timeout=TIMEOUT_EQUIPMENT)


def monster_quest(dry_run: bool):
    print("\n[몬스터 20마리]")
    claim_completed("몬스터 20마리", dry_run, timeout=TIMEOUT_MONSTER)


def bag_quest(dry_run: bool):
    print("\n[가방에서 상자 전부 열기]")
    tap(QUEST_PANEL, "가방 퀘스트 패널(자동 이동)", dry_run)
    time.sleep(1.2)
    tap(BAG_FIRST_ITEM, "가방 첫 번째 상자", dry_run)
    time.sleep(0.8)
    tap(ITEM_USE, "상자 전부 열기", dry_run)
    time.sleep(1.5)
    close_if_visible("상자 보상", dry_run)
    close_if_visible("가방", dry_run)
    claim_completed("상자 사용", dry_run, timeout=TIMEOUT_BAG)


def stage_quest(dry_run: bool):
    print("\n[스테이지 클리어]")
    claim_completed("스테이지 클리어", dry_run, timeout=TIMEOUT_STAGE)


def cycle(number: int, dry_run: bool):
    print(f"\n========== {number}회차 ==========")
    draw_quest("펫", dry_run)
    equipment_quest(dry_run)
    monster_quest(dry_run)
    bag_quest(dry_run)
    stage_quest(dry_run)
    draw_quest("쿠키", dry_run)


_REPEAT_EQUIPMENT_MASK = None


def repeat_equipment_reward_visible(image: Image.Image) -> bool:
    """Identify the completed repeat card, not a normal equipment or bag quest."""
    global _REPEAT_EQUIPMENT_MASK
    if screen_state(image) != "battle" or not quest_complete(image):
        return False
    repeat_badge = pixel_fraction(
        image, (990, 990, 1080, 1030),
        lambda r, g, b: r > 180 and g > 140 and b < 120,
    )
    if repeat_badge < 0.20:
        return False
    if _REPEAT_EQUIPMENT_MASK is None:
        with Image.open(ASSETS / "repeat_equipment_card.png") as reference:
            _REPEAT_EQUIPMENT_MASK = _text_mask(reference)
    sample = _shifted_bit_masks(_text_mask(image.crop((704, 960, 1080, 1206))))
    return _aligned_bit_score(sample, _REPEAT_EQUIPMENT_MASK) >= 0.72


def claim_repeat_equipment_rewards(image: Image.Image) -> Image.Image:
    """Claim up to two stacked rewards, confirming the card before each tap."""
    current = image
    for attempt in range(1, 3):
        check_stop()
        if not repeat_equipment_reward_visible(current):
            break
        time.sleep(0.35)
        confirmed = screenshot()
        if not repeat_equipment_reward_visible(confirmed):
            return confirmed
        tap(QUEST_PANEL, f"누적 장비 반복 보상 수령 ({attempt}/2)", dry_run=False)
        time.sleep(0.8)
        current = wait_for_state("battle", timeout=15)
    return current


def claim_reward_verified(quest_name: str, followup_depth: int = 0):
    timeout = {
        "pet": TIMEOUT_DRAW, "cookie": TIMEOUT_DRAW, "equipment": TIMEOUT_EQUIPMENT,
        "monster": TIMEOUT_MONSTER, "bag": TIMEOUT_BAG, "stage": TIMEOUT_STAGE,
    }[quest_name]
    if quest_name == "equipment":
        wait_equipment_completion(timeout)
    elif quest_name in ("pet", "cookie"):
        _, already_advanced = wait_draw_completion(quest_name, timeout)
        if already_advanced:
            print("  뽑기 퀘스트가 이미 다음 퀘스트로 전환되어 보상 클릭을 건너뜁니다.")
            return
    else:
        wait_until(f"{quest_name} 완료 표시", quest_complete, timeout=timeout)
    for attempt in range(1, 4):
        transitioned_to_incomplete = False
        # A shop offer can cover the card between claim attempts. Never retry
        # the card coordinate until the battle screen is visible again.
        before_claim = wait_for_state("battle", timeout=15)
        if not quest_complete(before_claim):
            print("  완료 표시가 사라져 다음 반복에서 퀘스트를 다시 확인합니다.")
            return
        # A newly completed draw quest can return directly to battle while a
        # short loot animation still occupies the screen.  The first tap uses
        # the configured card coordinate; retries use the lower progress area
        # of the same yellow card, which remains safely inside the panel.
        reward_point = QUEST_PANEL if attempt == 1 else (
            QUEST_PANEL[0], min(QUEST_PANEL[1] + 50, 1160)
        )
        if attempt == 1 and quest_name in ("pet", "cookie"):
            time.sleep(0.8)
        tap(reward_point, f"완료된 퀘스트 보상 ({attempt}/3)", dry_run=False)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            check_stop()
            current = screenshot()
            state = screen_state(current)
            if state == "unknown" and bottom_x_visible(current):
                print("  보상 수령 중 팝업 감지: 하단 X를 확인하고 전투 화면으로 복귀합니다.")
                wait_for_state("battle", timeout=15)
                break
            if state == "reward":
                tap_and_expect(BOTTOM_X, "보상 화면 닫기", "battle")
                break
            if state in (
                "gacha", "bag", "draw_result", "item_dialog", "auto_dialog",
                "equipment_auto_result", "equipment_auto_running", "equipment_compare",
                "level_up", "tssr_reveal",
            ):
                print(f"  보상 수령 후 다음 화면이 열렸습니다: {state}")
                if not recover_to_battle():
                    raise SafeStop("보상 수령 후 전투 화면으로 복귀하지 못했습니다.")
                break
            if state == "battle" and not quest_complete(current):
                transitioned_to_incomplete = True
                break
            time.sleep(SCREEN_POLL)
        try:
            # The next quest can legitimately be the same kind as the one just
            # claimed.  Excluding the previous name made a normal transition
            # (for example cookie -> cookie) look like a failed reward claim.
            # Accept any recognized card, then use the yellow completion marker
            # below to distinguish a newly issued quest from an unclaimed card.
            next_image, next_quest, confidence = wait_detect_quest(
                timeout=5, exclude=None, require_incomplete=False
            )
            if next_quest == "equipment_repeat":
                claim_repeat_equipment_rewards(next_image)
                return
            if next_quest == quest_name and quest_complete(next_image):
                raise SafeStop("완료된 퀘스트 카드가 그대로 남아 있습니다.")
            print(f"  다음 퀘스트 확인: {next_quest} ({confidence:.2f})")
            if quest_complete(next_image):
                if followup_depth >= 5:
                    print("  연속 완료 퀘스트가 6개를 넘어 다음 반복에서 계속 확인합니다.")
                    return
                print(f"  랜덤 완료 퀘스트 발견: {next_quest} - 보상을 연속 수령합니다.")
                claim_reward_verified(next_quest, followup_depth + 1)
            return
        except SafeStop:
            if transitioned_to_incomplete:
                print("  완료 표시가 사라져 보상 수령 성공으로 확인했습니다. 다음 퀘스트 이름은 다음 반복에서 다시 판별합니다.")
                return
            if attempt < 3:
                print("  완료 패널이 그대로여서 보상 클릭을 다시 시도합니다.")
    raise SafeStop("3회 시도 후에도 퀘스트 보상 수령을 확인하지 못했습니다.")


def verified_draw(kind: str) -> bool:
    expected_name = "pet" if kind == "pet" else "cookie"
    current = screenshot()
    current_name, current_score = detect_quest(current)
    if current_name == "unknown" or current_score < 0.56:
        print("  행동 직전 퀘스트 판별이 불확실합니다. 여러 화면에서 다시 확인합니다.")
        current, current_name, current_score = wait_detect_quest(timeout=12, initial_image=current)
    if current_name != expected_name:
        print(f"  행동 직전 퀘스트가 {current_name}로 바뀌었습니다 ({current_score:.2f}). 다음 반복에서 다시 시작합니다.")
        return False
    retry_tap_until_state(
        QUEST_PANEL, "퀘스트 패널 자동 이동", "battle", "gacha",
        timeout=30, max_taps=5,
    )
    currency = draw_currency(screenshot())
    print(f"  비용 판별: {currency}")
    if currency == "crystal":
        raise SafeStop("10회 뽑기가 크리스탈 비용으로 표시되었습니다.")
    if currency != "ticket":
        raise SafeStop("10회 뽑기 비용을 티켓으로 확정하지 못했습니다.")
    tap_and_expect(TEN_DRAW, "티켓 10회 뽑기", "draw_result", timeout=20)
    draw_closed = close_draw_result_verified()
    if screen_state(draw_closed) == "gacha":
        retry_tap_until_state(
            BOTTOM_X, "뽑기 화면 닫기", "gacha", "battle", timeout=25
        )
    else:
        print("  뽑기 화면 닫기 생략: 이미 battle 화면입니다.")
        time.sleep(0.8)
        stable_battle = screenshot()
        if screen_state(stable_battle) != "battle":
            if not recover_to_battle():
                raise SafeStop("뽑기 완료 후 전투 화면을 안정적으로 확인하지 못했습니다.")
        elif not quest_complete(stable_battle):
            print("  전투 화면 복귀 완료: 완료 표시가 나타날 때까지 계속 확인합니다.")
    claim_reward_verified(expected_name)
    return True


def equipment_context_active() -> bool:
    return EQUIPMENT_SESSION or time.monotonic() < EQUIPMENT_PENDING_UNTIL


def resolve_equipment_comparisons(image: Image.Image, state: str) -> Image.Image:
    comparisons = 0
    while state == "equipment_compare":
        # A single battle-effect frame can resemble the two dark equipment
        # cards. Require the popup in two consecutive screenshots before every
        # action. A genuinely delayed popup may appear after the Auto session,
        # so visual confirmation—not the session timer—controls the click.
        time.sleep(0.30)
        confirmed = screenshot()
        confirmed_state = screen_state(confirmed)
        if confirmed_state != "equipment_compare":
            print("  장비 비교 화면이 연속 확인되지 않아 좌표 클릭을 건너뜁니다.")
            return confirmed
        image = confirmed
        state = confirmed_state
        comparisons += 1
        if comparisons > MAX_EQUIPMENT_COMPARISONS:
            raise SafeStop(
                f"장착/판매 팝업이 {MAX_EQUIPMENT_COMPARISONS}회를 넘어 "
                "안전을 위해 중단합니다."
            )
        before = screenshot()
        tap(EQUIPMENT_ACTION, "장착/판매 팝업 공통 좌표", dry_run=False)
        image, state = wait_for_states(("battle", "equipment_compare"), timeout=15, previous=before)
    print(f"  장착/판매 팝업 처리 완료: {comparisons}개")
    return image


def resolve_equipment_auto_result(image: Image.Image) -> tuple[Image.Image, str]:
    """Organize a completed ten-item batch and clear any real comparisons."""
    print("  확인: 자동 열기 결과 정리 후 전투·장비 비교 화면 (최대 30초)")
    deadline = time.monotonic() + 30
    organize_taps = 0
    next_tap_at = 0.0
    current = image
    while time.monotonic() < deadline:
        check_stop()
        state = screen_state(current)
        if state == "equipment_auto_tutorial":
            dismiss_equipment_auto_tutorial()
            time.sleep(0.45)
        elif state == "equipment_auto_result":
            now = time.monotonic()
            if organize_taps < 3 and now >= next_tap_at:
                organize_taps += 1
                tap(
                    AUTO_START,
                    f"자동 열기 결과 정리하기 ({organize_taps}/3)",
                    dry_run=False,
                )
                next_tap_at = time.monotonic() + 1.0
            else:
                time.sleep(SCREEN_POLL)
        elif state == "equipment_compare":
            current = resolve_equipment_comparisons(current, state)
            return current, screen_state(current)
        elif state == "battle":
            print("  성공: 자동 열기 결과 정리 후 battle 화면 확인")
            return current, state
        else:
            time.sleep(SCREEN_POLL)
        current = screenshot()
    raise SafeStop("장비 Auto 안내·결과 화면을 닫고 전투 화면으로 돌아가지 못했습니다.")


def start_equipment_auto_verified(image: Image.Image, timeout: int = 30) -> tuple[Image.Image, str]:
    """Retry Start only while the Auto sheet is still visibly unchanged."""
    print(f"  확인: 장비 자동 열기 시작 후 화면 전환 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    attempts = 0
    next_tap_at = 0.0
    current = image
    while time.monotonic() < deadline:
        check_stop()
        state = screen_state(current)
        if state in ("battle", "equipment_compare"):
            print(f"  성공: {state} 화면 확인")
            return current, state
        if state == "equipment_auto_result":
            print("  장비 10개 자동 열기 결과를 확인했습니다.")
            current, state = resolve_equipment_auto_result(current)
            return current, state
        if state == "equipment_auto_tutorial":
            print("  장비 Auto 안내창을 오늘 그만보기로 닫고 결과를 정리합니다.")
            dismiss_equipment_auto_tutorial()
            time.sleep(0.45)
            current = screenshot()
            continue
        if state == "equipment_auto_running":
            print("  Auto가 이미 실행 중입니다. 재시작하지 않고 안내창만 닫습니다.")
            current = tap_and_expect(
                BOTTOM_X, "Auto 실행 중 안내창 닫기", "battle", timeout=12
            )
            return current, "running"
        now = time.monotonic()
        if state == "auto_dialog" and attempts < 3 and now >= next_tap_at:
            attempts += 1
            tap(AUTO_START, f"장비 자동 열기 시작 ({attempts}/3)", dry_run=False)
            next_tap_at = time.monotonic() + EQUIPMENT_AUTO_RETRY
        elif state != "auto_dialog":
            # Loading and transition frames are observed without blind taps.
            time.sleep(0.5)
        else:
            time.sleep(SCREEN_POLL)
        current = screenshot()
    final_state = screen_state(current)
    if final_state == "auto_dialog":
        raise SafeStop("장비 자동 열기 시작 버튼이 3회에도 반응하지 않았습니다.")
    raise SafeStop(f"장비 자동 열기 후 예상 화면을 확인하지 못했습니다: {final_state}")


def open_equipment_auto_for_next_batch(
    timeout: int = 45, not_before: float = 0.0
) -> tuple[Image.Image, str]:
    """Open Auto as soon as the current ten-item batch has finished."""
    print(f"  확인: 다음 장비 10개 Auto 준비 또는 50/50 완료 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    next_tap_at = 0.0
    taps = 0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state == "equipment_compare":
            resolve_equipment_comparisons(image, state)
            continue
        if state == "equipment_auto_result":
            print("  장비 10개 결과 확인: 정리하기 후 다음 묶음으로 이어갑니다.")
            resolve_equipment_auto_result(image)
            not_before = max(not_before, time.monotonic() + EQUIPMENT_BATCH_SETTLE)
            next_tap_at = not_before
            continue
        if state == "equipment_auto_tutorial":
            print("  장비 Auto 반복 안내를 오늘 그만보기로 닫습니다.")
            dismiss_equipment_auto_tutorial()
            time.sleep(0.45)
            continue
        if state == "level_up":
            tap(LEVEL_UP_TAP, "장비 열기 중 레벨업 화면 넘기기", dry_run=False)
            time.sleep(0.5)
            continue
        if state == "equipment_auto_running":
            print("  Auto 실행 중 확인: 재시작하지 않고 안내창을 닫고 기다립니다.")
            tap_and_expect(
                BOTTOM_X, "Auto 실행 중 안내창 닫기", "battle", timeout=12
            )
            not_before = max(not_before, time.monotonic() + 4.0)
            next_tap_at = not_before
            continue
        if state == "battle" and quest_complete(image):
            print("  장비 퀘스트 50/50 완료 표시를 확인했습니다.")
            return image, "complete"
        now = time.monotonic()
        if state == "auto_dialog" and now >= not_before:
            print("  성공: 다음 장비 10개를 시작할 Auto 화면 확인")
            return image, "auto_dialog"
        if state == "battle" and now >= not_before and now >= next_tap_at:
            taps += 1
            tap(AUTO_BUTTON, f"다음 장비 10개 Auto 열기 ({taps})", dry_run=False)
            next_tap_at = time.monotonic() + EQUIPMENT_AUTO_RETRY
        else:
            time.sleep(0.45)
    raise SafeStop("현재 장비 10개 처리가 끝난 뒤 다음 Auto 화면을 열지 못했습니다.")


def verified_equipment():
    global EQUIPMENT_SESSION, EQUIPMENT_PENDING_UNTIL
    current = screenshot()
    if screen_state(current) == "battle" and quest_complete(current):
        print("  장비 퀘스트가 이미 완료되어 Auto를 다시 누르지 않습니다.")
        claim_reward_verified("equipment")
        EQUIPMENT_PENDING_UNTIL = 0.0
        return
    resume_existing_auto = equipment_context_active()
    if resume_existing_auto:
        print("  장비 Auto 진행 기록이 있어 현재 10개 처리가 끝나는 시점부터 이어서 확인합니다.")
    EQUIPMENT_SESSION = True
    try:
        EQUIPMENT_PENDING_UNTIL = time.monotonic() + 180
        batches_started = 0
        next_batch_check_at = (
            time.monotonic() + EQUIPMENT_BATCH_SETTLE if resume_existing_auto else 0.0
        )
        while batches_started < 5:
            auto_image, ready_state = open_equipment_auto_for_next_batch(
                timeout=45, not_before=next_batch_check_at
            )
            if ready_state == "complete":
                break
            image, state = start_equipment_auto_verified(auto_image, timeout=30)
            batches_started += 1
            next_batch_check_at = time.monotonic() + EQUIPMENT_BATCH_SETTLE
            print(f"  장비 Auto 10개 묶음 시작: {batches_started}/5")
            if state == "equipment_compare":
                resolve_equipment_comparisons(image, state)
        if batches_started >= 5:
            print("  장비 Auto 10개 묶음 5회 시작 완료: 50/50 완료 표시를 즉시 확인합니다.")
        claim_reward_verified("equipment")
        EQUIPMENT_PENDING_UNTIL = 0.0
    finally:
        EQUIPMENT_SESSION = False


def verified_waiting(name: str):
    claim_reward_verified(name)


def verified_one_shot_reward():
    """Open the special one-shot card, close its reward X, and recheck battle."""
    print("  한 번에 클리어 하기 보상 카드 확인: 퀘스트 번호는 무시하고 바로 누릅니다.")
    deadline = time.monotonic() + 30
    taps = 0
    next_tap_at = 0.0
    reward_closed = False
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        if bottom_x_visible(image):
            tap(BOTTOM_X, "한 번에 클리어 보상 중앙 하단 X 닫기", dry_run=False)
            reward_closed = True
            time.sleep(1.0)
            continue

        state = screen_state(image)
        if state == "battle":
            special = one_shot_quest_visible(image)
            if reward_closed and not special:
                print("  보상 화면 닫기 완료: 전투 메인 화면과 다음 퀘스트를 다시 확인합니다.")
                return
            now = time.monotonic()
            if special and taps < 3 and now >= next_tap_at:
                taps += 1
                tap(QUEST_PANEL, f"한 번에 클리어 하기 보상 확인 ({taps}/3)", dry_run=False)
                next_tap_at = now + 3.0
                time.sleep(0.8)
                continue
            if taps and not special:
                print("  한 번에 클리어 보상 수령 후 전투 메인 화면을 확인했습니다.")
                return
        elif state in ("reward", "gacha", "bag", "draw_result") and bottom_x_visible(image):
            tap(BOTTOM_X, "한 번에 클리어 보상 화면 닫기", dry_run=False)
            reward_closed = True
            time.sleep(1.0)
            continue
        time.sleep(SCREEN_POLL)
    raise SafeStop("한 번에 클리어 하기 보상 화면을 닫고 메인 화면을 확인하지 못했습니다.")


def boss_movement_enabled(keys):
    # Never silently filter an unsupported combination into an enabled one.
    return ((keys == ("d",) and BOSS_D_MOVE_ENABLED is True)
            or (keys == ("a", "s") and BOSS_AS_MOVE_ENABLED is True))


def selected_boss_movements():
    """Return enabled movement patterns in the order used for boss retries."""
    movements = []
    if BOSS_D_MOVE_ENABLED:
        movements.append((("d",), BOSS_MOVE_SECONDS, "D 유지 - 오른쪽 이동"))
    if BOSS_AS_MOVE_ENABLED:
        movements.append((("a", "s"), BOSS_CORNER_MOVE_SECONDS, "A+S 동시 유지 - 왼쪽 아래 이동"))
    return movements


def verified_stage_waiting():
    """Retry a boss with the user-selected preset order, then wait for transition."""
    print("  스테이지 클리어 대기: 0/1이면 상단 보스 소환 버튼을 우선 확인합니다.")
    started = time.monotonic()
    next_report = started + 60
    next_summon_at = 0.0
    boss_visible_frames = 0
    summon_stage = None
    summons_for_stage = 0
    summon_limit_reported = False
    active_battle_preset = None
    next_quest_candidate = None
    next_quest_frames = 0
    while True:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state == "equipment_compare":
            print("  스테이지 완료 대기 중 장착/판매 팝업을 처리합니다.")
            resolve_equipment_comparisons(image, state)
            continue
        if state == "battle" and quest_complete(image):
            print("  스테이지 클리어 완료 표시 확인: 숫자 비교 없이 보상을 받습니다.")
            break
        if summons_for_stage >= (len(BOSS_PRESET_SEQUENCE) or 3) and state == "battle":
            name, confidence = detect_quest(image, assume_battle=True)
            if name not in ("unknown", "stage") and confidence >= 0.56:
                if name == next_quest_candidate:
                    next_quest_frames += 1
                else:
                    next_quest_candidate, next_quest_frames = name, 1
                if next_quest_frames >= 2:
                    print(f"  다음 퀘스트 전환 확인: {name} ({confidence:.2f}) - 다음 반복에서 진행합니다.")
                    return
            else:
                next_quest_candidate, next_quest_frames = None, 0
        if boss_summon_ready(image):
            boss_visible_frames += 1
            if boss_visible_frames >= 2 and time.monotonic() >= next_summon_at:
                boss_visible_frames = 0
                current_stage = current_stage_number(image)
                stage_key = current_stage if current_stage is not None else (summon_stage or ("unknown",))
                if stage_key != summon_stage:
                    summon_stage = stage_key
                    summons_for_stage = 0
                    summon_limit_reported = False
                    active_battle_preset = None
                    next_quest_candidate, next_quest_frames = None, 0
                presets = BOSS_PRESET_SEQUENCE
                attempt_limit = len(presets) or 3
                if summons_for_stage >= attempt_limit:
                    if not summon_limit_reported:
                        stage_label = f"{current_stage[0]}-{current_stage[1]}" if current_stage else "현재 스테이지"
                        print(
                            f"  {stage_label} 보스 프리셋 재시도 완료 "
                            f"({','.join(map(str, BOSS_PRESET_SEQUENCE))}): "
                            "더 이상 소환하지 않고 다음 퀘스트를 기다립니다."
                        )
                        summon_limit_reported = True
                    next_summon_at = time.monotonic() + 10
                    continue
                movement_attempt = summons_for_stage
                preset_number = presets[summons_for_stage] if presets else None
                preset_label = f"{preset_number}번 [{COOKIE_PRESET_NAMES[preset_number]}]" if preset_number else "현재 프리셋 유지"
                if preset_number is not None and preset_number != active_battle_preset:
                    if summons_for_stage == 0:
                        print(f"  보스 첫 소환 전 선택한 전투 프리셋 {preset_label}을 적용합니다.")
                    else:
                        print(f"  이전 보스 소환 미완료: 전투 프리셋을 {preset_label}으로 변경합니다.")
                    if select_battle_preset(preset_number):
                        active_battle_preset = preset_number
                summons_for_stage += 1
                print(
                    f"  같은 스테이지 보스 소환 횟수: "
                    f"{summons_for_stage}/{attempt_limit} "
                    f"(프리셋 {preset_label})"
                )
                tap_without_settle(BOSS_SUMMON_BUTTON, "0/1 스테이지 퀘스트 - 보스 소환")
                movement_sequence = selected_boss_movements()
                if not movement_sequence:
                    print("  보스 이동 조합 사용 안 함: 키보드 입력을 건너뜁니다.")
                else:
                    keys, duration, movement_label = movement_sequence[movement_attempt % len(movement_sequence)]
                    print(f"  보스 이동 조합 선택: {movement_label}")
                    hold_bluestacks_keys(keys, duration, movement_label)
                print("  보스 소환 후 클리어를 기다립니다. 미완료 시 버튼이 다시 나오면 재시도합니다.")
                next_summon_at = time.monotonic() + 10
                time.sleep(2.0)
                continue
        else:
            boss_visible_frames = 0
        now = time.monotonic()
        if now >= next_report:
            print("  스테이지 클리어를 계속 기다리는 중입니다.")
            next_report = now + 60
        time.sleep(quest_completion_poll_interval(started))
    claim_reward_verified("stage")


def verified_bag() -> bool:
    retry_tap_until_state(
        QUEST_PANEL, "가방 퀘스트 자동 이동", "battle", "bag",
        timeout=30, max_taps=5,
    )
    tap(BAG_FIRST_ITEM, "가방 첫 아이템 한 번 열기", dry_run=False)
    deadline = time.monotonic() + 3.0
    image = screenshot()
    state = screen_state(image)
    while time.monotonic() < deadline and state not in ("item_dialog", "battle"):
        check_stop()
        time.sleep(0.35)
        image = screenshot()
        state = screen_state(image)

    if state == "item_dialog":
        tap(ITEM_USE, "첫 아이템 전부 사용", dry_run=False)
        image, state = wait_for_bag_open_result(timeout=25)
        if state in ("reward", "reward_variant"):
            image, state = close_bag_reward_verified(timeout=35, max_taps=5)
        print("  가방 아이템 한 번 사용 완료: 남은 칸을 다시 확인하지 않습니다.")
    else:
        print("  첫 아이템 사용창이 없어 추가 확인 없이 가방을 닫습니다.")

    if state == "bag":
        image = retry_tap_until_state(
            BOTTOM_X, "가방 바로 닫기", "bag", "battle", timeout=25, max_taps=5
        )
        state = screen_state(image)
    if state != "battle":
        raise SafeStop(f"가방 한 번 사용 후 전투 화면으로 복귀하지 못했습니다: {state}")

    # The quest-card text animates for several seconds after closing the bag.
    # Re-detecting its name here caused valid 0.65+ matches to fluctuate into
    # unknown. We already know this operation belongs to the bag quest, so wait
    # for its completion marker directly and then claim the reward.
    print("  가방 화면 종료: 완료 표시가 반영됐는지 확인합니다.")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        if state == "equipment_compare":
            print("  가방 완료 확인 중 장착/판매 팝업을 처리합니다.")
            resolve_started = time.monotonic()
            resolve_equipment_comparisons(image, state)
            deadline += time.monotonic() - resolve_started
            continue
        if state == "battle" and quest_complete(image):
            claim_reward_verified("bag")
            return True
        time.sleep(QUEST_COMPLETION_POLL)

    # One use may not complete the quest when the selected item did not qualify.
    # Exit quickly without creating an error; the next loop can try the bag once.
    current = screenshot()
    name, confidence = detect_quest(current)
    if screen_state(current) == "battle":
        if name != "unknown" and confidence >= 0.56:
            # Some bag uses advance directly to the next quest without leaving
            # a stable yellow-completion frame.  A clearly recognized different
            # card is sufficient proof that the bag step has already finished.
            print(f"  가방 사용 후 다음 퀘스트 전환 확인: {name} ({confidence:.2f})")
            return True
        print(f"  가방 퀘스트 완료 표시가 아직 없습니다 ({confidence:.2f}). 다음 반복에서 한 번 다시 시도합니다.")
        return False
    raise SafeStop("가방 한 번 사용 후 전투 화면을 확인하지 못했습니다.")


def normalize_to_battle(image: Image.Image) -> Image.Image:
    state = screen_state(image)
    if state == "battle":
        return image
    if state == "level_up":
        return tap_and_expect(LEVEL_UP_TAP, "레벨업 화면 넘기기", "battle", timeout=15)
    if state == "tssr_reveal":
        tap(LEVEL_UP_TAP, "TSSR 쿠키 등장 화면 넘기기", dry_run=False)
        image = screenshot()
        if screen_state(image) == "draw_result":
            close_draw_result_verified()
            image = screenshot()
        return normalize_to_battle(image)
    if state == "equipment_compare":
        return resolve_equipment_comparisons(image, state)
    if state == "equipment_auto_result":
        image, _ = resolve_equipment_auto_result(image)
        return image
    if state == "equipment_auto_tutorial":
        dismiss_equipment_auto_tutorial()
        time.sleep(0.45)
        return normalize_to_battle(screenshot())
    if state == "equipment_auto_running":
        return tap_and_expect(BOTTOM_X, "Auto 실행 중 안내창 닫기", "battle", timeout=15)
    if state in ("gacha", "bag", "draw_result", "reward") and bottom_x_visible(image):
        return tap_and_expect(BOTTOM_X, "열린 화면 닫기", "battle", timeout=15)
    raise SafeStop(f"시작 화면을 전투 화면으로 복귀할 수 없습니다: {state}")


def recover_to_battle(timeout: int = 40) -> bool:
    """Return known transient screens to battle without tapping unknown frames."""
    print(f"  자동 복구: 현재 화면부터 다시 확인 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        state = screen_state(image)
        print(f"  복구 화면 판별: {state}")
        if state == "battle":
            print("  복구 성공: 전투 화면에서 퀘스트를 다시 확인합니다.")
            return True
        if state == "equipment_compare":
            resolve_equipment_comparisons(image, state)
            continue
        if state == "equipment_auto_result":
            resolve_equipment_auto_result(image)
            continue
        if state == "equipment_auto_tutorial":
            dismiss_equipment_auto_tutorial()
            time.sleep(0.45)
            continue
        if state == "level_up":
            tap(LEVEL_UP_TAP, "레벨업 화면 - 화면을 탭하세요", dry_run=False)
            time.sleep(1.0)
            continue
        if state == "tssr_reveal":
            tap(LEVEL_UP_TAP, "TSSR 쿠키 등장 화면 넘기기", dry_run=False)
            time.sleep(1.0)
            continue
        if state in (
            "gacha", "bag", "draw_result", "reward", "item_dialog", "auto_dialog",
            "equipment_auto_running",
        ):
            if bottom_x_visible(image):
                tap(BOTTOM_X, f"복구: {state} 화면 닫기", dry_run=False)
            else:
                time.sleep(1.0)
            continue
        if state == "unknown" and bottom_x_visible(image):
            tap(BOTTOM_X, "복구: 새 보상 화면 닫기", dry_run=False)
            continue
        # Animations and unrecognized frames are observed, never blindly tapped.
        time.sleep(1.5)
    print("  복구 보류: 전투 화면을 아직 확인하지 못했습니다.")
    return False


def recover_and_find_resume_point(timeout: int = 50) -> tuple[bool, str, float]:
    """Recover a known screen and identify the quest to resume safely.

    Recovery never taps an unknown frame unless a verified bottom X is visible.
    The returned quest is informational; the main loop detects it once more
    before taking an action.
    """
    print("  재시작 지점 검색: 현재 화면을 분류하고 전투 화면으로 복귀합니다.")
    if not recover_to_battle(timeout=timeout):
        return False, "unknown", 0.0
    try:
        image, quest, confidence = wait_detect_quest(timeout=15)
        print(f"  재시작 지점 확인: {quest} 퀘스트 (신뢰도 {confidence:.2f})")
        return True, quest, confidence
    except SafeStop as error:
        if STOP:
            raise
        print(f"  전투 화면 복구 성공, 퀘스트 재확인은 다음 반복에서 재시도: {error}")
        return True, "판별 재시도", 0.0


def recover_with_android_back(max_backs: int = 5) -> bool:
    """Use Android Back after repeated unknown errors, stopping at battle."""
    print(f"  연속 Unknown 복구: BlueStacks 뒤로가기 사용 (최대 {max_backs}회)")
    backs = 0
    while backs < max_backs:
        check_stop()
        first = screenshot()
        first_state = screen_state(first)
        if first_state == "battle":
            print("  뒤로가기 복구 성공: 전투 메인 화면 확인")
            return True
        time.sleep(0.6)
        second = screenshot()
        second_state = screen_state(second)
        if second_state == "battle":
            print("  뒤로가기 없이 전투 메인 화면으로 자연 복귀했습니다.")
            return True
        if first_state != second_state and "unknown" not in (first_state, second_state):
            print(f"  화면 전환 중: {first_state} -> {second_state}, 클릭하지 않고 재확인")
            continue
        backs += 1
        print(f"  BlueStacks 뒤로가기 ({backs}/{max_backs}), 현재 화면: {second_state}")
        adb("shell", "input", "keyevent", "4")
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            check_stop()
            current = screenshot()
            if screen_state(current) == "battle":
                print("  뒤로가기 복구 성공: 전투 메인 화면 확인")
                return True
            time.sleep(SCREEN_POLL)
    print("  뒤로가기 복구 실패: 최대 횟수 후에도 전투 화면을 확인하지 못했습니다.")
    return False


def recoverable_in_infinite_mode(error: Exception) -> bool:
    message = str(error)
    unsafe_markers = (
        "크리스탈", "비용을 티켓", "비용으로", "해상도",
        "내부 연결 도구", "긴급정지", "200회를 넘어", "누적 장비 보상 수령 한도",
    )
    return not any(marker in message for marker in unsafe_markers)


def infinite_recovery_tier(
    consecutive_unknown: int,
    consecutive_same: int,
    recovery_failures: int,
    allow_restart: bool,
) -> str:
    """Escalate repeated recoverable errors without using a lifetime cap."""
    if allow_restart and (
        consecutive_unknown >= 6 or consecutive_same >= 6 or recovery_failures >= 3
    ):
        return "restart"
    if consecutive_unknown >= 3 or consecutive_same >= 3 or recovery_failures >= 2:
        return "back"
    return "screen"


def recovery_reason_key(reason: str) -> str:
    """Group the same recognition failure even when its best score fluctuates."""
    return re.sub(r"\(최고\s+\d+(?:\.\d+)?\)", "(최고 변동)", reason)


def restart_game_for_infinite_recovery() -> bool:
    """Cold-restart a repeatedly stuck game and return to a known battle screen."""
    print("  강화 복구: 반복 오류로 쿠키런 앱을 다시 실행합니다.")
    adb("shell", "am", "force-stop", GAME_PACKAGE)
    time.sleep(1.0)
    try:
        relaunch_game(timeout=180)
    except GameRelaunched:
        pass
    return recover_to_battle(timeout=90)


def _wait_dungeon_screen(label: str, predicate, timeout: int = 20, previous=None) -> Image.Image:
    print(f"  확인: {label} (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    stable = 0
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        changed = previous is None or image_difference(previous, image) > 0.025
        if changed and predicate(image):
            stable += 1
            if stable >= 2:
                print(f"  성공: {label} 확인")
                return image
        else:
            stable = 0
        time.sleep(0.55)
    raise SafeStop(f"제한시간 안에 확인하지 못했습니다: {label}")


def _main_battle_visible(image: Image.Image) -> bool:
    return screen_state(image) == "battle" and not any((
        challenge_menu_visible(image), crumble_dungeon_visible(image),
        arena_home_visible(image), arena_opponents_visible(image),
        implant_tower_visible(image), tower_clear_visible(image),
        daily_menu_visible(image), daily_detail_visible(image),
        daily_achievement_visible(image), daily_clear_visible(image),
    ))


def return_to_main_battle(max_backs: int = 5) -> Image.Image:
    print(f"  복귀: 던전에서 전투 메인 화면으로 이동 (최대 {max_backs}회)")
    for attempt in range(max_backs + 1):
        check_stop()
        image = screenshot()
        if _main_battle_visible(image):
            print("  복귀 성공: 전투 메인 화면 확인")
            return image
        if dungeon_exit_confirm_visible(image):
            tap(
                DAILY_EXIT_CONFIRM,
                f"던전 전투 종료 확인 ({attempt + 1}/{max_backs})",
                dry_run=False,
            )
            time.sleep(1.5)
            continue
        if attempt == max_backs:
            break
        if not bottom_x_visible(image):
            raise SafeStop("던전의 게임 내부 뒤로가기 버튼을 확인하지 못했습니다.")
        tap(BOTTOM_X, f"던전 게임 내부 뒤로가기 ({attempt + 1}/{max_backs})", dry_run=False)
        time.sleep(1.4)
    raise SafeStop("던전에서 전투 메인 화면으로 복귀하지 못했습니다.")


def open_challenge_menu() -> Image.Image:
    current = screenshot()
    if challenge_menu_visible(current):
        return current
    if not _main_battle_visible(current):
        current = return_to_main_battle()
    tap(DUNGEON_NAV, "하단 던전 메뉴", dry_run=False)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        check_stop()
        current = screenshot()
        if challenge_menu_visible(current):
            print("  성공: 도전 던전 메뉴 확인")
            return current
        time.sleep(0.6)
    # The game remembers the last daily/challenge tab. Select Challenge once
    # explicitly, but only after the dungeon window has had time to open.
    tap(CHALLENGE_TAB, "도전 던전 탭", dry_run=False)
    return _wait_dungeon_screen("도전 던전 메뉴", challenge_menu_visible, timeout=15)


def open_challenge_dungeon(kind: str) -> Image.Image:
    predicates = {
        "crumble": crumble_dungeon_visible,
        "arena": arena_home_visible,
        "implant": implant_tower_visible,
    }
    labels = {"crumble": "크럼블 던전", "arena": "아레나", "implant": "임플란트 타워"}
    menu = open_challenge_menu()
    print(f"  확인: {labels[kind]} 준비 화면 (최대 24초)")
    deadline = time.monotonic() + 24
    taps = 0
    stable = 0
    next_tap_at = 0.0
    while time.monotonic() < deadline:
        check_stop()
        current = screenshot()
        if predicates[kind](current) and image_difference(menu, current) > 0.025:
            stable += 1
            if stable >= 2:
                print(f"  성공: {labels[kind]} 준비 화면 확인")
                return current
        else:
            stable = 0
        now = time.monotonic()
        if challenge_menu_visible(current) and taps < 3 and now >= next_tap_at:
            taps += 1
            tap(CHALLENGE_ROWS[kind], f"{labels[kind]} ({taps}/3)", dry_run=False)
            next_tap_at = time.monotonic() + 2.5
        elif not challenge_menu_visible(current) and not predicates[kind](current):
            # A transition/animation is observed without adding another tap.
            time.sleep(0.7)
        else:
            time.sleep(0.55)
    raise SafeStop(f"제한시간 안에 확인하지 못했습니다: {labels[kind]} 준비 화면")


def _wait_for_battle_start(previous: Image.Image, label: str) -> Image.Image:
    return _wait_dungeon_screen(
        f"{label} 전투 시작", dungeon_battle_visible, timeout=30, previous=previous
    )


def _wait_for_arena_start(previous: Image.Image) -> Image.Image:
    return _wait_dungeon_screen(
        "아레나 전투 시작",
        lambda image: not any((
            challenge_menu_visible(image), arena_home_visible(image),
            arena_opponents_visible(image), crumble_dungeon_visible(image),
            implant_tower_visible(image),
        )),
        timeout=35,
        previous=previous,
    )


def run_crumble_dungeon(runs: int) -> int:
    completed = 0
    detail = open_challenge_dungeon("crumble")
    for number in range(1, runs + 1):
        check_stop()
        if not dungeon_action_available(detail):
            print(f"  크럼블 던전 입장권이 없거나 도전 버튼이 비활성입니다. ({completed}/{runs}회 완료)")
            break
        tap(CRUMBLE_START, f"크럼블 던전 도전 ({number}/{runs})", dry_run=False)
        _wait_for_battle_start(detail, "크럼블 던전")
        result, completion_state = _wait_dungeon_completion(
            "크럼블 던전 전투", crumble_result_visible,
            crumble_dungeon_visible, timeout=360,
        )
        completed += 1
        print(f"  완료: 크럼블 던전 {completed}/{runs}회")
        if completion_state == "result":
            tap(BOTTOM_X, "크럼블 던전 결과 닫기", dry_run=False)
            detail = _wait_dungeon_screen(
                "크럼블 던전 준비 화면 복귀", crumble_dungeon_visible,
                timeout=25, previous=result,
            )
        else:
            detail = result
    return_to_main_battle()
    return completed


def _wait_arena_completion(timeout: int = 240) -> Image.Image:
    # The regular Arena task and the standalone Arena mode must follow the
    # exact same post-battle flow.  Keeping two result loops caused defeat and
    # rank-change pages to be handled in one mode but left open in the other.
    return wait_arena_mode_return(timeout=timeout)


def arena_decision_action(values, challenge_available, next_available, free_available):
    """The limited mode may only select one of the three arena buttons."""
    opponent_power, opponent_trophies, my_power, my_trophies = values
    if (any(value is None or value < 0 for value in values)
            or my_power <= 0 or opponent_power <= 0):
        # Missing comparison data forbids a fight, not a confirmed free skip.
        if next_available:
            return "next"
        return "refresh" if free_available else "wait"
    if my_power > opponent_power:
        return "challenge" if challenge_available else "wait"
    if next_available:
        return "next"
    if free_available:
        return "refresh"
    return "wait"


def arena_mode_action(mode, values, challenge_available, next_available, free_available, terminal_known=False):
    """Choose an action without expanding the arena mode's three-button scope."""
    if mode == "challenge":
        opponent_power, opponent_trophies, my_power, my_trophies = values
        power_known = all(value is not None and value > 0 for value in (opponent_power, my_power))
        trophy_known = all(value is not None and value >= 0 for value in (opponent_trophies, my_trophies))
        # Prefer a favourable power match. If power is unfavourable, accept a
        # favourable/equal trophy match. A single failed OCR value must not
        # freeze this priority mode: move to the next free opponent, use a
        # genuinely free refresh, or fight at the terminal paid-refresh section.
        if challenge_available and power_known and opponent_power <= my_power:
            return "challenge"
        if challenge_available and trophy_known and opponent_trophies <= my_trophies:
            return "challenge"
        if next_available:
            return "next"
        if free_available:
            return "refresh"
        # At the final opponent, never use a timed/diamond refresh: challenge
        # the current opponent instead when its button is available.
        return "challenge" if terminal_known and challenge_available else "wait"
    return arena_decision_action(values, challenge_available, next_available, free_available)


def arena_selector_options(image):
    next_available, free_available, _ = arena_selector_details(image)
    return next_available, free_available


def arena_refresh_kind(counter, text: str) -> str:
    """Classify the shared selector button without treating paid as free."""
    normalized = re.sub(r"\s+", "", text)
    if counter is not None and counter[0] < counter[1]:
        return "next"
    if "새로고침" not in normalized:
        return "unknown"
    if "무료" in normalized and not re.search(
        r"\d|크리스탈|다이아|분|초|후|남", normalized
    ):
        return "free"
    return "paid_or_wait"


def arena_free_refresh_visual(image, text):
    """Match the observed no-price green button; reject cost/cooldown OCR."""
    if not isinstance(image, Image.Image) or re.search(r"\d|크리스탈|다이아|분|초|후|남", text):
        return False
    wagle = wagle_arena_opponents_visible(image)
    offset = 112 if wagle else 0
    reference_path = ASSETS / ("wagle_free_refresh.png" if wagle else "arena_free_refresh.png")
    if not reference_path.is_file():
        return False
    sample = image.crop((780, 1330 + offset, 1070, 1460 + offset)).convert("RGB")
    with Image.open(reference_path) as reference:
        if image_difference(sample, reference) > 0.015:
            return False
        reference_mask = _text_mask(reference)
    # The full white label must match: price/timer additions are not free.
    return _aligned_bit_score(_shifted_bit_masks(_text_mask(sample)), reference_mask) > 0.97


def arena_selector_status(image):
    counter = arena_opponent_counter(image)
    offset = 112 if wagle_arena_opponents_visible(image) else 0
    text = re.sub(r"\s+", "", _ocr_region(image, (780, 1330 + offset, 1070, 1470 + offset)))
    has_next = "다음상대" in text
    has_refresh = "새로고침" in text and not has_next
    refresh_kind = arena_refresh_kind(counter, text)
    if counter is None:
        # Button text is enough to distinguish the free Next button from the
        # terminal Refresh/diamond section even when the small 1/5 counter is
        # temporarily unreadable.
        # A free-looking label without the terminal 5/5 counter is not enough
        # proof to click. It may be a transition/cooldown bubble.
        return has_next, False, has_refresh, refresh_kind
    # The small N/5 counter is inside a quiet, fixed region and is more stable
    # than OCR over the animated button label.  When it says 1/5..4/5, the
    # same right-hand button is necessarily "Next Opponent" even if its Korean
    # label is temporarily obscured or OCR returns an empty string.
    next_available = counter[0] < counter[1]
    if counter[0] == counter[1] and refresh_kind != "free" and arena_free_refresh_visual(image, text):
        refresh_kind = "free"
    free_available = counter[0] == counter[1] and refresh_kind == "free"
    return next_available, free_available, counter[0] == counter[1] or has_refresh, refresh_kind


def arena_selector_details(image):
    next_available, free_available, terminal_known, _ = arena_selector_status(image)
    return next_available, free_available, terminal_known


def arena_decision_capture():
    check_stop()
    if game_is_foreground(force=True) is not True:
        raise SafeStop("아레나 모드: 쿠키런 전면 화면을 확인하지 못해 중단합니다.")
    # No auto relaunch, sleep-mode drag, popup dismissal or quest recovery here.
    return _capture_screenshot()


def wait_arena_decision_change(action, before_values, before_image=None, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        image = arena_decision_capture()
        if not arena_opponents_visible(image):
            return
        if action != "challenge":
            after = arena_match_values(image)
            readable_change = any(
                before is not None and current is not None and before != current
                for before, current in zip(before_values, after)
            )
            visual_change = before_image is not None and image_difference(before_image, image) > 0.035
            if readable_change or visual_change:
                return
        time.sleep(0.4)
    raise SafeStop("아레나 모드: 버튼 클릭 후 화면 변화를 확인하지 못해 재클릭하지 않고 중단합니다.")


def wait_arena_mode_return(timeout=240):
    """Finish every Arena result page after this process initiated a battle."""
    print(f"  확인: 아레나 승리·패배 결과 및 상대 화면 복귀 (최대 {timeout}초)")
    deadline = time.monotonic() + timeout
    stable_kind = None
    stable_frames = 0
    result_taps = 0
    home_taps = 0
    previous_image = None
    next_wait_report = time.monotonic() + 20
    while time.monotonic() < deadline:
        image = arena_decision_capture()
        if arena_opponents_visible(image):
            print("  성공: 아레나 상대 화면으로 복귀했습니다.")
            return image
        if arena_home_visible(image):
            stable_frames = stable_frames + 1 if stable_kind == "home" else 1
            stable_kind = "home"
            if stable_frames >= 2:
                if home_taps >= 2:
                    raise SafeStop("아레나 홈에서 상대 선택 화면으로 돌아가지 못했습니다.")
                home_taps += 1
                tap(arena_action_point(image, "enter"), f"아레나 상대 화면 다시 열기 ({home_taps}/2)", dry_run=False)
                previous_image = None
                stable_kind = None
                stable_frames = 0
                time.sleep(1.2)
            else:
                time.sleep(0.35)
            continue
        if arena_victory_visible(image):
            kind = "victory"
        elif arena_result_visible(image):
            kind = "result"
        elif arena_rank_change_visible(image):
            # The defeat page has the same tap-to-continue prompt family as
            # promotion/demotion. This is safe here because a battle was just
            # launched by this mode, and generic battle screens are excluded.
            kind = "continue"
        elif arena_static_tap_result_visible(image, previous_image):
            kind = "defeat"
        else:
            kind = None
        previous_image = image
        if kind is None:
            stable_kind = None
            stable_frames = 0
            if time.monotonic() >= next_wait_report:
                print("  대기: 아레나 전투 중이거나 결과 연출 중입니다.")
                next_wait_report = time.monotonic() + 20
            time.sleep(0.4)
            continue
        # WIN has a very distinctive yellow title and prompt.  The fallback
        # defeat detector has already required two nearly identical frames.
        # Other generic/rank pages require two readings to avoid transition
        # frames, while WIN and stable defeat can be advanced immediately.
        required_frames = 1 if kind in {"victory", "defeat"} else 2
        stable_frames = stable_frames + 1 if stable_kind == kind else 1
        stable_kind = kind
        if stable_frames < required_frames:
            time.sleep(0.3)
            continue
        if result_taps >= 12:
            raise SafeStop("아레나 결과 화면을 여러 번 넘겼지만 상대 화면으로 돌아가지 못했습니다.")
        result_taps += 1
        point = BOTTOM_X if kind == "result" and bottom_x_visible(image) else ARENA_RESULT_CONTINUE
        label = {
            "victory": "승리 화면", "result": "전투 결과 화면",
            "continue": "승급·강등 화면", "defeat": "패배 화면",
        }[kind]
        tap(point, f"아레나 {label} 넘기기 ({result_taps}/12)", dry_run=False)
        stable_kind = None
        stable_frames = 0
        previous_image = None
        time.sleep(0.65)
    raise SafeStop("아레나 전투 결과를 넘기고 상대 화면으로 복귀하지 못했습니다.")


def arena_deck_can_challenge(number, values):
    opponent, _, mine, _ = values
    if opponent is None or mine is None or opponent <= 0 or mine <= 0:
        return False
    return opponent * 10 <= mine * 11 if number in (1, 2) else number in (3, 4, 5) and opponent < mine


def report_arena_deck_decision(number, values, result):
    if ARENA_DECISION_REPORTER is None:
        return
    opponent, _, mine, _ = values
    ARENA_DECISION_REPORTER({
        "deck": number, "mine": mine, "opponent": opponent, "result": result,
    })


ARENA_DECK_X = (160, 248, 335, 423, 510)


def select_regular_arena_deck(number):
    x = ARENA_DECK_X[number - 1]
    check_stop()
    image = arena_decision_capture()
    if not arena_opponents_visible(image) or wagle_arena_opponents_visible(image):
        raise SafeStop("일반 아레나 덱 비교 화면이 바뀌었습니다.")
    tap((x, 1280), f"일반 아레나 {number}번 덱 비교", dry_run=False)
    deadline = time.monotonic() + 8
    stable = 0
    last_values = None
    while time.monotonic() < deadline:
        check_stop()
        image = arena_decision_capture()
        if not arena_opponents_visible(image) or wagle_arena_opponents_visible(image):
            raise SafeStop("덱 선택 중 아레나 화면이 바뀌었습니다.")
        selected = _orange_button_fraction(image, (x-25, 1260, x+25, 1300)) > .35
        values = arena_match_values(image)
        readable = values[0] is not None and values[2] is not None and values[0] > 0 and values[2] > 0
        stable = stable + 1 if selected and readable and values == last_values else 0
        last_values = values if selected and readable else None
        if stable >= 1:
            return values
        time.sleep(.4)
    else:
        raise SafeStop("아레나 덱 선택 또는 전투력 반영을 확인하지 못했습니다.")


def compare_regular_arena_decks():
    """Start with the main deck; try alternatives only against a stronger opponent."""
    values = select_regular_arena_deck(1)
    print(f"  주덱 1번 확인: {_arena_match_description(values)}")
    if arena_deck_can_challenge(1, values):
        opponent, _, mine, _ = values
        result = "10% 허용 도전" if opponent >= mine else "전투력 우위 도전"
        report_arena_deck_decision(1, values, result)
        return 1
    report_arena_deck_decision(1, values, "조건 미충족")
    opponent, _, mine, _ = values
    if opponent is None or mine is None or opponent <= 0 or mine <= 0 or opponent <= mine:
        return None
    for number in range(2, 6):
        values = select_regular_arena_deck(number)
        print(f"  {number}번 덱 비교: {_arena_match_description(values)}")
        if arena_deck_can_challenge(number, values):
            opponent, _, mine, _ = values
            result = "10% 허용 도전" if number in (1, 2) and opponent >= mine else "전투력 우위 도전"
            report_arena_deck_decision(number, values, result)
            print(f"  {number}번 덱 도전 기준 충족: 순차 비교를 마칩니다.")
            return number
        report_arena_deck_decision(number, values, "조건 미충족")
    print("  1~5번 덱 비교 완료: 도전 기준에 맞는 덱이 없습니다.")
    restored = select_regular_arena_deck(1)
    report_arena_deck_decision(1, restored, "주덱 복원")


def enter_selected_arena(kind):
    if kind not in {"regular", "wagle"}:
        raise SafeStop("아레나 종류를 확인하지 못했습니다.")
    def opponents(im):
        return arena_opponents_visible(im) and wagle_arena_opponents_visible(im) == (kind == "wagle")
    def home(im):
        return arena_home_visible(im) and wagle_arena_home_visible(im) == (kind == "wagle")
    current = screenshot()
    if opponents(current):
        return current
    if not home(current):
        if kind == "regular":
            current = open_challenge_dungeon("arena")
        else:
            if not _main_battle_visible(current):
                current = return_to_main_battle()
            if not _main_battle_visible(current):
                raise SafeStop("아레나 진입 전 전투 화면을 확인하지 못했습니다.")
            tap((1000, 815), "와글와글 아레나 VS 진입", dry_run=False)
            current = _wait_dungeon_screen("와글와글 아레나 홈", home, timeout=25)
    if not home(current):
        raise SafeStop("선택한 아레나와 열린 화면이 다릅니다.")
    tap(arena_action_point(current, "enter"), "아레나 도전하기 가기", dry_run=False)
    return _wait_dungeon_screen("선택한 아레나 상대 화면", opponents, timeout=25)


def run_arena_decision_only(mode="compare", arena_kind=None):
    if mode not in {"compare", "challenge"}:
        raise SafeStop("아레나 모드 설정을 확인하지 못했습니다.")
    mode_label = "전투력·트로피 비교" if mode == "compare" else "도전 우선"
    print(f"  아레나 모드: {mode_label}")
    print("  실행 횟수: 무한 · 정지 버튼을 누를 때까지 계속 비교합니다.")
    print("  도전 상대 화면에서만 허용된 아레나 버튼을 처리합니다.")
    print("  이 모드가 시작한 전투의 승리·패배·승급·강등 화면은 자동으로 넘깁니다.")
    previous = None
    decks_checked = False
    selected_deck = None
    handled = 0
    next_report = 0.0
    while True:
        image = arena_decision_capture()
        if not arena_opponents_visible(image):
            previous = None
            if time.monotonic() >= next_report:
                print("  대기: 아레나 도전 상대 화면을 직접 열어 주세요. 다른 화면은 클릭하지 않습니다.")
                next_report = time.monotonic() + 15
            time.sleep(0.5)
            continue
        if arena_kind is not None and wagle_arena_opponents_visible(image) != (arena_kind == "wagle"):
            raise SafeStop("선택한 아레나와 현재 화면이 달라 중단합니다.")
        challenge_available = (_orange_button_fraction(image, (320, 1490, 760, 1590)) > .14
                               if wagle_arena_opponents_visible(image) else dungeon_action_available(image))
        values = arena_match_values(image)
        if mode == "compare" and arena_kind == "regular" and not wagle_arena_opponents_visible(image) and not decks_checked:
            selected_deck = compare_regular_arena_decks()
            decks_checked = True
            previous = None
            continue
        next_available, free_available, terminal_known = arena_selector_details(image)
        refresh_kind = (
            "next" if next_available else
            "free" if free_available else
            "paid_or_wait" if terminal_known else
            "unknown"
        )
        action = arena_mode_action(
            mode, values, challenge_available, next_available, free_available, terminal_known
        )
        if (mode == "compare" and arena_kind == "regular" and selected_deck is not None
                and not wagle_arena_opponents_visible(image)
                and challenge_available and arena_deck_can_challenge(selected_deck, values)):
            action = "challenge"
        # Require the same decision twice, not byte-for-byte identical OCR.
        # Arena number readings commonly wobble by one digit between frames.
        signature = (action, next_available, terminal_known)
        if action == "wait":
            previous = None
            if time.monotonic() >= next_report:
                print(f"  아레나 비교: {_arena_match_description(values)}")
                if mode == "compare":
                    print("  대기: 판독 불확실·조건 불충족·재화 부족·유료 새로고침은 누르지 않습니다.")
                else:
                    print("  대기: 숫자를 읽지 못했거나 도전하기 버튼이 활성화되지 않았습니다.")
                if refresh_kind == "paid_or_wait":
                    print("  새로고침 상태: 다이아 비용 또는 무료 대기시간 · 클릭하지 않습니다.")
                next_report = time.monotonic() + 15
            time.sleep(1)
            continue
        if signature != previous:
            previous = signature
            time.sleep(0.3)
            continue
        check_stop()
        if game_is_foreground(force=True) is not True:
            raise SafeStop("아레나 모드: 게임 전면 화면이 바뀌어 클릭을 취소합니다.")
        print(f"  아레나 비교: {_arena_match_description(values)}")
        if mode == "challenge":
            opponent_power, opponent_trophies, my_power, my_trophies = values
            power_known = all(value is not None and value > 0 for value in (opponent_power, my_power))
            trophy_known = all(value is not None and value >= 0 for value in (opponent_trophies, my_trophies))
            if action == "next":
                if power_known and trophy_known:
                    print("  판단: 상대 전투력과 트로피가 모두 높아 다음 상대를 확인합니다.")
                else:
                    print("  판단: 일부 숫자가 불확실해 무료 다음 상대를 확인합니다.")
            elif action == "refresh":
                print("  판단: 마지막 상대까지 확인해 무료 새로고침을 사용합니다.")
            elif terminal_known and not (
                (power_known and opponent_power <= my_power)
                or (trophy_known and opponent_trophies <= my_trophies)
            ):
                print("  판단: 마지막 상대이므로 새로고침·다이아 대신 현재 상대에게 도전합니다.")
            elif power_known and opponent_power <= my_power:
                print("  판단: 상대 전투력이 더 높지 않아 도전합니다.")
            elif trophy_known:
                print("  판단: 상대 트로피가 더 높지 않아 도전합니다.")
            else:
                print("  판단: 도전 우선 조건에 따라 현재 상대에게 도전합니다.")
        elif action == "next":
            print("  판단: 현재 상대에게 도전하지 않고 사용 가능한 다음 상대를 확인합니다.")
        elif action == "refresh":
            print("  판단: 마지막 상대에게 도전하지 않고 확인된 무료 새로고침을 사용합니다.")
        elif action == "challenge":
            print("  판단: 현재 덱의 전투력 도전 기준을 충족해 도전합니다.")
        label = {"challenge": "도전하기", "next": "다음 상대", "refresh": "무료 새로고침"}[action]
        point = arena_action_point(image, action)
        tap(point, f"아레나 모드 - {label}", dry_run=False)
        wait_arena_decision_change(action, values, before_image=image)
        if action == "challenge":
            wait_arena_mode_return()
        decks_checked = False
        selected_deck = None
        handled += 1
        print(f"  아레나 판단 처리: {handled}회 (전투 승리 횟수 아님)")
        previous = None


def run_arena(runs: int) -> int:
    completed = 0
    home = open_challenge_dungeon("arena")
    tap(ARENA_ENTER, "아레나 도전 상대 보기", dry_run=False)
    opponents = _wait_dungeon_screen(
        "아레나 도전 상대 화면", arena_opponents_visible, timeout=25, previous=home
    )
    refreshes = 0
    leave_arena = False
    for number in range(1, runs + 1):
        check_stop()
        if not dungeon_action_available(opponents):
            print(f"  아레나 도전 재화가 부족하거나 버튼이 비활성입니다. ({completed}/{runs}회 완료)")
            break
        while True:
            values = arena_match_values(opponents)
            opponent_power, opponent_trophies, my_power, my_trophies = values
            print(f"  아레나 비교: {_arena_match_description(values)}")
            if None in values:
                print("  아레나 숫자를 정확히 읽지 못해 도전·새로고침을 누르지 않고 퀘스트로 복귀합니다.")
                leave_arena = True
                break
            if my_power > opponent_power:
                print("  내 전투력이 더 높아 이 상대에게 도전합니다.")
                break
            counter = arena_opponent_counter(opponents)
            if arena_next_opponent_available(opponents):
                before_change = opponents
                current = counter[0] if counter is not None else 0
                tap(
                    ARENA_REFRESH,
                    f"아레나 다음 상대 ({current}/5)",
                    dry_run=False,
                )
                opponents = _wait_dungeon_screen(
                    "다음 아레나 상대", arena_opponents_visible, timeout=20,
                    previous=before_change,
                )
                print("  상대 전투력이 높아 다음 상대로 이동합니다. 전투력과 트로피를 다시 비교합니다.")
                continue
            if opponent_trophies > my_trophies:
                if refreshes >= 5:
                    print("  무료 새로고침 확인을 5회 마쳐 퀘스트로 복귀합니다.")
                    leave_arena = True
                    break
                if not arena_free_refresh_available(opponents):
                    print("  새로고침 대기시간 또는 크리스탈 비용을 확인했습니다. 크리스탈을 사용하지 않고 퀘스트로 복귀합니다.")
                    leave_arena = True
                    break
                before_refresh = opponents
                refreshes += 1
                tap(ARENA_REFRESH, f"아레나 무료 새로고침 ({refreshes}/5)", dry_run=False)
                opponents = _wait_dungeon_screen(
                    "새 아레나 상대", arena_opponents_visible, timeout=20,
                    previous=before_refresh,
                )
                print("  무료 새로고침 완료: 상대를 다시 비교합니다.")
                # A refresh does not consume an arena run.
                continue
            print("  다음 상대 5회를 모두 확인했지만 상대 전투력이 더 높아 퀘스트로 복귀합니다.")
            leave_arena = True
            break
        if leave_arena:
            break
        tap(ARENA_CHALLENGE, f"아레나 도전 ({number}/{runs})", dry_run=False)
        _wait_for_arena_start(opponents)
        returned = _wait_arena_completion()
        completed += 1
        print(f"  완료: 아레나 {completed}/{runs}회")
        if number < runs:
            if arena_home_visible(returned):
                tap(ARENA_ENTER, "아레나 도전 상대 다시 보기", dry_run=False)
                opponents = _wait_dungeon_screen(
                    "아레나 도전 상대 화면", arena_opponents_visible, timeout=25,
                    previous=returned,
                )
            else:
                opponents = returned
    return_to_main_battle()
    return completed


def run_implant_tower(runs: int) -> int:
    completed = 0
    detail = open_challenge_dungeon("implant")
    if implant_continuous_enabled(detail):
        tap(IMPLANT_CONTINUOUS, "임플란트 타워 연속 도전 해제", dry_run=False)
        detail = _wait_dungeon_screen(
            "연속 도전 해제 확인",
            lambda image: implant_tower_visible(image) and not implant_continuous_enabled(image),
            timeout=12,
        )
    if not dungeon_action_available(detail):
        print(f"  임플란트 타워 도전 버튼이 비활성입니다. ({completed}/{runs}회 완료)")
        return_to_main_battle()
        return completed

    tap(IMPLANT_START, f"임플란트 타워 도전 (1/{runs})", dry_run=False)
    previous = detail
    while completed < runs:
        check_stop()
        _wait_for_battle_start(previous, "임플란트 타워")
        result, completion_state = _wait_dungeon_completion(
            "임플란트 타워", tower_clear_visible,
            implant_tower_visible, timeout=360,
        )
        completed += 1
        print(f"  완료: 임플란트 타워 {completed}/{runs}회")
        if completed < runs:
            if completion_state == "result":
                tap(IMPLANT_NEXT_FLOOR, "다음 층 도전", dry_run=False)
            else:
                if not dungeon_action_available(result):
                    print("  임플란트 타워 다음 도전 버튼이 비활성이라 반복을 종료합니다.")
                    break
                tap(IMPLANT_START, f"임플란트 타워 도전 ({completed + 1}/{runs})", dry_run=False)
            previous = result
        elif completion_state == "result":
            tap(BOTTOM_X, "임플란트 타워 결과 닫기", dry_run=False)
            _wait_dungeon_screen(
                "임플란트 타워 준비 화면 복귀",
                implant_tower_visible,
                timeout=25,
                previous=result,
            )
    return_to_main_battle()
    return min(completed, runs)


def run_challenge_dungeon(kind: str, runs: int, dry_run: bool = False) -> int:
    labels = {"crumble": "크럼블 던전", "arena": "아레나", "implant": "임플란트 타워"}
    runs = max(1, min(int(runs), 5))
    print(f"\n---------- 도전 던전: {labels[kind]} {runs}회 ----------")
    if dry_run:
        print("  점검 모드: 실제 클릭 없이 실행 계획만 확인합니다.")
        return 0
    runners = {
        "crumble": run_crumble_dungeon,
        "arena": run_arena,
        "implant": run_implant_tower,
    }
    completed = runners[kind](runs)
    print(f"---------- {labels[kind]} 종료: {completed}/{runs}회 ----------\n")
    return completed


def open_daily_menu() -> Image.Image:
    current = screenshot()
    if daily_menu_visible(current):
        return current
    if not _main_battle_visible(current):
        current = return_to_main_battle()
    tap(DUNGEON_NAV, "하단 던전 메뉴", dry_run=False)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        check_stop()
        current = screenshot()
        if daily_menu_visible(current):
            print("  성공: 일일 던전 메뉴 확인")
            return current
        time.sleep(0.6)
    tap(DAILY_TAB, "일일 던전 탭", dry_run=False)
    return _wait_dungeon_screen("일일 던전 메뉴", daily_menu_visible, timeout=15)


def _normalize_daily_menu(kind: str) -> Image.Image:
    menu = open_daily_menu()
    # The game remembers the last list position, so establish a known origin.
    for number in range(2):
        swipe((540, 650), (540, 1450), f"일일 던전 목록 맨 위로 ({number + 1}/2)")
        menu = _wait_dungeon_screen("일일 던전 목록", daily_menu_visible, timeout=10)
    if kind in DAILY_ROWS_SCROLLED:
        previous = menu
        swipe((540, 1420), (540, 650), "연구석·룬결정 던전 위치로 이동")
        menu = _wait_dungeon_screen(
            "일일 던전 아래 목록", daily_menu_visible, timeout=12, previous=previous
        )
    return menu


def open_daily_dungeon(kind: str) -> Image.Image:
    labels = {
        "exp": "경험치 던전", "coin": "코인 던전", "dough": "반죽 던전",
        "research_stone": "연구석 던전", "rune_crystal": "룬결정 던전",
    }
    menu = _normalize_daily_menu(kind)
    point = DAILY_ROWS_TOP.get(kind, DAILY_ROWS_SCROLLED.get(kind))
    if point is None:
        raise SafeStop(f"지원하지 않는 일일 던전입니다: {kind}")
    print(f"  확인: {labels[kind]} 준비 화면 (최대 24초)")
    deadline = time.monotonic() + 24
    taps = 0
    stable = 0
    next_tap_at = 0.0
    while time.monotonic() < deadline:
        check_stop()
        current = screenshot()
        if daily_detail_screen(current) and image_difference(menu, current) > 0.025:
            stable += 1
            if stable >= 2:
                print(f"  성공: {labels[kind]} 준비 화면 확인")
                return current
        else:
            stable = 0
        now = time.monotonic()
        if daily_menu_visible(current) and taps < 3 and now >= next_tap_at:
            taps += 1
            tap(point, f"{labels[kind]} ({taps}/3)", dry_run=False)
            next_tap_at = time.monotonic() + 2.5
        else:
            time.sleep(0.6)
    raise SafeStop(f"제한시간 안에 확인하지 못했습니다: {labels[kind]} 준비 화면")


def _set_daily_continuous(detail: Image.Image, enabled: bool) -> Image.Image:
    current = daily_continuous_enabled(detail)
    if current == enabled:
        print(f"  일일 던전 연속 도전: {'선택됨' if enabled else '해제됨'}")
        return detail
    action = "선택" if enabled else "해제"
    tap(DAILY_CONTINUOUS, f"일일 던전 연속 도전 {action}", dry_run=False)
    return _wait_dungeon_screen(
        f"일일 던전 연속 도전 {action}",
        lambda image: daily_detail_screen(image) and daily_continuous_enabled(image) == enabled,
        timeout=12,
    )


def _wait_daily_clear(label: str, timeout: int = 360) -> tuple[Image.Image, str]:
    return _wait_dungeon_completion(
        f"{label} 클리어", daily_clear_visible,
        daily_detail_screen, timeout, service_quests=True,
    )


def _collect_daily_achievement(detail: Image.Image, label: str) -> Image.Image:
    if daily_achievement_available(detail):
        print(f"  {label} 달성 보상 알림을 확인했습니다.")
    else:
        print(f"  {label} 달성 보상 알림이 없어도 수령 가능 여부를 확인합니다.")
    tap(DAILY_ACHIEVEMENT, f"{label} 달성 보상 열기", dry_run=False)
    deadline = time.monotonic() + 15
    popup = None
    stable_detail = 0
    open_attempts = 1
    next_open_at = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        check_stop()
        current = screenshot()
        if daily_achievement_visible(current):
            popup = current
            break
        if daily_detail_screen(current):
            stable_detail += 1
            now = time.monotonic()
            if open_attempts < 3 and now >= next_open_at:
                open_attempts += 1
                tap(
                    DAILY_ACHIEVEMENT,
                    f"{label} 달성 보상 열기 재시도 ({open_attempts}/3)",
                    dry_run=False,
                )
                stable_detail = 0
                next_open_at = time.monotonic() + 2.5
                continue
            if open_attempts >= 3 and stable_detail >= 4:
                print(f"  {label} 받을 달성 보상이 없어 준비 화면을 유지합니다.")
                return current
        else:
            stable_detail = 0
        time.sleep(0.55)
    if popup is None:
        raise SafeStop(f"{label} 달성 보상 화면을 확인하지 못했습니다.")
    if daily_claim_all_available(popup):
        tap(DAILY_CLAIM_ALL, f"{label} 달성 보상 모두 받기", dry_run=False)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            check_stop()
            current = screenshot()
            if daily_achievement_visible(current) and not daily_claim_all_available(current):
                break
            time.sleep(0.6)
    tap(BOTTOM_X, f"{label} 달성 보상 닫기", dry_run=False)
    return _wait_dungeon_screen(
        f"{label} 준비 화면 복귀", daily_detail_screen, timeout=20
    )


def _verify_daily_attempts(
    detail: Image.Image,
    label: str,
    completed: int,
    requested: int,
    continuous: bool,
) -> Image.Image:
    """Verify the actual clear count and the final Challenge button state."""
    print(f"  확인: {label} 도전하기! 횟수 및 종료 상태")
    deadline = time.monotonic() + 8
    stable = 0
    latest = detail
    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        if not daily_detail_screen(image):
            stable = 0
            time.sleep(0.45)
            continue
        latest = image
        available = daily_start_available(image)
        if continuous:
            stable = stable + 1 if not available else 0
            if stable >= 3:
                print(f"  도전하기! 횟수 확인: 실제 클리어 {completed}회 · 남은 도전 없음(회색)")
                return latest
        else:
            stable += 1
            if stable >= 2:
                if completed >= requested:
                    print(f"  도전하기! 횟수 확인: {completed}/{requested}회 완료")
                    return latest
                if not available:
                    print(
                        f"  도전하기! 횟수 확인: {completed}/{requested}회 · "
                        "남은 입장 가능 횟수가 없어 가능한 만큼 완료했습니다."
                    )
                    return latest
                raise SafeStop(
                    f"{label} 도전 횟수가 부족합니다: {completed}/{requested}회"
                )
        time.sleep(0.45)
    if continuous:
        raise SafeStop(f"{label} 도전하기! 버튼이 회색인지 확인하지 못했습니다.")
    raise SafeStop(f"{label} 도전하기! 횟수를 확인하지 못했습니다.")


def _run_daily_fixed(detail: Image.Image, label: str, runs: int) -> tuple[Image.Image, int]:
    detail = _set_daily_continuous(detail, False)
    completed = 0
    for number in range(1, runs + 1):
        check_stop()
        if not daily_start_available(detail):
            print(f"  {label} 입장권이 부족하거나 도전 버튼이 비활성입니다. ({completed}/{runs}회 완료)")
            break
        tap(DAILY_START, f"{label} 도전 ({number}/{runs})", dry_run=False)
        _wait_for_battle_start(detail, label)
        result, completion_state = _wait_daily_clear(label)
        completed += 1
        print(f"  완료: {label} {completed}/{runs}회")
        if completion_state == "result":
            # Close immediately so a result animation cannot begin another run.
            tap(BOTTOM_X, f"{label} 클리어 화면 닫기", dry_run=False)
            detail = _wait_dungeon_screen(
                f"{label} 준비 화면 복귀", daily_detail_screen,
                timeout=25, previous=result,
            )
        else:
            detail = result
        detail = _set_daily_continuous(detail, False)
    return detail, completed


def _run_daily_continuous(detail: Image.Image, label: str) -> tuple[Image.Image, int]:
    """Run until both keys and the paid ad-skip entry become unavailable."""
    detail = _set_daily_continuous(detail, True)
    if not daily_start_available(detail):
        print(f"  {label} 열쇠와 광고 스킵 도전이 이미 소진되어 있습니다.")
        return detail, 0

    completed = 0
    clear_visible = False
    exhausted_frames = 0
    service_quests = True
    next_quest_check_at = time.monotonic() + 1.0
    deadline = time.monotonic() + 2700
    tap(DAILY_START, f"{label} 연속 도전 시작", dry_run=False)
    _wait_for_battle_start(detail, label)
    print("  연속 도전 대기: 열쇠와 광고 스킵 도전이 모두 회색이 될 때까지 계속합니다.")

    while time.monotonic() < deadline:
        check_stop()
        image = screenshot()
        if dungeon_exit_confirm_visible(image):
            tap(DAILY_EXIT_CONTINUE, f"{label} 연속 도전 계속하기", dry_run=False)
            time.sleep(0.8)
            continue
        if daily_clear_visible(image):
            if not clear_visible:
                completed += 1
                print(f"  완료: {label} 연속 도전 {completed}회")
            clear_visible = True
            exhausted_frames = 0
            # Do not close the result. The game's continuous challenge starts
            # the next run after its own countdown.
            time.sleep(0.45)
            continue
        clear_visible = False
        if daily_detail_screen(image):
            if daily_start_available(image):
                # Keys may have reached zero while the paid ad-skip entry is
                # still orange. Start it and continue waiting for gray.
                print(f"  {label} 도전 버튼 활성 확인: 남은 열쇠 또는 광고 스킵을 계속 사용합니다.")
                tap(DAILY_START, f"{label} 남은 열쇠·광고 스킵 도전", dry_run=False)
                _wait_for_battle_start(image, label)
                exhausted_frames = 0
                continue
            exhausted_frames += 1
            if exhausted_frames >= 3:
                print(f"  {label} 도전 버튼 회색 확인: 열쇠와 광고 스킵을 모두 사용했습니다.")
                return image, completed
        else:
            exhausted_frames = 0
        now = time.monotonic()
        if service_quests and now >= next_quest_check_at and dungeon_battle_visible(image):
            service_started = time.monotonic()
            try:
                if _service_quest_during_daily_dungeon(image):
                    deadline += time.monotonic() - service_started
                    clear_visible = False
                    exhausted_frames = 0
            except SafeStop as error:
                if STOP or isinstance(error, SkipAction):
                    raise
                print(f"  일일 던전 연속 도전 중 퀘스트 처리를 보류합니다: {error}")
                service_quests = False
            next_quest_check_at = time.monotonic() + 2.0
            continue
        time.sleep(0.55)
    raise SafeStop(f"{label} 연속 도전이 45분 안에 소진 상태로 돌아오지 않았습니다.")


def _advance_daily_dungeon(detail: Image.Image, current: str, target: str) -> Image.Image:
    current_index = DAILY_ORDER.index(current)
    target_index = DAILY_ORDER.index(target)
    steps = target_index - current_index
    if steps <= 0:
        raise SafeStop(f"일일 던전 이동 순서가 올바르지 않습니다: {current} -> {target}")
    labels = {
        "exp": "경험치 던전", "coin": "코인 던전", "dough": "반죽 던전",
        "research_stone": "연구석 던전", "rune_crystal": "룬결정 던전",
    }
    for step in range(steps):
        before = detail
        destination = DAILY_ORDER[current_index + step + 1]
        tap(
            DAILY_NEXT_DUNGEON,
            f"달성 보상 위 오른쪽 이동 - {labels[destination]}",
            dry_run=False,
        )
        detail = _wait_dungeon_screen(
            f"{labels[destination]} 준비 화면 바로 이동",
            daily_detail_screen,
            timeout=20,
            previous=before,
        )
    return detail


def run_daily_dungeon_sequence(tasks, dry_run: bool = False) -> dict[str, int]:
    labels = {
        "exp": "경험치 던전", "coin": "코인 던전", "dough": "반죽 던전",
        "research_stone": "연구석 던전", "rune_crystal": "룬결정 던전",
    }
    selected = []
    for kind, runs, continuous in tasks:
        if kind not in labels:
            raise SafeStop(f"지원하지 않는 일일 던전입니다: {kind}")
        selected.append((kind, max(1, min(int(runs), 3)), bool(continuous) and int(runs) >= 3))
    if not selected:
        return {}
    if dry_run:
        print("  점검 모드: 선택한 일일 던전의 실행 계획만 확인합니다.")
        return {kind: 0 for kind, _, _ in selected}

    detail = open_daily_dungeon(selected[0][0])
    completed_by_kind = {}
    for index, (kind, runs, continuous) in enumerate(selected):
        label = labels[kind]
        mode = "열쇠·광고 스킵 소진" if continuous else f"{runs}회"
        print(f"\n---------- 일일 던전: {label} · {mode} ----------")
        if continuous:
            detail, completed = _run_daily_continuous(detail, label)
        else:
            detail, completed = _run_daily_fixed(detail, label, runs)
        completed_by_kind[kind] = completed
        detail = _verify_daily_attempts(detail, label, completed, runs, continuous)
        detail = _collect_daily_achievement(detail, label)
        print(f"---------- {label} 종료: {completed}회 ----------\n")
        if index + 1 < len(selected):
            detail = _advance_daily_dungeon(detail, kind, selected[index + 1][0])

    return_to_main_battle()
    return completed_by_kind


def run_daily_dungeon(
    kind: str, runs: int, dry_run: bool = False, continuous: bool = False
) -> int:
    result = run_daily_dungeon_sequence(((kind, runs, continuous),), dry_run=dry_run)
    return result.get(kind, 0)


def run_dynamic(cycles: int, dry_run: bool, infinite: bool = False):
    image = screenshot()
    state = screen_state(image)
    print(f"현재 화면 판별: {state}")
    if dry_run:
        if state != "battle":
            if state == "equipment_compare":
                print("점검 결과: 장착/판매 팝업이 열려 있습니다.")
            else:
                print(f"점검 결과: {state} 화면입니다. 전투 화면으로 돌아온 뒤 다시 점검하세요.")
            return
        quest, confidence = detect_quest(image)
        print(f"현재 퀘스트 판별: {quest} (신뢰도 {confidence:.2f})")
        if quest == "unknown":
            raise SafeStop("현재 퀘스트를 확실하게 판별하지 못했습니다.")
        print("점검 성공: 실제 클릭 없이 화면과 퀘스트를 확인했습니다.")
        return

    if infinite:
        if state != "battle":
            recover_to_battle()
    else:
        image = normalize_to_battle(image)
    target = None if infinite else max(1, min(cycles, 100)) * 6
    completed = 0
    error_total = 0
    consecutive_errors = 0
    consecutive_unknown_errors = 0
    consecutive_same_errors = 0
    recovery_failures = 0
    previous_error_reason = None
    error_counts = {}
    quest = "판별 전"
    repeat_reward_passes = 0
    if infinite:
        print("\n무한 반복 모드: 정지 버튼을 누를 때까지 계속합니다.")
    while target is None or completed < target:
        try:
            check_stop()
            quest = "판별 중"
            image = wait_for_state("battle", timeout=15)
            image, quest, confidence = wait_detect_quest(timeout=12, initial_image=image)
            print(f"\n현재 퀘스트: {quest} (신뢰도 {confidence:.2f})")
            if quest == "unknown":
                raise SafeStop("현재 퀘스트를 판별하지 못했습니다.")
            if quest == "equipment_repeat":
                repeat_reward_passes += 1
                if repeat_reward_passes > 20:
                    raise SafeStop("누적 장비 보상 수령 한도: 일반 퀘스트로 전환되지 않아 중단합니다.")
                claim_repeat_equipment_rewards(image)
                continue
            repeat_reward_passes = 0
            if one_shot_quest_visible(image):
                verified_one_shot_reward()
            elif quest_complete(image):
                print("  현재 퀘스트가 이미 완료 상태이므로 보상부터 확인합니다.")
                claim_reward_verified(quest)
            elif quest == "pet":
                if not verified_draw("pet"):
                    continue
            elif quest == "cookie":
                if not verified_draw("cookie"):
                    continue
            elif quest == "equipment":
                verified_equipment()
            elif quest == "monster":
                verified_waiting("monster")
            elif quest == "bag":
                if not verified_bag():
                    time.sleep(10)
                    continue
            elif quest == "stage":
                verified_stage_waiting()
            completed += 1
            consecutive_errors = 0
            consecutive_unknown_errors = 0
            consecutive_same_errors = 0
            recovery_failures = 0
            previous_error_reason = None
            if PROGRESS_REPORTER:
                PROGRESS_REPORTER(completed)
            total_label = "∞" if target is None else str(target)
            print(f"검증 완료 퀘스트: {completed}/{total_label}")
        except SafeStop as error:
            if isinstance(error, SkipAction):
                raise
            if isinstance(error, GameRelaunched):
                print("\n---------- 게임 재실행 복구 ----------")
                print("  쿠키런 게임 화면을 확인했습니다. 현재 퀘스트부터 다시 확인합니다.")
                print("----------------------------------------\n")
                consecutive_errors = 0
                consecutive_unknown_errors = 0
                consecutive_same_errors = 0
                recovery_failures = 0
                previous_error_reason = None
                time.sleep(2)
                continue
            if STOP or not infinite or not recoverable_in_infinite_mode(error):
                raise
            error_total += 1
            consecutive_errors += 1
            reason = str(error)
            reason_key = recovery_reason_key(reason)
            error_counts[reason_key] = error_counts.get(reason_key, 0) + 1
            consecutive_same_errors = (
                consecutive_same_errors + 1 if reason_key == previous_error_reason else 1
            )
            previous_error_reason = reason_key
            print("\n---------- 무한 반복 오류 보고 ----------")
            print(f"  전체 화면 오류: {error_total}회")
            print(f"  같은 오류: {error_counts[reason_key]}회")
            print(f"  동일 오류 연속: {consecutive_same_errors}회")
            print(f"  연속 오류: {consecutive_errors}회")
            print(f"  완료한 퀘스트: {completed}개")
            print(f"  오류 내용: {reason}")
            before_image = None
            try:
                before_image = screenshot()
                before_state = screen_state(before_image)
            except Exception:
                before_state = "확인 실패"
            unknown_failure = before_state == "unknown" or any(
                marker in reason for marker in ("판별하지 못", "예상 화면을 확인하지 못")
            )
            consecutive_unknown_errors = consecutive_unknown_errors + 1 if unknown_failure else 0
            print(f"  연속 Unknown 오류: {consecutive_unknown_errors}회")
            recovery_result = "복구 실패"
            after_state = "확인하지 못함"
            resume_quest = "확인하지 못함"
            try:
                recovery_tier = infinite_recovery_tier(
                    consecutive_unknown_errors,
                    consecutive_same_errors,
                    recovery_failures,
                    AUTO_RELAUNCH_GAME,
                )
                print({
                    "screen": "  복구 단계 1/3: 현재 화면 분류 후 복귀",
                    "back": "  복구 단계 2/3: Android 뒤로가기 후 복귀",
                    "restart": "  복구 단계 3/3: 쿠키런 앱 재실행 후 복귀",
                }[recovery_tier])
                used_back = recovery_tier == "back"
                restarted = recovery_tier == "restart"
                if restarted:
                    recovered = restart_game_for_infinite_recovery()
                    if recovered:
                        try:
                            _, resume_quest, resume_confidence = wait_detect_quest(timeout=20)
                        except SafeStop:
                            resume_quest, resume_confidence = "판별 재시도", 0.0
                elif used_back:
                    recovered = recover_with_android_back(max_backs=5)
                    if recovered:
                        try:
                            _, resume_quest, resume_confidence = wait_detect_quest(timeout=15)
                        except SafeStop:
                            resume_quest, resume_confidence = "판별 재시도", 0.0
                    else:
                        recovered, resume_quest, resume_confidence = recover_and_find_resume_point()
                else:
                    recovered, resume_quest, resume_confidence = recover_and_find_resume_point()
                recovery_result = (
                    ("게임 재실행 후 " if restarted else "뒤로가기 후 " if used_back else "")
                    + f"전투 화면 복구 성공, {resume_quest}에서 재시작"
                    + (f" (신뢰도 {resume_confidence:.2f})" if resume_confidence else "")
                    if recovered else "복구 시간 초과"
                )
                recovery_failures = 0 if recovered else recovery_failures + 1
                if recovered and restarted:
                    # A cold restart is the final escalation step. Start a new
                    # streak afterward instead of restarting on every later
                    # recoverable error.
                    consecutive_same_errors = 0
                    consecutive_unknown_errors = 0
                    previous_error_reason = None
                try:
                    after_state = screen_state(screenshot())
                except Exception:
                    after_state = "확인 실패"
            except SafeStop as recovery_error:
                if STOP:
                    raise
                print(f"  자동 복구 중 추가 오류: {recovery_error}")
                recovery_result = f"복구 도중 추가 오류: {recovery_error}"
                recovery_failures += 1
            if ERROR_REPORTER:
                ERROR_REPORTER({
                    "kind": "무한 반복 복구 오류",
                    "reason": reason,
                    "total": error_total,
                    "same": error_counts[reason_key],
                    "consecutive": consecutive_errors,
                    "completed": completed,
                    "quest": quest,
                    "before_state": before_state,
                    "recovery": recovery_result,
                    "after_state": after_state,
                    "resume_quest": resume_quest,
                    "unknown_consecutive": consecutive_unknown_errors,
                    "_screenshot_image": before_image,
                })
            print("---------- 처음부터 재판별 ----------\n")
            time.sleep(2)


def main() -> int:
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    print("쿠키런: 크럼블 퀘스트 도우미")
    print("긴급정지: 이 창에서 Ctrl+C")
    print("주의: 게임 이용약관에 따라 계정 제재 가능성이 있습니다.\n")

    try:
        ensure_adb_connection()
    except SafeStop as error:
        print(error)
        return 2
    size = adb("shell", "wm", "size").stdout
    device_width, device_height = configure_device_size(size)
    print(f"BlueStacks 화면 크기: {device_width}x{device_height} (좌표 자동 변환)")

    print("1) 점검 실행(클릭하지 않음, 권장)")
    print("2) 실제 실행")
    mode = input("선택 [1]: ").strip() or "1"
    dry_run = mode != "2"
    try:
        count = int(input("반복 횟수 [1, 최대 100]: ").strip() or "1")
    except ValueError:
        print("반복 횟수가 올바르지 않습니다.")
        return 2
    count = max(1, min(count, 100))

    if not dry_run:
        print("\n시작 전 조건:")
        print("- 전투 화면이며 현재 퀘스트가 '펫 뽑기 10회'여야 합니다.")
        print("- 장비 비교/판매 팝업 등 다른 창을 모두 닫아야 합니다.")
        phrase = input("실행하려면 정확히 '시작'을 입력하세요: ").strip()
        if phrase != "시작":
            print("취소했습니다.")
            return 0

    try:
        for number in range(1, count + 1):
            cycle(number, dry_run)
    except (SafeStop, subprocess.CalledProcessError) as error:
        print(f"\n안전 중단: {error}")
        print("게임 화면을 직접 확인해 주세요.")
        return 1

    print("\n점검이 끝났습니다." if dry_run else "\n요청한 반복을 마쳤습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
