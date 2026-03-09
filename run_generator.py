"""
AVL Run Case File Generator
Generates run case definitions, builds batch scripts, and runs AVL
to produce stability derivative output files.

###############################################################################
# CRITICAL SAFETY RULE — AVL EXECUTABLE
#
# PRODUCTION (Windows): This app MUST use "avl352.exe" EXCLUSIVELY.
# avl_mac is used ONLY on macOS during development/testing — it is NEVER
# shipped or used in the production Windows build.
# This software is used by aircraft engineers — lives depend on it.
# See CLAUDE.md for full details.
###############################################################################
"""

import math
import os
import re
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Fixed parameters: (name, default_value, unit, decimal_places)
# These appear in the "properties" section of each run case block.
# Order matters — it must match the AVL .run file format exactly.
# ---------------------------------------------------------------------------
FIXED_PARAMS = [
    ("CL",        0.0,       "",                5),
    ("CDo",       0.0,       "",                5),
    ("bank",      0.0,       "deg",             5),
    ("elevation", 0.0,       "deg",             5),
    ("heading",   0.0,       "deg",             5),
    ("velocity",  6.8,       "Lunit/Tunit",     5),
    ("density",   1.225,     "Munit/Lunit^3",   7),
    ("grav.acc.", 1.0,       "Lunit/Tunit^2",   5),
    ("turn_rad.", 0.0,       "Lunit",           5),
    ("load_fac.", 0.0,       "",                5),
    ("X_cg",      0.36,      "Lunit",           5),
    ("Y_cg",      0.0,       "Lunit",           5),
    ("Z_cg",      0.0,       "Lunit",           5),
    ("mass",      7.0,       "Munit",           5),
    ("Ixx",       0.564114,  "Munit-Lunit^2",   6),
    ("Iyy",       1.202967,  "Munit-Lunit^2",   6),
    ("Izz",       0.655341,  "Munit-Lunit^2",   6),
    ("Ixy",       0.0,       "Munit-Lunit^2",   5),
    ("Iyz",       0.0,       "Munit-Lunit^2",   5),
    ("Izx",       0.0,       "Munit-Lunit^2",   5),
    ("visc CL_a", 0.0,       "",                5),
    ("visc CL_u", 0.0,       "",                5),
    ("visc CM_a", 0.0,       "",                5),
    ("visc CM_u", 0.0,       "",                5),
]

# Constraint lines that always appear (order matters)
CONSTRAINT_NAMES = ["alpha", "beta", "pb/2V", "qc/2V", "rb/2V",
                    "FLAP", "AIL", "ELEV", "RUDD"]

ANGLE_ABBREVS = {"Alpha": "A", "Beta": "B"}
SURFACE_NAMES = ["FLAP", "AIL", "ELEV", "RUDD"]

# AVL 3.52 supports at most 25 run cases per .run file (NRMAX=25).
# Exceeding this causes cases beyond 25 to be silently ignored.
MAX_CASES_PER_RUN = 25


def format_mach_scientific(value):
    """Format Mach as Fortran-style scientific: 0.200000E-01 for 0.02."""
    if value == 0.0:
        return "0.000000E+00"
    exponent = math.floor(math.log10(abs(value))) + 1
    mantissa = value / (10.0 ** exponent)
    return f"{mantissa:.6f}E{exponent:+03d}"



def _clean_number_str(value):
    """Format a number for filenames: remove trailing zeros after decimal,
    remove decimal point if integer. E.g., 0.02 -> '0.02', 4.0 -> '4'."""
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def build_run_case_name(mach, angle_type, angle_val, surface_type, surface_val):
    """Build case name like 'M0.02A-4' or 'M0.1A2FLAP5'.

    Surface name is only included when surface_val != 0.
    """
    angle_abbrev = ANGLE_ABBREVS[angle_type]
    name = f"M{_clean_number_str(mach)}{angle_abbrev}{_clean_number_str(angle_val)}"
    if surface_val != 0.0:
        name += f"{surface_type}{_clean_number_str(surface_val)}"
    return name


