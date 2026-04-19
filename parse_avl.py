"""
AVL Output Parser
Reads AVL (Athena Vortex Lattice) output files and exports aerodynamic
coefficients to a single .mat file for MATLAB.

Usage:
    python parse_avl.py

MATLAB usage:
    load('output/avl_data.mat')
    Alpha_values         % [-4, -2, 0, ..., 20]
    Mach_values          % [0.02, 0.05, 0.1, 0.15, 0.2]
    CLtot                % 13x5 matrix (Alpha rows x Mach columns)
    plot(Alpha_values, CLtot(:,3))   % plot CL vs Alpha at Mach 0.1

###############################################################################
# CRITICAL SAFETY RULE — AVL EXECUTABLE
#
# This app MUST use "avl352.exe" EXCLUSIVELY when running AVL analysis.
# DO NOT use avl_mac or any other binary. DO NOT add OS-based binary switching.
# avl_mac exists only for local macOS dev testing — NEVER in production code.
# This software is used by aircraft engineers — lives depend on it.
# See CLAUDE.md for full details.
###############################################################################
"""

import os
import re
import sys
import numpy as np
from scipy.io import savemat

# --- Configuration ---

if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, 'test files')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')

# All coefficient labels using the standard regex pattern: LABEL = VALUE
STANDARD_LABELS = [
    # Total forces
    'CLtot', 'CDtot', 'CYtot', 'CXtot', 'CZtot', 'Cmtot', 'Cltot', 'Cntot',
    'CDind', 'CDff', 'CLff', 'CYff',
    # Stability derivatives - alpha
    'CLa', 'CYa', 'CDa', 'Cla', 'Cma', 'Cna',
    # Stability derivatives - beta
    'CLb', 'CYb', 'CDb', 'Clb', 'Cmb', 'Cnb',
    # Roll rate (p) derivatives
    'CLp', 'CYp', 'CDp', 'Clp', 'Cmp', 'Cnp',
    # Pitch rate (q) derivatives
    'CLq', 'CYq', 'CDq', 'Clq', 'Cmq', 'Cnq',
    # Yaw rate (r) derivatives
    'CLr', 'CYr', 'CDr', 'Clr', 'Cmr', 'Cnr',
    # Control surface derivatives - FLAP (d01)
    'CLd01', 'CYd01', 'CDd01', 'Cld01', 'Cmd01', 'Cnd01',
    # Control surface derivatives - AIL (d02)
    'CLd02', 'CYd02', 'CDd02', 'Cld02', 'Cmd02', 'Cnd02',
    # Control surface derivatives - ELEV (d03)
    'CLd03', 'CYd03', 'CDd03', 'Cld03', 'Cmd03', 'Cnd03',
    # Control surface derivatives - RUDD (d04)
    'CLd04', 'CYd04', 'CDd04', 'Cld04', 'Cmd04', 'Cnd04',
    # Trefftz drag derivatives
    'CDffd01', 'CDffd02', 'CDffd03', 'CDffd04',
    # Span efficiency derivatives
    'ed01', 'ed02', 'ed03', 'ed04',
    # Neutral point
    'Xnp',
]

# Labels requiring special regex patterns
SPECIAL_PATTERNS = {
    'e': r'e\s*=\s+([-\d.]+)\s*\|\s*Plane',
    'spiral_stability': r'Clb Cnr / Clr Cnb\s*=\s*([-\d.]+)',
}

ALL_LABELS = STANDARD_LABELS + list(SPECIAL_PATTERNS.keys())

# Variables that can be paired with Mach (rows of the output matrix)
PAIRABLE_VARS = {
    'Alpha': r'Alpha\s*=\s*([-\d.]+)',
    'Beta':  r'Beta\s*=\s*([-\d.]+)',
    'FLAP':  r'FLAP\s*=\s*([-\d.]+)',
    'AIL':   r'AIL\s*=\s*([-\d.]+)',
    'ELEV':  r'ELEV\s*=\s*([-\d.]+)',
    'RUDD':  r'RUDD\s*=\s*([-\d.]+)',
}

