"""
Value Set Card widget for the File Generator.

Used by app.py to build the generator UI inside the main window.
"""

import customtkinter as ctk

from run_generator import DIM_CHOICES


class ValueSetCard(ctk.CTkFrame):
    """A single value set card: Mach × Alpha × (FLAP|AIL|ELEV|RUDD|Beta).

    Alpha is the only angle axis — Beta moved to the surface dropdown as a
    surface-like 3D dim.
    """

    def __init__(self, parent, card_index, on_delete, on_change):
        super().__init__(parent, corner_radius=8,
                         fg_color=("gray88", "gray20"),
                         border_width=1,
                         border_color=("gray75", "gray35"))
        self.card_index = card_index
        self._on_delete = on_delete
        self._on_change = on_change

        self._build()

    def _build(self):
        # --- Header row ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))

        self.title_label = ctk.CTkLabel(
            header, text=f"Value Set {self.card_index}",
            font=ctk.CTkFont(size=12, weight="bold"))
        self.title_label.pack(side="left")

        ctk.CTkButton(
            header, text="X", width=28, height=24,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="transparent", border_width=1,
            border_color=("gray60", "gray40"),
            text_color=("gray30", "gray80"),
            hover_color=("#c0392b", "#c0392b"),
            command=lambda: self._on_delete(self)
        ).pack(side="right")

        # --- Mach values ---
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(2, 2))

        ctk.CTkLabel(row1, text="Mach values:",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self.mach_entry = ctk.CTkEntry(row1, placeholder_text="0.02, 0.05, 0.1, 0.15, 0.2",
                                       font=ctk.CTkFont(size=11))
        self.mach_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.mach_entry.bind("<KeyRelease>", self._update_count)

        # --- Alpha row ---
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=(2, 2))

        ctk.CTkLabel(row2, text="Alpha values:",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self.angle_entry = ctk.CTkEntry(row2, placeholder_text="-4, -2, 0, 2, 4",
                                        font=ctk.CTkFont(size=11))
        self.angle_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.angle_entry.bind("<KeyRelease>", self._update_count)

        # --- Surface row ---
        row3 = ctk.CTkFrame(self, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(2, 2))

        ctk.CTkLabel(row3, text="Surface:",
                     font=ctk.CTkFont(size=11)).pack(side="left")

        self.surface_var = ctk.StringVar(value="FLAP")
        self.surface_menu = ctk.CTkOptionMenu(
            row3, values=DIM_CHOICES, variable=self.surface_var,
            width=90, height=26, font=ctk.CTkFont(size=11),
            command=lambda _: self._update_count())
        self.surface_menu.pack(side="left", padx=(6, 0))

        ctk.CTkLabel(row3, text="Values:",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=(12, 0))
        self.surface_entry = ctk.CTkEntry(row3, placeholder_text="0, 5, 10",
                                          font=ctk.CTkFont(size=11))
        self.surface_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.surface_entry.bind("<KeyRelease>", self._update_count)

        # --- File count ---
        self.count_label = ctk.CTkLabel(
            self, text="Total: 0 files",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray60"))
        self.count_label.pack(padx=10, pady=(2, 8), anchor="e")

    def _parse_csv(self, text):
        """Parse comma-separated floats, ignoring empty/invalid segments."""
        values = []
        for part in text.split(","):
            part = part.strip()
            if part:
                try:
                    values.append(float(part))
                except ValueError:
                    pass
        return values

    def _update_count(self, *_args):
        m = len(self._parse_csv(self.mach_entry.get()))
        a = len(self._parse_csv(self.angle_entry.get()))
        s = len(self._parse_csv(self.surface_entry.get()))
        total = m * a * s
        if m and a and s:
            self.count_label.configure(
                text=f"Total: {m} x {a} x {s} = {total} files")
        else:
            self.count_label.configure(text="Total: 0 files")
        self._on_change()

    def set_index(self, idx):
        self.card_index = idx
        self.title_label.configure(text=f"Value Set {idx}")

    def validate(self):
        """Check all fields for invalid entries.

        Rejects: non-numeric values, empty segments (,,), leading/trailing commas,
        and duplicate values.

        Returns:
            None if valid, or an error message string if invalid.
        """
        fields = [
            ("Mach", self.mach_entry.get()),
            ("Alpha", self.angle_entry.get()),
            (self.surface_var.get(), self.surface_entry.get()),
        ]
        for field_name, text in fields:
            text = text.strip()
            if not text:
                continue
            # Reject leading/trailing commas: ",1,2" or "1,2,"
            if text.startswith(",") or text.endswith(","):
                return f"{field_name} values: remove leading/trailing commas."
            parts = text.split(",")
            values = []
            for part in parts:
                part = part.strip()
                if not part:
                    # Empty segment between commas (e.g. "1,,2")
                    return f"{field_name} values: empty entry between commas."
                try:
                    val = float(part)
                except ValueError:
                    return f"'{part}' is not a valid number in {field_name} values."
                if val in values:
                    return f"Duplicate value {part} in {field_name} values."
                values.append(val)
            # Mach must be subsonic (AVL uses vortex lattice method)
            if field_name == "Mach":
                for v in values:
                    if v <= 0 or v >= 1.0:
                        return (f"Mach {v} is out of range. "
                                "Values must be between 0 and 1 (subsonic only).\n"
                                "AVL cannot compute supersonic flows.")
        return None

    def get_data(self):
        """Return value set dict, or None if incomplete."""
        mach = self._parse_csv(self.mach_entry.get())
        angle = self._parse_csv(self.angle_entry.get())
        surface = self._parse_csv(self.surface_entry.get())

        if not mach or not angle or not surface:
            return None

        return {
            "mach_values": mach,
            "angle_type": "Alpha",
            "angle_values": angle,
            "surface_type": self.surface_var.get(),
            "surface_values": surface,
        }

    def get_file_count(self):
        m = len(self._parse_csv(self.mach_entry.get()))
        a = len(self._parse_csv(self.angle_entry.get()))
        s = len(self._parse_csv(self.surface_entry.get()))
        return m * a * s
