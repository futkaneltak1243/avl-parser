"""
AVL Parser — Desktop App
Double-click to open. Select AVL files, then export to .mat for MATLAB.
Works on macOS and Windows.

Requirements: pip install customtkinter
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

# Ensure imports work when running from any directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_avl import (process_files, process_files_3d, validate_file,
                        ALL_LABELS, PAIRABLE_VARS, SURFACE_SUFFIX,
                        SURFACE_COEFF_GROUPS)

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


class AVLParserApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AVL Parser")
        self.geometry("600x620")
        self.minsize(500, 550)

        # Set window icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.png')
        if os.path.isfile(icon_path):
            from PIL import Image, ImageTk
            icon_img = ImageTk.PhotoImage(Image.open(icon_path))
            self.iconphoto(True, icon_img)
            self._icon_ref = icon_img  # prevent garbage collection

        self.filepaths = []

        self._build_ui()

    def _build_ui(self):
        # --- Main container ---
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=25, pady=20)

        # ============================================================
        # CREATE all widgets first, then PACK in correct order so that
        # the file list (expand=True) doesn't starve bottom widgets.
        # ============================================================

        # --- Header ---
        header_frame = ctk.CTkFrame(container, fg_color="transparent")

        title = ctk.CTkLabel(header_frame, text="AVL Parser",
                              font=ctk.CTkFont(size=26, weight="bold"))
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(header_frame,
                                 text="Select AVL output files and export to .mat for MATLAB",
                                 font=ctk.CTkFont(size=13),
                                 text_color=("gray50", "gray60"))
        subtitle.pack(anchor="w", pady=(2, 0))

        # --- Separator ---
        sep = ctk.CTkFrame(container, height=2, fg_color=("gray80", "gray30"))

        # --- Mode Selector ---
        mode_frame = ctk.CTkFrame(container, fg_color="transparent")

        mode_label = ctk.CTkLabel(mode_frame, text="Mode",
                                   font=ctk.CTkFont(size=12),
                                   text_color=("gray50", "gray60"))
        mode_label.pack(side="left", padx=(0, 10))

        self.mode_var = ctk.StringVar(value="2D Tables")
        self.mode_selector = ctk.CTkSegmentedButton(
            mode_frame,
            values=["2D Tables", "3D Tables"],
            variable=self.mode_var,
            command=self._on_mode_change,
            font=ctk.CTkFont(size=12),
            height=28,
        )
        self.mode_selector.pack(side="left")

        # --- Buttons row ---
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")

        self.add_btn = ctk.CTkButton(btn_frame, text="Add Files", command=self.add_files,
                                      width=140, height=36, font=ctk.CTkFont(size=13))
        self.add_btn.pack(side="left")

        self.clear_btn = ctk.CTkButton(btn_frame, text="Clear All", command=self.clear_files,
                                        width=120, height=36, font=ctk.CTkFont(size=13),
                                        fg_color=("gray70", "gray30"),
                                        hover_color=("gray60", "gray40"),
                                        text_color=("gray20", "gray90"))
        self.clear_btn.pack(side="right")

        # --- File count ---
        self.count_label = ctk.CTkLabel(container, text="No files selected",
                                         font=ctk.CTkFont(size=12),
                                         text_color=("gray50", "gray60"),
                                         anchor="w")

        # --- File list ---
        list_frame = ctk.CTkFrame(container, corner_radius=8)

        self.file_listbox = tk.Listbox(
            list_frame,
            font=("Courier", 12),
            selectmode="extended",
            bg="#2b2b2b",
            fg="#dcdcdc",
            selectbackground="#1f6aa5",
            selectforeground="white",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
        )
        scrollbar = ctk.CTkScrollbar(list_frame, command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)

        self.file_listbox.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=8)

        # --- Remove selected ---
        self.remove_btn = ctk.CTkButton(container, text="Remove Selected",
                                          command=self.remove_selected,
                                          width=140, height=32,
                                          font=ctk.CTkFont(size=12),
                                          fg_color="transparent",
                                          border_width=1,
                                          border_color=("gray60", "gray40"),
                                          text_color=("gray30", "gray80"),
                                          hover_color=("gray85", "gray25"))

        # --- Options container (holds either 2D or 3D panel) ---
        self.options_container = ctk.CTkFrame(container, fg_color="transparent")

        # --- 2D Panel (variable pairing dropdown) ---
        self.panel_2d = ctk.CTkFrame(self.options_container, fg_color="transparent")

        pair_label = ctk.CTkLabel(self.panel_2d, text="Mach  \u00d7",
                                   font=ctk.CTkFont(size=12),
                                   text_color=("gray50", "gray60"))
        pair_label.pack(side="left", padx=(0, 6))

        self.second_var = ctk.StringVar(value="Alpha")
        self.pair_menu = ctk.CTkOptionMenu(
            self.panel_2d,
            variable=self.second_var,
            values=list(PAIRABLE_VARS.keys()),
            width=90, height=26,
            font=ctk.CTkFont(size=12),
            dynamic_resizing=False,
        )
        self.pair_menu.pack(side="left")

        # --- 3D Panel (Alpha/Beta radio + checkbox grid) ---
        self.panel_3d = ctk.CTkFrame(self.options_container, fg_color="transparent")
        self._build_3d_panel()

        # --- Export button ---
        self.export_btn = ctk.CTkButton(container, text="Export .mat",
                                          command=self.export_mat,
                                          height=42, font=ctk.CTkFont(size=15, weight="bold"),
                                          fg_color=("#2d8a4e", "#2d8a4e"),
                                          hover_color=("#247a42", "#247a42"))

        # --- Status bar ---
        status_frame = ctk.CTkFrame(container, height=30, corner_radius=6,
                                      fg_color=("gray90", "gray20"))
        status_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(status_frame, text="Ready",
                                           font=ctk.CTkFont(size=12),
                                           text_color=("gray50", "gray60"),
                                           anchor="w")
        self.status_label.pack(fill="x", padx=12, pady=4)

        # ============================================================
        # PACK ORDER: top section from top, bottom section from bottom,
        # then file list fills the remaining middle space.
        # ============================================================

        # Top section (from top)
        header_frame.pack(fill="x", pady=(0, 5))
        sep.pack(fill="x", pady=(8, 10))
        mode_frame.pack(fill="x", pady=(0, 8))
        btn_frame.pack(fill="x", pady=(0, 6))
        self.count_label.pack(fill="x", pady=(0, 3))

        # Bottom section (from bottom — packed first so they're guaranteed space)
        status_frame.pack(fill="x", side="bottom")
        self.export_btn.pack(fill="x", side="bottom", pady=(0, 10))
        self.options_container.pack(fill="x", side="bottom", pady=(0, 4))
        self.remove_btn.pack(side="bottom", pady=(0, 10))

        # 2D panel shown by default inside options_container
        self.panel_2d.pack(fill="x")

        # Middle — file list fills remaining space
        list_frame.pack(fill="both", expand=True, pady=(0, 6))

    def _build_3d_panel(self):
        """Build the 3D mode options panel (Alpha/Beta radio + collapsible coefficient toggles)."""
        # --- Angle axis radio buttons ---
        angle_frame = ctk.CTkFrame(self.panel_3d, fg_color="transparent")
        angle_frame.pack(fill="x", pady=(0, 4))

        angle_label = ctk.CTkLabel(angle_frame, text="Angle axis:",
                                    font=ctk.CTkFont(size=12),
                                    text_color=("gray50", "gray60"))
        angle_label.pack(side="left", padx=(0, 10))

        self.angle_var = ctk.StringVar(value="Alpha")
        for val in ["Alpha", "Beta"]:
            rb = ctk.CTkRadioButton(angle_frame, text=val, variable=self.angle_var,
                                     value=val, font=ctk.CTkFont(size=12))
            rb.pack(side="left", padx=(0, 12))

        # --- Collapsible section toggle ---
        self._coeff_expanded = True
        self.coeff_toggle_btn = ctk.CTkButton(
            self.panel_3d, text="\u25bc Control Derivatives",
            command=self._toggle_coefficients,
            font=ctk.CTkFont(size=11),
            fg_color="transparent", hover_color=("gray85", "gray25"),
            text_color=("gray30", "gray80"),
            anchor="w", height=24,
        )
        self.coeff_toggle_btn.pack(fill="x", pady=(2, 2))

        # --- Collapsible content frame ---
        self.coeff_section = ctk.CTkFrame(self.panel_3d, fg_color="transparent")
        self.coeff_section.pack(fill="x")

        # Legend
        legend = ctk.CTkLabel(self.coeff_section,
                               text="\u03b1,M = Angle\u00d7Mach    "
                                    "\u03b4,M = Surface\u00d7Mach    "
                                    "3D = Angle\u00d7Mach\u00d7Surface",
                               font=ctk.CTkFont(size=10),
                               text_color=("gray50", "gray55"))
        legend.pack(fill="x", anchor="w", pady=(0, 2))

        # --- 4-column grid ---
        coeff_grid = ctk.CTkFrame(self.coeff_section, fg_color="transparent")
        coeff_grid.pack(fill="x")

        for col in range(4):
            coeff_grid.columnconfigure(col, weight=1)

        self.coeff_mode_vars = {}   # {label: StringVar}

        for col_idx, (surface, suffix) in enumerate(SURFACE_SUFFIX.items()):
            col_frame = ctk.CTkFrame(coeff_grid, fg_color="transparent")
            col_frame.grid(row=0, column=col_idx, sticky="nw", padx=2)

            # Surface header + "Set All" toggle on same line
            hdr_frame = ctk.CTkFrame(col_frame, fg_color="transparent")
            hdr_frame.pack(anchor="w", fill="x", pady=(0, 3))

            ctk.CTkLabel(hdr_frame, text=f"{surface}",
                          font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")

            group_var = ctk.StringVar(value=MODE_LABELS[0])
            ctk.CTkSegmentedButton(
                hdr_frame, values=MODE_LABELS, variable=group_var,
                font=ctk.CTkFont(size=9), height=20,
                command=lambda val, s=surface: self._set_group(s, val),
            ).pack(side="right")

            # Individual coefficient rows
            for label in SURFACE_COEFF_GROUPS[surface]:
                row_frame = ctk.CTkFrame(col_frame, fg_color="transparent")
                row_frame.pack(anchor="w", fill="x", pady=1)

                ctk.CTkLabel(row_frame, text=label,
                              font=ctk.CTkFont(size=10),
                              anchor="w").pack(side="left")

                var = ctk.StringVar(value=MODE_LABELS[0])
                ctk.CTkSegmentedButton(
                    row_frame, values=MODE_LABELS, variable=var,
                    font=ctk.CTkFont(size=9), height=18,
                ).pack(side="right")
                self.coeff_mode_vars[label] = var

    def _toggle_coefficients(self):
        """Collapse or expand the coefficients grid."""
        if self._coeff_expanded:
            self.coeff_section.pack_forget()
            self.coeff_toggle_btn.configure(text="\u25b6 Control Derivatives")
            self._coeff_expanded = False
        else:
            self.coeff_section.pack(fill="x")
            self.coeff_toggle_btn.configure(text="\u25bc Control Derivatives")
            self._coeff_expanded = True

    def _set_group(self, surface, mode):
        """Set all coefficients in a surface group to the chosen mode."""
        for label in SURFACE_COEFF_GROUPS[surface]:
            self.coeff_mode_vars[label].set(mode)

    def _on_mode_change(self, value):
        """Toggle between 2D and 3D panels."""
        if value == "2D Tables":
            self.panel_3d.pack_forget()
            self.panel_2d.pack(fill="x")
            self.geometry("600x620")
            self.minsize(500, 550)
        else:
            self.panel_2d.pack_forget()
            self.panel_3d.pack(fill="x")
            self.geometry("600x800")
            self.minsize(550, 700)

    # --- Actions ---

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select AVL output files",
            filetypes=[("All files", "*.*")],
        )
        if not paths:
            return

        added = 0
        duplicates = 0
        rejected = []  # [(filename, reason)]

        for path in paths:
            filename = os.path.basename(path)

            # Skip duplicates
            if path in self.filepaths:
                duplicates += 1
                continue

            # Validate before adding
            valid, info = validate_file(path)
            if not valid:
                rejected.append((filename, info))
                continue

            self.filepaths.append(path)
            self.file_listbox.insert("end", filename)
            added += 1

        self._update_count()

        # Build status message
        parts = []
        if added > 0:
            parts.append(f"Added {added} file{'s' if added != 1 else ''}")
        if duplicates > 0:
            parts.append(f"{duplicates} duplicate{'s' if duplicates != 1 else ''} skipped")

        if rejected:
            parts.append(f"{len(rejected)} rejected")
            self._set_status(" | ".join(parts))

            # Show detailed rejection popup
            detail_lines = [f"  {name}:\n    {reason}\n" for name, reason in rejected]
            detail = "\n".join(detail_lines)
            messagebox.showwarning(
                "Some files were rejected",
                f"{len(rejected)} file{'s' if len(rejected) != 1 else ''} "
                f"could not be added:\n\n{detail}"
                f"Only valid AVL output files are accepted."
            )
        elif parts:
            self._set_status(" | ".join(parts))
        else:
            self._set_status("No new files added")

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

    def _build_filename(self, stats, is_3d):
        """Build a descriptive default filename from export stats."""
        if is_3d:
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

    def export_mat(self):
        if not self.filepaths:
            messagebox.showwarning("No files", "Please add AVL files first.")
            return

        is_3d = self.mode_var.get() == "3D Tables"

        self._set_status("Processing...")
        self.update()

        try:
            if is_3d:
                angle = self.angle_var.get()
                coeff_modes = {}
                for label, var in self.coeff_mode_vars.items():
                    coeff_modes[label] = DISPLAY_TO_MODE[var.get()]
                mat_data, stats = process_files_3d(
                    self.filepaths, angle_var=angle, coeff_modes=coeff_modes
                )
            else:
                sv = self.second_var.get()
                mat_data, stats = process_files(self.filepaths, second_var=sv)
        except ValueError as e:
            self._set_status("Export failed — no valid files")
            messagebox.showerror("Export failed", str(e))
            return
        except Exception as e:
            self._set_status(f"Error: {e}")
            messagebox.showerror("Unexpected error", str(e))
            return

        default_name = self._build_filename(stats, is_3d)

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
        if is_3d:
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
            sv = stats['second_var']
            self._set_status(f"Exported {stats['parsed']} files ({sv} x Mach)")

        has_issues = stats['skipped'] or stats['duplicates'] or stats['warnings']
        title = "Export complete (with warnings)" if has_issues else "Export complete"
        self._show_report(title, msg)

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

    def _update_count(self):
        n = len(self.filepaths)
        if n == 0:
            self.count_label.configure(text="No files selected")
        else:
            self.count_label.configure(text=f"{n} files selected")

    def _set_status(self, text):
        self.status_label.configure(text=text)


if __name__ == '__main__':
    app = AVLParserApp()
    app.mainloop()