def build_run_case_block(case_number, case_name, alpha, beta, mach,
                         surfaces, fixed_params):
    """Build a complete run case text block matching cases1.run format.

    Args:
        case_number: integer case number (typically 1 for individual files)
        case_name: string like 'M0.02A-4'
        alpha: angle of attack in degrees
        beta: sideslip angle in degrees
        mach: Mach number
        surfaces: dict with keys FLAP, AIL, ELEV, RUDD (float values)
        fixed_params: dict of {param_name: float_value}

    Returns:
        Complete text block as a string.
    """
    lines = []

    # --- Separator and header ---
    lines.append(" " + "-" * 45)
    lines.append(f" Run case  {case_number}:   {case_name}")
    lines.append("")

    # --- Constraint lines (the '->' section) ---
    constraint_values = {
        "alpha": alpha,
        "beta": beta,
        "pb/2V": fixed_params.get("pb/2V", 0.0),
        "qc/2V": fixed_params.get("qc/2V", 0.0),
        "rb/2V": fixed_params.get("rb/2V", 0.0),
        "FLAP": surfaces.get("FLAP", 0.0),
        "AIL": surfaces.get("AIL", 0.0),
        "ELEV": surfaces.get("ELEV", 0.0),
        "RUDD": surfaces.get("RUDD", 0.0),
    }

    for name in CONSTRAINT_NAMES:
        val = constraint_values[name]
        decimals = 4 if name == "AIL" else 5
        val_str = f"{val:.{decimals}f}"
        lines.append(f" {name:<13}->  {name:<12}=   {val_str}")

    lines.append("")

    # --- Properties section (exact order from cases1.run) ---
    p = fixed_params  # shorthand
    lines.append(f" alpha     =   {alpha:.5f}     deg")
    lines.append(f" beta      =   {beta:.5f}     deg")
    lines.append(f" pb/2V     =   {p.get('pb/2V', 0.0):.5f}")
    lines.append(f" qc/2V     =   {p.get('qc/2V', 0.0):.5f}")
    lines.append(f" rb/2V     =   {p.get('rb/2V', 0.0):.5f}")
    lines.append(f" CL        =   {p.get('CL', 0.0):.5f}")
    lines.append(f" CDo       =   {p.get('CDo', 0.0):.5f}")
    lines.append(f" bank      =   {p.get('bank', 0.0):.5f}     deg")
    lines.append(f" elevation =   {p.get('elevation', 0.0):.5f}     deg")
    lines.append(f" heading   =   {p.get('heading', 0.0):.5f}     deg")
    lines.append(f" Mach      =  {format_mach_scientific(mach)}")
    lines.append(f" velocity  =   {p.get('velocity', 6.8):.5f}     Lunit/Tunit")
    lines.append(f" density   =   {p.get('density', 1.225):.7f}     Munit/Lunit^3")
    lines.append(f" grav.acc. =   {p.get('grav.acc.', 1.0):.5f}     Lunit/Tunit^2")
    lines.append(f" turn_rad. =   {p.get('turn_rad.', 0.0):.5f}     Lunit")
    lines.append(f" load_fac. =   {p.get('load_fac.', 0.0):.5f}")
    lines.append(f" X_cg      =   {p.get('X_cg', 0.36):.5f}     Lunit")
    lines.append(f" Y_cg      =   {p.get('Y_cg', 0.0):.5f}     Lunit")
    lines.append(f" Z_cg      =   {p.get('Z_cg', 0.0):.5f}     Lunit")
    lines.append(f" mass      =   {p.get('mass', 7.0):.5f}     Munit")
    lines.append(f" Ixx       =   {p.get('Ixx', 0.564114):.6f}  Munit-Lunit^2")
    lines.append(f" Iyy       =   {p.get('Iyy', 1.202967):.6f}     Munit-Lunit^2")
    lines.append(f" Izz       =   {p.get('Izz', 0.655341):.6f}     Munit-Lunit^2")
    lines.append(f" Ixy       =   {p.get('Ixy', 0.0):.5f}     Munit-Lunit^2")
    lines.append(f" Iyz       =   {p.get('Iyz', 0.0):.5f}     Munit-Lunit^2")
    lines.append(f" Izx       =   {p.get('Izx', 0.0):.5f}     Munit-Lunit^2")
    lines.append(f" visc CL_a =   {p.get('visc CL_a', 0.0):.5f}")
    lines.append(f" visc CL_u =   {p.get('visc CL_u', 0.0):.5f}")
    lines.append(f" visc CM_a =   {p.get('visc CM_a', 0.0):.5f}")
    lines.append(f" visc CM_u =   {p.get('visc CM_u', 0.0):.5f}")

    return "\n".join(lines) + "\n"


def build_combined_cases_file(fixed_params, value_sets):
    """Build run case blocks for all cases from all value sets.

    Returns:
        (list_of_block_strings, list_of_case_names)
        Blocks are unnumbered — caller re-numbers them per batch.
    """
    blocks = []
    case_names = []

    for vs in value_sets:
        for mach in vs["mach_values"]:
            for angle_val in vs["angle_values"]:
                for surface_val in vs["surface_values"]:
                    if vs["angle_type"] == "Alpha":
                        alpha, beta = angle_val, 0.0
                    else:
                        alpha, beta = 0.0, angle_val

                    surfaces = {s: 0.0 for s in SURFACE_NAMES}
                    surfaces[vs["surface_type"]] = surface_val

                    case_name = build_run_case_name(
                        mach, vs["angle_type"], angle_val,
                        vs["surface_type"], surface_val
                    )

                    block = build_run_case_block(
                        case_number=1,  # placeholder, re-numbered per batch
                        case_name=case_name,
                        alpha=alpha, beta=beta, mach=mach,
                        surfaces=surfaces,
                        fixed_params=fixed_params,
                    )

                    blocks.append(block)
                    case_names.append(case_name)

    return blocks, case_names