# --- Pre-compiled regex patterns (avoids recompiling per file) ---
_RE_MACH = re.compile(r'Mach\s*=\s*([\d.]+)')
_RE_PAIRABLE = {name: re.compile(pat) for name, pat in PAIRABLE_VARS.items()}
_RE_STANDARD = {
    label: re.compile(r'(?<![A-Za-z])' + re.escape(label) + r'\s*=\s*([-\d.]+)')
    for label in STANDARD_LABELS
}
_RE_SPECIAL = {label: re.compile(pat) for label, pat in SPECIAL_PATTERNS.items()}

# Control surface name -> derivative suffix mapping
SURFACE_SUFFIX = {'FLAP': 'd01', 'AIL': 'd02', 'ELEV': 'd03', 'RUDD': 'd04'}
SUFFIX_TO_SURFACE = {v: k for k, v in SURFACE_SUFFIX.items()}

# All control surface derivative labels, grouped by surface
SURFACE_COEFF_GROUPS = {}
for _surface, _suffix in SURFACE_SUFFIX.items():
    SURFACE_COEFF_GROUPS[_surface] = [l for l in STANDARD_LABELS if _suffix in l]

# Beta, when swept in 3D mode, is a virtual "surface-like" dimension:
# each Beta value produces its own (alpha, mach) slice stored as a 3D array.
# Beta's coefficient group is the 6 stability derivatives w.r.t. beta.
BETA_DIM = 'Beta'
BETA_COEFFS = ['CLb', 'CYb', 'CDb', 'Clb', 'Cmb', 'Cnb']

# Unified 3D dimensions: physical control surfaces + Beta as virtual dim.
DIMS_3D = list(SURFACE_SUFFIX.keys()) + [BETA_DIM]
DIM_COEFF_GROUPS = dict(SURFACE_COEFF_GROUPS)
DIM_COEFF_GROUPS[BETA_DIM] = BETA_COEFFS


# --- Exceptions ---

class FileReadError(Exception):
    """Raised when a file cannot be read at all."""
    def __init__(self, filename, reason):
        self.filename = filename
        self.reason = reason
        super().__init__(f"{filename}: {reason}")


class AVLFormatError(Exception):
    """Raised when a file is readable but not valid AVL output."""
    def __init__(self, filename, reason):
        self.filename = filename
        self.reason = reason
        super().__init__(f"{filename}: {reason}")


# --- Parsing ---

def parse_filename(filename):
    """Extract Mach number and angle of attack from filename like 'M0.05A-4'."""
    m = re.match(r'^M([\d.]+)A(-?\d+)$', filename)
    if not m:
        raise ValueError(f"Cannot parse filename: {filename}")
    return float(m.group(1)), int(m.group(2))


def parse_file(filepath):
    """Parse an AVL output file and return (mach, run_vars, coefficients, warnings).

    Reads Mach and all pairable variables from the file content.
    Returns:
        (mach, run_vars, result, warnings) where:
            - mach is a float (always required)
            - run_vars is a dict of {var_name: float_or_None} for all PAIRABLE_VARS
            - result is a dict of {label: float_value} for all coefficients
            - warnings is a list of missing coefficient label strings
    Raises:
        FileReadError: if the file cannot be read (permissions, binary, etc.)
        AVLFormatError: if the file is not a valid AVL output file.
    """
    filename = os.path.basename(filepath)

    # Try to read the file — catch all I/O and encoding problems
    try:
        with open(filepath, 'r', encoding='utf-8', errors='strict') as f:
            text = f.read()
    except PermissionError:
        raise FileReadError(filename, "permission denied")
    except UnicodeDecodeError:
        raise FileReadError(filename, "not a text file (binary?)")
    except OSError as e:
        raise FileReadError(filename, str(e))

    # Check for AVL header signature
    if 'Vortex Lattice Output' not in text:
        raise AVLFormatError(filename, "not an AVL output file")

    # Extract Mach (always required)
    mach_match = _RE_MACH.search(text)
    if not mach_match:
        raise AVLFormatError(filename, "Mach value not found")
    mach = float(mach_match.group(1))

    # Extract all pairable variables (None if not found)
    run_vars = {}
    for var_name, compiled in _RE_PAIRABLE.items():
        m = compiled.search(text)
        run_vars[var_name] = float(m.group(1)) if m else None

    result = {}
    warnings = []

    # Standard labels: use pre-compiled lookbehind patterns
    for label, compiled in _RE_STANDARD.items():
        m = compiled.search(text)
        if m:
            result[label] = float(m.group(1))
        else:
            warnings.append(label)
            result[label] = None

    # Special labels with pre-compiled custom patterns
    for label, compiled in _RE_SPECIAL.items():
        m = compiled.search(text)
        if m:
            result[label] = float(m.group(1))
        else:
            warnings.append(label)
            result[label] = None

    return mach, run_vars, result, warnings


