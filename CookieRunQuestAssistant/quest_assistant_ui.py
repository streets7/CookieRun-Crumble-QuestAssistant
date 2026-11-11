#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import quest_assistant as engine


ROOT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT_DIR / "settings.json"

DEFAULTS = {
    "cycles": 1,
    "dry_run": True,
    "draw_timeout": 25,
    "equipment_timeout": 90,
    "monster_timeout": 180,
    "bag_timeout": 30,
    "stage_timeout": 300,
    "quest_panel": "900,1060",
    "ten_draw": "575,1565",
    "bottom_x": "540,1845",
    "auto_button": "415,1725",
    "auto_start": "540,1690",
    "bag_item": "160,1160",
    "item_minus": "225,708",
    "item_use": "540,850",
    "boss_summon": "540,305",
}


class QueueWriter(io.TextIOBase):
    def __init__(self, messages: queue.Queue):
        self.messages = messages

    def write(self, text):
        if text:
            self.messages.put(("log", text))
        return len(text)

    def flush(self):
        return None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("쿠키런: 크럼블 퀘스트 도우미")
        self.geometry("720x700")
        self.minsize(660, 600)
        self.messages = queue.Queue()
        self.worker = None
        self.vars = {}
        self._build()
        self._load_settings(silent=True)
        self.after(100, self._poll_messages)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Helvetica", 20, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 12, "bold"))

        top = ttk.Frame(self, padding=18)
        top.pack(fill="x")
        ttk.Label(top, text="쿠키런: 크럼블 퀘스트 도우미", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            top,
            text="티켓 뽑기만 실행하며 크리스탈·알 수 없는 화면에서는 자동 중단합니다.",
        ).pack(anchor="w", pady=(4, 0))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        main = ttk.Frame(notebook, padding=16)
        advanced = ttk.Frame(notebook, padding=16)
        notebook.add(main, text="시작 메뉴")
        notebook.add(advanced, text="세부 설정")

        self.vars["cycles"] = tk.IntVar(value=1)
        self.vars["dry_run"] = tk.BooleanVar(value=True)
        ttk.Label(main, text="반복 횟수").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Spinbox(main, from_=1, to=20, textvariable=self.vars["cycles"], width=8).grid(
            row=0, column=1, sticky="w", padx=12
        )
        ttk.Checkbutton(
            main,
            text="점검 모드 (실제 클릭하지 않음)",
            variable=self.vars["dry_run"],
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)

        buttons = ttk.Frame(main)
        buttons.grid(row=2, column=0, columnspan=3, sticky="ew", pady=12)
        self.start_button = ttk.Button(buttons, text="시작", command=self._start)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.stop_button = ttk.Button(buttons, text="정지", command=self._stop, state="disabled")
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.status = tk.StringVar(value="대기 중")
        ttk.Label(main, textvariable=self.status, style="Status.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(4, 8)
        )

        self.log = tk.Text(main, height=20, wrap="word", state="disabled")
        self.log.grid(row=4, column=0, columnspan=3, sticky="nsew")
        scrollbar = ttk.Scrollbar(main, command=self.log.yview)
        scrollbar.grid(row=4, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)
        main.columnconfigure(2, weight=1)
        main.rowconfigure(4, weight=1)

        timeouts = [
            ("draw_timeout", "뽑기 완료 대기", 25),
            ("equipment_timeout", "장비 15개 대기", 90),
            ("monster_timeout", "몬스터 20마리 대기", 180),
            ("bag_timeout", "상자 사용 완료 대기", 30),
            ("stage_timeout", "스테이지 완료 대기", 300),
        ]
        ttk.Label(advanced, text="최대 대기시간(초)", font=("Helvetica", 13, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        row = 1
        for key, label, default in timeouts:
            self.vars[key] = tk.IntVar(value=default)
            ttk.Label(advanced, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Spinbox(advanced, from_=5, to=900, textvariable=self.vars[key], width=10).grid(
                row=row, column=1, sticky="w", padx=12
            )
            row += 1

        ttk.Separator(advanced).grid(row=row, column=0, columnspan=3, sticky="ew", pady=12)
        row += 1
        ttk.Label(advanced, text="화면 좌표 (x,y)", font=("Helvetica", 13, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        row += 1
        ttk.Label(
            advanced,
            text="화면 크기를 자동으로 맞춥니다. 좌표 변경 후에는 점검 모드를 먼저 사용하세요.",
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
        row += 1
        coords = [
            ("quest_panel", "오른쪽 퀘스트 패널", "900,1060"),
            ("ten_draw", "10회 뽑기", "575,1565"),
            ("bottom_x", "하단 중앙 X", "540,1845"),
            ("auto_button", "Auto", "415,1725"),
            ("auto_start", "Auto 시작", "540,1690"),
            ("bag_item", "가방 첫 아이템", "160,1160"),
            ("item_minus", "수량 감소", "225,708"),
            ("item_use", "아이템 사용", "540,850"),
            ("boss_summon", "보스 소환", "540,305"),
        ]
        for key, label, default in coords:
            self.vars[key] = tk.StringVar(value=default)
            ttk.Label(advanced, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(advanced, textvariable=self.vars[key], width=15).grid(
                row=row, column=1, sticky="w", padx=12
            )
            row += 1

        actions = ttk.Frame(advanced)
        actions.grid(row=row, column=0, columnspan=3, sticky="ew", pady=14)
        ttk.Button(actions, text="설정 저장", command=self._save_settings).pack(side="left")
        ttk.Button(actions, text="기본값 복원", command=self._restore_defaults).pack(
            side="left", padx=8
        )

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    @staticmethod
    def _coord(text):
        pieces = [int(piece.strip()) for piece in text.split(",")]
        if len(pieces) != 2:
            raise ValueError
        x, y = pieces
        if not (0 <= x < 1080 and 0 <= y < 1920):
            raise ValueError
        return x, y

    def _collect(self):
        data = {key: variable.get() for key, variable in self.vars.items()}
        data["cycles"] = max(1, min(int(data["cycles"]), 20))
        for key in ("draw_timeout", "equipment_timeout", "monster_timeout", "bag_timeout", "stage_timeout"):
            data[key] = max(5, min(int(data[key]), 900))
        for key in ("quest_panel", "ten_draw", "bottom_x", "auto_button", "auto_start", "bag_item", "item_minus", "item_use", "boss_summon"):
            self._coord(str(data[key]))
        return data

    def _apply_engine_settings(self, data):
        engine.QUEST_PANEL = self._coord(data["quest_panel"])
        engine.TEN_DRAW = self._coord(data["ten_draw"])
        engine.BOTTOM_X = self._coord(data["bottom_x"])
        engine.AUTO_BUTTON = self._coord(data["auto_button"])
        engine.AUTO_START = self._coord(data["auto_start"])
        engine.BAG_FIRST_ITEM = self._coord(data["bag_item"])
        engine.ITEM_MINUS = self._coord(data["item_minus"])
        engine.ITEM_USE = self._coord(data["item_use"])
        engine.BOSS_SUMMON_BUTTON = self._coord(data["boss_summon"])
        engine.TIMEOUT_DRAW = data["draw_timeout"]
        engine.TIMEOUT_EQUIPMENT = data["equipment_timeout"]
        engine.TIMEOUT_MONSTER = data["monster_timeout"]
        engine.TIMEOUT_BAG = data["bag_timeout"]
        engine.TIMEOUT_STAGE = data["stage_timeout"]

    def _save_settings(self):
        try:
            data = self._collect()
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            messagebox.showinfo("저장 완료", "설정을 저장했습니다.")
        except (ValueError, tk.TclError):
            messagebox.showerror("설정 오류", "숫자와 좌표 값을 확인해 주세요.")

    def _load_settings(self, silent=False):
        data = DEFAULTS.copy()
        if SETTINGS_FILE.exists():
            try:
                data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
            except Exception:
                if not silent:
                    messagebox.showwarning("설정", "저장된 설정을 읽지 못해 기본값을 사용합니다.")
        for key, value in data.items():
            if key in self.vars:
                self.vars[key].set(value)

    def _restore_defaults(self):
        for key, value in DEFAULTS.items():
            if key in self.vars:
                self.vars[key].set(value)

    def _preflight(self):
        engine.ensure_adb_connection()
        size = engine.adb("shell", "wm", "size").stdout
        engine.configure_device_size(size)

    def _start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            data = self._collect()
        except (ValueError, tk.TclError):
            messagebox.showerror("설정 오류", "반복 횟수·대기시간·좌표를 확인해 주세요.")
            return
        if not data["dry_run"]:
            okay = messagebox.askyesno(
                "실제 실행 확인",
                "전투 화면이며 현재 퀘스트가 '펫 뽑기 10회'입니까?\n\n"
                "자동화 사용은 게임 약관 위반이나 계정 제재로 이어질 수 있습니다.",
            )
            if not okay:
                return
        self._apply_engine_settings(data)
        engine.STOP = False
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("점검 중" if data["dry_run"] else "실행 중")
        self._append_log("\n--- 새 실행 ---\n")
        self.worker = threading.Thread(target=self._run, args=(data,), daemon=True)
        self.worker.start()

    def _run(self, data):
        writer = QueueWriter(self.messages)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                self._preflight()
                for number in range(1, data["cycles"] + 1):
                    engine.cycle(number, data["dry_run"])
            self.messages.put(("done", "점검 완료" if data["dry_run"] else "실행 완료"))
        except Exception as error:
            self.messages.put(("error", str(error)))

    def _stop(self):
        engine.STOP = True
        self.status.set("정지 요청 중")
        self._append_log("\n정지 요청을 보냈습니다.\n")

    def _poll_messages(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "log":
                    self._append_log(value)
                elif kind == "done":
                    self.status.set(value)
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                elif kind == "error":
                    self.status.set("안전 중단")
                    self._append_log(f"\n안전 중단: {value}\n")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    messagebox.showwarning("안전 중단", value)
        except queue.Empty:
            pass
        self.after(100, self._poll_messages)

    def _close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("종료", "실행을 정지하고 창을 닫을까요?"):
                return
            engine.STOP = True
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
