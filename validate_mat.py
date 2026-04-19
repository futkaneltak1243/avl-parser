"""
AVL Mat Validator — companion app to AVL Parser.

Loads an exported .mat file and its source folder of AVL text files, then
verifies every value in the .mat matches the originating source file.

Three modes:
  1. Quick Report        — analyse everything and show matched/wrong/not-found
  2. Show Process        — animated walkthrough of all tables
  3. One Table Check     — animated walkthrough scoped to one coefficient

Requirements: pip install customtkinter scipy numpy
Read-only: never writes to .mat or source files.
"""

import os
import re
import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
import numpy as np
from scipy.io import loadmat

# Resolve app directory (next to EXE when frozen, else script dir)
def _app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, _app_dir())
from parse_avl import (parse_file, FileReadError, AVLFormatError,
                       PAIRABLE_VARS, SURFACE_SUFFIX, SUFFIX_TO_SURFACE,
                       SURFACE_COEFF_GROUPS, ALL_LABELS,
                       BETA_DIM, DIMS_3D)
from view_mat import (detect_mode, get_coefficients, detect_row_var,
                      detect_angle_var, get_2d_surface_labels,
                      classify_full_coefficients, coeff_surface)

# --- Theme (matches app.py) ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

TOL = 1e-6                      # absolute comparison tolerance
COL_W = 14                      # table column width (matches view_mat.py)
ROW_W = 8                       # table row-header width
STATUS_MATCH = "match"
STATUS_WRONG = "wrong"
STATUS_NOTFOUND = "notfound"


# --- Tooltip (copied from app.py for self-contained companion app) ---

class Tooltip:
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


# ======================================================================
# Data structures
# ======================================================================

@dataclass
class ParsedSource:
    """A single source AVL file that has been parsed."""
    filepath: str
    filename: str
    mach: float
    run_vars: dict
    coefficients: dict
    text: str  # full file contents, for display

    def matches(self, constraints: dict) -> bool:
        """Check whether this file satisfies all (var -> value) constraints."""
        for key, want in constraints.items():
            if key == 'mach':
                if not _close(self.mach, want):
                    return False
            else:
                have = self.run_vars.get(key)
                if have is None:
                    return False
                if not _close(have, want):
                    return False
        return True


@dataclass
class Cell:
    """One value in the .mat that needs to be validated."""
    coefficient: str          # e.g. 'CLtot' or 'Beta_CLa'
    label_in_file: str        # e.g. 'CLtot' (stripped of 'Beta_' prefix)
    indices: tuple            # (i, j) or (i, j, k)
    mat_value: float
    constraints: dict         # {'mach': 0.1, 'Alpha': 5.0, ...}
    table_id: str             # groups cells into tables for display

    # Populated during validation:
    source: ParsedSource | None = None
    text_value: float | None = None
    status: str = ""          # STATUS_MATCH / STATUS_WRONG / STATUS_NOTFOUND


@dataclass
class Table:
    """Display metadata for one 2D slice that will be rendered on screen."""
    table_id: str
    title: str                # e.g. 'CLtot'  or 'CLd01 (Alpha = 5.0)'
    row_name: str             # 'Alpha'
    row_vals: list
    col_name: str             # 'Mach'
    col_vals: list
    matrix: np.ndarray        # 2D slice for rendering
    cell_coords: dict = field(default_factory=dict)   # (i,j) -> (line, col_start, col_end)


def _close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < TOL


# ======================================================================
# Build validation plan
# ======================================================================

def load_sources(folder: str) -> tuple[list[ParsedSource], list[tuple]]:
    """Parse every regular file in folder. Return (sources, skipped)."""
    sources = []
    skipped = []
    try:
        names = sorted(os.listdir(folder))
    except OSError as e:
        raise ValueError(f"Cannot read folder: {e}")

    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            mach, run_vars, coeffs, _ = parse_file(path)
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            sources.append(ParsedSource(
                filepath=path, filename=name,
                mach=mach, run_vars=run_vars,
                coefficients=coeffs, text=text,
            ))
        except (FileReadError, AVLFormatError) as e:
            skipped.append((name, e.reason))
        except Exception as e:
            skipped.append((name, str(e)))

    return sources, skipped


def find_source(sources: list[ParsedSource], constraints: dict) -> ParsedSource | None:
    for src in sources:
        if src.matches(constraints):
            return src
    return None


def build_plan(mat_data: dict) -> tuple[list[Cell], list[Table], str]:
    """Walk a loaded mat dict and produce the cell list + render tables.

    Returns (cells, tables, mode_string).
    """
    mode = detect_mode(mat_data)
    if mode == 'full':
        return _plan_full(mat_data) + ('full',)
    if mode == '3d':
        return _plan_3d(mat_data) + ('3d',)
    return _plan_2d(mat_data) + ('2d',)


def _plan_2d(data) -> tuple[list[Cell], list[Table]]:
    cells = []
    tables = []
    coeffs = get_coefficients(data)
    row_name, row_vals = detect_row_var(data)
    machs = data['Mach_values'].flatten().tolist()
    row_vals = row_vals.tolist()

    for label in coeffs:
        if data[label].ndim != 2:
            continue
        tid = f"2d::{label}"
        tables.append(Table(
            table_id=tid, title=label,
            row_name=row_name, row_vals=row_vals,
            col_name='Mach', col_vals=machs,
            matrix=data[label],
        ))
        for i, rv in enumerate(row_vals):
            for j, mach in enumerate(machs):
                val = float(data[label][i, j])
                if np.isnan(val):
                    continue
                cells.append(Cell(
                    coefficient=label, label_in_file=label,
                    indices=(i, j), mat_value=val,
                    constraints={'mach': mach, row_name: rv},
                    table_id=tid,
                ))
    return cells, tables


