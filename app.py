"""
AVL Parser — Desktop App
Double-click to open. Select AVL files, then export to .mat for MATLAB.
Works on macOS and Windows.

Requirements: pip install customtkinter
"""

import json
import os
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

# Drag & drop — optional dependency
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DnDMixin = TkinterDnD.DnDWrapper
    HAS_DND = True
except ImportError:
    _DnDMixin = object
    HAS_DND = False

# Ensure imports work when running from any directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_avl import (process_files, process_files_3d, process_files_full,
                        parse_file, validate_file, ALL_LABELS, PAIRABLE_VARS,
                        SURFACE_SUFFIX, SURFACE_COEFF_GROUPS)

from scipy.io import savemat


# --- Theme ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# --- Mode display mapping ---
MODE_LABELS = ['\u03b1,M', '\u03b4,M', '3D']
DISPLAY_TO_MODE = {
    '\u03b1,M': '2d_angle',
    '\u03b4,M': '2d_surface',
    '3D': '3d',
}
MODE_TO_DISPLAY = {v: k for k, v in DISPLAY_TO_MODE.items()}

MAX_CONFIG_HISTORY = 50


class Tooltip:
    """Hover tooltip for any tkinter/CTk widget."""

    def __init__(self, widget, text, delay=400):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._tip_window = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        self._hide()

    def _show(self):
        if self._tip_window:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify="left",
                         background="#333333", foreground="#e0e0e0",
                         relief="solid", borderwidth=1,
                         font=("Helvetica", 11), padx=6, pady=3)
        label.pack()

    def _hide(self):
        if self._tip_window:
            self._tip_window.destroy()
            self._tip_window = None

# Compact config encoding: each coefficient mode → single char
_MODE_ENCODE = {'\u03b1,M': 'a', '\u03b4,M': 'd', '3D': '3'}
_MODE_DECODE = {v: k for k, v in _MODE_ENCODE.items()}
_COEFF_ORDER = []
for _s in SURFACE_SUFFIX:
    _COEFF_ORDER.extend(SURFACE_COEFF_GROUPS[_s])


class _LoadConfigDialog(ctk.CTkToplevel):
    """Searchable scrollable dialog for loading saved configurations."""

    def __init__(self, parent, configs, on_load, on_delete):
        super().__init__(parent)
        self.title("Load Configuration")
        self.geometry("400x420")
        self.resizable(True, True)
        self.transient(parent)

        self._configs = list(configs)  # local copy
        self._filtered = list(self._configs)  # currently visible
        self._on_load = on_load
        self._on_delete = on_delete

        # --- Search bar ---
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        search_entry = ctk.CTkEntry(self, textvariable=self._search_var,
                                     placeholder_text="Search...",
                                     height=32, font=ctk.CTkFont(size=13))
        search_entry.pack(fill="x", padx=12, pady=(12, 8))

        # --- Scrollable list (plain tk.Listbox — reliable on all platforms) ---
        list_frame = ctk.CTkFrame(self, corner_radius=8)
        list_frame.pack(fill="both", expand=True, padx=12)

        self._listbox = tk.Listbox(
            list_frame, font=("Courier", 13), selectmode="browse",
            bg="#2b2b2b", fg="#dcdcdc", selectbackground="#1f6aa5",
            selectforeground="white", borderwidth=0,
            highlightthickness=0, activestyle="none",
        )
        scrollbar = ctk.CTkScrollbar(list_frame, command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scrollbar.set)
        self._listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=8)

        self._listbox.bind("<<ListboxSelect>>", lambda e: self._update_buttons())
        self._listbox.bind("<Double-Button-1>", lambda e: self._load_selected())

        self._populate_listbox()

        # --- Button row ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(8, 12))

        self._delete_btn = ctk.CTkButton(
            btn_frame, text="Delete", width=80, height=32,
            font=ctk.CTkFont(size=12),
            fg_color=("gray70", "gray30"), hover_color=("#c0392b", "#c0392b"),
            text_color=("gray20", "gray90"),
            command=self._delete_selected, state="disabled",
        )
        self._delete_btn.pack(side="left")

        self._load_btn = ctk.CTkButton(
            btn_frame, text="Load", width=80, height=32,
            font=ctk.CTkFont(size=12),
            command=self._load_selected, state="disabled",
        )
        self._load_btn.pack(side="right")

        self.after(200, lambda: (self.grab_set(), search_entry.focus_set()))

    def _populate_listbox(self):
        """Fill the listbox from self._filtered."""
        self._listbox.delete(0, "end")
        for cfg in self._filtered:
            name = cfg.get("n", "Unnamed")
            ts = cfg.get("ts", "")
            date_str = ts[:10] if len(ts) >= 10 else ""
            self._listbox.insert("end", f"{name}   {date_str}")

    def _filter(self):
        """Rebuild list based on search text."""
        query = self._search_var.get().strip().lower()
        if query:
            self._filtered = [c for c in self._configs
                              if query in c.get("n", "").lower()]
        else:
            self._filtered = list(self._configs)
        self._populate_listbox()
        self._update_buttons()

    def _get_selected(self):
        """Return (index_in_filtered, config) or (None, None)."""
        sel = self._listbox.curselection()
        if not sel:
            return None, None
        idx = sel[0]
        if idx < len(self._filtered):
            return idx, self._filtered[idx]
        return None, None

    def _update_buttons(self):
        idx, _ = self._get_selected()
        has_sel = idx is not None
        self._load_btn.configure(state="normal" if has_sel else "disabled")
        self._delete_btn.configure(state="normal" if has_sel else "disabled")

    def _load_selected(self):
        _, cfg = self._get_selected()
        if cfg is None:
            return
        self.grab_release()
        self.destroy()
        self._on_load(cfg)

    def _delete_selected(self):
        _, cfg = self._get_selected()
        if cfg is None:
            return
        confirm = messagebox.askyesno(
            "Delete configuration?",
            f"Delete \"{cfg.get('n', 'Unnamed')}\"?",
            parent=self,
        )
        if not confirm:
            return
        self._on_delete(cfg)
        if cfg in self._configs:
            self._configs.remove(cfg)
        self._filter()


