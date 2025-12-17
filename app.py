from __future__ import annotations

import hashlib
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from adoptme_macro import hotkeys as hotkeys_mod
from adoptme_macro.hotkeys import HotkeyConfig, HotkeyManager
from adoptme_macro.input_backend import build_backend
from adoptme_macro.logging_utils import configure_logging
from adoptme_macro.models import AppState, Dot
from adoptme_macro.overlay import OverlayManager
from adoptme_macro.runner import MacroRunner, RunnerStatus
from adoptme_macro import storage
from adoptme_macro.win_focus import is_foreground_process


TOS_VERSION = 1
DISCORD_INVITE_URL = "https://discord.com/invite/498tyUUaBw"
ACCESS_KEY_SHA256 = "017787675c118bb908c3e4b8bf44ecb26e42beddc5ad2d153ed38c289534d3a2"


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Adopt Me Macro")
        self.geometry("980x680")
        self.minsize(900, 620)

        self._state: AppState = storage.load_config()
        ctk.set_appearance_mode(self._state.settings.theme)
        ctk.set_default_color_theme("blue")

        try:
            s = self._state.settings
            accepted = int(getattr(s, "tos_accepted_version", 0) or 0)
            self._startup_gate_needed = accepted < TOS_VERSION or not bool(getattr(s, "access_key_accepted", False))
        except Exception:
            self._startup_gate_needed = True

        self._ttk_style = ttk.Style(self)
        self._apply_ttk_theme()

        self._logger = configure_logging(self._state.settings)

        self._ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self._closing = False
        self._ui_drain_job = self.after(25, self._drain_ui_queue)

        self._autosave_job = None
        self._msg_job = None
        self._emergency_exit_cancel = threading.Event()

        self._record_dot_win: tk.Toplevel | None = None

        self._last_run_preview = False

        self._overlay = OverlayManager(self, self._state.settings, on_dot_moved=self._on_dot_moved)
        for idx, d in enumerate(self._state.dots):
            self._overlay.add_dot(d, idx)

        self._dots_visible_user = True

        self._runner = MacroRunner(
            backend=build_backend(self._state.settings),
            get_settings=lambda: self._state.settings,
            get_dots=lambda: self._state.dots,
            on_status=lambda st: self._post_ui(lambda st=st: self._on_runner_status(st)),
            on_flash_dot=lambda dot_id: self._post_ui(lambda dot_id=dot_id: self._overlay.flash_dot(dot_id)),
            on_started=lambda preview: self._post_ui(lambda preview=preview: self._on_runner_started(preview)),
            on_stopped=lambda: self._post_ui(self._on_runner_stopped),
        )

        self._hotkeys = HotkeyManager(
            HotkeyConfig(
                start_stop=self._state.settings.start_stop_hotkey,
                pause_resume=self._state.settings.pause_resume_hotkey,
            ),
            on_start_stop=self._on_hotkey_start_stop,
            on_pause_resume=self._on_hotkey_pause_resume,
            on_emergency_stop=self._on_hotkey_emergency_stop,
        )
        self._hotkeys_active = False
        self._hotkeys_failed = False
        if not self._startup_gate_needed:
            self._try_start_hotkeys()

        self._build_ui()
        self._apply_ttk_theme()
        self._sync_ui_from_state()
        self._refresh_dots_table()
        self._update_status(RunnerStatus(state="STOPPED"))

        if self._startup_gate_needed:
            self._set_controls_enabled(False)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._focus_job = self.after(self._state.settings.window_check_interval_ms, self._focus_poll)

        self.after(150, self._maybe_show_first_run_modals)

    def _maybe_show_first_run_modals(self) -> None:
        if self._closing:
            return

        s = self._state.settings
        accepted = int(getattr(s, "tos_accepted_version", 0) or 0)
        if accepted < TOS_VERSION:
            ok = self._show_tos_modal()
            if not ok:
                try:
                    self.after(10, self._on_close)
                except Exception:
                    pass
                return

            try:
                s.tos_accepted_version = TOS_VERSION
                storage.save_config(self._state)
            except Exception:
                pass

        if not bool(getattr(s, "access_key_accepted", False)):
            ok = self._show_access_key_modal()
            if not ok:
                try:
                    self.after(10, self._on_close)
                except Exception:
                    pass
                return

            try:
                s.access_key_accepted = True
                s.discord_prompt_shown = True
                storage.save_config(self._state)
            except Exception:
                pass

        try:
            accepted_now = int(getattr(s, "tos_accepted_version", 0) or 0)
            gate_now = accepted_now < TOS_VERSION or not bool(getattr(s, "access_key_accepted", False))
        except Exception:
            gate_now = True

        self._startup_gate_needed = bool(gate_now)
        if not self._startup_gate_needed:
            self._set_controls_enabled(True)
            self._try_start_hotkeys()

        shown = bool(getattr(s, "discord_prompt_shown", False))
        if not shown:
            self._show_discord_prompt()

    def _show_tos_modal(self) -> bool:
        if self._closing:
            return False

        win = ctk.CTkToplevel(self)
        win.title("Terms of Service")
        win.geometry("720x520")
        win.resizable(False, False)
        try:
            win.transient(self)
            win.grab_set()
        except Exception:
            pass

        decision = {"ok": False}

        def decline() -> None:
            decision["ok"] = False
            try:
                win.destroy()
            except Exception:
                pass

        def accept() -> None:
            decision["ok"] = True
            try:
                win.destroy()
            except Exception:
                pass

        try:
            win.protocol("WM_DELETE_WINDOW", decline)
        except Exception:
            pass

        title = ctk.CTkLabel(win, text="Terms of Service", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(anchor="w", padx=18, pady=(16, 8))

        body = (
            "By using this macro, you agree to the following rules:\n\n"
            "1) You use this software at your own risk.\n"
            "2) You are responsible for how you use this software and any consequences.\n"
            "3) Do not use this software to harm others or violate platform rules.\n\n"
            "Ownership / Credits:\n"
            "- This project is owned by the developer.\n"
            "- If you share or redistribute this software, you must provide proper credit.\n"
            "- If you share it without credit, the owner may file a DMCA takedown.\n\n"
            "Click 'I Agree' to continue, or 'Decline' to exit."
        )

        txt = tk.Text(win, wrap="word", height=18, padx=12, pady=12)
        txt.insert("1.0", body)
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkButton(btns, text="Decline", fg_color="#9B2C2C", hover_color="#7A2222", command=decline).pack(
            side="left"
        )
        ctk.CTkButton(btns, text="I Agree", command=accept).pack(side="right")

        try:
            self.wait_window(win)
        except Exception:
            return False

        return bool(decision["ok"])

    def _show_access_key_modal(self) -> bool:
        if self._closing:
            return False

        win = ctk.CTkToplevel(self)
        win.title("Access Key Required")
        win.geometry("560x320")
        win.resizable(False, False)
        try:
            win.transient(self)
            win.grab_set()
        except Exception:
            pass

        decision = {"ok": False}

        def decline() -> None:
            decision["ok"] = False
            try:
                win.destroy()
            except Exception:
                pass

        def join_discord() -> None:
            try:
                webbrowser.open(DISCORD_INVITE_URL)
            except Exception:
                pass

        key_var = tk.StringVar(value="")
        err_var = tk.StringVar(value="")

        def submit() -> None:
            raw = (key_var.get() or "").strip()
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if digest == ACCESS_KEY_SHA256:
                decision["ok"] = True
                try:
                    win.destroy()
                except Exception:
                    pass
                return
            err_var.set("Invalid key. Please join the Discord and try again.")

        try:
            win.protocol("WM_DELETE_WINDOW", decline)
        except Exception:
            pass

        ctk.CTkLabel(win, text="Access Key Required", font=ctk.CTkFont(size=18, weight="bold")).pack(
            anchor="w", padx=18, pady=(18, 8)
        )
        ctk.CTkLabel(
            win,
            text="To use this macro, you need an access key.\nYou must join the Discord server to get the key.",
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 10))

        ctk.CTkButton(win, text="Join Discord Server", command=join_discord).pack(anchor="w", padx=18, pady=(0, 8))
        ctk.CTkLabel(win, text=DISCORD_INVITE_URL).pack(anchor="w", padx=18, pady=(0, 14))

        ctk.CTkLabel(win, text="Paste your key below:").pack(anchor="w", padx=18)
        entry = ctk.CTkEntry(win, textvariable=key_var, width=520, placeholder_text="Paste key here")
        entry.pack(anchor="w", padx=18, pady=(6, 6))

        err_lbl = ctk.CTkLabel(win, textvariable=err_var, text_color="#D9534F")
        err_lbl.pack(anchor="w", padx=18, pady=(0, 10))

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(btns, text="Exit", fg_color="#9B2C2C", hover_color="#7A2222", command=decline).pack(
            side="left"
        )
        ctk.CTkButton(btns, text="Submit", command=submit).pack(side="right")

        try:
            entry.focus_set()
        except Exception:
            pass

        try:
            self.wait_window(win)
        except Exception:
            return False

        return bool(decision["ok"])

    def _show_discord_prompt(self) -> None:
        if self._closing:
            return

        s = self._state.settings

        win = ctk.CTkToplevel(self)
        win.title("Join our Discord")
        win.geometry("520x240")
        win.resizable(False, False)
        try:
            win.transient(self)
            win.grab_set()
        except Exception:
            pass

        def mark_shown_and_close() -> None:
            try:
                s.discord_prompt_shown = True
                storage.save_config(self._state)
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass

        def join() -> None:
            try:
                webbrowser.open(DISCORD_INVITE_URL)
            except Exception:
                pass
            mark_shown_and_close()

        try:
            win.protocol("WM_DELETE_WINDOW", mark_shown_and_close)
        except Exception:
            pass

        ctk.CTkLabel(win, text="Want updates and support?", font=ctk.CTkFont(size=16, weight="bold")).pack(
            anchor="w", padx=18, pady=(18, 8)
        )
        ctk.CTkLabel(
            win,
            text="Join the Discord server for help, updates, and new features.",
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 8))

        ctk.CTkLabel(win, text=DISCORD_INVITE_URL).pack(anchor="w", padx=18, pady=(0, 18))

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(btns, text="No thanks", command=mark_shown_and_close).pack(side="left")
        ctk.CTkButton(btns, text="Join", command=join).pack(side="right")

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, corner_radius=16, border_width=1)
        top.grid(row=0, column=0, padx=14, pady=(14, 10), sticky="ew")

        top.grid_columnconfigure(0, weight=1)
        top.grid_columnconfigure(1, weight=0)

        info = ctk.CTkFrame(top, fg_color="transparent")
        info.grid(row=0, column=0, padx=14, pady=12, sticky="w")
        info.grid_columnconfigure(2, weight=1)

        title_lbl = ctk.CTkLabel(info, text="Adopt Me Macro", font=ctk.CTkFont(size=18, weight="bold"))
        title_lbl.grid(row=0, column=0, padx=(0, 12), pady=(0, 2), sticky="w")

        self._status_var = tk.StringVar(value="Status: STOPPED")
        self._status_pill = ctk.CTkLabel(
            info,
            textvariable=self._status_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=12,
            padx=12,
            pady=6,
        )
        self._status_pill.grid(row=0, column=1, pady=(0, 2), sticky="w")

        self._msg_var = tk.StringVar(value="")
        msg_lbl = ctk.CTkLabel(info, textvariable=self._msg_var)
        msg_lbl.grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="w")

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.grid(row=0, column=1, padx=14, pady=12, sticky="e")

        self._start_btn = ctk.CTkButton(btns, text="Start / Stop", width=130, corner_radius=10, command=self._on_start_stop_clicked)
        self._start_btn.grid(row=0, column=0, padx=(0, 8))

        self._pause_btn = ctk.CTkButton(btns, text="Pause / Resume", width=140, corner_radius=10, command=self._on_pause_resume_clicked)
        self._pause_btn.grid(row=0, column=1, padx=(0, 8))

        self._test_btn = ctk.CTkButton(btns, text="Test Run", width=110, corner_radius=10, command=self._on_test_run_clicked)
        self._test_btn.grid(row=0, column=2)

        tab_selected = "#2A5BD7" if self._is_dark() else "#2A5BD7"
        tab_unselected = "#2B2B2B" if self._is_dark() else "#E9E9E9"
        tab_unselected_hover = "#333333" if self._is_dark() else "#DEDEDE"

        self._tabs = ctk.CTkTabview(
            self,
            corner_radius=16,
            segmented_button_selected_color=tab_selected,
            segmented_button_selected_hover_color=tab_selected,
            segmented_button_unselected_color=tab_unselected,
            segmented_button_unselected_hover_color=tab_unselected_hover,
        )
        self._tabs.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")

        self._tab_dots = self._tabs.add("Dots")
        self._tab_hotkeys = self._tabs.add("Hotkeys")
        self._tab_perf = self._tabs.add("Performance")
        self._tab_profiles = self._tabs.add("Profiles")
        self._tab_post = self._tabs.add("Post Action")
        self._tab_advanced = self._tabs.add("Advanced")
        self._tab_visual = self._tabs.add("Visual")
        self._tab_roblox = self._tabs.add("Roblox")

        self._build_dots_tab()
        self._build_hotkeys_tab()
        self._build_perf_tab()
        self._build_profiles_tab()
        self._build_post_tab()
        self._build_advanced_tab()
        self._build_visual_tab()
        self._build_roblox_tab()

    def _build_dots_tab(self) -> None:
        self._tab_dots.grid_columnconfigure(0, weight=1)
        self._tab_dots.grid_rowconfigure(2, weight=1)

        bar = ctk.CTkFrame(self._tab_dots, corner_radius=12)
        bar.grid(row=0, column=0, padx=12, pady=12, sticky="ew")

        add_btn = ctk.CTkButton(bar, text="Add Dot", command=self._add_dot)
        add_btn.grid(row=0, column=0, padx=10, pady=10)

        rec_btn = ctk.CTkButton(bar, text="Record Dot", command=self._start_record_dot_mode)
        rec_btn.grid(row=0, column=1, padx=10, pady=10)

        rem_btn = ctk.CTkButton(bar, text="Remove Selected", command=self._remove_selected_dot)
        rem_btn.grid(row=0, column=2, padx=10, pady=10)

        clear_btn = ctk.CTkButton(bar, text="Clear All", command=self._clear_dots)
        clear_btn.grid(row=0, column=3, padx=10, pady=10)

        toggle_btn = ctk.CTkButton(bar, text="Toggle Dots", command=self._toggle_dots)
        toggle_btn.grid(row=0, column=4, padx=10, pady=10)

        reset_btn = ctk.CTkButton(bar, text="Reset Positions", command=self._reset_positions)
        reset_btn.grid(row=0, column=5, padx=10, pady=10)

        self._dot_type_var = tk.StringVar(value="click")
        dot_type = ctk.CTkOptionMenu(bar, values=["click", "double", "hold", "key"], variable=self._dot_type_var)
        dot_type.grid(row=0, column=6, padx=10, pady=10)

        self._dot_key_var = tk.StringVar(value="{E}")
        self._add_key_entry = ctk.CTkEntry(bar, textvariable=self._dot_key_var, width=120)
        self._add_key_entry.grid(row=0, column=7, padx=10, pady=10)

        self._dot_type_var.trace_add("write", lambda *_: self._sync_add_dot_editor_state())

        edit = ctk.CTkFrame(self._tab_dots, corner_radius=12)
        edit.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        edit.grid_columnconfigure(0, weight=1)
        edit.grid_columnconfigure(1, weight=0)

        self._sel_dot_name = tk.StringVar(value="")
        self._sel_dot_type = tk.StringVar(value="click")
        self._sel_dot_key = tk.StringVar(value="{E}")
        self._sel_dot_delay = tk.StringVar(value="")
        self._universal_delay = tk.StringVar(value="")

        header = ctk.CTkFrame(edit, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 0), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="Dot Editor", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(actions, text="Apply", width=90, corner_radius=10, command=self._apply_selected_dot).grid(
            row=0, column=0, padx=(0, 8)
        )
        ctk.CTkButton(actions, text="Copy", width=90, corner_radius=10, command=self._copy_selected_dot).grid(
            row=0, column=1
        )

        fields = ctk.CTkFrame(edit, fg_color="transparent")
        fields.grid(row=1, column=0, padx=12, pady=(8, 12), sticky="ew")
        fields.grid_columnconfigure(0, weight=3)
        fields.grid_columnconfigure(1, weight=1)
        fields.grid_columnconfigure(2, weight=1)
        fields.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(fields, text="Name").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(fields, text="Type").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(fields, text="Key").grid(row=0, column=2, sticky="w")
        ctk.CTkLabel(fields, text="Delay Override (ms)").grid(row=0, column=3, sticky="w")

        ctk.CTkEntry(fields, textvariable=self._sel_dot_name, placeholder_text="Dot name").grid(
            row=1, column=0, padx=(0, 10), pady=(6, 0), sticky="ew"
        )
        ctk.CTkOptionMenu(fields, values=["click", "double", "hold", "key"], variable=self._sel_dot_type).grid(
            row=1, column=1, padx=(0, 10), pady=(6, 0), sticky="ew"
        )
        self._sel_key_entry = ctk.CTkEntry(fields, textvariable=self._sel_dot_key, placeholder_text="{E}")
        self._sel_key_entry.grid(row=1, column=2, padx=(0, 10), pady=(6, 0), sticky="ew")
        ctk.CTkEntry(fields, textvariable=self._sel_dot_delay, placeholder_text="(blank = default)").grid(
            row=1, column=3, pady=(6, 0), sticky="ew"
        )

        bulk = ctk.CTkFrame(edit, fg_color="transparent")
        bulk.grid(row=1, column=1, padx=(0, 12), pady=(8, 12), sticky="ne")
        ctk.CTkLabel(bulk, text="All dots delay (seconds)").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(bulk, textvariable=self._universal_delay, width=140, placeholder_text="seconds").grid(
            row=1, column=0, pady=(6, 8), sticky="ew"
        )
        ctk.CTkButton(bulk, text="Set All", width=140, corner_radius=10, command=self._set_universal_delay).grid(
            row=2, column=0, sticky="ew"
        )

        self._sel_dot_type.trace_add("write", lambda *_: self._sync_selected_dot_editor_state())
        self._sync_add_dot_editor_state()
        self._sync_selected_dot_editor_state()

        table_frame = ctk.CTkFrame(self._tab_dots, corner_radius=12)
        table_frame.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            table_frame,
            columns=("name", "x", "y", "type", "delay"),
            show="headings",
            selectmode="browse",
        )
        for col, title, w in [
            ("name", "Dot", 180),
            ("x", "X", 120),
            ("y", "Y", 120),
            ("type", "Type", 120),
            ("delay", "Delay(ms)", 120),
        ]:
            self._tree.heading(col, text=title)
            self._tree.column(col, width=w, anchor=("w" if col == "name" else "center"))

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._on_dot_selected())

        self._tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        vsb.grid(row=0, column=1, sticky="ns", pady=10, padx=(0, 10))

        self._apply_ttk_theme()

    def _sync_add_dot_editor_state(self) -> None:
        try:
            is_key = self._dot_type_var.get() == "key"
            self._add_key_entry.configure(state=("normal" if is_key else "disabled"))
        except Exception:
            return

    def _sync_selected_dot_editor_state(self) -> None:
        try:
            is_key = self._sel_dot_type.get() == "key"
            self._sel_key_entry.configure(state=("normal" if is_key else "disabled"))
        except Exception:
            return

    def _parse_hotkey_for_picker(self, hk: str) -> tuple[bool, bool, bool, str]:
        try:
            norm = hotkeys_mod._normalize_hotkey(hk)
        except Exception:
            norm = ""
        s = norm.replace(" ", "").lower()
        tokens = [t for t in s.split("+") if t]
        ctrl = "<ctrl>" in tokens
        shift = "<shift>" in tokens
        alt = "<alt>" in tokens
        key = ""
        for t in tokens:
            if t in ("<ctrl>", "<shift>", "<alt>"):
                continue
            if t.startswith("<") and t.endswith(">"):
                t = t[1:-1]
            key = t
        if key.startswith("f") and key[1:].isdigit():
            key = key.upper()
        elif key == "space":
            key = "Space"
        elif key == "enter":
            key = "Enter"
        elif key == "tab":
            key = "Tab"
        elif key == "esc":
            key = "Esc"
        else:
            key = key.upper() if len(key) == 1 else key
        return ctrl, shift, alt, key

    def _sync_hotkey_picker_from_state(self) -> None:
        s = self._state.settings
        if hasattr(self, "_hk_st_ctrl") and hasattr(self, "_hk_st_key"):
            c, sh, a, k = self._parse_hotkey_for_picker(s.start_stop_hotkey)
            try:
                self._hk_st_ctrl.set(bool(c))
                self._hk_st_shift.set(bool(sh))
                self._hk_st_alt.set(bool(a))
                if k:
                    self._hk_st_key.set(k)
            except Exception:
                pass

        if hasattr(self, "_hk_pr_ctrl") and hasattr(self, "_hk_pr_key"):
            c, sh, a, k = self._parse_hotkey_for_picker(s.pause_resume_hotkey)
            try:
                self._hk_pr_ctrl.set(bool(c))
                self._hk_pr_shift.set(bool(sh))
                self._hk_pr_alt.set(bool(a))
                if k:
                    self._hk_pr_key.set(k)
            except Exception:
                pass

    def _build_hotkeys_tab(self) -> None:
        frame = ctk.CTkFrame(self._tab_hotkeys, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        self._hk_start_stop = tk.StringVar(value=self._state.settings.start_stop_hotkey)
        self._hk_pause_resume = tk.StringVar(value=self._state.settings.pause_resume_hotkey)

        frame.grid_columnconfigure(0, weight=0)
        frame.grid_columnconfigure(1, weight=1)

        keys = [
            *[f"F{i}" for i in range(1, 13)],
            *list("1234567890"),
            *list("QWERTYUIOP"),
            *list("ASDFGHJKL"),
            *list("ZXCVBNM"),
            "Space",
            "Enter",
            "Tab",
            "Esc",
        ]

        def build_hotkey(mod_ctrl: tk.BooleanVar, mod_shift: tk.BooleanVar, mod_alt: tk.BooleanVar, key_var: tk.StringVar) -> str:
            parts: list[str] = []
            if bool(mod_ctrl.get()):
                parts.append("ctrl")
            if bool(mod_shift.get()):
                parts.append("shift")
            if bool(mod_alt.get()):
                parts.append("alt")

            k = (key_var.get() or "").strip()
            if k.upper().startswith("F") and k[1:].isdigit():
                parts.append(k.lower())
            elif k == "Space":
                parts.append("space")
            elif k == "Enter":
                parts.append("enter")
            elif k == "Tab":
                parts.append("tab")
            elif k == "Esc":
                parts.append("esc")
            elif len(k) == 1:
                parts.append(k.lower())
            else:
                parts.append(k.lower())

            return "+".join([p for p in parts if p])

        def parse_hotkey(hk: str) -> tuple[bool, bool, bool, str]:
            try:
                norm = hotkeys_mod._normalize_hotkey(hk)
            except Exception:
                norm = ""
            s = norm.replace(" ", "").lower()
            tokens = [t for t in s.split("+") if t]
            ctrl = "<ctrl>" in tokens
            shift = "<shift>" in tokens
            alt = "<alt>" in tokens
            key = ""
            for t in tokens:
                if t in ("<ctrl>", "<shift>", "<alt>"):
                    continue
                if t.startswith("<") and t.endswith(">"):
                    t = t[1:-1]
                key = t
            if key.startswith("f") and key[1:].isdigit():
                key = key.upper()
            elif key == "space":
                key = "Space"
            elif key == "enter":
                key = "Enter"
            elif key == "tab":
                key = "Tab"
            elif key == "esc":
                key = "Esc"
            else:
                key = key.upper() if len(key) == 1 else key
            return ctrl, shift, alt, key

        # Start/Stop
        ctk.CTkLabel(frame, text="Start/Stop Hotkey").grid(row=0, column=0, padx=12, pady=(18, 6), sticky="w")
        st_wrap = ctk.CTkFrame(frame, fg_color="transparent")
        st_wrap.grid(row=0, column=1, padx=12, pady=(18, 6), sticky="ew")

        self._hk_st_ctrl = tk.BooleanVar(value=False)
        self._hk_st_shift = tk.BooleanVar(value=False)
        self._hk_st_alt = tk.BooleanVar(value=False)
        self._hk_st_key = tk.StringVar(value="F6")

        c, s, a, k = parse_hotkey(self._hk_start_stop.get())
        self._hk_st_ctrl.set(c)
        self._hk_st_shift.set(s)
        self._hk_st_alt.set(a)
        if k:
            self._hk_st_key.set(k)

        ctk.CTkCheckBox(st_wrap, text="Ctrl", variable=self._hk_st_ctrl).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkCheckBox(st_wrap, text="Shift", variable=self._hk_st_shift).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkCheckBox(st_wrap, text="Alt", variable=self._hk_st_alt).grid(row=0, column=2, padx=(0, 10))
        ctk.CTkOptionMenu(st_wrap, values=keys, variable=self._hk_st_key, width=140).grid(row=0, column=3)
        st_preview = ctk.CTkLabel(st_wrap, textvariable=self._hk_start_stop)
        st_preview.grid(row=0, column=4, padx=(12, 0), sticky="w")

        # Pause/Resume
        ctk.CTkLabel(frame, text="Pause/Resume Hotkey").grid(row=1, column=0, padx=12, pady=6, sticky="w")
        pr_wrap = ctk.CTkFrame(frame, fg_color="transparent")
        pr_wrap.grid(row=1, column=1, padx=12, pady=6, sticky="ew")

        self._hk_pr_ctrl = tk.BooleanVar(value=False)
        self._hk_pr_shift = tk.BooleanVar(value=False)
        self._hk_pr_alt = tk.BooleanVar(value=False)
        self._hk_pr_key = tk.StringVar(value="F7")

        c, s, a, k = parse_hotkey(self._hk_pause_resume.get())
        self._hk_pr_ctrl.set(c)
        self._hk_pr_shift.set(s)
        self._hk_pr_alt.set(a)
        if k:
            self._hk_pr_key.set(k)

        ctk.CTkCheckBox(pr_wrap, text="Ctrl", variable=self._hk_pr_ctrl).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkCheckBox(pr_wrap, text="Shift", variable=self._hk_pr_shift).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkCheckBox(pr_wrap, text="Alt", variable=self._hk_pr_alt).grid(row=0, column=2, padx=(0, 10))
        ctk.CTkOptionMenu(pr_wrap, values=keys, variable=self._hk_pr_key, width=140).grid(row=0, column=3)
        pr_preview = ctk.CTkLabel(pr_wrap, textvariable=self._hk_pause_resume)
        pr_preview.grid(row=0, column=4, padx=(12, 0), sticky="w")

        def sync_start_stop(*_a) -> None:
            self._hk_start_stop.set(build_hotkey(self._hk_st_ctrl, self._hk_st_shift, self._hk_st_alt, self._hk_st_key))

        def sync_pause_resume(*_a) -> None:
            self._hk_pause_resume.set(build_hotkey(self._hk_pr_ctrl, self._hk_pr_shift, self._hk_pr_alt, self._hk_pr_key))

        for v in (self._hk_st_ctrl, self._hk_st_shift, self._hk_st_alt, self._hk_st_key):
            v.trace_add("write", lambda *_: sync_start_stop())
        for v in (self._hk_pr_ctrl, self._hk_pr_shift, self._hk_pr_alt, self._hk_pr_key):
            v.trace_add("write", lambda *_: sync_pause_resume())

        sync_start_stop()
        sync_pause_resume()

        apply_btn = ctk.CTkButton(frame, text="Apply Hotkeys", command=self._apply_hotkeys)
        apply_btn.grid(row=2, column=0, columnspan=2, padx=12, pady=18, sticky="w")

        if getattr(self, "_hotkeys_failed", False):
            self._set_message("Hotkeys failed to start. Buttons still work.")

    def _build_perf_tab(self) -> None:
        frame = ctk.CTkFrame(self._tab_perf, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        s = self._state.settings

        self._loop_delay = tk.IntVar(value=int(s.loop_delay_ms))
        self._click_delay = tk.IntVar(value=int(s.click_delay_ms))
        self._loop_count = tk.IntVar(value=int(s.loop_count))
        self._max_loops = tk.IntVar(value=int(s.max_loops))
        self._mouse_speed = tk.IntVar(value=int(s.mouse_speed))
        self._click_speed = tk.IntVar(value=int(s.click_speed_ms))
        self._randomize = tk.BooleanVar(value=bool(s.randomize_order))
        self._random_delay = tk.IntVar(value=int(s.random_delay_pct))
        self._min_on_start = tk.BooleanVar(value=bool(s.minimize_on_start))
        self._restore_on_stop = tk.BooleanVar(value=bool(s.restore_on_stop))

        row = 0
        for label, var in [
            ("Loop Delay (ms)", self._loop_delay),
            ("Click Delay (ms)", self._click_delay),
            ("Loop Count (0 = infinite)", self._loop_count),
            ("Max Loops (0 = no cap)", self._max_loops),
            ("Mouse Speed", self._mouse_speed),
            ("Click Speed (ms)", self._click_speed),
            ("Random Delay %", self._random_delay),
        ]:
            ctk.CTkLabel(frame, text=label).grid(row=row, column=0, padx=12, pady=8, sticky="w")
            ctk.CTkEntry(frame, textvariable=var, width=180).grid(row=row, column=1, padx=12, pady=8, sticky="w")
            row += 1

        ctk.CTkCheckBox(frame, text="Randomize Order", variable=self._randomize).grid(row=row, column=0, padx=12, pady=8, sticky="w")
        row += 1
        ctk.CTkCheckBox(frame, text="Minimize on Start", variable=self._min_on_start).grid(row=row, column=0, padx=12, pady=8, sticky="w")
        row += 1
        ctk.CTkCheckBox(frame, text="Restore on Stop", variable=self._restore_on_stop).grid(row=row, column=0, padx=12, pady=8, sticky="w")
        row += 1

        save_btn = ctk.CTkButton(frame, text="Apply Performance", command=self._apply_performance)
        save_btn.grid(row=row, column=0, columnspan=2, padx=12, pady=18, sticky="w")

    def _build_profiles_tab(self) -> None:
        frame = ctk.CTkFrame(self._tab_profiles, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(frame, corner_radius=12)
        bar.grid(row=0, column=0, padx=12, pady=12, sticky="ew")

        self._profile_name = tk.StringVar(value="")
        ctk.CTkEntry(bar, textvariable=self._profile_name, width=220, placeholder_text="Profile name").grid(
            row=0, column=0, padx=10, pady=10
        )
        ctk.CTkButton(bar, text="Save", command=self._save_profile).grid(row=0, column=1, padx=10, pady=10)
        ctk.CTkButton(bar, text="Load", command=self._load_selected_profile).grid(row=0, column=2, padx=10, pady=10)
        ctk.CTkButton(bar, text="Delete", command=self._delete_selected_profile).grid(row=0, column=3, padx=10, pady=10)
        ctk.CTkButton(bar, text="Refresh", command=self._refresh_profiles).grid(row=0, column=4, padx=10, pady=10)

        self._profiles_list = ttk.Treeview(frame, columns=("name", "modified"), show="headings", selectmode="browse")
        self._profiles_list.heading("name", text="Profile")
        self._profiles_list.heading("modified", text="Modified")
        self._profiles_list.column("name", width=240, anchor="w")
        self._profiles_list.column("modified", width=240, anchor="w")
        self._profiles_list.grid(row=1, column=0, padx=24, pady=(0, 24), sticky="nsew")

        self._refresh_profiles()

    def _build_post_tab(self) -> None:
        frame = ctk.CTkFrame(self._tab_post, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        s = self._state.settings
        self._post_action = tk.StringVar(value=str(getattr(s, "post_action", "none")))

        ctk.CTkLabel(frame, text="Post Action (when macro stops)").pack(anchor="w", padx=14, pady=(18, 8))
        ctk.CTkOptionMenu(frame, values=["none", "beep", "message", "close"], variable=self._post_action, width=220).pack(
            anchor="w", padx=14, pady=8
        )
        ctk.CTkButton(frame, text="Apply Post Action", command=self._apply_post_action).pack(anchor="w", padx=14, pady=18)

    def _build_advanced_tab(self) -> None:
        frame = ctk.CTkFrame(self._tab_advanced, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        s = self._state.settings
        self._pause_on_focus = tk.BooleanVar(value=bool(s.pause_on_window_change))
        self._auto_resume = tk.BooleanVar(value=bool(s.auto_resume_on_focus))
        self._debug_mode = tk.BooleanVar(value=bool(s.debug_mode))
        self._enable_logs = tk.BooleanVar(value=bool(s.enable_logs))
        self._autosave = tk.BooleanVar(value=bool(s.autosave_config))

        ctk.CTkCheckBox(frame, text="Pause on Window Change", variable=self._pause_on_focus).pack(anchor="w", padx=14, pady=(18, 8))
        ctk.CTkCheckBox(frame, text="Auto Resume on Roblox Focus", variable=self._auto_resume).pack(anchor="w", padx=14, pady=8)
        ctk.CTkCheckBox(frame, text="Enable Debug Mode", variable=self._debug_mode).pack(anchor="w", padx=14, pady=8)
        ctk.CTkCheckBox(frame, text="Enable Logs", variable=self._enable_logs).pack(anchor="w", padx=14, pady=8)
        ctk.CTkCheckBox(frame, text="Auto-save Configuration", variable=self._autosave).pack(anchor="w", padx=14, pady=8)

        ctk.CTkButton(frame, text="Apply Advanced", command=self._apply_advanced).pack(anchor="w", padx=14, pady=18)

    def _build_visual_tab(self) -> None:
        frame = ctk.CTkFrame(self._tab_visual, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        s = self._state.settings

        self._opacity = tk.DoubleVar(value=float(s.overlay_opacity))
        self._show_numbers = tk.BooleanVar(value=bool(s.show_dot_numbers))
        self._show_coords = tk.BooleanVar(value=bool(s.show_coordinates))
        self._lock_dots = tk.BooleanVar(value=bool(s.lock_dots))
        self._theme = tk.StringVar(value=str(s.theme))

        ctk.CTkLabel(frame, text="Overlay Opacity").pack(anchor="w", padx=14, pady=(18, 6))
        slider = ctk.CTkSlider(frame, from_=0.2, to=1.0, number_of_steps=80, variable=self._opacity, command=lambda _: self._apply_visual_live())
        slider.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkCheckBox(frame, text="Show Dot Numbers", variable=self._show_numbers, command=self._apply_visual_live).pack(anchor="w", padx=14, pady=8)

        ctk.CTkCheckBox(frame, text="Show Coordinates", variable=self._show_coords, command=self._apply_visual_live).pack(anchor="w", padx=14, pady=8)

        ctk.CTkCheckBox(frame, text="Lock Dots (click-through)", variable=self._lock_dots, command=self._apply_visual_live).pack(anchor="w", padx=14, pady=8)

        ctk.CTkLabel(frame, text="Theme").pack(anchor="w", padx=14, pady=(14, 6))
        ctk.CTkOptionMenu(frame, values=["dark", "light"], variable=self._theme, command=lambda _: self._apply_visual()).pack(anchor="w", padx=14, pady=(0, 14))

        ctk.CTkButton(frame, text="Apply Visual", command=self._apply_visual).pack(anchor="w", padx=14, pady=18)

    def _build_roblox_tab(self) -> None:
        frame = ctk.CTkFrame(self._tab_roblox, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        s = self._state.settings
        self._roblox_mode = tk.BooleanVar(value=bool(s.enable_roblox_mode))
        self._backend_var = tk.StringVar(value=str(s.click_backend))

        ctk.CTkCheckBox(frame, text="Enable Roblox Mode", variable=self._roblox_mode).pack(anchor="w", padx=14, pady=(18, 8))
        ctk.CTkLabel(frame, text="Click Backend").pack(anchor="w", padx=14, pady=(12, 6))
        ctk.CTkOptionMenu(frame, values=["autoit", "win32"], variable=self._backend_var).pack(anchor="w", padx=14, pady=(0, 12))

        btns = ctk.CTkFrame(frame, fg_color="transparent")
        btns.pack(anchor="w", padx=14, pady=10)

        ctk.CTkButton(btns, text="Apply Roblox", command=self._apply_roblox).grid(row=0, column=0, padx=(0, 10))
        ctk.CTkButton(btns, text="Check AutoIt", command=self._check_autoit).grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(btns, text="Install AutoIt", command=self._install_autoit).grid(row=0, column=2)

        self._roblox_status = tk.StringVar(value="")
        ctk.CTkLabel(frame, textvariable=self._roblox_status).pack(anchor="w", padx=14, pady=14)

    def _schedule_autosave(self) -> None:
        if not self._state.settings.autosave_config:
            return
        if self._closing:
            return
        self._cancel_job("_autosave_job")
        self._autosave_job = self.after(350, self._save_config)

    def _save_config(self) -> None:
        try:
            storage.save_config(self._state)
        finally:
            self._autosave_job = None

    def _emergency_stop(self) -> None:
        if self._closing:
            return

        self._emergency_exit_cancel = threading.Event()

        def kill_later() -> None:
            time.sleep(1.5)
            if self._emergency_exit_cancel.is_set():
                return
            os._exit(0)

        try:
            threading.Thread(target=kill_later, daemon=True).start()
        except Exception:
            pass

        try:
            self._set_message("Emergency stop", timeout_ms=1500)
        except Exception:
            pass

        try:
            self._on_close()
            self._emergency_exit_cancel.set()
        except Exception:
            os._exit(0)

    def _set_message(self, msg: str, timeout_ms: int = 4500) -> None:
        if not hasattr(self, "_msg_var"):
            return
        self._cancel_job("_msg_job")
        self._msg_var.set(msg)
        if timeout_ms > 0:
            try:
                self._msg_job = self.after(timeout_ms, lambda: (not self._closing) and self._msg_var.set(""))
            except Exception:
                pass

    def _safe_int(self, var, default: int) -> int:
        try:
            return int(var.get())
        except Exception:
            return int(default)

    def _cancel_job(self, attr: str) -> None:
        job = getattr(self, attr, None)
        if job is None:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass
        try:
            setattr(self, attr, None)
        except Exception:
            pass

    def _try_start_hotkeys(self) -> None:
        if self._closing:
            return
        if getattr(self, "_startup_gate_needed", False):
            return
        if getattr(self, "_hotkeys_active", False):
            return

        try:
            self._hotkeys.start()
        except Exception:
            try:
                self._logger.exception("Failed to start hotkeys")
            except Exception:
                pass
            self._hotkeys_failed = True
            self._hotkeys_active = False
            if hasattr(self, "_msg_var"):
                try:
                    self._set_message("Hotkeys failed to start. Buttons still work.")
                except Exception:
                    pass
        else:
            self._hotkeys_failed = False
            self._hotkeys_active = True

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for attr in ("_start_btn", "_pause_btn", "_test_btn"):
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            try:
                btn.configure(state=state)
            except Exception:
                pass

    def _post_ui(self, fn: Callable[[], None]) -> None:
        if self._closing:
            return
        self._ui_queue.put(fn)

    def _on_hotkey_start_stop(self) -> None:
        if getattr(self, "_startup_gate_needed", False):
            self._post_ui(lambda: self._set_message("Please enter an access key to continue", timeout_ms=1800))
            return
        try:
            try:
                self._logger.info("Hotkey: start/stop")
            except Exception:
                pass
            self._runner.toggle_start_stop()
        except Exception:
            try:
                self._logger.exception("Hotkey start/stop handler failed")
            except Exception:
                pass
        self._post_ui(lambda: self._set_message("Hotkey: Start/Stop", timeout_ms=1200))

    def _on_hotkey_pause_resume(self) -> None:
        if getattr(self, "_startup_gate_needed", False):
            self._post_ui(lambda: self._set_message("Please enter an access key to continue", timeout_ms=1800))
            return
        try:
            try:
                self._logger.info("Hotkey: pause/resume")
            except Exception:
                pass
            self._runner.toggle_pause_resume()
        except Exception:
            try:
                self._logger.exception("Hotkey pause/resume handler failed")
            except Exception:
                pass
        self._post_ui(lambda: self._set_message("Hotkey: Pause/Resume", timeout_ms=1200))

    def _on_hotkey_emergency_stop(self) -> None:
        try:
            try:
                self._logger.warning("Hotkey: emergency stop")
            except Exception:
                pass
            self._post_ui(self._emergency_stop)
        except Exception:
            try:
                self._logger.exception("Hotkey emergency stop handler failed")
            except Exception:
                pass

    def _drain_ui_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                try:
                    fn = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn()
                except Exception:
                    try:
                        self._logger.exception("UI task failed")
                    except Exception:
                        pass
        finally:
            if self._closing:
                return
            try:
                if not self.winfo_exists():
                    return
            except Exception:
                return
            self._ui_drain_job = self.after(25, self._drain_ui_queue)

    def _rebuild_runner(self) -> None:
        try:
            self._runner.stop()
        except Exception:
            pass

        s = self._state.settings
        self._runner = MacroRunner(
            backend=build_backend(s),
            get_settings=lambda: self._state.settings,
            get_dots=lambda: self._state.dots,
            on_status=lambda st: self._post_ui(lambda st=st: self._on_runner_status(st)),
            on_flash_dot=lambda dot_id: self._post_ui(lambda dot_id=dot_id: self._overlay.flash_dot(dot_id)),
            on_started=lambda preview: self._post_ui(lambda preview=preview: self._on_runner_started(preview)),
            on_stopped=lambda: self._post_ui(self._on_runner_stopped),
        )

    def _sync_ui_from_state(self) -> None:
        s = self._state.settings

        if hasattr(self, "_hk_start_stop"):
            self._hk_start_stop.set(s.start_stop_hotkey)
        if hasattr(self, "_hk_pause_resume"):
            self._hk_pause_resume.set(s.pause_resume_hotkey)

        self._sync_hotkey_picker_from_state()

        if hasattr(self, "_loop_delay"):
            self._loop_delay.set(int(s.loop_delay_ms))
        if hasattr(self, "_click_delay"):
            self._click_delay.set(int(s.click_delay_ms))
        if hasattr(self, "_loop_count"):
            self._loop_count.set(int(s.loop_count))
        if hasattr(self, "_max_loops"):
            self._max_loops.set(int(s.max_loops))
        if hasattr(self, "_mouse_speed"):
            self._mouse_speed.set(int(s.mouse_speed))
        if hasattr(self, "_click_speed"):
            self._click_speed.set(int(s.click_speed_ms))
        if hasattr(self, "_randomize"):
            self._randomize.set(bool(s.randomize_order))
        if hasattr(self, "_random_delay"):
            self._random_delay.set(int(s.random_delay_pct))
        if hasattr(self, "_min_on_start"):
            self._min_on_start.set(bool(s.minimize_on_start))
        if hasattr(self, "_restore_on_stop"):
            self._restore_on_stop.set(bool(s.restore_on_stop))

        if hasattr(self, "_pause_on_focus"):
            self._pause_on_focus.set(bool(s.pause_on_window_change))
        if hasattr(self, "_auto_resume"):
            self._auto_resume.set(bool(s.auto_resume_on_focus))
        if hasattr(self, "_debug_mode"):
            self._debug_mode.set(bool(s.debug_mode))
        if hasattr(self, "_enable_logs"):
            self._enable_logs.set(bool(s.enable_logs))
        if hasattr(self, "_autosave"):
            self._autosave.set(bool(s.autosave_config))

        if hasattr(self, "_post_action"):
            self._post_action.set(str(getattr(s, "post_action", "none")))

        if hasattr(self, "_opacity"):
            self._opacity.set(float(s.overlay_opacity))
        if hasattr(self, "_show_numbers"):
            self._show_numbers.set(bool(s.show_dot_numbers))
        if hasattr(self, "_show_coords"):
            self._show_coords.set(bool(s.show_coordinates))
        if hasattr(self, "_lock_dots"):
            self._lock_dots.set(bool(s.lock_dots))
        if hasattr(self, "_theme"):
            self._theme.set(str(s.theme))

        if hasattr(self, "_roblox_mode"):
            self._roblox_mode.set(bool(s.enable_roblox_mode))
        if hasattr(self, "_backend_var"):
            self._backend_var.set(str(s.click_backend))

    def _on_dot_moved(self, dot: Dot) -> None:
        self._refresh_dots_table()
        self._schedule_autosave()

    def _toggle_dots(self) -> None:
        self._dots_visible_user = not self._dots_visible_user
        if self._runner.status().state == "STOPPED":
            self._overlay.set_visible(self._dots_visible_user)

    def _reset_positions(self) -> None:
        if self._runner.status().state != "STOPPED":
            return

        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        cx = w // 2
        cy = h // 2

        for d in self._state.dots:
            d.x = cx
            d.y = cy

        self._overlay.rebuild(self._state.dots)
        self._refresh_dots_table()
        self._schedule_autosave()

    def _refresh_dots_table(self) -> None:
        selected = self._selected_dot_id()
        existing = set(self._tree.get_children(""))
        for item in existing:
            self._tree.delete(item)

        for idx, d in enumerate(self._state.dots):
            tags = ("even" if (idx % 2 == 0) else "odd",)
            self._tree.insert(
                "",
                "end",
                iid=d.id,
                tags=tags,
                values=(
                    d.name,
                    d.x,
                    d.y,
                    d.click_type,
                    "" if d.delay_override_ms is None else d.delay_override_ms,
                ),
            )

        if selected and selected in {d.id for d in self._state.dots}:
            try:
                self._tree.selection_set(selected)
                self._tree.see(selected)
            except Exception:
                pass

    def _add_dot(self) -> None:
        idx = len(self._state.dots) + 1
        dot = Dot(name=f"Dot {idx}")

        dot.click_type = self._dot_type_var.get()
        if dot.click_type == "key":
            k = self._dot_key_var.get().strip()
            if not k:
                self._set_message("Key is required for type=key")
                return
            dot.key = k

        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()
        dot.x = w // 2
        dot.y = h // 2

        self._state.dots.append(dot)
        self._overlay.add_dot(dot, index=len(self._state.dots) - 1)
        self._refresh_dots_table()
        try:
            self._tree.selection_set(dot.id)
            self._tree.see(dot.id)
        except Exception:
            pass
        self._schedule_autosave()

    def _start_record_dot_mode(self) -> None:
        if self._closing:
            return
        if self._runner.is_running():
            self._set_message("Stop the macro before recording a dot")
            return
        if self._record_dot_win is not None:
            return

        self._set_message("Record Dot: Click where the Roblox button is (Esc to cancel)")

        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()

        win = tk.Toplevel(self)
        self._record_dot_win = win
        try:
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.geometry(f"{w}x{h}+0+0")
            win.configure(bg="#000000")
            win.attributes("-alpha", 0.08)
            win.configure(cursor="crosshair")
        except Exception:
            pass

        try:
            lbl = tk.Label(
                win,
                text="Click where the Roblox button is\n(Esc to cancel)",
                bg="#000000",
                fg="#FFFFFF",
                font=("Segoe UI", 18, "bold"),
            )
            lbl.place(relx=0.5, rely=0.1, anchor="center")
        except Exception:
            pass

        try:
            win.bind("<Button-1>", self._on_record_dot_click)
            win.bind("<Escape>", lambda _e: self._cancel_record_dot_mode())
            win.focus_force()
        except Exception:
            pass

    def _cancel_record_dot_mode(self) -> None:
        win = self._record_dot_win
        self._record_dot_win = None
        if win is None:
            return
        try:
            win.destroy()
        except Exception:
            pass

    def _on_record_dot_click(self, event: tk.Event) -> None:
        x = int(getattr(event, "x_root", 0))
        y = int(getattr(event, "y_root", 0))
        self._cancel_record_dot_mode()

        idx = len(self._state.dots) + 1
        dot = Dot(name=f"Dot {idx}")
        dot.click_type = self._dot_type_var.get()
        if dot.click_type == "key":
            k = self._dot_key_var.get().strip()
            if not k:
                self._set_message("Key is required for type=key")
                return
            dot.key = k
        dot.x = x
        dot.y = y

        self._state.dots.append(dot)
        self._overlay.add_dot(dot, index=len(self._state.dots) - 1)
        self._refresh_dots_table()
        try:
            self._tree.selection_set(dot.id)
            self._tree.see(dot.id)
        except Exception:
            pass
        self._set_message(f"Recorded dot at {x}, {y}")
        self._schedule_autosave()

    def _selected_dot_id(self) -> str | None:
        sel = self._tree.selection()
        if not sel:
            return None
        return str(sel[0])

    def _get_dot_by_id(self, dot_id: str) -> Dot | None:
        for d in self._state.dots:
            if d.id == dot_id:
                return d
        return None

    def _on_dot_selected(self) -> None:
        dot_id = self._selected_dot_id()
        if not dot_id:
            return
        d = self._get_dot_by_id(dot_id)
        if d is None:
            return
        self._sel_dot_name.set(d.name)
        self._sel_dot_type.set(d.click_type)
        self._sel_dot_key.set(d.key or "{E}")
        self._sel_dot_delay.set("" if d.delay_override_ms is None else str(d.delay_override_ms))

    def _apply_selected_dot(self) -> None:
        dot_id = self._selected_dot_id()
        if not dot_id:
            self._set_message("Select a dot first")
            return
        d = self._get_dot_by_id(dot_id)
        if d is None:
            self._set_message("Select a dot first")
            return

        d.name = self._sel_dot_name.get().strip() or d.name
        d.click_type = self._sel_dot_type.get().strip() or d.click_type

        if d.click_type == "key":
            k = self._sel_dot_key.get().strip()
            if not k:
                self._set_message("Key is required for type=key")
                return
            d.key = k
        else:
            d.key = None

        delay_txt = self._sel_dot_delay.get().strip()
        if delay_txt == "":
            d.delay_override_ms = None
        else:
            try:
                d.delay_override_ms = max(0, int(delay_txt))
            except Exception:
                self._set_message("Invalid delay (ms)")
                return

        self._refresh_dots_table()
        self._schedule_autosave()

    def _copy_selected_dot(self) -> None:
        dot_id = self._selected_dot_id()
        if not dot_id:
            return
        d = self._get_dot_by_id(dot_id)
        if d is None:
            return

        copy = Dot(
            name=(d.name or "Dot") + " Copy",
            x=int(d.x) + 10,
            y=int(d.y) + 10,
            click_type=d.click_type,
            key=d.key,
            delay_override_ms=d.delay_override_ms,
        )
        self._state.dots.append(copy)
        self._overlay.add_dot(copy, index=len(self._state.dots) - 1)
        self._overlay.reindex(self._state.dots)
        self._refresh_dots_table()
        self._schedule_autosave()

    def _set_universal_delay(self) -> None:
        txt = self._universal_delay.get().strip()
        if txt == "":
            self._set_message("Enter a delay (seconds)")
            return
        try:
            seconds = max(0.0, float(txt))
            v = int(round(seconds * 1000.0))
        except Exception:
            self._set_message("Invalid delay (seconds)")
            return
        for d in self._state.dots:
            d.delay_override_ms = v
        self._refresh_dots_table()
        self._schedule_autosave()

    def _remove_selected_dot(self) -> None:
        dot_id = self._selected_dot_id()
        if not dot_id:
            return
        self._state.dots = [d for d in self._state.dots if d.id != dot_id]
        self._overlay.remove_dot(dot_id)
        self._overlay.reindex(self._state.dots)
        self._refresh_dots_table()
        self._schedule_autosave()

    def _clear_dots(self) -> None:
        self._state.dots.clear()
        self._overlay.clear()
        self._refresh_dots_table()
        self._schedule_autosave()

    def _apply_hotkeys(self) -> None:
        new_start = self._hk_start_stop.get().strip()
        new_pause = self._hk_pause_resume.get().strip()

        try:
            norm_start = hotkeys_mod._normalize_hotkey(new_start)
            norm_pause = hotkeys_mod._normalize_hotkey(new_pause)
        except Exception as e:
            self._set_message(f"Invalid hotkey: {e}")
            return

        if norm_start == norm_pause:
            self._set_message("Start/Stop and Pause/Resume hotkeys must be different")
            return

        cfg = HotkeyConfig(start_stop=new_start, pause_resume=new_pause)

        try:
            self._hotkeys.update(cfg)
        except Exception as e:
            self._set_message(f"Invalid hotkey: {e}")
            return

        self._state.settings.start_stop_hotkey = new_start
        self._state.settings.pause_resume_hotkey = new_pause

        self._set_message("Hotkeys applied")
        self._schedule_autosave()

    def _apply_performance(self) -> None:
        s = self._state.settings
        s.loop_delay_ms = self._safe_int(self._loop_delay, s.loop_delay_ms)
        s.click_delay_ms = self._safe_int(self._click_delay, s.click_delay_ms)
        s.loop_count = self._safe_int(self._loop_count, s.loop_count)
        s.max_loops = self._safe_int(self._max_loops, s.max_loops)
        s.mouse_speed = self._safe_int(self._mouse_speed, s.mouse_speed)
        s.click_speed_ms = self._safe_int(self._click_speed, s.click_speed_ms)
        s.randomize_order = bool(self._randomize.get())
        s.random_delay_pct = self._safe_int(self._random_delay, s.random_delay_pct)
        s.minimize_on_start = bool(self._min_on_start.get())
        s.restore_on_stop = bool(self._restore_on_stop.get())
        self._set_message("Performance applied")
        self._schedule_autosave()

    def _apply_advanced(self) -> None:
        s = self._state.settings
        s.pause_on_window_change = bool(self._pause_on_focus.get())
        s.auto_resume_on_focus = bool(self._auto_resume.get())
        s.debug_mode = bool(self._debug_mode.get())
        s.enable_logs = bool(self._enable_logs.get())
        s.autosave_config = bool(self._autosave.get())
        try:
            self._logger = configure_logging(s)
        except Exception:
            pass
        self._schedule_autosave()

    def _apply_post_action(self) -> None:
        s = self._state.settings
        s.post_action = str(self._post_action.get() or "none")
        self._set_message("Post action applied")
        self._schedule_autosave()

    def _run_post_action(self) -> None:
        if self._closing:
            return
        action = str(getattr(self._state.settings, "post_action", "none") or "none")
        if action == "none":
            return
        if action == "beep":
            try:
                self.bell()
            except Exception:
                pass
            return
        if action == "message":
            self._set_message("Macro finished")
            return
        if action == "close":
            try:
                self.after(50, self._on_close)
            except Exception:
                pass
            return

    def _apply_visual_live(self) -> None:
        s = self._state.settings
        s.overlay_opacity = float(self._opacity.get())
        s.show_dot_numbers = bool(self._show_numbers.get())
        s.show_coordinates = bool(self._show_coords.get())
        s.lock_dots = bool(self._lock_dots.get())
        self._overlay.set_settings(s)
        self._schedule_autosave()

    def _apply_visual(self) -> None:
        self._apply_visual_live()
        self._state.settings.theme = self._theme.get()
        ctk.set_appearance_mode(self._state.settings.theme)
        self._apply_ttk_theme()
        self._schedule_autosave()

    def _apply_roblox(self) -> None:
        try:
            self._runner.stop()
        except Exception:
            pass
        s = self._state.settings
        s.enable_roblox_mode = bool(self._roblox_mode.get())
        s.click_backend = str(self._backend_var.get())
        self._rebuild_runner()
        self._schedule_autosave()

    def _check_autoit(self) -> None:
        p1 = "C:/Program Files (x86)/AutoIt3/AutoIt3.exe"
        p2 = "C:/Program Files/AutoIt3/AutoIt3.exe"
        if os.path.exists(p1) or os.path.exists(p2):
            self._roblox_status.set("AutoIt installed")
        else:
            self._roblox_status.set("AutoIt not found")

    def _install_autoit(self) -> None:
        import urllib.request
        import subprocess

        url = "https://www.autoitscript.com/files/autoit3/autoit-v3-setup.exe"
        dst = os.path.join(os.path.dirname(__file__), "autoit-setup.exe")
        try:
            self._roblox_status.set("Downloading AutoIt...")
            urllib.request.urlretrieve(url, dst)
            self._roblox_status.set("Running installer...")
            subprocess.Popen([dst, "/S"], shell=False)
            self._roblox_status.set("Installer started")
        except Exception as e:
            self._roblox_status.set(f"Install failed: {e}")

    def _refresh_profiles(self) -> None:
        for item in self._profiles_list.get_children(""):
            self._profiles_list.delete(item)

        for name, mtime in storage.list_profiles():
            ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            self._profiles_list.insert("", "end", iid=name, values=(name, ts))

    def _save_profile(self) -> None:
        name = self._profile_name.get().strip()
        if not name:
            return
        try:
            storage.save_profile(name, self._state)
        except Exception:
            try:
                self._logger.exception("Failed to save profile")
            except Exception:
                pass
            self._set_message("Failed to save profile")
            return
        self._refresh_profiles()

    def _selected_profile(self) -> str | None:
        sel = self._profiles_list.selection()
        if not sel:
            return None
        return str(sel[0])

    def _load_selected_profile(self) -> None:
        name = self._selected_profile()
        if not name:
            return
        try:
            st = storage.load_profile(name)
        except Exception:
            try:
                self._logger.exception("Failed to load profile")
            except Exception:
                pass
            self._set_message("Failed to load profile (file may be corrupted)")
            return
        self._apply_loaded_state(st)

    def _delete_selected_profile(self) -> None:
        name = self._selected_profile()
        if not name:
            return
        try:
            storage.delete_profile(name)
        except Exception:
            try:
                self._logger.exception("Failed to delete profile")
            except Exception:
                pass
            self._set_message("Failed to delete profile")
            return
        self._refresh_profiles()

    def _apply_loaded_state(self, st: AppState) -> None:
        prev = self._state.settings
        prev_start = str(getattr(prev, "start_stop_hotkey", "f6"))
        prev_pause = str(getattr(prev, "pause_resume_hotkey", "f7"))
        prev_tos = int(getattr(prev, "tos_accepted_version", 0) or 0)
        prev_discord = bool(getattr(prev, "discord_prompt_shown", False))
        prev_key = bool(getattr(prev, "access_key_accepted", False))

        try:
            self._runner.stop()
        except Exception:
            pass
        self._overlay.clear()
        self._state = st

        try:
            self._state.settings.tos_accepted_version = prev_tos
            self._state.settings.discord_prompt_shown = prev_discord
            self._state.settings.access_key_accepted = prev_key
        except Exception:
            pass

        ctk.set_appearance_mode(self._state.settings.theme)
        self._overlay.set_settings(self._state.settings)
        for idx, d in enumerate(self._state.dots):
            self._overlay.add_dot(d, idx)
        self._refresh_dots_table()

        self._sync_ui_from_state()

        new_start = str(self._state.settings.start_stop_hotkey)
        new_pause = str(self._state.settings.pause_resume_hotkey)
        try:
            norm_start = hotkeys_mod._normalize_hotkey(new_start)
            norm_pause = hotkeys_mod._normalize_hotkey(new_pause)
            if norm_start == norm_pause:
                raise ValueError("Start/Stop and Pause/Resume hotkeys must be different")
            self._hotkeys.update(HotkeyConfig(start_stop=new_start, pause_resume=new_pause))
            self._hotkeys_failed = False
            self._hotkeys_active = True
        except Exception:
            try:
                self._logger.exception("Failed to apply hotkeys from profile")
            except Exception:
                pass

            try:
                self._state.settings.start_stop_hotkey = prev_start
                self._state.settings.pause_resume_hotkey = prev_pause
            except Exception:
                pass

            try:
                self._hotkeys.update(HotkeyConfig(start_stop=prev_start, pause_resume=prev_pause))
                self._hotkeys_failed = False
                self._hotkeys_active = True
            except Exception:
                self._hotkeys_failed = True
                self._hotkeys_active = False

            self._sync_ui_from_state()
            self._set_message("Profile hotkeys invalid; keeping previous hotkeys")

        self._rebuild_runner()

        self._schedule_autosave()

    def _on_start_stop_clicked(self) -> None:
        if getattr(self, "_startup_gate_needed", False):
            self._set_message("Please enter an access key to continue")
            return
        self._runner.toggle_start_stop()

    def _on_pause_resume_clicked(self) -> None:
        if getattr(self, "_startup_gate_needed", False):
            self._set_message("Please enter an access key to continue")
            return
        self._runner.toggle_pause_resume()

    def _on_test_run_clicked(self) -> None:
        if getattr(self, "_startup_gate_needed", False):
            self._set_message("Please enter an access key to continue")
            return
        if self._runner.status().state != "STOPPED":
            return
        self._runner.start(preview=True)

    def _on_runner_started(self, preview: bool) -> None:
        self._last_run_preview = bool(preview)
        if preview:
            return

        self._overlay.set_visible(False)
        if self._state.settings.minimize_on_start:
            try:
                self.iconify()
            except Exception:
                pass

    def _on_runner_stopped(self) -> None:
        self._overlay.set_visible(self._dots_visible_user)
        if self._state.settings.restore_on_stop:
            try:
                self.deiconify()
                self.lift()
            except Exception:
                pass

        if not self._last_run_preview:
            self._run_post_action()

    def _on_runner_status(self, st: RunnerStatus) -> None:
        self._update_status(st)

    def _update_status(self, st: RunnerStatus) -> None:
        text = f"Status: {st.state} | Dot: {st.current_dot_index + 1} | Loop: {st.current_loop}"
        if st.paused_reason:
            text += f" | Paused: {st.paused_reason}"
        self._status_var.set(text)

        if hasattr(self, "_status_pill"):
            if st.state == "RUNNING" and not st.paused_reason:
                fg = "#1F6F43" if self._is_dark() else "#D6F5E3"
                tc = "#EAFBF2" if self._is_dark() else "#0D3D22"
            elif st.paused_reason:
                fg = "#7A5C00" if self._is_dark() else "#FFF1C2"
                tc = "#FFF3D4" if self._is_dark() else "#4A3500"
            else:
                fg = "#2B2B2B" if self._is_dark() else "#EEEEEE"
                tc = "#EAEAEA" if self._is_dark() else "#111111"
            try:
                self._status_pill.configure(fg_color=fg, text_color=tc)
            except Exception:
                pass

    def _is_dark(self) -> bool:
        return str(self._state.settings.theme).lower() != "light"

    def _apply_ttk_theme(self) -> None:
        try:
            self._ttk_style.theme_use("clam")
        except Exception:
            pass

        if self._is_dark():
            card = "#242424"
            fg = "#EAEAEA"
            head_bg = "#2B2B2B"
            sel = "#2A5BD7"
            border = "#3A3A3A"
            even = "#242424"
            odd = "#202020"
        else:
            card = "#FFFFFF"
            fg = "#111111"
            head_bg = "#E9E9E9"
            sel = "#2A5BD7"
            border = "#D0D0D0"
            even = "#FFFFFF"
            odd = "#F3F3F3"

        try:
            self._ttk_style.configure(
                "Treeview",
                background=card,
                fieldbackground=card,
                foreground=fg,
                bordercolor=card,
                lightcolor=card,
                darkcolor=card,
                focuscolor=card,
                borderwidth=0,
                relief="flat",
                rowheight=28,
                font=("Segoe UI", 10),
            )
            self._ttk_style.map("Treeview", background=[("selected", sel)], foreground=[("selected", "#FFFFFF")])
            self._ttk_style.configure(
                "Treeview.Heading",
                background=head_bg,
                foreground=fg,
                bordercolor=head_bg,
                lightcolor=head_bg,
                darkcolor=head_bg,
                borderwidth=0,
                relief="flat",
                font=("Segoe UI", 10, "bold"),
            )
            self._ttk_style.map(
                "Treeview.Heading",
                background=[("active", head_bg), ("pressed", head_bg)],
                relief=[("active", "flat"), ("pressed", "flat")],
            )
        except Exception:
            pass

        for attr in ("_tree", "_profiles_list"):
            tv = getattr(self, attr, None)
            if tv is None:
                continue
            try:
                tv.tag_configure("even", background=even)
                tv.tag_configure("odd", background=odd)
                tv.configure(takefocus=0, relief="flat", borderwidth=0)
            except Exception:
                pass

    def _focus_poll(self) -> None:
        if self._closing:
            return
        try:
            s = self._state.settings
            if s.pause_on_window_change:
                active = is_foreground_process("RobloxPlayerBeta.exe")
                if not active and self._runner.is_running():
                    self._runner.pause(reason="focus")
                elif active and self._runner.is_paused() and s.auto_resume_on_focus:
                    self._runner.resume(reason="focus")
        finally:
            if self._closing:
                return
            try:
                if not self.winfo_exists():
                    return
            except Exception:
                return
            self._focus_job = self.after(max(50, int(self._state.settings.window_check_interval_ms)), self._focus_poll)

    def _on_close(self) -> None:
        self._closing = True
        self._cancel_record_dot_mode()
        self._cancel_job("_ui_drain_job")
        self._cancel_job("_focus_job")
        self._cancel_job("_autosave_job")
        self._cancel_job("_msg_job")
        try:
            self._hotkeys.stop()
        except Exception:
            pass
        try:
            self._runner.stop()
        except Exception:
            pass
        try:
            self._overlay.clear()
        except Exception:
            pass

        try:
            self._save_config()
        except Exception:
            pass

        self.destroy()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