def _plan_3d(data) -> tuple[list[Cell], list[Table]]:
    cells = []
    tables = []
    coeffs = get_coefficients(data)
    machs = data['Mach_values'].flatten().tolist()
    angle_name, angle_vals_arr = detect_angle_var(data)
    angle_vals = angle_vals_arr.tolist() if angle_name else []
    surf_2d_labels = get_2d_surface_labels(data)
    surface_vals = {
        s: data[f'{s}_values'].flatten().tolist()
        for s in DIMS_3D if f'{s}_values' in data
    }

    for label in coeffs:
        mat = data[label]
        surface = coeff_surface(label)
        if surface is None or surface not in surface_vals:
            continue
        svals = surface_vals[surface]
        # Beta_CLb lives in the mat as 'Beta_CLb' but is written in the AVL
        # file as 'CLb' — strip the prefix for source lookup.
        file_label = (label[len('Beta_'):]
                      if label.startswith('Beta_') else label)

        if mat.ndim == 3:
            # (n_angle, n_mach, n_surface) — one sub-table per angle
            for i, ang in enumerate(angle_vals):
                tid = f"3d::{label}::{i}"
                slc = mat[i, :, :].T  # rows=surface, cols=mach — to render
                tables.append(Table(
                    table_id=tid,
                    title=f"{label}  ({angle_name} = {ang:.2f})",
                    row_name=surface, row_vals=svals,
                    col_name='Mach', col_vals=machs,
                    matrix=slc,
                ))
                for k, sv in enumerate(svals):
                    for j, mach in enumerate(machs):
                        val = float(mat[i, j, k])
                        if np.isnan(val):
                            continue
                        cells.append(Cell(
                            coefficient=label, label_in_file=file_label,
                            indices=(i, j, k), mat_value=val,
                            constraints={
                                'mach': mach, angle_name: ang, surface: sv,
                            },
                            table_id=tid,
                        ))
        elif mat.ndim == 2 and label in surf_2d_labels:
            # (n_surface, n_mach) — angle must be zero
            tid = f"2ds::{label}"
            tables.append(Table(
                table_id=tid, title=f"{label}  ({angle_name} = 0)",
                row_name=surface, row_vals=svals,
                col_name='Mach', col_vals=machs,
                matrix=mat,
            ))
            for k, sv in enumerate(svals):
                for j, mach in enumerate(machs):
                    val = float(mat[k, j])
                    if np.isnan(val):
                        continue
                    cells.append(Cell(
                        coefficient=label, label_in_file=file_label,
                        indices=(k, j), mat_value=val,
                        constraints={
                            'mach': mach, surface: sv, angle_name: 0.0,
                        },
                        table_id=tid,
                    ))
        elif mat.ndim == 2:
            # (n_angle, n_mach) — 2d_angle for a surface (surface val varies)
            tid = f"2da::{label}"
            tables.append(Table(
                table_id=tid, title=f"{label}  ({surface} — any)",
                row_name=angle_name, row_vals=angle_vals,
                col_name='Mach', col_vals=machs,
                matrix=mat,
            ))
            for i, ang in enumerate(angle_vals):
                for j, mach in enumerate(machs):
                    val = float(mat[i, j])
                    if np.isnan(val):
                        continue
                    cells.append(Cell(
                        coefficient=label, label_in_file=file_label,
                        indices=(i, j), mat_value=val,
                        constraints={'mach': mach, angle_name: ang},
                        table_id=tid,
                    ))
    return cells, tables


def _plan_full(data) -> tuple[list[Cell], list[Table]]:
    cells = []
    tables = []
    coeffs = get_coefficients(data)
    alpha_coeffs, beta_coeffs, td_coeffs = classify_full_coefficients(coeffs, data)

    # --- Alpha 2D section ---
    if 'Alpha_Mach_values' in data and 'Alpha_values' in data:
        a_machs = data['Alpha_Mach_values'].flatten().tolist()
        a_vals = data['Alpha_values'].flatten().tolist()
        for label in alpha_coeffs:
            if data[label].ndim != 2:
                continue
            tid = f"full_a::{label}"
            tables.append(Table(
                table_id=tid, title=f"{label}  (Alpha section)",
                row_name='Alpha', row_vals=a_vals,
                col_name='Mach', col_vals=a_machs,
                matrix=data[label],
            ))
            for i, av in enumerate(a_vals):
                for j, mach in enumerate(a_machs):
                    val = float(data[label][i, j])
                    if np.isnan(val):
                        continue
                    cells.append(Cell(
                        coefficient=label, label_in_file=label,
                        indices=(i, j), mat_value=val,
                        constraints={'mach': mach, 'Alpha': av},
                        table_id=tid,
                    ))

    # --- Beta 2D section ---
    if 'Beta_Mach_values' in data and 'Beta_values' in data:
        b_machs = data['Beta_Mach_values'].flatten().tolist()
        b_vals = data['Beta_values'].flatten().tolist()
        for label in beta_coeffs:
            if data[label].ndim != 2:
                continue
            base = label[len('Beta_'):] if label.startswith('Beta_') else label
            tid = f"full_b::{label}"
            tables.append(Table(
                table_id=tid, title=f"{label}  (Beta section)",
                row_name='Beta', row_vals=b_vals,
                col_name='Mach', col_vals=b_machs,
                matrix=data[label],
            ))
            for i, bv in enumerate(b_vals):
                for j, mach in enumerate(b_machs):
                    val = float(data[label][i, j])
                    if np.isnan(val):
                        continue
                    cells.append(Cell(
                        coefficient=label, label_in_file=base,
                        indices=(i, j), mat_value=val,
                        constraints={'mach': mach, 'Beta': bv},
                        table_id=tid,
                    ))

    # --- 3D section (control surfaces) — same as _plan_3d ---
    if 'Mach_values' in data and td_coeffs:
        machs = data['Mach_values'].flatten().tolist()
        angle_var = (str(data['Angle_var'].flat[0])
                     if 'Angle_var' in data else 'Alpha')
        angle_vals = (data['Angle_values'].flatten().tolist()
                      if 'Angle_values' in data else [])
        surf_2d_labels = get_2d_surface_labels(data)
        surface_vals = {
            s: data[f'{s}_values'].flatten().tolist()
            for s in SURFACE_SUFFIX if f'{s}_values' in data
        }
        for label in td_coeffs:
            mat = data[label]
            surface = coeff_surface(label)
            if surface is None or surface not in surface_vals:
                continue
            svals = surface_vals[surface]

            # For Beta 3D arrays the mat variable is 'Beta_CLb' but the AVL
            # file line is 'CLb' — strip the prefix so find_source can match.
            file_label = (label[len('Beta_'):]
                          if label.startswith('Beta_') else label)

            if mat.ndim == 3:
                for i, ang in enumerate(angle_vals):
                    tid = f"full_3d::{label}::{i}"
                    slc = mat[i, :, :].T
                    tables.append(Table(
                        table_id=tid,
                        title=f"{label}  ({angle_var} = {ang:.2f})",
                        row_name=surface, row_vals=svals,
                        col_name='Mach', col_vals=machs,
                        matrix=slc,
                    ))
                    for k, sv in enumerate(svals):
                        for j, mach in enumerate(machs):
                            val = float(mat[i, j, k])
                            if np.isnan(val):
                                continue
                            cells.append(Cell(
                                coefficient=label, label_in_file=file_label,
                                indices=(i, j, k), mat_value=val,
                                constraints={
                                    'mach': mach, angle_var: ang,
                                    surface: sv,
                                },
                                table_id=tid,
                            ))
            elif mat.ndim == 2 and label in surf_2d_labels:
                tid = f"full_2ds::{label}"
                tables.append(Table(
                    table_id=tid, title=f"{label}  ({angle_var} = 0)",
                    row_name=surface, row_vals=svals,
                    col_name='Mach', col_vals=machs,
                    matrix=mat,
                ))
                for k, sv in enumerate(svals):
                    for j, mach in enumerate(machs):
                        val = float(mat[k, j])
                        if np.isnan(val):
                            continue
                        cells.append(Cell(
                            coefficient=label, label_in_file=file_label,
                            indices=(k, j), mat_value=val,
                            constraints={
                                'mach': mach, surface: sv, angle_var: 0.0,
                            },
                            table_id=tid,
                        ))
            elif mat.ndim == 2:
                tid = f"full_2da::{label}"
                tables.append(Table(
                    table_id=tid, title=f"{label}  ({surface} — any)",
                    row_name=angle_var, row_vals=angle_vals,
                    col_name='Mach', col_vals=machs,
                    matrix=mat,
                ))
                for i, ang in enumerate(angle_vals):
                    for j, mach in enumerate(machs):
                        val = float(mat[i, j])
                        if np.isnan(val):
                            continue
                        cells.append(Cell(
                            coefficient=label, label_in_file=file_label,
                            indices=(i, j), mat_value=val,
                            constraints={'mach': mach, angle_var: ang},
                            table_id=tid,
                        ))
    return cells, tables


