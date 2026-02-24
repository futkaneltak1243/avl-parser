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
from parse_avl import process_files, validate_file, ALL_LABELS, PAIRABLE_VARS

from scipy.io import savemat


# --- Theme ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AVLParserApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AVL Parser")
        self.geometry("600x550")
        self.minsize(500, 450)

        self.filepaths = []

        self._build_ui()

    def _build_ui(self):
        # --- Main container ---
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=25, pady=20)

        # --- Header ---
        header_frame = ctk.CTkFrame(container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 5))

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
        sep.pack(fill="x", pady=(12, 15))

        # --- Buttons row ---
        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 10))

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
        self.count_label.pack(fill="x", pady=(0, 5))

        # --- File list ---
        list_frame = ctk.CTkFrame(container, corner_radius=8)
        list_frame.pack(fill="both", expand=True, pady=(0, 10))

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
        self.remove_btn.pack(pady=(0, 12))

        # --- Variable pairing selector ---
        pair_frame = ctk.CTkFrame(container, fg_color="transparent")
        pair_frame.pack(fill="x", pady=(0, 12))

        pair_label = ctk.CTkLabel(pair_frame, text="Pair with Mach:",
                                   font=ctk.CTkFont(size=13),
                                   text_color=("gray30", "gray80"))
        pair_label.pack(side="left", padx=(0, 10))

        self.second_var = ctk.StringVar(value="Alpha")
        self.pair_menu = ctk.CTkOptionMenu(
            pair_frame,
            variable=self.second_var,
            values=list(PAIRABLE_VARS.keys()),
            width=140, height=32,
            font=ctk.CTkFont(size=13),
        )
        self.pair_menu.pack(side="left")

        # --- Export button ---
        self.export_btn = ctk.CTkButton(container, text="Export .mat",
                                          command=self.export_mat,
                                          height=45, font=ctk.CTkFont(size=15, weight="bold"),
                                          fg_color=("#2d8a4e", "#2d8a4e"),
                                          hover_color=("#247a42", "#247a42"))
        self.export_btn.pack(fill="x", pady=(0, 15))

        # --- Status bar ---
        status_frame = ctk.CTkFrame(container, height=30, corner_radius=6,
                                      fg_color=("gray90", "gray20"))
        status_frame.pack(fill="x")
        status_frame.pack_propagate(False)

        self.status_label = ctk.CTkLabel(status_frame, text="Ready",
                                           font=ctk.CTkFont(size=12),
                                           text_color=("gray50", "gray60"),
                                           anchor="w")
        self.status_label.pack(fill="x", padx=12, pady=4)

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

    def export_mat(self):
        if not self.filepaths:
            messagebox.showwarning("No files", "Please add AVL files first.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Save .mat file",
            defaultextension=".mat",
            filetypes=[("MATLAB file", "*.mat")],
            initialfile="avl_data.mat",
        )
        if not save_path:
            return

        self._set_status("Processing...")
        self.update()

        sv = self.second_var.get()

        try:
            mat_data, stats = process_files(self.filepaths, second_var=sv)
            savemat(save_path, mat_data)
        except ValueError as e:
            self._set_status("Export failed — no valid files")
            messagebox.showerror("Export failed", str(e))
            return
        except Exception as e:
            self._set_status(f"Error: {e}")
            messagebox.showerror("Unexpected error", str(e))
            return

        # --- Build the success report ---
        n_v = len(stats['var_values'])
        n_m = len(stats['machs'])

        msg = (f"Paired: Mach x {sv}\n"
               f"Parsed {stats['parsed']} files\n"
               f"{n_m} Mach number{'s' if n_m != 1 else ''}, "
               f"{n_v} {sv} value{'s' if n_v != 1 else ''}\n"
               f"{len(ALL_LABELS)} coefficients\n\n"
               f"Saved to:\n{save_path}")

        # Report skipped files with reasons
        if stats['skipped']:
            msg += f"\n\n--- Skipped ({len(stats['skipped'])}) ---"
            for name, reason in stats['skipped']:
                msg += f"\n  {name}: {reason}"

        # Report duplicate Mach/var pairs (last file wins)
        if stats['duplicates']:
            msg += f"\n\n--- Duplicates ({len(stats['duplicates'])}) ---"
            for name, mach, var_val, replaced in stats['duplicates']:
                msg += (f"\n  {name} has same Mach={mach}, {sv}={var_val}"
                        f"\n    (overwrote {replaced})")

        # Report files with missing coefficients
        if stats['warnings']:
            msg += f"\n\n--- Missing coefficients ---"
            for name, labels in stats['warnings'].items():
                msg += f"\n  {name}: {', '.join(labels)}"

        self._set_status(f"Exported {stats['parsed']} files ({sv} x Mach)")

        # Use warning icon if there were any issues, info icon if clean
        has_issues = stats['skipped'] or stats['duplicates'] or stats['warnings']
        if has_issues:
            messagebox.showwarning("Export complete (with warnings)", msg)
        else:
            messagebox.showinfo("Export complete", msg)

    # --- Helpers ---

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