def mach_to_varname(mach):
    """Convert Mach number to a valid MATLAB variable name, e.g. 0.05 -> 'M0_05'."""
    return 'M' + str(mach).replace('.', '_')


# --- Processing ---

def parse_run_vars(filepath):
    """Fast parse: read only the first 2 KB and extract the run variables.

    Returns (mach, run_vars) where run_vars is a dict of {var_name: float|None}
    for all PAIRABLE_VARS. Coefficients are NOT extracted — use parse_file()
    for that. ~100× faster than parse_file() for pre-export validation.

    Returns (None, None) if the file can't be read or isn't an AVL output.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='strict') as f:
            text = f.read(2048)
    except (OSError, UnicodeDecodeError):
        return None, None
    if 'Vortex Lattice Output' not in text:
        return None, None
    m = _RE_MACH.search(text)
    if not m:
        return None, None
    mach = float(m.group(1))
    run_vars = {}
    for var_name, compiled in _RE_PAIRABLE.items():
        m = compiled.search(text)
        run_vars[var_name] = float(m.group(1)) if m else None
    return mach, run_vars


def validate_file(filepath):
    """Quick-validate a single file without full coefficient parsing.

    Returns (True, info_string) if valid, (False, error_string) if not.
    Only Mach is required. The info string shows all detected run variables.
    Reads only the first 2 KB for speed — header + run variables appear early.
    """
    filename = os.path.basename(filepath)
    try:
        with open(filepath, 'r', encoding='utf-8', errors='strict') as f:
            text = f.read(2048)
    except PermissionError:
        return False, "permission denied"
    except UnicodeDecodeError:
        return False, "not a text file (binary?)"
    except OSError as e:
        return False, str(e)

    if 'Vortex Lattice Output' not in text:
        return False, "not an AVL output file"

    mach_match = _RE_MACH.search(text)
    if not mach_match:
        return False, "Mach value not found"

    # Build info string with all detected pairable variables
    parts = [f"Mach={float(mach_match.group(1))}"]
    for var_name, compiled in _RE_PAIRABLE.items():
        m = compiled.search(text)
        if m:
            parts.append(f"{var_name}={float(m.group(1))}")
    return True, ", ".join(parts)


def process_files(filepaths, second_var='Alpha', skip_conflicts=True):
    """Parse a list of AVL file paths and return a dict ready for savemat().

    Reads Mach and the selected second variable from inside each file.

    Args:
        filepaths: list of file paths to parse.
        second_var: which variable to pair with Mach ('Alpha', 'Beta',
                    'FLAP', 'AIL', 'ELEV', or 'RUDD'). Default: 'Alpha'.

    Returns:
        (mat_data, stats) where stats is a dict with:
            'parsed'     - number of successfully parsed files
            'skipped'    - list of (filename, reason) tuples
            'duplicates' - list of (filename, mach, var_val, replaced_filename) tuples
            'warnings'   - dict of {filename: [missing_labels]}
            'machs'      - sorted list of Mach values
            'second_var' - name of the second variable
            'var_values' - sorted list of second variable values
    Raises:
        ValueError if no valid AVL files were found.
    """
    if second_var not in PAIRABLE_VARS:
        raise ValueError(f"Unknown variable: {second_var}. "
                         f"Choose from: {', '.join(PAIRABLE_VARS.keys())}")

    mach_vars = {}     # {mach: set of second_var values}
    file_list = []
    skipped = []       # [(filename, reason)]
    duplicates = []    # [(filename, mach, var_val, replaced_filename)]
    file_warnings = {} # {filename: [missing_labels]}
    data = {}
    key_to_file = {}   # {(mach, var_val): filename}

    # Pre-compute the list of variables to check for non-zero values
    _needs_zero_check = skip_conflicts
    _is_surface_pair = second_var in SURFACE_SUFFIX
    if _needs_zero_check and not _is_surface_pair:
        check_vars = list(SURFACE_SUFFIX)
        opposite = 'Beta' if second_var == 'Alpha' else 'Alpha'
        check_vars.append(opposite)

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        try:
            mach, run_vars, coefficients, warnings = parse_file(filepath)
        except (FileReadError, AVLFormatError) as e:
            skipped.append((e.filename, e.reason))
            continue
        except Exception as e:
            skipped.append((filename, str(e)))
            continue

        # Check that the selected second variable exists in this file
        var_val = run_vars.get(second_var)
        if var_val is None:
            skipped.append((filename, f"{second_var} value not found"))
            continue

        # Skip files with conflicting non-zero angles/deflections
        if _needs_zero_check:
            if _is_surface_pair:
                # Pairing by surface: skip if both angles non-zero or
                # another surface is also non-zero
                conflicts = []
                alpha = run_vars.get('Alpha')
                beta = run_vars.get('Beta')
                if alpha and beta:
                    conflicts.append(f"Alpha={alpha}, Beta={beta}")
                other_surfaces = [
                    s for s in SURFACE_SUFFIX if s != second_var
                    and run_vars.get(s) is not None and run_vars[s] != 0.0
                ]
                if other_surfaces:
                    conflicts.extend(f"{s}={run_vars[s]}" for s in other_surfaces)
                if conflicts:
                    skipped.append((filename, f"non-zero values: {', '.join(conflicts)}"))
                    continue
            else:
                nonzero = [
                    name for name in check_vars
                    if run_vars.get(name) is not None and run_vars[name] != 0.0
                ]
                if nonzero:
                    vals_str = ", ".join(f"{n}={run_vars[n]}" for n in nonzero)
                    skipped.append((filename, f"non-zero values: {vals_str}"))
                    continue

        # Track missing labels per file
        if warnings:
            file_warnings[filename] = warnings

        # Check for duplicate Mach/var pairs
        key = (mach, var_val)
        if key in data:
            old_file = key_to_file[key]
            duplicates.append((filename, mach, var_val, old_file))

        mach_vars.setdefault(mach, set()).add(var_val)
        file_list.append((mach, var_val, filepath))
        data[key] = coefficients
        key_to_file[key] = filename

    # Fail if nothing was parsed
    if not file_list:
        if skipped:
            reasons = "\n".join(f"  {name}: {reason}" for name, reason in skipped)
            raise ValueError(f"No valid AVL files found.\n\n{reasons}")
        else:
            raise ValueError("No files to process.")

    machs = sorted(mach_vars.keys())
    for mach in machs:
        mach_vars[mach] = sorted(mach_vars[mach])

    all_var_values = sorted(set(v for vals in mach_vars.values() for v in vals))

    # Filter labels: control surfaces only get their own derivatives
    if second_var in SURFACE_SUFFIX:
        suffix = SURFACE_SUFFIX[second_var]
        export_labels = [l for l in ALL_LABELS if suffix in l]
    else:
        export_labels = ALL_LABELS

    mat_data = {
        'Mach_values': np.array(machs),
        f'{second_var}_values': np.array(all_var_values, dtype=float),
    }

    for label in export_labels:
        matrix = np.full((len(all_var_values), len(machs)), float('nan'))
        for j, mach in enumerate(machs):
            for i, var_val in enumerate(all_var_values):
                entry = data.get((mach, var_val))
                if entry and entry.get(label) is not None:
                    matrix[i, j] = entry[label]
        mat_data[label] = matrix

    stats = {
        'parsed': len(file_list),
        'skipped': skipped,
        'duplicates': duplicates,
        'warnings': file_warnings,
        'machs': machs,
        'second_var': second_var,
        'var_values': all_var_values,
        'n_labels': len(export_labels),
    }

    return mat_data, stats


def process_files_3d(filepaths, angle_var='Alpha', coeff_modes=None,
                     checked_coeffs=None):
    """Parse AVL files and return 3D/2D matrices for control surface derivatives.

    Each coefficient can be one of three modes:
      '3d'         — 3D array (angle × Mach × surface_value)
      '2d_angle'   — 2D array (angle × Mach)
      '2d_surface' — 2D array (surface_value × Mach)

    Args:
        filepaths: list of file paths to parse.
        angle_var: 'Alpha' or 'Beta' — the angle axis.
        coeff_modes: dict {label: mode} where mode is '3d', '2d_angle',
            or '2d_surface'. Labels not in dict default to '2d_angle'.
        checked_coeffs: deprecated — set of labels for 3D treatment.
            Converted to coeff_modes internally if coeff_modes is None.

    Returns:
        (mat_data, stats) where mat_data is ready for scipy.io.savemat().
    Raises:
        ValueError if no valid data is found.
    """
    if angle_var not in ('Alpha', 'Beta'):
        raise ValueError(f"angle_var must be 'Alpha' or 'Beta', got '{angle_var}'")

    # Backward compat: convert checked_coeffs to coeff_modes
    if coeff_modes is None and checked_coeffs is not None:
        coeff_modes = {l: '3d' for l in checked_coeffs}
    if coeff_modes is None:
        coeff_modes = {}

    # Active 3D dims: surfaces always, plus Beta unless it's already the axis.
    # (Beta-as-axis and Beta-as-dim are mutually exclusive by construction.)
    if angle_var == BETA_DIM:
        _active_dims = list(SURFACE_SUFFIX.keys())
    else:
        _active_dims = list(DIMS_3D)

    skipped = []
    duplicates_3d = []
    duplicates_2d_angle = []
    duplicates_2d_surface = []
    file_warnings = {}

    # Data storage: keyed by dim (surface name or 'Beta')
    data_3d = {d: {} for d in _active_dims}           # (mach, angle, dim_val)
    data_2d_angle = {d: {} for d in _active_dims}      # (mach, angle)
    data_2d_surface = {d: {} for d in _active_dims}    # (mach, dim_val)
    # Temp storage for 2D-surface: collect all angles, then keep only zero-angle
    _temp_2d_surface = {d: {} for d in _active_dims}  # (mach, dim_val, angle)
    # Track which file produced each key for duplicate reporting
    key_to_file_3d = {d: {} for d in _active_dims}
    key_to_file_2d_angle = {d: {} for d in _active_dims}
    key_to_file_2d_surface = {d: {} for d in _active_dims}

    mach_set = set()
    angle_set = set()
    dim_value_sets = {d: set() for d in _active_dims}

    # Pre-compute label groups per dim (coeff_modes is constant)
    _labels_3d = {}
    _labels_2d_angle = {}
    _labels_2d_surface = {}
    for dname in _active_dims:
        dl = DIM_COEFF_GROUPS[dname]
        _labels_3d[dname] = [l for l in dl if coeff_modes.get(l) == '3d']
        _labels_2d_angle[dname] = [l for l in dl
                                   if coeff_modes.get(l, '2d_angle') == '2d_angle']
        _labels_2d_surface[dname] = [l for l in dl
                                     if coeff_modes.get(l) == '2d_surface']

    parsed_count = 0

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        try:
            mach, run_vars, coefficients, warnings = parse_file(filepath)
        except (FileReadError, AVLFormatError) as e:
            skipped.append((e.filename, e.reason))
            continue
        except Exception as e:
            skipped.append((filename, str(e)))
            continue

        # Need at least one surface value (Beta alone is never sufficient —
        # files without any control-surface columns are not valid 3D inputs).
        has_surface = any(run_vars.get(s) is not None for s in SURFACE_SUFFIX)
        if not has_surface:
            skipped.append((filename, "no control surface values found"))
            continue

        if warnings:
            file_warnings[filename] = warnings

        angle_val = run_vars.get(angle_var)
        mach_set.add(mach)
        if angle_val is not None:
            angle_set.add(angle_val)

        parsed_count += 1

        for dim_name in _active_dims:
            dim_val = run_vars.get(dim_name)
            if dim_val is None:
                continue

            # Skip if any OTHER 3D dim is non-zero — this file belongs to that
            # other dim's table. Without this, e.g. a RUDD=30 file would
            # overwrite the AIL=0 bucket of the AIL table, and a Beta=5 file
            # would contaminate every surface's zero-beta row.
            # The current dim and the angle-axis variable are excluded, since
            # both are expected to vary across files.
            if any(run_vars.get(other) not in (None, 0.0)
                   for other in DIMS_3D
                   if other != dim_name and other != angle_var):
                continue

            dim_value_sets[dim_name].add(dim_val)

            labels_3d = _labels_3d[dim_name]
            labels_2d_angle = _labels_2d_angle[dim_name]
            labels_2d_surface = _labels_2d_surface[dim_name]

            # 3D data: needs angle_val
            if angle_val is not None and labels_3d:
                key_3d = (mach, angle_val, dim_val)
                if key_3d in data_3d[dim_name]:
                    old_file = key_to_file_3d[dim_name][key_3d]
                    duplicates_3d.append((
                        filename, dim_name,
                        f"Mach={mach}, {angle_var}={angle_val}, {dim_name}={dim_val}",
                        old_file
                    ))
                data_3d[dim_name][key_3d] = coefficients
                key_to_file_3d[dim_name][key_3d] = filename

            # 2D-angle data: keyed by (mach, angle_val)
            if labels_2d_angle and angle_val is not None:
                key_2d = (mach, angle_val)
                if key_2d in data_2d_angle[dim_name]:
                    old_file = key_to_file_2d_angle[dim_name][key_2d]
                    if old_file != filename:
                        duplicates_2d_angle.append((
                            filename, dim_name,
                            f"Mach={mach}, {angle_var}={angle_val}",
                            old_file
                        ))
                data_2d_angle[dim_name][key_2d] = coefficients
                key_to_file_2d_angle[dim_name][key_2d] = filename

            # 2D-surface data: collect with angle, filter to zero-angle after loop
            if labels_2d_surface and angle_val is not None:
                key_temp = (mach, dim_val, angle_val)
                _temp_2d_surface[dim_name][key_temp] = (coefficients, filename)

    if parsed_count == 0:
        if skipped:
            reasons = "\n".join(f"  {name}: {reason}" for name, reason in skipped)
            raise ValueError(f"No valid AVL files found.\n\n{reasons}")
        else:
            raise ValueError("No files to process.")

    machs = sorted(mach_set)
    angle_vals = sorted(angle_set)

    # Build data_2d_surface from zero-angle entries only
    zero_angle = min(angle_set, key=lambda a: abs(a)) if angle_set else 0.0
    for dim_name in _active_dims:
        for (mach, dval, angle), (coeffs, fname) in _temp_2d_surface[dim_name].items():
            if angle != zero_angle:
                continue
            key_2d_s = (mach, dval)
            if key_2d_s in data_2d_surface[dim_name]:
                old_file = key_to_file_2d_surface[dim_name][key_2d_s]
                if old_file != fname:
                    duplicates_2d_surface.append((
                        fname, dim_name,
                        f"Mach={mach}, {dim_name}={dval}",
                        old_file
                    ))
            data_2d_surface[dim_name][key_2d_s] = coeffs
            key_to_file_2d_surface[dim_name][key_2d_s] = fname

    # Build mat_data
    mat_data = {
        'Mach_values': np.array(machs),
    }

    if angle_vals:
        mat_data[f'{angle_var}_values'] = np.array(angle_vals, dtype=float)

    dim_values_sorted = {}
    for dim_name in _active_dims:
        vals = sorted(dim_value_sets[dim_name])
        if vals:
            dim_values_sorted[dim_name] = vals
            mat_data[f'{dim_name}_values'] = np.array(vals, dtype=float)

    n_3d = 0
    n_2d_angle = 0
    n_2d_surface = 0
    labels_2d_surface_list = []

    for dim_name in _active_dims:
        dim_vals = dim_values_sorted.get(dim_name, [])
        if not dim_vals:
            continue

        # Beta coefficients get a 'Beta_' output prefix; surface coefficients
        # are already uniquely named by their d0N suffix.
        out_prefix = 'Beta_' if dim_name == BETA_DIM else ''

        for label in DIM_COEFF_GROUPS[dim_name]:
            mode = coeff_modes.get(label, '2d_angle')
            out_label = f'{out_prefix}{label}'

            if mode == '3d':
                # 3D matrix: (n_angle, n_mach, n_dim_val)
                if not angle_vals:
                    continue
                matrix = np.full((len(angle_vals), len(machs), len(dim_vals)), np.nan)
                for i, angle in enumerate(angle_vals):
                    for j, mach in enumerate(machs):
                        for k, dval in enumerate(dim_vals):
                            entry = data_3d[dim_name].get((mach, angle, dval))
                            if entry and entry.get(label) is not None:
                                matrix[i, j, k] = entry[label]
                mat_data[out_label] = matrix
                n_3d += 1

            elif mode == '2d_surface':
                # 2D matrix: (n_dim_val, n_mach)
                matrix = np.full((len(dim_vals), len(machs)), np.nan)
                for k, dval in enumerate(dim_vals):
                    for j, mach in enumerate(machs):
                        entry = data_2d_surface[dim_name].get((mach, dval))
                        if entry and entry.get(label) is not None:
                            matrix[k, j] = entry[label]
                mat_data[out_label] = matrix
                n_2d_surface += 1
                labels_2d_surface_list.append(out_label)

            else:
                # 2D matrix: (n_angle, n_mach)
                if not angle_vals:
                    continue
                matrix = np.full((len(angle_vals), len(machs)), np.nan)
                for i, angle in enumerate(angle_vals):
                    for j, mach in enumerate(machs):
                        entry = data_2d_angle[dim_name].get((mach, angle))
                        if entry and entry.get(label) is not None:
                            matrix[i, j] = entry[label]
                mat_data[out_label] = matrix
                n_2d_angle += 1

    # Store metadata for view_mat.py to distinguish 2D types
    if labels_2d_surface_list:
        mat_data['x_2d_surface_labels'] = np.array(labels_2d_surface_list, dtype=object)

    all_duplicates = []
    for name, dim, desc, old in duplicates_3d:
        all_duplicates.append((name, f"3D {dim}: {desc} (overwrote {old})"))
    for name, dim, desc, old in duplicates_2d_angle:
        all_duplicates.append((name, f"2D-angle {dim}: {desc} (overwrote {old})"))
    for name, dim, desc, old in duplicates_2d_surface:
        all_duplicates.append((name, f"2D-surface {dim}: {desc} (overwrote {old})"))

    stats = {
        'parsed': parsed_count,
        'skipped': skipped,
        'duplicates': all_duplicates,
        'warnings': file_warnings,
        'machs': machs,
        'angle_var': angle_var,
        'angle_values': angle_vals,
        'surface_values': dim_values_sorted,
        'n_3d': n_3d,
        'n_2d_angle': n_2d_angle,
        'n_2d_surface': n_2d_surface,
        'n_labels': n_3d + n_2d_angle + n_2d_surface,
        'coeff_modes': coeff_modes,
    }

    return mat_data, stats


# --- Labels that are NOT control-surface derivatives ---
_CS_SUFFIXES = set(SURFACE_SUFFIX.values())        # {'d01','d02','d03','d04'}
NON_CS_LABELS = [l for l in ALL_LABELS if not any(s in l for s in _CS_SUFFIXES)]


def process_files_full(filepaths, angle_var='Alpha', coeff_modes=None,
                        progress_cb=None, skip_conflicts=True):
    """Combined export: 2D tables for the angle axis + 3D tables for surfaces + Beta.

    Non-CS coefficients come from 2D processing (angle_var × Mach).
    CS coefficients come from 3D processing. Beta participates in the 3D
    section as a virtual surface-like dim, producing 'Beta_<coef>' arrays.

    Args:
        filepaths: list of file paths to parse.
        angle_var: 'Alpha' or 'Beta' — the angle axis for 2D and 3D sections.
        coeff_modes: dict {label: mode} for 3D coefficient modes.
        progress_cb: optional callback(step, total) called after each pass.

    Returns:
        (mat_data, full_stats) where mat_data is ready for scipy.io.savemat().
    Raises:
        ValueError if both processing calls fail.
    """
    mat_data = {}
    alpha_stats = None
    td_stats = None
    errors = []

    # --- Alpha 2D section (always alpha×mach, regardless of angle_var) ---
    try:
        alpha_data, alpha_stats = process_files(filepaths, second_var='Alpha',
                                                     skip_conflicts=skip_conflicts)
        # Rename axes
        mat_data['Alpha_values'] = alpha_data.pop('Alpha_values')
        mat_data['Alpha_Mach_values'] = alpha_data.pop('Mach_values')
        # Copy only non-CS coefficients
        for label in NON_CS_LABELS:
            if label in alpha_data:
                mat_data[label] = alpha_data[label]
    except ValueError as e:
        errors.append(f"Alpha 2D: {e}")

    if progress_cb:
        progress_cb(1, 2)

    # --- 3D section (surfaces + Beta-as-dim) ---
    try:
        td_data, td_stats = process_files_3d(
            filepaths, angle_var=angle_var, coeff_modes=coeff_modes
        )
        mat_data['Mach_values'] = td_data.pop('Mach_values')
        # Angle values — use 'Angle_values' to avoid conflict with Alpha_values
        angle_key = f'{angle_var}_values'
        if angle_key in td_data:
            mat_data['Angle_values'] = td_data.pop(angle_key)
        mat_data['Angle_var'] = np.array([angle_var])
        # Dim value arrays (surfaces + Beta)
        for dim in DIMS_3D:
            key = f'{dim}_values'
            if key in td_data:
                mat_data[key] = td_data.pop(key)
        # CS + Beta_ coefficients
        for key, val in td_data.items():
            mat_data[key] = val
    except ValueError as e:
        errors.append(f"3D: {e}")

    if progress_cb:
        progress_cb(2, 2)

    if not mat_data:
        raise ValueError(
            "No valid data from any section.\n\n" + "\n".join(errors)
        )

    # Count labels per section
    n_alpha = sum(1 for l in NON_CS_LABELS if l in mat_data) if alpha_stats else 0
    n_td = (td_stats['n_labels'] if td_stats else 0)

    full_stats = {
        'alpha_stats': alpha_stats,
        'beta_stats': None,  # 2D Beta section removed; beta now lives in 3D
        'td_stats': td_stats,
        'n_alpha_labels': n_alpha,
        'n_beta_labels': 0,
        'n_td_labels': n_td,
        'errors': errors,
    }

    return mat_data, full_stats


# --- Main ---

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    filepaths = [
        os.path.join(INPUT_DIR, f)
        for f in os.listdir(INPUT_DIR)
        if os.path.isfile(os.path.join(INPUT_DIR, f))
    ]

    mat_data, stats = process_files(filepaths, second_var='Alpha')

    sv = stats['second_var']
    print(f"Found {len(stats['machs'])} Mach numbers: {stats['machs']}")
    print(f"Parsed {stats['parsed']} files")
    if stats['skipped']:
        print(f"Skipped: {stats['skipped']}")

    output_path = os.path.join(OUTPUT_DIR, 'avl_data.mat')
    savemat(output_path, mat_data)

    n_v = len(stats['var_values'])
    n_m = len(stats['machs'])
    print(f"\nOutput: {output_path}")
    print(f"  Mach_values:    {stats['machs']}")
    print(f"  {sv}_values:  {stats['var_values']}")
    print(f"  {len(ALL_LABELS)} coefficient matrices, each {n_v} x {n_m} ({sv} x Mach)")
    print(f"\nMATLAB usage:")
    print(f"  load('output/avl_data.mat')")
    print(f"  CLtot            % {n_v}x{n_m} matrix (rows={sv}, cols=Mach)")
    print(f"  {sv}_values   % {n_v}x1 vector")
    print(f"  Mach_values      % 1x{n_m} vector")


if __name__ == '__main__':
    main()