# ======================================================================
# Per-cell validation
# ======================================================================

def resolve(cells: list[Cell], sources: list[ParsedSource]) -> None:
    """Fill in cell.source, cell.text_value, cell.status for every cell."""
    for cell in cells:
        src = find_source(sources, cell.constraints)
        cell.source = src
        if src is None:
            cell.status = STATUS_NOTFOUND
            continue
        text_val = src.coefficients.get(cell.label_in_file)
        cell.text_value = text_val
        if text_val is None:
            cell.status = STATUS_NOTFOUND
            continue
        if _close(text_val, cell.mat_value):
            cell.status = STATUS_MATCH
        else:
            cell.status = STATUS_WRONG


def walk_order(cells: list[Cell], tables: list[Table]) -> list[Cell]:
    """Sort cells table-by-table. Within a table, order by indices.

    Table order follows the rendering order in `tables`.  Not-found cells
    stay with their table (they still belong to it).
    """
    table_rank = {t.table_id: i for i, t in enumerate(tables)}
    def key(c: Cell):
        return (table_rank.get(c.table_id, 10**9), c.indices)
    return sorted(cells, key=key)


# ======================================================================
# Table rendering for on-screen display
# ======================================================================

def render_table(table: Table) -> str:
    """Render one table to a fixed-width string and record cell coords."""
    col_vals = table.col_vals
    row_vals = table.row_vals
    lines = []
    # Title + separator
    lines.append(f"  {table.title}")
    # Header row
    header = f"  {table.row_name:<{ROW_W}}"
    for m in col_vals:
        header += f'{"M=" + _fmt_axis(m):>{COL_W}}'
    lines.append(header)
    lines.append('  ' + '-' * (ROW_W + COL_W * len(col_vals)))

    # Data rows — record cell coords by (i, j) -> (line_index, col_start, col_end)
    table.cell_coords = {}
    for i, rv in enumerate(row_vals):
        row_line = f"  {rv:<{ROW_W}.2f}"
        for j in range(len(col_vals)):
            val = table.matrix[i, j]
            if np.isnan(val):
                cell_str = f'{"--":>{COL_W}}'
            else:
                cell_str = f'{val:>{COL_W}.6f}'
            col_start = len(row_line)
            row_line += cell_str
            col_end = len(row_line)
            line_idx_in_table = 3 + i  # relative to table's first line
            table.cell_coords[(i, j)] = (line_idx_in_table, col_start, col_end)
        lines.append(row_line)
    lines.append('')
    return '\n'.join(lines)


def _fmt_axis(v):
    """Short axis label, e.g. 0.1 -> '0.1', 5.0 -> '5.0'."""
    if abs(v - round(v)) < 1e-9:
        return f'{v:.1f}'
    return f'{v:g}'


# ======================================================================
# Main application window
# ======================================================================

class ValidatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AVL Mat Validator")
        self.geometry("950x680")
        self.minsize(800, 600)

        icon_path = os.path.join(_app_dir(), 'validator_icon.png')
        if os.path.isfile(icon_path):
            try:
                from PIL import Image, ImageTk
                icon_img = ImageTk.PhotoImage(Image.open(icon_path))
                self.iconphoto(True, icon_img)
                self._icon_ref = icon_img
            except Exception:
                pass

        self.mat_path: str | None = None
        self.folder_path: str | None = None

        # Cached analysis (invalidated when inputs change)
        self._mat_data = None
        self._cells: list[Cell] = []
        self._tables: list[Table] = []
        self._sources: list[ParsedSource] = []
        self._source_skipped: list[tuple] = []

        self._build_ui()

    def _build_ui(self):
        # HEADER
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(header, text="AVL Mat Validator",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkLabel(header,
                     text="Verify .mat values against source AVL files",
                     font=ctk.CTkFont(size=12),
                     text_color=("gray50", "gray60")).pack(side="left",
                                                           padx=(12, 0))

        # STATUS BAR (bottom)
        self.status_frame = ctk.CTkFrame(self, height=32, corner_radius=0,
                                         fg_color=("gray90", "gray18"))
        self.status_frame.pack(fill="x", side="bottom")
        self.status_frame.pack_propagate(False)
        self.status_label = ctk.CTkLabel(self.status_frame, text="Ready",
                                         font=ctk.CTkFont(size=12),
                                         text_color=("gray50", "gray60"),
                                         anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True,
                               padx=12, pady=4)

        # MAIN CONTENT
        main_area = ctk.CTkFrame(self, corner_radius=10,
                                 fg_color=("gray92", "gray17"))
        main_area.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # --- Inputs section ---
        inputs = ctk.CTkFrame(main_area, fg_color="transparent")
        inputs.pack(fill="x", padx=16, pady=(14, 8))

        # .mat row
        row1 = ctk.CTkFrame(inputs, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(row1, text=".mat file:", width=90, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=("gray30", "gray80")).pack(side="left")
        self.mat_label = ctk.CTkLabel(
            row1, text="(none selected)",
            font=ctk.CTkFont(size=12, family="Courier"),
            text_color=("gray50", "gray60"), anchor="w")
        self.mat_label.pack(side="left", fill="x", expand=True, padx=(4, 8))
        ctk.CTkButton(row1, text="Pick .mat", width=110, height=28,
                      command=self._pick_mat,
                      font=ctk.CTkFont(size=12)).pack(side="right")

        # folder row
        row2 = ctk.CTkFrame(inputs, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(row2, text="Source folder:", width=90, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=("gray30", "gray80")).pack(side="left")
        self.folder_label = ctk.CTkLabel(
            row2, text="(none selected)",
            font=ctk.CTkFont(size=12, family="Courier"),
            text_color=("gray50", "gray60"), anchor="w")
        self.folder_label.pack(side="left", fill="x", expand=True,
                               padx=(4, 8))
        ctk.CTkButton(row2, text="Pick folder", width=110, height=28,
                      command=self._pick_folder,
                      font=ctk.CTkFont(size=12)).pack(side="right")

        # --- Mode selector ---
        mode_row = ctk.CTkFrame(main_area, fg_color="transparent")
        mode_row.pack(fill="x", padx=16, pady=(8, 4))

        ctk.CTkLabel(mode_row, text="Mode:", width=90, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=("gray30", "gray80")).pack(side="left")

        self.mode_var = ctk.StringVar(value="Quick Report")
        self.mode_selector = ctk.CTkSegmentedButton(
            mode_row,
            values=["Quick Report", "Show Process", "One Table"],
            variable=self.mode_var,
            command=self._on_mode_change,
            font=ctk.CTkFont(size=12),
            height=32,
        )
        self.mode_selector.pack(side="left", fill="x", expand=True,
                                padx=(4, 0))

        # --- Mode-specific options (for One Table) ---
        self.options_frame = ctk.CTkFrame(main_area, fg_color="transparent")
        self.options_frame.pack(fill="x", padx=16, pady=(4, 4))

        self.table_picker_label = ctk.CTkLabel(
            self.options_frame, text="Table:", width=90, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray30", "gray80"))
        self.table_var = ctk.StringVar(value="(none)")
        self.table_menu = ctk.CTkOptionMenu(
            self.options_frame, variable=self.table_var,
            values=["(load inputs first)"],
            width=280, height=28, font=ctk.CTkFont(size=12),
            dynamic_resizing=False,
        )
        # Visibility toggled in _on_mode_change

        # --- Description / help ---
        self.desc_label = ctk.CTkLabel(
            main_area,
            text=self._desc_for("Quick Report"),
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray60"),
            justify="left", wraplength=860, anchor="w",
        )
        self.desc_label.pack(fill="x", padx=16, pady=(8, 0))

        # --- Start button (large, green) ---
        self.start_btn = ctk.CTkButton(
            main_area, text="Start Validation", height=44, corner_radius=8,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=("#2d8a4e", "#2d8a4e"),
            hover_color=("#247a42", "#247a42"),
            command=self._on_start, state="disabled",
        )
        self.start_btn.pack(fill="x", padx=16, pady=(14, 10), side="bottom")

        # Tooltip on buttons
        Tooltip(self.start_btn,
                "Loads the .mat, parses source files, and runs the selected mode")

        self._on_mode_change("Quick Report")

    # --- Mode-change handler ---
    def _on_mode_change(self, mode):
        self.desc_label.configure(text=self._desc_for(mode))
        for child in self.options_frame.winfo_children():
            child.pack_forget()
        if mode == "One Table":
            self.table_picker_label.pack(side="left")
            self.table_menu.pack(side="left", fill="x", expand=True,
                                 padx=(4, 0))
            self._refresh_table_menu()

    def _desc_for(self, mode):
        if mode == "Quick Report":
            return ("Analyse every cell and show a summary: how many matched, "
                    "how many are wrong, and how many source files are missing. "
                    "Expand each section to see the mat ↔ file pairs.")
        if mode == "Show Process":
            return ("Animated walkthrough of every table. Current cell is "
                    "highlighted gray; source file opens on the right. Match = "
                    "green, mismatch = red. Play / Pause / Step / Reset.")
        return ("Pick one coefficient table and step through it the same way "
                "as Show Process.")

    # --- File pickers ---
    def _pick_mat(self):
        initial = os.path.join(_app_dir(), 'output')
        if not os.path.isdir(initial):
            initial = _app_dir()
        path = filedialog.askopenfilename(
            title="Select .mat file", initialdir=initial,
            filetypes=[("MATLAB .mat", "*.mat"), ("All files", "*.*")],
        )
        if not path:
            return
        self.mat_path = path
        self.mat_label.configure(text=self._shorten(path))
        self._invalidate_cache()
        self._update_ready()

    def _pick_folder(self):
        initial = _app_dir()
        path = filedialog.askdirectory(title="Select source AVL folder",
                                       initialdir=initial)
        if not path:
            return
        self.folder_path = path
        self.folder_label.configure(text=self._shorten(path))
        self._invalidate_cache()
        self._update_ready()

    def _shorten(self, path):
        if len(path) <= 80:
            return path
        return "..." + path[-77:]

    def _invalidate_cache(self):
        self._mat_data = None
        self._cells = []
        self._tables = []
        self._sources = []
        self._source_skipped = []

    def _update_ready(self):
        ready = bool(self.mat_path and self.folder_path)
        self.start_btn.configure(state="normal" if ready else "disabled")
        if ready:
            self._set_status(f"Ready — {os.path.basename(self.mat_path)} "
                             f"vs {os.path.basename(self.folder_path)}")

    def _set_status(self, text):
        self.status_label.configure(text=text)

    # --- Start button ---
    def _on_start(self):
        if not self.mat_path or not self.folder_path:
            return
        try:
            self._ensure_analysed()
        except Exception as e:
            messagebox.showerror("Validation error", str(e), parent=self)
            self._set_status("Error")
            return
        mode = self.mode_var.get()
        if mode == "Quick Report":
            self._show_quick_report()
        elif mode == "Show Process":
            WalkthroughWindow(self, self._tables, self._cells,
                              filter_table_id=None)
        else:
            tid = self._selected_table_id()
            if tid is None:
                messagebox.showwarning(
                    "No table selected",
                    "Pick a coefficient table from the dropdown first.",
                    parent=self)
                return
            WalkthroughWindow(self, self._tables, self._cells,
                              filter_table_id=tid)

    def _ensure_analysed(self):
        if self._mat_data is not None and self._sources:
            return
        self._set_status("Loading .mat…")
        self.update_idletasks()
        self._mat_data = loadmat(self.mat_path)
        self._set_status("Parsing source files…")
        self.update_idletasks()
        self._sources, self._source_skipped = load_sources(self.folder_path)
        if not self._sources:
            skipped_report = "\n".join(f"  {n}: {r}"
                                       for n, r in self._source_skipped[:10])
            raise ValueError(
                "No valid AVL files found in the source folder.\n\n"
                + skipped_report)
        self._set_status("Building validation plan…")
        self.update_idletasks()
        cells, tables, mode = build_plan(self._mat_data)
        self._cells = cells
        self._tables = tables
        self._set_status(f"Validating {len(cells)} cells…")
        self.update_idletasks()
        resolve(cells, self._sources)
        n_m = sum(1 for c in cells if c.status == STATUS_MATCH)
        n_w = sum(1 for c in cells if c.status == STATUS_WRONG)
        n_n = sum(1 for c in cells if c.status == STATUS_NOTFOUND)
        self._set_status(f"Done — {n_m} matched, {n_w} wrong, "
                         f"{n_n} not found ({len(self._sources)} source files)")
        self._refresh_table_menu()

    def _refresh_table_menu(self):
        if not self._tables:
            self.table_menu.configure(values=["(load inputs first)"])
            self.table_var.set("(load inputs first)")
            return
        labels = [t.title for t in self._tables]
        self.table_menu.configure(values=labels)
        if self.table_var.get() not in labels:
            self.table_var.set(labels[0])

    def _selected_table_id(self):
        sel = self.table_var.get()
        for t in self._tables:
            if t.title == sel:
                return t.table_id
        return None

    # --- Mode 1 report ---
    def _show_quick_report(self):
        QuickReportDialog(self, self._cells, self._sources,
                          self._source_skipped)


# ======================================================================
# Mode 1 — Quick Report
# ======================================================================

class QuickReportDialog(ctk.CTkToplevel):
    def __init__(self, parent, cells, sources, source_skipped):
        super().__init__(parent)
        self.title("Quick Report")
        self.geometry("780x560")
        self.resizable(True, True)
        self.transient(parent)

        matched = [c for c in cells if c.status == STATUS_MATCH]
        wrong = [c for c in cells if c.status == STATUS_WRONG]
        notfound = [c for c in cells if c.status == STATUS_NOTFOUND]

        # --- Summary row (big counters) ---
        summary = ctk.CTkFrame(self, fg_color="transparent")
        summary.pack(fill="x", padx=16, pady=(14, 8))

        self._make_counter(summary, "Matched", len(matched),
                           "#2d8a4e").pack(side="left", expand=True, fill="x",
                                          padx=(0, 6))
        self._make_counter(summary, "Wrong", len(wrong),
                           "#c0392b").pack(side="left", expand=True, fill="x",
                                          padx=6)
        self._make_counter(summary, "Not Found", len(notfound),
                           "#c08a1e").pack(side="left", expand=True, fill="x",
                                          padx=(6, 0))

        # --- File stats ---
        stat_frame = ctk.CTkFrame(self, fg_color="transparent")
        stat_frame.pack(fill="x", padx=16, pady=(0, 8))
        n_src = len(sources)
        n_skip = len(source_skipped)
        ctk.CTkLabel(stat_frame,
                     text=f"Total cells: {len(cells)}    "
                          f"Source files parsed: {n_src}    "
                          f"Skipped: {n_skip}",
                     font=ctk.CTkFont(size=12),
                     text_color=("gray50", "gray60")
        ).pack(anchor="w")

        # --- Tabbed details ---
        tabs = ctk.CTkTabview(self, fg_color=("gray92", "gray17"))
        tabs.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        for name, items, color in [("Wrong", wrong, "#c0392b"),
                                   ("Not Found", notfound, "#c08a1e"),
                                   ("Matched", matched, "#2d8a4e")]:
            tabs.add(name)
            tab = tabs.tab(name)
            self._fill_tab(tab, items, color)

        # Default tab: wrong if any, else not-found, else matched
        if wrong:
            tabs.set("Wrong")
        elif notfound:
            tabs.set("Not Found")
        else:
            tabs.set("Matched")

        ctk.CTkButton(self, text="Close", width=100, height=32,
                      command=self.destroy).pack(pady=(0, 12))

        self.after(100, self.focus_force)

    def _make_counter(self, parent, label, count, color):
        frame = ctk.CTkFrame(parent, corner_radius=8,
                             fg_color=("gray88", "#252525"),
                             border_width=2, border_color=color)
        ctk.CTkLabel(frame, text=label,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=("gray30", "gray80")
        ).pack(pady=(10, 0))
        ctk.CTkLabel(frame, text=str(count),
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color=color
        ).pack(pady=(2, 10))
        return frame

    def _fill_tab(self, tab, items, color):
        if not items:
            ctk.CTkLabel(tab, text="(none)",
                         font=ctk.CTkFont(size=13),
                         text_color=("gray50", "gray60")
            ).pack(expand=True)
            return

        tb = ctk.CTkTextbox(tab, font=("Courier", 12), wrap="none")
        tb.pack(fill="both", expand=True, padx=8, pady=8)

        for cell in items:
            tb.insert("end", _format_cell_report_line(cell) + "\n")

        tb.tag_config("colored", foreground=color)
        tb.tag_add("colored", "1.0", "end")
        tb.configure(state="disabled")


def _format_cell_report_line(cell: Cell) -> str:
    idx_str = ",".join(str(i) for i in cell.indices)
    constr = ", ".join(f"{k}={_fmt_num(v)}"
                       for k, v in cell.constraints.items())
    if cell.status == STATUS_MATCH:
        return (f"  {cell.coefficient}[{idx_str}]  "
                f"mat={cell.mat_value:+.6f}  "
                f"file={cell.text_value:+.6f}  "
                f"({cell.source.filename})")
    if cell.status == STATUS_WRONG:
        diff = cell.mat_value - (cell.text_value or 0)
        return (f"  {cell.coefficient}[{idx_str}]  "
                f"mat={cell.mat_value:+.6f}  "
                f"file={cell.text_value:+.6f}  "
                f"diff={diff:+.6e}  "
                f"({cell.source.filename})")
    # not found
    if cell.source is None:
        return (f"  {cell.coefficient}[{idx_str}]  "
                f"mat={cell.mat_value:+.6f}  "
                f"(no source file for {constr})")
    return (f"  {cell.coefficient}[{idx_str}]  "
            f"mat={cell.mat_value:+.6f}  "
            f"({cell.coefficient} missing in {cell.source.filename})")


def _fmt_num(v):
    if isinstance(v, (int, float)):
        if abs(v - round(v)) < 1e-9:
            return f"{v:g}"
        return f"{v:g}"
    return str(v)


# ======================================================================
# Modes 2 & 3 — Show Process (animated walkthrough)
# ======================================================================

class WalkthroughWindow(ctk.CTkToplevel):
    def __init__(self, parent, tables, cells, filter_table_id=None):
        super().__init__(parent)
        title = ("Show Process — One Table" if filter_table_id
                 else "Show Process")
        self.title(title)
        self.geometry("1200x780")
        self.minsize(1000, 600)
        self.transient(parent)

        # Filter to selected table (for Mode 3)
        if filter_table_id:
            tables = [t for t in tables if t.table_id == filter_table_id]
            cells = [c for c in cells if c.table_id == filter_table_id]

        self.tables = tables
        self.cells_ordered = walk_order(cells, tables)
        self.table_by_id = {t.table_id: t for t in tables}
        self.table_index = {t.table_id: i for i, t in enumerate(tables)}
        self.current_index = -1
        self.active_table_id: str | None = None
        self.playing = False
        self.delay_ms = 500
        self.current_source_filename: str | None = None

        # Animation state: each cell is a 2-phase reveal.
        #   phase A (gray highlight + open file) → _gray_hold_frac of delay
        #   phase B (flip to green/red)          → remaining delay
        self._gray_hold_frac = 0.45
        self._min_gray_ms = 0
        self._pending_finish_id = None     # after_id for phase B
        self._pending_tick_id = None       # after_id for next tick
        self._active_left_tag_loc = None   # (line, c0, c1) to clear
        self._active_right_tag_loc = None  # (line, c0, c1) to clear

        self._matched = 0
        self._wrong = 0
        self._missing = 0

        self._build_ui()
        # Show the first table up-front so the user sees something immediately.
        if self.tables:
            self._render_active_table(self.tables[0].table_id)
        self.after(100, self.focus_force)

    # --- UI ---
    def _build_ui(self):
        # Status banner (current cell being checked — big and prominent)
        banner = ctk.CTkFrame(self, corner_radius=10,
                              fg_color=("gray88", "#202020"),
                              border_width=1,
                              border_color=("gray75", "gray25"))
        banner.pack(fill="x", padx=12, pady=(12, 4))

        self.banner_title = ctk.CTkLabel(
            banner, text="Idle — press Play to start",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("gray30", "gray80"), anchor="w")
        self.banner_title.pack(fill="x", padx=14, pady=(10, 2))

        self.banner_detail = ctk.CTkLabel(
            banner, text=" ",
            font=ctk.CTkFont(size=12, family="Courier"),
            text_color=("gray40", "gray70"), anchor="w", justify="left")
        self.banner_detail.pack(fill="x", padx=14, pady=(0, 10))

        # Counters + controls row
        top = ctk.CTkFrame(self, fg_color=("gray92", "gray17"),
                           corner_radius=10)
        top.pack(fill="x", padx=12, pady=(4, 6))

        counters = ctk.CTkFrame(top, fg_color="transparent")
        counters.pack(side="left", padx=10, pady=6)

        self.matched_label = ctk.CTkLabel(
            counters, text="✓ Matched: 0",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#2d8a4e")
        self.matched_label.pack(side="left", padx=(0, 16))

        self.wrong_label = ctk.CTkLabel(
            counters, text="✗ Wrong: 0",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#c0392b")
        self.wrong_label.pack(side="left", padx=(0, 16))

        self.missing_label = ctk.CTkLabel(
            counters, text="? Missing: 0",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#c08a1e")
        self.missing_label.pack(side="left")

        # Progress
        self.progress_label = ctk.CTkLabel(
            top, text=f"0 / {len(self.cells_ordered)}",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray60"))
        self.progress_label.pack(side="right", padx=10, pady=6)

        # Controls row
        ctrls = ctk.CTkFrame(self, fg_color="transparent")
        ctrls.pack(fill="x", padx=12, pady=(0, 6))

        self.play_btn = ctk.CTkButton(
            ctrls, text="▶ Play", width=80, height=32,
            command=self._toggle_play,
            font=ctk.CTkFont(size=12, weight="bold"))
        self.play_btn.pack(side="left")

        ctk.CTkButton(ctrls, text="Step ▷", width=80, height=32,
                      command=self._step_once,
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(6, 0))

        ctk.CTkButton(ctrls, text="Reset", width=80, height=32,
                      fg_color=("gray70", "gray30"),
                      hover_color=("gray60", "gray40"),
                      command=self._reset,
                      font=ctk.CTkFont(size=12)).pack(side="left", padx=(6, 0))

        # Speed slider
        ctk.CTkLabel(ctrls, text="Speed:", font=ctk.CTkFont(size=12),
                     text_color=("gray50", "gray60")
        ).pack(side="left", padx=(20, 4))
        # Slider: left = slow, right = fast.  CTkSlider supports reversed
        # ranges by passing from_ > to, so dragging right lowers delay_ms.
        self.speed_var = ctk.IntVar(value=self.delay_ms)
        self.speed_slider = ctk.CTkSlider(
            ctrls, from_=1500, to=10, number_of_steps=149,
            variable=self.speed_var,
            command=lambda v: self._on_speed_change(v), width=200)
        self.speed_slider.pack(side="left")
        self.speed_label = ctk.CTkLabel(
            ctrls, text=f"{self.delay_ms} ms", width=64,
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"))
        self.speed_label.pack(side="left", padx=(6, 0))

        # Split pane
        body = ctk.CTkFrame(self, fg_color=("gray92", "gray17"),
                            corner_radius=10)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        body.columnconfigure(0, weight=1, uniform="panes")
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=1, uniform="panes")
        body.rowconfigure(0, weight=1)

        # Left pane — one table at a time
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=10)

        self.left_header_label = ctk.CTkLabel(
            left, text="Mat table  —  (no table active)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray30", "gray80"))
        self.left_header_label.pack(anchor="w", pady=(0, 4))

        self.left_tb = ctk.CTkTextbox(left, font=("Courier", 12), wrap="none")
        self.left_tb.pack(fill="both", expand=True)
        self._config_tags(self.left_tb)

        # Divider
        ctk.CTkFrame(body, width=1, fg_color=("gray80", "gray30")
        ).grid(row=0, column=1, sticky="ns", pady=12)

        # Right pane — source file
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(4, 10), pady=10)

        self.right_header_label = ctk.CTkLabel(
            right, text="Source file  —  (none open)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray30", "gray80"))
        self.right_header_label.pack(anchor="w", pady=(0, 4))

        self.right_tb = ctk.CTkTextbox(right, font=("Courier", 12), wrap="none")
        self.right_tb.pack(fill="both", expand=True)
        self._config_tags(self.right_tb)

    def _config_tags(self, tb):
        try:
            inner = tb._textbox
        except AttributeError:
            inner = tb
        # Priorities: final verdict colours sit on top of 'current'.
        inner.tag_config("current", background="#3d3d3d", foreground="#f2f2f2")
        inner.tag_config("match",
                         background="#1f6b3d", foreground="#e9ffe9")
        inner.tag_config("wrong",
                         background="#8a2a20", foreground="#ffeaea")
        inner.tag_config("missing",
                         background="#7a5a14", foreground="#fff3d1")
        inner.tag_raise("match")
        inner.tag_raise("wrong")
        inner.tag_raise("missing")

    # --- Left-pane layout ---
    def _render_active_table(self, table_id: str):
        """Render a single table into the left textbox, replacing any prior one."""
        table = self.table_by_id.get(table_id)
        if table is None:
            return
        self.active_table_id = table_id

        tb = self.left_tb
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        # render_table records cell_coords relative to table start (line 1)
        tb.insert("end", render_table(table))
        tb.configure(state="disabled")

        idx1 = self.table_index[table_id] + 1
        total = len(self.tables)
        self.left_header_label.configure(
            text=f"Mat table  {idx1} / {total}  —  {table.title}")

    def _cell_line_col(self, cell: Cell) -> tuple[int, int, int] | None:
        """Return (line_1based, col_start, col_end) for a cell in the
        currently-rendered single table."""
        if cell.table_id != self.active_table_id:
            return None
        table = self.table_by_id.get(cell.table_id)
        if table is None:
            return None
        # 2D indices vs 3D indices: 3D tables are sliced on i (angle)
        if len(cell.indices) == 2:
            ij = cell.indices
        else:
            _, j, k = cell.indices
            ij = (k, j)
        if ij not in table.cell_coords:
            return None
        line_offset, col_start, col_end = table.cell_coords[ij]
        # render_table's offsets are relative to table start; start line is 1
        return line_offset + 1, col_start, col_end

    # --- Playback ---
    def _on_speed_change(self, v):
        ms = int(float(v))
        self.delay_ms = ms
        self.speed_label.configure(text=f"{ms} ms")

    def _toggle_play(self):
        if self.playing:
            self._pause()
            return
        if self.current_index + 1 >= len(self.cells_ordered):
            return
        self.playing = True
        self.play_btn.configure(text="❚❚ Pause")
        self._start_next_step()

    def _pause(self):
        self.playing = False
        self.play_btn.configure(text="▶ Play")
        if self._pending_tick_id is not None:
            self.after_cancel(self._pending_tick_id)
            self._pending_tick_id = None

    def _step_once(self):
        """Advance by one full gray→color reveal. Cancels any in-flight tick."""
        if self.playing:
            self._pause()
        if self._pending_tick_id is not None:
            self.after_cancel(self._pending_tick_id)
            self._pending_tick_id = None
        if self._pending_finish_id is not None:
            # an earlier cell is still on its gray hold — flush it immediately
            self.after_cancel(self._pending_finish_id)
            self._pending_finish_id = None
            self._finish_step()
        self._begin_step(then_finish_and_continue=False)

    def _reset(self):
        self._pause()
        if self._pending_finish_id is not None:
            self.after_cancel(self._pending_finish_id)
            self._pending_finish_id = None
        self.current_index = -1
        self._matched = 0
        self._wrong = 0
        self._missing = 0
        self._update_counters()
        # Reset right pane
        self._clear_all_highlights(self.right_tb)
        self.right_tb.configure(state="normal")
        self.right_tb.delete("1.0", "end")
        self.right_tb.configure(state="disabled")
        self.right_header_label.configure(text="Source file  —  (none open)")
        self.current_source_filename = None
        # Reset left pane to the first table (re-render clears all highlights)
        if self.tables:
            self._render_active_table(self.tables[0].table_id)
        self.progress_label.configure(
            text=f"0 / {len(self.cells_ordered)}")
        self._active_left_tag_loc = None
        self._active_right_tag_loc = None
        self._set_banner_idle()

    # --- Two-phase reveal ---

    def _start_next_step(self):
        """Schedule the next begin_step (for auto-play)."""
        self._pending_tick_id = self.after(10,
            lambda: self._begin_step(then_finish_and_continue=True))

    def _begin_step(self, then_finish_and_continue: bool):
        """Phase A: pick next cell, show gray highlight + open source file.

        Schedule phase B (flip to final colour) after gray-hold.
        """
        self._pending_tick_id = None
        if self.current_index + 1 >= len(self.cells_ordered):
            self._pause()
            self._set_banner_done()
            return
        self.current_index += 1
        cell = self.cells_ordered[self.current_index]
        self._current_cell = cell

        # Swap the left pane if this cell belongs to a different table.
        if cell.table_id != self.active_table_id:
            self._render_active_table(cell.table_id)

        # Right pane: swap file if needed
        new_fname = cell.source.filename if cell.source else None
        if new_fname != self.current_source_filename:
            self.current_source_filename = new_fname
            self._load_source_pane(cell.source)

        # Phase A highlight — gray (left cell)
        loc = self._cell_line_col(cell)
        if loc is not None:
            line, c0, c1 = loc
            self._tag(self.left_tb, line, c0, c1, "current")
            # Scroll to the tag itself (wrap=none means col 0 isn't enough).
            self.left_tb.see(f"{line}.{c1}")
            self.left_tb.see(f"{line}.{max(0, c0 - 4)}")
            self._active_left_tag_loc = (line, c0, c1)
        else:
            self._active_left_tag_loc = None

        # Phase A highlight — gray (right value span only)
        if cell.source is not None:
            span = _find_label_span(cell.source.text, cell.label_in_file)
            if span is not None:
                rline, rc0, rc1 = span
                self._tag(self.right_tb, rline, rc0, rc1, "current")
                self.right_tb.see(f"{rline}.{rc1}")
                self.right_tb.see(f"{rline}.{max(0, rc0 - 4)}")
                self._active_right_tag_loc = (rline, rc0, rc1)
            else:
                self._active_right_tag_loc = None
        else:
            self._active_right_tag_loc = None

        self._set_banner(cell, phase="check")
        self.progress_label.configure(
            text=f"{self.current_index + 1} / {len(self.cells_ordered)}")

        gray_ms = max(self._min_gray_ms,
                      int(self.delay_ms * self._gray_hold_frac))
        if then_finish_and_continue:
            self._pending_finish_id = self.after(
                gray_ms, self._finish_step_and_continue)
        else:
            self._pending_finish_id = self.after(
                gray_ms, self._finish_step)

    def _finish_step_and_continue(self):
        self._finish_step()
        if self.playing:
            rest = max(30, self.delay_ms - int(
                self.delay_ms * self._gray_hold_frac))
            self._pending_tick_id = self.after(
                rest, lambda: self._begin_step(then_finish_and_continue=True))

    def _finish_step(self):
        """Phase B: remove gray, apply final match/wrong/missing colour."""
        self._pending_finish_id = None
        cell = getattr(self, "_current_cell", None)
        if cell is None:
            return

        tag = self._status_tag(cell.status)

        if self._active_left_tag_loc is not None:
            line, c0, c1 = self._active_left_tag_loc
            self._remove_tag(self.left_tb, "current", line, c0, c1)
            self._tag(self.left_tb, line, c0, c1, tag)
            self._active_left_tag_loc = None

        if self._active_right_tag_loc is not None:
            line, c0, c1 = self._active_right_tag_loc
            self._remove_tag(self.right_tb, "current", line, c0, c1)
            self._tag(self.right_tb, line, c0, c1, tag)
            self._active_right_tag_loc = None

        if cell.status == STATUS_MATCH:
            self._matched += 1
        elif cell.status == STATUS_WRONG:
            self._wrong += 1
        else:
            self._missing += 1
        self._update_counters()
        self._set_banner(cell, phase="result")

    # --- Banner ---

    def _set_banner_idle(self):
        self.banner_title.configure(text="Idle — press Play to start",
                                    text_color=("gray30", "gray80"))
        self.banner_detail.configure(text=" ")

    def _set_banner_done(self):
        total = self._matched + self._wrong + self._missing
        if self._wrong == 0 and self._missing == 0:
            self.banner_title.configure(
                text=f"✓ Done — all {total} values matched",
                text_color="#2d8a4e")
        else:
            self.banner_title.configure(
                text=f"Done — {self._matched} matched, "
                     f"{self._wrong} wrong, {self._missing} missing",
                text_color=("gray25", "#e6e6e6"))
        self.banner_detail.configure(text=" ")

    def _set_banner(self, cell: Cell, phase: str):
        idx_str = ",".join(str(i) for i in cell.indices)
        constr = "  ".join(f"{k}={_fmt_num(v)}"
                           for k, v in cell.constraints.items())
        file_str = cell.source.filename if cell.source else "(no source)"
        if phase == "check":
            title = f"Checking  {cell.coefficient}[{idx_str}]"
            colour = ("gray25", "#e6e6e6")
            mat_s = f"mat = {cell.mat_value:+.6f}"
            file_s = (f"file = {cell.text_value:+.6f}"
                      if cell.text_value is not None else "file = ?")
            detail = f"{mat_s}      {file_s}      {constr}      [{file_str}]"
        else:
            if cell.status == STATUS_MATCH:
                title = f"✓ MATCH  {cell.coefficient}[{idx_str}]"
                colour = "#2d8a4e"
            elif cell.status == STATUS_WRONG:
                title = f"✗ WRONG  {cell.coefficient}[{idx_str}]"
                colour = "#c0392b"
            else:
                title = f"? MISSING  {cell.coefficient}[{idx_str}]"
                colour = "#c08a1e"
            if cell.text_value is not None:
                diff = cell.mat_value - cell.text_value
                detail = (f"mat = {cell.mat_value:+.6f}   "
                          f"file = {cell.text_value:+.6f}   "
                          f"diff = {diff:+.2e}   "
                          f"{constr}   [{file_str}]")
            else:
                detail = (f"mat = {cell.mat_value:+.6f}   "
                          f"file = (not found)   {constr}   [{file_str}]")
        self.banner_title.configure(text=title, text_color=colour)
        self.banner_detail.configure(text=detail)

    def _status_tag(self, status: str) -> str:
        if status == STATUS_MATCH:
            return "match"
        if status == STATUS_WRONG:
            return "wrong"
        return "missing"

    def _update_counters(self):
        self.matched_label.configure(text=f"✓ Matched: {self._matched}")
        self.wrong_label.configure(text=f"✗ Wrong: {self._wrong}")
        self.missing_label.configure(text=f"? Missing: {self._missing}")

    # --- Right-pane helpers ---
    def _load_source_pane(self, source: ParsedSource | None):
        tb = self.right_tb
        tb.configure(state="normal")
        tb.delete("1.0", "end")
        self._clear_all_highlights(tb)
        if source is None:
            tb.insert("1.0", "(no source file matched for this cell)")
            self.right_header_label.configure(
                text="Source file  —  (not found)")
        else:
            tb.insert("1.0", source.text)
            self.right_header_label.configure(
                text=f"Source file  —  {source.filename}")
        tb.configure(state="disabled")

    # --- Raw textbox tag helpers ---
    def _raw(self, tb):
        try:
            return tb._textbox
        except AttributeError:
            return tb

    def _tag(self, tb, line, col_start, col_end, tag):
        self._raw(tb).tag_add(
            tag, f"{line}.{col_start}", f"{line}.{col_end}")

    def _remove_tag(self, tb, tag, line, col_start, col_end):
        self._raw(tb).tag_remove(
            tag, f"{line}.{col_start}", f"{line}.{col_end}")

    def _clear_all_highlights(self, tb):
        inner = self._raw(tb)
        for t in ("current", "match", "wrong", "missing"):
            inner.tag_remove(t, "1.0", "end")


def _find_label_span(text: str, label: str) -> tuple[int, int, int] | None:
    """Return (line_1based, col_start, col_end) covering 'LABEL = VALUE'.

    A single AVL line often holds several LABEL=VALUE pairs
    (e.g. "CLa = 3.77   CLb = 0.006"), so we narrow the highlight
    to just the requested label's value, not the whole line.
    """
    pat = re.compile(
        r'(?<![A-Za-z])' + re.escape(label) + r'\s*=\s*[-+]?[\d.]+'
    )
    for i, line in enumerate(text.splitlines(), start=1):
        m = pat.search(line)
        if m:
            return i, m.start(), m.end()
    return None


# ======================================================================
# Entry point
# ======================================================================

def main():
    app = ValidatorApp()
    app.mainloop()


if __name__ == '__main__':
    main()