def _renumber_blocks(blocks):
    """Re-number a list of run case blocks sequentially from 1."""
    renumbered = []
    for i, block in enumerate(blocks, 1):
        # Replace "Run case  N:" with "Run case  i:"
        new_block = re.sub(
            r'(Run case\s+)\d+(:)',
            rf'\g<1>{i}\2',
            block,
            count=1,
        )
        renumbered.append(new_block)
    return "\n".join(renumbered)


def build_batch_script(case_names):
    """Build the AVL batch command script to execute all cases and save output.

    Disables graphics for headless mode. Each case is executed (x) and
    its stability output saved (st) to a file named after the case.
    """
    lines = [
        "PLOP",
        "G F",
        "",
        "oper",
    ]

    for i, name in enumerate(case_names, 1):
        lines.append(str(i))
        lines.append("x")
        lines.append("st")
        lines.append(name)

    lines.append("")
    lines.append("quit")
    lines.append("")

    return "\n".join(lines)


# CRITICAL: DO NOT CHANGE — see CLAUDE.md
AVL_EXE = "avl352.exe"

# macOS dev-only binary (NEVER shipped in production)
_AVL_MAC = "avl_mac"

if getattr(sys, 'frozen', False):
    _SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_avl_executable():
    """Return the path to the correct AVL executable for the current platform.

    Windows (production): avl352.exe in the application directory.
    macOS (development only): avl_mac in the application or 'friend files/' directory.

    Raises FileNotFoundError if the executable cannot be found.
    """
    if sys.platform == "win32":
        # --- PRODUCTION: always avl352.exe ---
        path = os.path.join(_SCRIPT_DIR, AVL_EXE)
        if os.path.isfile(path):
            return path
        raise FileNotFoundError(
            f"Cannot find {AVL_EXE} in:\n{_SCRIPT_DIR}\n\n"
            f"Please place {AVL_EXE} in the application directory."
        )

    # --- macOS dev testing only ---
    for candidate_dir in [_SCRIPT_DIR, os.path.join(_SCRIPT_DIR, "friend files")]:
        path = os.path.join(candidate_dir, _AVL_MAC)
        if os.path.isfile(path):
            return path

    raise FileNotFoundError(
        f"Cannot find {_AVL_MAC} for macOS development testing.\n"
        f"Looked in: {_SCRIPT_DIR} and friend files/\n\n"
        f"Download avl_mac from MIT or copy it to the application directory."
    )


def run_avl(avl_exe, geometry_file, output_dir, fixed_params, value_sets):
    """Run AVL to generate stability derivative output files.

    Automatically splits into batches of MAX_CASES_PER_RUN (25) to stay
    within AVL's run case limit.

    Args:
        avl_exe: path to AVL executable (must be avl352.exe in production)
        geometry_file: path to .avl geometry file
        output_dir: directory where output files will be written
        fixed_params: dict of {param_name: float_value}
        value_sets: list of value set dicts

    Returns:
        (total_files, list_of_filenames)

    Raises:
        RuntimeError: if AVL fails to run or produces errors
    """
    os.makedirs(output_dir, exist_ok=True)

    # Build all case blocks and names
    all_blocks, all_names = build_combined_cases_file(fixed_params, value_sets)

    created = []

    # Process in batches of MAX_CASES_PER_RUN to avoid AVL's case limit
    for chunk_start in range(0, len(all_names), MAX_CASES_PER_RUN):
        chunk_blocks = all_blocks[chunk_start:chunk_start + MAX_CASES_PER_RUN]
        chunk_names = all_names[chunk_start:chunk_start + MAX_CASES_PER_RUN]

        cases_content = _renumber_blocks(chunk_blocks)
        batch_script = build_batch_script(chunk_names)

        with tempfile.TemporaryDirectory() as tmpdir:
            cases_path = os.path.join(tmpdir, "cases.run")
            with open(cases_path, "w") as f:
                f.write(cases_content)

            result = subprocess.run(
                [avl_exe, geometry_file, cases_path],
                input=batch_script,
                cwd=output_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0 and result.returncode != 1:
                raise RuntimeError(
                    f"AVL exited with code {result.returncode}.\n"
                    f"stderr: {result.stderr[:500]}"
                )

        for name in chunk_names:
            if os.path.isfile(os.path.join(output_dir, name)):
                created.append(name)

    if not created:
        raise RuntimeError(
            "AVL ran but produced no output files.\n"
            f"stdout (last 500 chars): {result.stdout[-500:]}"
        )

    return len(created), created