class AVLParserApp(ctk.CTk, _DnDMixin):
    def __init__(self):
        super().__init__()
        if HAS_DND:
            self.TkdndVersion = TkinterDnD._require(self)

        self.title("AVL Parser")
        self.geometry("950x680")
        self.minsize(800, 600)

        # Set window icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.png')
        if os.path.isfile(icon_path):
            from PIL import Image, ImageTk
            icon_img = ImageTk.PhotoImage(Image.open(icon_path))
            self.iconphoto(True, icon_img)
            self._icon_ref = icon_img  # prevent garbage collection

        self.filepaths = []
        self._file_limit = 1000

        # Config history state (populated after UI is built)
        self._config_history = []
        self._config_cursor = -1
        self._history_navigating = False
        self._saved_configs = []
        self._config_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "avl_configs.json"
        )

        self._build_ui()
        self._load_persistence()
        self._limit_var.set(str(self._file_limit))
        self._limit_apply_btn.configure(state="disabled")
        self._setup_config_traces()

        # Enable drag & drop if tkinterdnd2 is installed
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_drop)

    def _build_ui(self):
        # ==========================================================
        # HEADER (full width)
        # ==========================================================
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(header_frame, text="AVL Parser",
                      font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")

        ctk.CTkLabel(header_frame,
                      text="Parse AVL output files and export to .mat for MATLAB",
                      font=ctk.CTkFont(size=12),
                      text_color=("gray50", "gray60")).pack(side="left", padx=(12, 0))

        # ==========================================================
        # STATUS BAR (pinned to bottom)
        # ==========================================================
        self.status_frame = ctk.CTkFrame(self, height=32, corner_radius=0,
                                      fg_color=("gray90", "gray18"))
        self.status_frame.pack(fill="x", side="bottom")
        self.status_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(self.status_frame, text="Ready",
                                           font=ctk.CTkFont(size=12),
                                           text_color=("gray50", "gray60"),
                                           anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True, padx=12, pady=4)

        self.progress_bar = ctk.CTkProgressBar(self.status_frame, height=6, width=180)
        self.progress_bar.set(0)

        # ==========================================================
        # TWO-PANE SPLIT (files left, settings right)
        # ==========================================================
        main_area = ctk.CTkFrame(self, corner_radius=10,
                                  fg_color=("gray92", "gray17"))
        main_area.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        main_area.columnconfigure(0, weight=2)   # left ~40%
        main_area.columnconfigure(1, weight=0)   # divider
        main_area.columnconfigure(2, weight=3)   # right ~60%
        main_area.rowconfigure(0, weight=1)

        # ==========================================================
        # LEFT PANE — FILES
        # ==========================================================
        left_pane = ctk.CTkFrame(main_area, corner_radius=0,
                                  fg_color="transparent")
        left_pane.grid(row=0, column=0, sticky="nsew")

        # Pane header
        left_header = ctk.CTkFrame(left_pane, fg_color="transparent")
        left_header.pack(fill="x", padx=12, pady=(10, 6))

        ctk.CTkLabel(left_header, text="Files",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      text_color=("gray30", "gray80")).pack(side="left")

        self.count_label = ctk.CTkLabel(left_header, text="No files selected",
                                         font=ctk.CTkFont(size=11),
                                         text_color=("gray50", "gray60"))
        self.count_label.pack(side="right")

        # File limit row
        limit_frame = ctk.CTkFrame(left_pane, fg_color="transparent")
        limit_frame.pack(fill="x", padx=12, pady=(0, 4))

        ctk.CTkLabel(limit_frame, text="Max files:",
                      font=ctk.CTkFont(size=11),
                      text_color=("gray50", "gray60")).pack(side="left")

        self._limit_var = ctk.StringVar(value=str(self._file_limit))
        self._limit_entry = ctk.CTkEntry(
            limit_frame, textvariable=self._limit_var,
            width=60, height=24, font=ctk.CTkFont(size=11),
            justify="center",
        )
        self._limit_entry.pack(side="left", padx=(6, 0))
        self._limit_entry.bind("<Return>", lambda e: self._apply_limit())

        self._limit_apply_btn = ctk.CTkButton(
            limit_frame, text="✓", width=24, height=24,
            font=ctk.CTkFont(size=13), state="disabled",
            command=self._apply_limit,
        )
        self._limit_apply_btn.pack(side="left", padx=(4, 0))

        self._limit_var.trace_add("write", self._on_limit_changed)

        Tooltip(self._limit_entry,
                "Max files allowed (prevents accidental deep folder scans)")

        # Button rows
        btn_row1 = ctk.CTkFrame(left_pane, fg_color="transparent")
        btn_row1.pack(fill="x", padx=12, pady=(0, 4))

        self.add_btn = ctk.CTkButton(btn_row1, text="Add Files", command=self.add_files,
                                      height=30, font=ctk.CTkFont(size=12))
        self.add_btn.pack(side="left", fill="x", expand=True)

        self.add_folder_btn = ctk.CTkButton(btn_row1, text="Add Folder",
                                              command=self.add_folder,
                                              height=30, font=ctk.CTkFont(size=12))
        self.add_folder_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        btn_row2 = ctk.CTkFrame(left_pane, fg_color="transparent")
        btn_row2.pack(fill="x", padx=12, pady=(0, 8))

        self.remove_btn = ctk.CTkButton(btn_row2, text="Remove Selected",
                                          command=self.remove_selected,
                                          height=28, font=ctk.CTkFont(size=11),
                                          fg_color="transparent", border_width=1,
                                          border_color=("gray60", "gray40"),
                                          text_color=("gray30", "gray80"),
                                          hover_color=("gray85", "gray25"))
        self.remove_btn.pack(side="left", fill="x", expand=True)

        self.clear_btn = ctk.CTkButton(btn_row2, text="Clear All", command=self.clear_files,
                                        height=28, font=ctk.CTkFont(size=11),
                                        fg_color=("gray70", "gray30"),
                                        hover_color=("gray60", "gray40"),
                                        text_color=("gray20", "gray90"))
        self.clear_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # File list area (fills remaining height)
        self.list_container = ctk.CTkFrame(left_pane, corner_radius=6,
                                            fg_color=("gray88", "#2b2b2b"))
        self.list_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Empty state overlay
        self.empty_state = ctk.CTkFrame(self.list_container, corner_radius=6,
                                         fg_color="transparent",
                                         border_width=2,
                                         border_color=("gray75", "gray35"))
        self.empty_state_label = ctk.CTkLabel(
            self.empty_state,
            text="Drop files here\nor use Add Files / Add Folder",
            font=ctk.CTkFont(size=13),
            text_color=("gray55", "gray50"),
            justify="center",
        )
        self.empty_state_label.pack(expand=True)

        # File listbox (hidden when empty)
        self.list_inner = ctk.CTkFrame(self.list_container, fg_color="transparent")

        self.file_listbox = tk.Listbox(
            self.list_inner, font=("Courier", 12), selectmode="extended",
            bg="#2b2b2b", fg="#dcdcdc", selectbackground="#1f6aa5",
            selectforeground="white", borderwidth=0,
            highlightthickness=0, activestyle="none",
        )
        scrollbar = ctk.CTkScrollbar(self.list_inner, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=6)

        # Show empty state by default
        self.empty_state.pack(fill="both", expand=True, padx=8, pady=8)

        # Vertical divider
        ctk.CTkFrame(main_area, width=1,
                       fg_color=("gray80", "gray30")
        ).grid(row=0, column=1, sticky="ns", pady=10)

        # ==========================================================
        # RIGHT PANE — EXPORT SETTINGS
        # ==========================================================
        right_pane = ctk.CTkFrame(main_area, corner_radius=0,
                                   fg_color="transparent")
        right_pane.grid(row=0, column=2, sticky="nsew")

        # Pane header with mode selector
        right_header = ctk.CTkFrame(right_pane, fg_color="transparent")
        right_header.pack(fill="x", padx=12, pady=(10, 8))

        ctk.CTkLabel(right_header, text="Export Settings",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      text_color=("gray30", "gray80")).pack(side="left")

        self.mode_var = ctk.StringVar(value="2D Tables")
        self.mode_selector = ctk.CTkSegmentedButton(
            right_header,
            values=["2D Tables", "3D Tables", "Full Analysis"],
            variable=self.mode_var,
            command=self._on_mode_change,
            font=ctk.CTkFont(size=12),
            height=28,
        )
        self.mode_selector.pack(side="right")

        # Options container (holds either 2D or 3D panel)
        self.options_container = ctk.CTkFrame(right_pane, fg_color="transparent")
        self.options_container.pack(fill="both", expand=True, padx=12, pady=(0, 0))

        # 2D Panel
        self.panel_2d = ctk.CTkFrame(self.options_container, fg_color="transparent")

        pair_label = ctk.CTkLabel(self.panel_2d, text="Mach  \u00d7",
                                   font=ctk.CTkFont(size=12),
                                   text_color=("gray50", "gray60"))
        pair_label.pack(side="left", padx=(0, 6))

        self.second_var = ctk.StringVar(value="Alpha")
        self.pair_menu = ctk.CTkOptionMenu(
            self.panel_2d, variable=self.second_var,
            values=list(PAIRABLE_VARS.keys()),
            width=90, height=26, font=ctk.CTkFont(size=12),
            dynamic_resizing=False,
        )
        self.pair_menu.pack(side="left")

        self.check_2d_conflicts = ctk.BooleanVar(value=True)
        self.chk_2d = ctk.CTkCheckBox(
            self.panel_2d, text="Single angle/deflection",
            variable=self.check_2d_conflicts,
            font=ctk.CTkFont(size=11), checkbox_width=16, checkbox_height=16)
        self.chk_2d.pack(side="right")

        # 3D Panel
        self.panel_3d = ctk.CTkFrame(self.options_container, fg_color="transparent")
        self._build_3d_panel()

        # 2D panel shown by default
        self.panel_2d.pack(fill="x")

        # Validation checkboxes (compact, only visible in 3D mode)
        self.check_single_angle = ctk.BooleanVar(value=True)
        self.check_single_defl = ctk.BooleanVar(value=True)

        self.validation_frame = ctk.CTkFrame(right_pane, fg_color="transparent")

        _chk_font = ctk.CTkFont(size=11)
        self.chk_angle = ctk.CTkCheckBox(
            self.validation_frame, text="Single angle",
            variable=self.check_single_angle,
            font=_chk_font, checkbox_width=16, checkbox_height=16)
        self.chk_angle.pack(side="left", padx=(0, 10))

        self.chk_defl = ctk.CTkCheckBox(
            self.validation_frame, text="Single deflection",
            variable=self.check_single_defl,
            font=_chk_font, checkbox_width=16, checkbox_height=16)
        self.chk_defl.pack(side="left")

        self.check_fa_skip = ctk.BooleanVar(value=True)
        self.chk_fa_skip = ctk.CTkCheckBox(
            self.validation_frame, text="Skip conflicts",
            variable=self.check_fa_skip,
            font=_chk_font, checkbox_width=16, checkbox_height=16)
        # Not packed yet — shown only in Full Analysis mode

        # Export button (bottom of right pane)
        self.export_btn = ctk.CTkButton(right_pane, text="Export .mat",
                                          command=self.export_mat,
                                          height=40, corner_radius=8,
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          fg_color=("#2d8a4e", "#2d8a4e"),
                                          hover_color=("#247a42", "#247a42"))
        self.export_btn.pack(fill="x", padx=12, pady=(8, 12), side="bottom")

        self._setup_tooltips()

    def _setup_tooltips(self):
        """Attach hover tooltips to all interactive widgets."""
        # File buttons
        Tooltip(self.add_btn, "Select individual AVL output files")
        Tooltip(self.add_folder_btn, "Add all AVL files from a folder")
        Tooltip(self.remove_btn, "Remove highlighted files from the list")
        Tooltip(self.clear_btn, "Remove all files from the list")

        # Mode selector — CTkSegmentedButton doesn't support .bind(),
        # so attach tooltip to its parent frame instead
        Tooltip(self.mode_selector.master,
                "2D: Mach \u00d7 one variable\n"
                "3D: Mach \u00d7 Angle \u00d7 Surface deflections\n"
                "Full: All modes combined in one .mat")

        # 2D panel
        Tooltip(self.pair_menu, "Second axis variable paired with Mach")

        # Config toolbar
        Tooltip(self.history_back_btn, "Undo last coefficient change")
        Tooltip(self.history_fwd_btn, "Redo coefficient change")
        Tooltip(self.save_config_btn, "Save current coefficient settings")
        Tooltip(self.load_config_btn, "Load a saved configuration")

        # Export
        Tooltip(self.export_btn, "Export parsed data to a MATLAB .mat file")

        # Validation checkboxes
        Tooltip(self.chk_2d, "Skip files with multiple non-zero angles or deflections")
        Tooltip(self.chk_angle, "Block export if any file has both Alpha and Beta non-zero")
        Tooltip(self.chk_defl, "Block export if any file has multiple control surfaces non-zero")
        Tooltip(self.chk_fa_skip, "Skip conflicting files in Alpha and Beta 2D passes")

    def _build_3d_panel(self):
        """Build the 3D mode options panel (Alpha/Beta radio + tabbed coefficient controls)."""
        # --- Angle axis radio buttons ---
        angle_frame = ctk.CTkFrame(self.panel_3d, fg_color="transparent")
        angle_frame.pack(fill="x", pady=(0, 6))

        angle_label = ctk.CTkLabel(angle_frame, text="Angle axis:",
                                    font=ctk.CTkFont(size=12),
                                    text_color=("gray50", "gray60"))
        angle_label.pack(side="left", padx=(0, 10))

        self.angle_var = ctk.StringVar(value="Alpha")
        for val in ["Alpha", "Beta"]:
            rb = ctk.CTkRadioButton(angle_frame, text=val, variable=self.angle_var,
                                     value=val, font=ctk.CTkFont(size=12))
            rb.pack(side="left", padx=(0, 12))

        # --- Control Derivatives header + legend ---
        deriv_header = ctk.CTkLabel(self.panel_3d, text="Control Derivatives",
                                     font=ctk.CTkFont(size=12, weight="bold"),
                                     text_color=("gray30", "gray80"),
                                     anchor="w")
        deriv_header.pack(fill="x", pady=(4, 2))

        legend = ctk.CTkLabel(self.panel_3d,
                               text="\u03b1,M = Angle\u00d7Mach    "
                                    "\u03b4,M = Surface\u00d7Mach    "
                                    "3D = Angle\u00d7Mach\u00d7Surface",
                               font=ctk.CTkFont(size=10),
                               text_color=("gray50", "gray55"),
                               anchor="w")
        legend.pack(fill="x", pady=(0, 4))

        # --- 4-column coefficient grid (all surfaces visible) ---
        coeff_grid = ctk.CTkFrame(self.panel_3d, fg_color=("gray88", "gray20"),
                                   corner_radius=6)
        coeff_grid.pack(fill="both", expand=True, pady=(0, 6))

        self.coeff_mode_vars = {}   # {label: StringVar}

        surfaces = list(SURFACE_SUFFIX.keys())
        surface_colors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444"]

        # Configure grid columns: label + 4 surface columns
        coeff_grid.columnconfigure(0, weight=0, minsize=52)
        for i in range(1, 5):
            coeff_grid.columnconfigure(i, weight=1)

        # Row 0: Surface headers
        for col_idx, surface in enumerate(surfaces):
            ctk.CTkLabel(coeff_grid, text=surface,
                          font=ctk.CTkFont(size=11, weight="bold"),
                          text_color=surface_colors[col_idx]
            ).grid(row=0, column=col_idx + 1, padx=2, pady=(6, 2))

        # Row 1: "Set all" buttons
        ctk.CTkLabel(coeff_grid, text="Set all",
                      font=ctk.CTkFont(size=10, weight="bold"),
                      text_color=("gray45", "gray65"),
                      anchor="w"
        ).grid(row=1, column=0, padx=(8, 2), pady=2, sticky="w")

        for col_idx, surface in enumerate(surfaces):
            group_var = ctk.StringVar(value=MODE_LABELS[0])
            ctk.CTkSegmentedButton(
                coeff_grid, values=MODE_LABELS, variable=group_var,
                font=ctk.CTkFont(size=9), height=22,
                command=lambda val, s=surface: self._set_group(s, val),
            ).grid(row=1, column=col_idx + 1, padx=2, pady=2, sticky="ew")

        # Row 2: Separator
        ctk.CTkFrame(coeff_grid, height=1,
                       fg_color=("gray80", "gray30")
        ).grid(row=2, column=0, columnspan=5, sticky="ew", padx=4, pady=2)

        # Rows 3-10: Coefficient rows (8 per surface)
        num_coeffs = len(SURFACE_COEFF_GROUPS[surfaces[0]])
        first_suffix = SURFACE_SUFFIX[surfaces[0]]

        for row_idx in range(num_coeffs):
            grid_row = row_idx + 3
            # Base coefficient name (strip surface suffix)
            base_name = SURFACE_COEFF_GROUPS[surfaces[0]][row_idx].replace(first_suffix, "")

            ctk.CTkLabel(coeff_grid, text=base_name,
                          font=ctk.CTkFont(size=10),
                          anchor="w"
            ).grid(row=grid_row, column=0, padx=(8, 2), pady=1, sticky="w")

            for col_idx, surface in enumerate(surfaces):
                label = SURFACE_COEFF_GROUPS[surface][row_idx]
                var = ctk.StringVar(value=MODE_LABELS[0])
                ctk.CTkSegmentedButton(
                    coeff_grid, values=MODE_LABELS, variable=var,
                    font=ctk.CTkFont(size=9), height=22,
                ).grid(row=grid_row, column=col_idx + 1, padx=2, pady=1, sticky="ew")
                self.coeff_mode_vars[label] = var

        # --- Separator before config toolbar ---
        ctk.CTkFrame(self.panel_3d, height=1,
                       fg_color=("gray80", "gray30")).pack(fill="x", pady=(4, 4))

        # --- Config toolbar (always visible) ---
        self.config_toolbar = ctk.CTkFrame(self.panel_3d, fg_color="transparent")

        self.history_back_btn = ctk.CTkButton(
            self.config_toolbar, text="\u25c0", width=32, height=28,
            font=ctk.CTkFont(size=12),
            command=self._history_back, state="disabled",
            fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"),
            text_color=("gray30", "gray80"),
        )
        self.history_back_btn.pack(side="left")

        self.history_fwd_btn = ctk.CTkButton(
            self.config_toolbar, text="\u25b6", width=32, height=28,
            font=ctk.CTkFont(size=12),
            command=self._history_forward, state="disabled",
            fg_color=("gray75", "gray30"), hover_color=("gray65", "gray40"),
            text_color=("gray30", "gray80"),
        )
        self.history_fwd_btn.pack(side="left", padx=(4, 16))

        self.save_config_btn = ctk.CTkButton(
            self.config_toolbar, text="Save Config", width=100, height=28,
            font=ctk.CTkFont(size=11), command=self._save_config,
        )
        self.save_config_btn.pack(side="left")

        self.load_config_btn = ctk.CTkButton(
            self.config_toolbar, text="Load Config", width=100, height=28,
            font=ctk.CTkFont(size=11), command=self._open_load_dialog,
        )
        self.load_config_btn.pack(side="left", padx=(8, 0))

        self.config_toolbar.pack(fill="x", pady=(0, 4))

    def _set_group(self, surface, mode):
        """Set all coefficients in a surface group to the chosen mode."""
        for label in SURFACE_COEFF_GROUPS[surface]:
            self.coeff_mode_vars[label].set(mode)

    def _on_mode_change(self, value):
        """Toggle between 2D, 3D, and Full Analysis panels."""
        if value == "2D Tables":
            self.panel_3d.pack_forget()
            self.panel_2d.pack(fill="x")
            self.chk_fa_skip.pack_forget()
            self.validation_frame.pack_forget()
        elif value == "3D Tables":
            self.panel_2d.pack_forget()
            self.panel_3d.pack(fill="x")
            self.chk_fa_skip.pack_forget()
            self.validation_frame.pack(fill="x", padx=12, pady=(4, 0), side="bottom")
        else:
            # Full Analysis — show all 3 checkboxes
            self.panel_2d.pack_forget()
            self.panel_3d.pack(fill="x")
            self.chk_fa_skip.pack(side="left", padx=(10, 0))
            self.validation_frame.pack(fill="x", padx=12, pady=(4, 0), side="bottom")

    # --- Configuration history & presets ---

    def _encode_config(self):
        """Encode current UI state as a compact string like 'A:aaaddd333...'."""
        angle = 'A' if self.angle_var.get() == 'Alpha' else 'B'
        modes = ''.join(
            _MODE_ENCODE[self.coeff_mode_vars[l].get()] for l in _COEFF_ORDER
        )
        return f"{angle}:{modes}"

    def _decode_config(self, code):
        """Apply a compact config string to the UI widgets."""
        self._history_navigating = True
        self.angle_var.set('Alpha' if code[0] == 'A' else 'Beta')
        for i, label in enumerate(_COEFF_ORDER):
            if label in self.coeff_mode_vars:
                self.coeff_mode_vars[label].set(_MODE_DECODE[code[i + 2]])
        self._history_navigating = False
        self._update_history_buttons()

    def _setup_config_traces(self):
        """No-op — history is recorded on export, not on every click."""
        pass

    def _record_config(self):
        """Push current config to history (undo/redo style)."""
        code = self._encode_config()

        # Don't record if identical to current position
        if (self._config_cursor >= 0 and
                self._config_history[self._config_cursor]["c"] == code):
            return

        # Truncate any redo future
        self._config_history = self._config_history[:self._config_cursor + 1]

        entry = {"c": code, "ts": datetime.now().isoformat(timespec="seconds")}
        self._config_history.append(entry)

        # Enforce max size
        if len(self._config_history) > MAX_CONFIG_HISTORY:
            self._config_history.pop(0)

        self._config_cursor = len(self._config_history) - 1
        self._update_history_buttons()
        self._persist()

    def _history_back(self):
        """Go to previous configuration (undo)."""
        if self._config_cursor <= 0:
            return
        self._config_cursor -= 1
        self._decode_config(self._config_history[self._config_cursor]["c"])

    def _history_forward(self):
        """Go to next configuration (redo)."""
        if self._config_cursor >= len(self._config_history) - 1:
            return
        self._config_cursor += 1
        self._decode_config(self._config_history[self._config_cursor]["c"])

    def _update_history_buttons(self):
        """Enable/disable ← → buttons based on cursor position."""
        can_back = self._config_cursor > 0
        can_fwd = self._config_cursor < len(self._config_history) - 1
        self.history_back_btn.configure(
            state="normal" if can_back else "disabled"
        )
        self.history_fwd_btn.configure(
            state="normal" if can_fwd else "disabled"
        )

    def _save_config(self):
        """Save current config with a user-chosen name."""
        dialog = ctk.CTkInputDialog(
            text="Enter a name for this configuration:",
            title="Save Configuration",
        )
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()

        # Check for duplicate name
        existing = next((c for c in self._saved_configs if c["n"] == name), None)
        if existing:
            overwrite = messagebox.askyesno(
                "Overwrite?",
                f"A configuration named \"{name}\" already exists.\nOverwrite it?"
            )
            if not overwrite:
                return
            self._saved_configs.remove(existing)

        entry = {
            "c": self._encode_config(),
            "ts": datetime.now().isoformat(timespec="seconds"),
            "n": name,
        }
        self._saved_configs.append(entry)
        self._persist()
        self._set_status(f"Saved config: {name}")

    def _open_load_dialog(self):
        """Open the searchable load-configuration dialog."""
        if not self._saved_configs:
            messagebox.showinfo("No saved configs",
                                "No saved configurations yet.\n"
                                "Use 'Save Config' to save one first.")
            return
        _LoadConfigDialog(self, self._saved_configs, self._on_load_config,
                          self._on_delete_config)

    def _on_load_config(self, config):
        """Callback when user loads a config from the dialog."""
        self._decode_config(config["c"])
        # Also record it in history so the user can undo back
        self._record_config()
        self._set_status(f"Loaded config: {config.get('n', '?')}")

    def _on_delete_config(self, config):
        """Callback when user deletes a saved config from the dialog."""
        if config in self._saved_configs:
            self._saved_configs.remove(config)
            self._persist()

    # --- Persistence ---

    def _persist(self):
        """Write history and saved configs to disk (atomic write)."""
        data = {
            "history": self._config_history[-MAX_CONFIG_HISTORY:],
            "saved": self._saved_configs,
            "file_limit": self._file_limit,
        }
        try:
            dir_path = os.path.dirname(self._config_file)
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, indent=2)
                os.replace(tmp_path, self._config_file)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        except OSError:
            pass  # Non-critical — silently skip if write fails

    @staticmethod
    def _migrate_entry(e):
        """Convert old verbose config entry to compact format."""
        angle = 'A' if e.get("angle_var") == "Alpha" else 'B'
        cm = e.get("coeff_modes", {})
        modes = ''.join(
            _MODE_ENCODE.get(cm.get(l, '\u03b1,M'), 'a') for l in _COEFF_ORDER
        )
        result = {"c": f"{angle}:{modes}", "ts": e.get("ts", "")}
        if "name" in e:
            result["n"] = e["name"]
        return result

    def _load_persistence(self):
        """Load history and saved configs from disk, then record initial state."""
        load_ok = False
        try:
            with open(self._config_file) as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._config_history = data.get("history", [])
                self._saved_configs = data.get("saved", [])
                self._file_limit = max(1, int(data.get("file_limit", 1000)))
                load_ok = True
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            pass  # keep defaults (empty lists from __init__)

        # Migrate old verbose format if needed
        if self._config_history and "angle_var" in self._config_history[0]:
            self._config_history = [self._migrate_entry(e) for e in self._config_history]
            self._saved_configs = [self._migrate_entry(e) for e in self._saved_configs]
            self._persist()

        if self._config_history:
            self._config_cursor = len(self._config_history) - 1
            self._decode_config(self._config_history[self._config_cursor]["c"])
        else:
            self._config_cursor = -1
            # Only persist the default config if we know the file was
            # loaded successfully (or didn't exist yet). If the file was
            # corrupted, don't overwrite it — the user can fix it manually.
            if load_ok or not os.path.exists(self._config_file):
                self._record_config()

    # --- Actions ---

    def _add_paths(self, paths):
        """Validate and add file paths to the list.

        Returns (added, duplicates, rejected, hit_limit) where rejected is
        a list of (filename, reason) tuples and hit_limit is True if the
        file limit was reached.
        """
        added = 0
        duplicates = 0
        rejected = []
        hit_limit = False
        new_names = []  # batch listbox inserts

        for path in paths:
            if len(self.filepaths) + len(new_names) >= self._file_limit:
                hit_limit = True
                break
            if not os.path.isfile(path):
                continue
            filename = os.path.basename(path)
            if path in self.filepaths:
                duplicates += 1
                continue
            valid, info = validate_file(path)
            if not valid:
                rejected.append((filename, info))
                continue
            self.filepaths.append(path)
            new_names.append(filename)
            added += 1

        # Batch insert all validated filenames at once
        for name in new_names:
            self.file_listbox.insert("end", name)

        self._update_count()
        return added, duplicates, rejected, hit_limit

    def _collect_files_from_dir(self, directory):
        """Recursively collect file paths from a directory (respects file limit)."""
        remaining = max(0, self._file_limit - len(self.filepaths))
        paths = []
        for root, _dirs, files in os.walk(directory):
            for f in sorted(files):
                if len(paths) >= remaining:
                    return paths
                paths.append(os.path.join(root, f))
        return paths

    def _report_add_results(self, added, duplicates, rejected, hit_limit=False):
        """Show status and popup for file-add results."""
        parts = []
        if added > 0:
            parts.append(f"Added {added} file{'s' if added != 1 else ''}")
        if duplicates > 0:
            parts.append(f"{duplicates} duplicate{'s' if duplicates != 1 else ''} skipped")
        if hit_limit:
            parts.append(f"Limit reached ({self._file_limit})")

        if rejected:
            parts.append(f"{len(rejected)} rejected")
            self._set_status(" | ".join(parts))
            self._show_rejected_dialog(rejected)
        elif parts:
            self._set_status(" | ".join(parts))
        else:
            self._set_status("No new files added")

    def _show_rejected_dialog(self, rejected):
        """Show rejected files in a scrollable dialog."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Rejected Files")
        dlg.geometry("480x320")
        dlg.resizable(True, True)
        dlg.transient(self)

        n = len(rejected)
        ctk.CTkLabel(dlg,
                      text=f"{n} file{'s' if n != 1 else ''} could not be added:",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      anchor="w").pack(fill="x", padx=16, pady=(14, 6))

        text_frame = ctk.CTkFrame(dlg, corner_radius=6)
        text_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        textbox = ctk.CTkTextbox(text_frame, font=ctk.CTkFont(size=12),
                                  wrap="word", activate_scrollbars=True)
        textbox.pack(fill="both", expand=True, padx=4, pady=4)
        for name, reason in rejected:
            textbox.insert("end", f"{name}\n  {reason}\n\n")
        textbox.configure(state="disabled")

        ctk.CTkButton(dlg, text="OK", width=100, height=32,
                       command=dlg.destroy).pack(pady=(0, 14))

        dlg.after(200, dlg.grab_set)

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select AVL output files",
            filetypes=[("All files", "*.*")],
        )
        if not paths:
            return
        added, duplicates, rejected, hit_limit = self._add_paths(paths)
        self._report_add_results(added, duplicates, rejected, hit_limit)

    def add_folder(self):
        directory = filedialog.askdirectory(title="Select folder with AVL files")
        if not directory:
            return
        paths = self._collect_files_from_dir(directory)
        if not paths:
            self._set_status("No files found in folder")
            return
        added, duplicates, rejected, hit_limit = self._add_paths(paths)
        self._report_add_results(added, duplicates, rejected, hit_limit)

    def _on_drop(self, event):
        """Handle drag & drop of files and folders."""
        raw = event.data
        # tkinterdnd2 wraps paths with spaces in {}, others are space-separated
        parsed = re.findall(r'\{(.+?)\}|(\S+)', raw)
        drop_paths = [p[0] or p[1] for p in parsed]

        all_files = []
        for path in drop_paths:
            if os.path.isdir(path):
                all_files.extend(self._collect_files_from_dir(path))
            elif os.path.isfile(path):
                all_files.append(path)

        if not all_files:
            self._set_status("No valid files in drop")
            return
        added, duplicates, rejected, hit_limit = self._add_paths(all_files)
        self._report_add_results(added, duplicates, rejected, hit_limit)

    def clear_files(self):
        self.filepaths.clear()
        self.file_listbox.delete(0, "end")
        self._update_count()
        self._set_status("Cleared all files")

    def remove_selected(self):
        selected = list(self.file_listbox.curselection())
        if not selected:
            return
        for i in reversed(selected):
            self.file_listbox.delete(i)
            del self.filepaths[i]
        self._update_count()
        self._set_status(f"Removed {len(selected)} files")

    def _build_filename(self, stats, mode):
        """Build a descriptive default filename from export stats."""
        if mode == "Full Analysis":
            parts = ["avl_full"]
            a = stats.get('alpha_stats')
            if a:
                parts.append(f"{len(a['var_values'])}Alpha")
            b = stats.get('beta_stats')
            if b:
                parts.append(f"{len(b['var_values'])}Beta")
            td = stats.get('td_stats')
            if td:
                parts.append(f"{len(td['machs'])}Mach")
                for surface_name in SURFACE_SUFFIX:
                    vals = td['surface_values'].get(surface_name, [])
                    if vals:
                        parts.append(f"{len(vals)}{surface_name}")
            return "_".join(parts) + ".mat"
        elif mode == "3D Tables":
            angle = stats['angle_var']
            n_angle = len(stats.get('angle_values', []))
            n_mach = len(stats['machs'])
            parts = [f"avl_3d_{n_angle}{angle}_{n_mach}Mach"]
            for surface_name in SURFACE_SUFFIX:
                vals = stats['surface_values'].get(surface_name, [])
                if vals:
                    parts.append(f"{len(vals)}{surface_name}")
            return "_".join(parts) + ".mat"
        else:
            sv = stats['second_var']
            n_v = len(stats['var_values'])
            n_m = len(stats['machs'])
            return f"avl_{n_v}{sv}_x_{n_m}Mach.mat"

    def _show_progress(self, determinate=False):
        """Show the progress bar inline in the status bar."""
        if determinate:
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)
        else:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
        self.progress_bar.pack(side="right", padx=(8, 12), pady=8)
        self.update()

    def _hide_progress(self):
        """Hide and reset the progress bar."""
        self.progress_bar.stop()
        self.progress_bar.pack_forget()

    def _progress_callback(self, step, total):
        """Called by process_files_full between passes (throttled)."""
        now = time.monotonic()
        # Only update UI at most every 100 ms, or on the final step
        if step < total and (now - self._last_progress_time) < 0.1:
            return
        self._last_progress_time = now
        self.progress_bar.set(step / total)
        self._set_status(f"Processing... ({step}/{total})")
        self.update_idletasks()

    def _validate_files_pre_export(self):
        """Check files for angle and deflection conflicts before export.

        Returns (ok, angle_violations, defl_violations) where each violations
        list contains (filename, detail_string) tuples.
        """
        check_angle = self.check_single_angle.get()
        check_defl = self.check_single_defl.get()
        angle_violations = []
        defl_violations = []

        for filepath in self.filepaths:
            filename = os.path.basename(filepath)
            try:
                _mach, run_vars, _coeffs, _warns = parse_file(filepath)
            except Exception:
                continue  # skip — will be caught during actual processing

            if check_angle:
                alpha = run_vars.get('Alpha')
                beta = run_vars.get('Beta')
                if alpha is not None and alpha != 0 and beta is not None and beta != 0:
                    angle_violations.append(
                        (filename, f"Alpha={alpha}, Beta={beta}"))

            if check_defl:
                nonzero = []
                for surface in ('FLAP', 'AIL', 'ELEV', 'RUDD'):
                    val = run_vars.get(surface)
                    if val is not None and val != 0:
                        nonzero.append(f"{surface}={val}")
                if len(nonzero) > 1:
                    defl_violations.append((filename, ", ".join(nonzero)))

        ok = not angle_violations and not defl_violations
        return ok, angle_violations, defl_violations

    def _show_validation_warning(self, angle_violations, defl_violations):
        """Show an attention-grabbing dialog listing validation violations."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Export Blocked")
        dlg.geometry("540x420")
        dlg.resizable(True, True)
        dlg.transient(self)

        total = len(angle_violations) + len(defl_violations)

        # --- Red warning banner with icon ---
        banner = ctk.CTkFrame(dlg, fg_color=("#e53935", "#b71c1c"),
                               corner_radius=0, height=56)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        ctk.CTkLabel(banner,
                      text="\u26A0",
                      font=ctk.CTkFont(size=24),
                      text_color="#FFD600",
                      anchor="center", width=40
                      ).pack(side="left", padx=(14, 0))
        ctk.CTkLabel(banner,
                      text=f"Export blocked  \u2014  {total} violation{'s' if total != 1 else ''}",
                      font=ctk.CTkFont(size=15, weight="bold"),
                      text_color="white",
                      anchor="w").pack(side="left", padx=(6, 16), expand=True, fill="x")

        # --- Subtitle ---
        ctk.CTkLabel(dlg,
                      text="The following files have conflicting parameters.\n"
                           "Fix the files or uncheck the validation options to proceed.",
                      font=ctk.CTkFont(size=12),
                      text_color=("gray40", "gray65"),
                      anchor="w", justify="left"
                      ).pack(fill="x", padx=18, pady=(10, 6))

        # --- Scrollable violation list ---
        text_frame = ctk.CTkFrame(dlg, corner_radius=6,
                                   border_width=1,
                                   border_color=("#d32f2f", "#c62828"))
        text_frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        textbox = ctk.CTkTextbox(text_frame, font=ctk.CTkFont(family="Courier", size=12),
                                  wrap="word", activate_scrollbars=True)
        textbox.pack(fill="both", expand=True, padx=4, pady=4)

        if angle_violations:
            textbox.insert("end", "BOTH ANGLES NON-ZERO\n")
            textbox.insert("end", "-" * 44 + "\n")
            for name, detail in angle_violations:
                textbox.insert("end", f"  {name}\n")
                textbox.insert("end", f"    -> {detail}\n\n")

        if angle_violations and defl_violations:
            textbox.insert("end", "\n")

        if defl_violations:
            textbox.insert("end", "MULTIPLE DEFLECTIONS NON-ZERO\n")
            textbox.insert("end", "-" * 44 + "\n")
            for name, detail in defl_violations:
                textbox.insert("end", f"  {name}\n")
                textbox.insert("end", f"    -> {detail}\n\n")

        textbox.configure(state="disabled")

        # --- Dismiss button ---
        ctk.CTkButton(dlg, text="OK", width=120, height=36,
                       fg_color=("#d32f2f", "#b71c1c"),
                       hover_color=("#b71c1c", "#8e0000"),
                       command=dlg.destroy).pack(pady=(0, 14))

        dlg.after(200, dlg.grab_set)

    def export_mat(self):
        if not self.filepaths:
            messagebox.showwarning("No files", "Please add AVL files first.")
            return

        mode = self.mode_var.get()

        # Pre-export validation (3D Tables and Full Analysis)
        if mode in ("3D Tables", "Full Analysis") and (self.check_single_angle.get() or self.check_single_defl.get()):
            ok, angle_viol, defl_viol = self._validate_files_pre_export()
            if not ok:
                self._show_validation_warning(angle_viol, defl_viol)
                return

        # Snapshot all UI values before spawning the worker thread
        filepaths = list(self.filepaths)
        if mode in ("3D Tables", "Full Analysis"):
            angle = self.angle_var.get()
            coeff_modes = {}
            for label, var in self.coeff_mode_vars.items():
                coeff_modes[label] = DISPLAY_TO_MODE[var.get()]
            fa_skip = self.check_fa_skip.get() if mode == "Full Analysis" else False
        else:
            sv = self.second_var.get()
            skip_conflicts = self.check_2d_conflicts.get()
            angle = None
            coeff_modes = None

        self._set_status("Processing...")
        self._show_progress(determinate=(mode == "Full Analysis"))
        self.export_btn.configure(state="disabled")
        self._last_progress_time = 0.0

        def _worker():
            """Run heavy processing off the main thread."""
            try:
                if mode == "Full Analysis":
                    mat_data, stats = process_files_full(
                        filepaths, angle_var=angle, coeff_modes=coeff_modes,
                        progress_cb=self._progress_callback,
                        skip_conflicts=fa_skip,
                    )
                elif mode == "3D Tables":
                    mat_data, stats = process_files_3d(
                        filepaths, angle_var=angle, coeff_modes=coeff_modes
                    )
                else:
                    mat_data, stats = process_files(filepaths, second_var=sv,
                                                       skip_conflicts=skip_conflicts)
                self.after(0, lambda m=mode, d=mat_data, s=stats:
                           self._export_finish(m, d, s))
            except ValueError as e:
                msg = str(e)
                self.after(0, lambda m=msg: self._export_error(
                    "Export failed", "Export failed — no valid files", m))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self._export_error(
                    "Unexpected error", f"Error: {m}", m))

        threading.Thread(target=_worker, daemon=True).start()

    def _export_error(self, title, status_msg, detail):
        """Handle export errors back on the main thread."""
        self._hide_progress()
        self.export_btn.configure(state="normal")
        self._set_status(status_msg)
        messagebox.showerror(title, detail)

    def _export_finish(self, mode, mat_data, stats):
        """Complete the export flow on the main thread (save dialog + report)."""
        self._hide_progress()
        self.export_btn.configure(state="normal")

        # Record config to history on successful export
        if mode in ("3D Tables", "Full Analysis"):
            self._record_config()

        default_name = self._build_filename(stats, mode)

        save_path = filedialog.asksaveasfilename(
            title="Save .mat file",
            defaultextension=".mat",
            filetypes=[("MATLAB file", "*.mat")],
            initialfile=default_name,
        )
        if not save_path:
            self._set_status("Export cancelled")
            return

        try:
            savemat(save_path, mat_data)
        except Exception as e:
            self._set_status(f"Error saving: {e}")
            messagebox.showerror("Save error", str(e))
            return

        # Build report
        if mode == "Full Analysis":
            msg = self._build_full_report(stats, save_path)
            na = stats['n_alpha_labels']
            nb = stats['n_beta_labels']
            nt = stats['n_td_labels']
            self._set_status(
                f"Full Analysis: {na} Alpha + {nb} Beta + {nt} CS coefficients"
            )
        elif mode == "3D Tables":
            msg = self._build_3d_report(stats, save_path)
            n3 = stats['n_3d']
            na = stats['n_2d_angle']
            ns = stats['n_2d_surface']
            self._set_status(
                f"Exported {stats['parsed']} files "
                f"({n3} 3D + {na} 2D-angle + {ns} 2D-surface)"
            )
        else:
            msg = self._build_2d_report(stats, save_path)
            sv_name = stats['second_var']
            self._set_status(f"Exported {stats['parsed']} files ({sv_name} x Mach)")

        has_issues = self._has_issues(stats, mode)
        title = "Export complete (with warnings)" if has_issues else "Export complete"
        self._show_report(title, msg)

    def _has_issues(self, stats, mode):
        """Check if any section has skipped/duplicate/warning issues."""
        if mode == "Full Analysis":
            for key in ('alpha_stats', 'beta_stats', 'td_stats'):
                s = stats.get(key)
                if s and (s.get('skipped') or s.get('duplicates') or s.get('warnings')):
                    return True
            return bool(stats.get('errors'))
        return stats.get('skipped') or stats.get('duplicates') or stats.get('warnings')

    # --- Report builders ---

    def _build_2d_report(self, stats, save_path):
        sv = stats['second_var']
        n_v = len(stats['var_values'])
        n_m = len(stats['machs'])

        msg = (f"Paired: Mach x {sv}\n"
               f"Parsed {stats['parsed']} files\n"
               f"{n_m} Mach number{'s' if n_m != 1 else ''}, "
               f"{n_v} {sv} value{'s' if n_v != 1 else ''}\n"
               f"{stats['n_labels']} coefficients\n\n"
               f"Saved to:\n{save_path}")

        if stats['skipped']:
            msg += f"\n\n--- Skipped ({len(stats['skipped'])}) ---"
            for name, reason in stats['skipped']:
                msg += f"\n  {name}: {reason}"

        if stats['duplicates']:
            msg += f"\n\n--- Duplicates ({len(stats['duplicates'])}) ---"
            for name, mach, var_val, replaced in stats['duplicates']:
                msg += (f"\n  {name} has same Mach={mach}, {sv}={var_val}"
                        f"\n    (overwrote {replaced})")

        if stats['warnings']:
            msg += f"\n\n--- Missing coefficients ---"
            for name, labels in stats['warnings'].items():
                msg += f"\n  {name}: {', '.join(labels)}"

        return msg

    def _build_3d_report(self, stats, save_path):
        angle = stats['angle_var']
        n_angle = len(stats.get('angle_values', []))
        n_m = len(stats['machs'])

        lines = [
            f"Mode: 3D Tables",
            f"Angle axis: {angle}",
            f"Parsed {stats['parsed']} files",
            f"{n_m} Mach values, {n_angle} {angle} values",
            "",
        ]

        # Per-surface summary
        for surface_name in SURFACE_SUFFIX:
            vals = stats['surface_values'].get(surface_name, [])
            if vals:
                lines.append(f"{surface_name}: {len(vals)} values {vals}")

        lines.append("")
        lines.append(f"{stats['n_3d']} coefficients as 3D "
                     f"({angle} x Mach x \u03b4)")
        lines.append(f"{stats['n_2d_angle']} coefficients as 2D "
                     f"({angle} x Mach)")
        lines.append(f"{stats['n_2d_surface']} coefficients as 2D "
                     f"(\u03b4 x Mach)")
        lines.append("")
        lines.append(f"Saved to:\n{save_path}")

        if stats['skipped']:
            lines.append(f"\n--- Skipped ({len(stats['skipped'])}) ---")
            for name, reason in stats['skipped']:
                lines.append(f"  {name}: {reason}")

        if stats['duplicates']:
            lines.append(f"\n--- Duplicates ({len(stats['duplicates'])}) ---")
            for name, info in stats['duplicates']:
                lines.append(f"  {name}: {info}")

        if stats['warnings']:
            lines.append(f"\n--- Missing coefficients ---")
            for name, labels in stats['warnings'].items():
                lines.append(f"  {name}: {', '.join(labels)}")

        return "\n".join(lines)

    def _build_full_report(self, stats, save_path):
        lines = ["Mode: Full Analysis", ""]

        # Alpha 2D section
        a = stats.get('alpha_stats')
        if a:
            n_a = len(a['var_values'])
            n_m = len(a['machs'])
            lines.append(f"--- Alpha x Mach (2D) ---")
            lines.append(f"Parsed {a['parsed']} files")
            lines.append(f"{n_a} Alpha values, {n_m} Mach values")
            lines.append(f"{stats['n_alpha_labels']} coefficients")
            if a['skipped']:
                lines.append(f"Skipped {len(a['skipped'])} files:")
                for name, reason in a['skipped']:
                    lines.append(f"  {name}: {reason}")
            if a['duplicates']:
                lines.append(f"Duplicates ({len(a['duplicates'])}):")
                for name, mach, var_val, replaced in a['duplicates']:
                    lines.append(f"  {name}: Mach={mach}, Alpha={var_val} (overwrote {replaced})")
            lines.append("")
        else:
            lines.append("--- Alpha x Mach (2D) ---")
            lines.append("No valid Alpha data found")
            lines.append("")

        # Beta 2D section
        b = stats.get('beta_stats')
        if b:
            n_b = len(b['var_values'])
            n_m = len(b['machs'])
            lines.append(f"--- Beta x Mach (2D) ---")
            lines.append(f"Parsed {b['parsed']} files")
            lines.append(f"{n_b} Beta values, {n_m} Mach values")
            lines.append(f"{stats['n_beta_labels']} coefficients (Beta_ prefix)")
            if b['skipped']:
                lines.append(f"Skipped {len(b['skipped'])} files:")
                for name, reason in b['skipped']:
                    lines.append(f"  {name}: {reason}")
            if b['duplicates']:
                lines.append(f"Duplicates ({len(b['duplicates'])}):")
                for name, mach, var_val, replaced in b['duplicates']:
                    lines.append(f"  {name}: Mach={mach}, Beta={var_val} (overwrote {replaced})")
            lines.append("")
        else:
            lines.append("--- Beta x Mach (2D) ---")
            lines.append("No valid Beta data found")
            lines.append("")

        # 3D section
        td = stats.get('td_stats')
        if td:
            angle = td['angle_var']
            n_angle = len(td.get('angle_values', []))
            n_m = len(td['machs'])
            lines.append(f"--- Control Surfaces (3D) ---")
            lines.append(f"Angle axis: {angle}")
            lines.append(f"Parsed {td['parsed']} files")
            lines.append(f"{n_m} Mach values, {n_angle} {angle} values")
            for surface_name in SURFACE_SUFFIX:
                vals = td['surface_values'].get(surface_name, [])
                if vals:
                    lines.append(f"{surface_name}: {len(vals)} values {vals}")
            lines.append(f"{td['n_3d']} 3D + {td['n_2d_angle']} 2D-angle"
                         f" + {td['n_2d_surface']} 2D-surface coefficients")
            if td['skipped']:
                lines.append(f"Skipped {len(td['skipped'])} files:")
                for name, reason in td['skipped']:
                    lines.append(f"  {name}: {reason}")
            lines.append("")
        else:
            lines.append("--- Control Surfaces (3D) ---")
            lines.append("No valid 3D data found")
            lines.append("")

        if stats.get('errors'):
            lines.append("--- Errors ---")
            for err in stats['errors']:
                lines.append(f"  {err}")
            lines.append("")

        lines.append(f"Saved to:\n{save_path}")
        return "\n".join(lines)

    # --- Helpers ---

    def _show_report(self, title, message):
        """Show a scrollable report dialog."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("500x400")
        dialog.resizable(True, True)
        dialog.transient(self)
        dialog.grab_set()

        textbox = ctk.CTkTextbox(dialog, font=("Courier", 13), wrap="word")
        textbox.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        textbox.insert("1.0", message)
        textbox.configure(state="disabled")

        close_btn = ctk.CTkButton(dialog, text="OK", width=100, height=32,
                                   command=dialog.destroy)
        close_btn.pack(pady=(0, 12))

        dialog.after(100, dialog.focus_force)

    def _on_limit_changed(self, *_args):
        """Enable the ✓ button when the user edits the limit field."""
        self._limit_apply_btn.configure(state="normal")

    def _apply_limit(self):
        """Apply the file limit from the entry field, trimming excess files."""
        try:
            val = int(self._limit_var.get().strip())
            if val < 1:
                val = 1
        except ValueError:
            val = self._file_limit  # revert to current
        self._file_limit = val
        self._limit_var.set(str(val))
        self._limit_apply_btn.configure(state="disabled")

        # Trim the file list if it exceeds the new limit
        if len(self.filepaths) > val:
            self.filepaths = self.filepaths[:val]
            self.file_listbox.delete(val, "end")
            self._update_count()

        self._persist()

    def _update_count(self):
        n = len(self.filepaths)
        if n == 0:
            self.count_label.configure(text="No files selected")
            # Show empty state, hide listbox
            self.list_inner.pack_forget()
            self.empty_state.pack(fill="both", expand=True, padx=8, pady=8)
        else:
            self.count_label.configure(text=f"{n} file{'s' if n != 1 else ''} selected")
            # Hide empty state, show listbox
            self.empty_state.pack_forget()
            self.list_inner.pack(fill="both", expand=True)

    def _set_status(self, text):
        self.status_label.configure(text=text)


if __name__ == '__main__':
    app = AVLParserApp()
    app.mainloop()
