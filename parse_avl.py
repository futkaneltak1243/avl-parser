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
"""

import os
import re
import numpy as np
from scipy.io import savemat

# --- Configuration ---

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
    mach_match = re.search(r'Mach\s*=\s*([\d.]+)', text)
    if not mach_match:
        raise AVLFormatError(filename, "Mach value not found")
    mach = float(mach_match.group(1))

    # Extract all pairable variables (None if not found)
    run_vars = {}
    for var_name, pattern in PAIRABLE_VARS.items():
        m = re.search(pattern, text)
        run_vars[var_name] = float(m.group(1)) if m else None

    result = {}
    warnings = []

    # Standard labels: use lookbehind to prevent partial matches
    for label in STANDARD_LABELS:
        pattern = r'(?<![A-Za-z])' + re.escape(label) + r'\s*=\s*([-\d.]+)'
        m = re.search(pattern, text)
        if m:
            result[label] = float(m.group(1))
        else:
            warnings.append(label)
            result[label] = None

    # Special labels with custom patterns
    for label, pattern in SPECIAL_PATTERNS.items():
        m = re.search(pattern, text)
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

def validate_file(filepath):
    """Quick-validate a single file without full coefficient parsing.

    Returns (True, info_string) if valid, (False, error_string) if not.
    Only Mach is required. The info string shows all detected run variables.
    """
    filename = os.path.basename(filepath)
    try:
        with open(filepath, 'r', encoding='utf-8', errors='strict') as f:
            text = f.read()
    except PermissionError:
        return False, "permission denied"
    except UnicodeDecodeError:
        return False, "not a text file (binary?)"
    except OSError as e:
        return False, str(e)

    if 'Vortex Lattice Output' not in text:
        return False, "not an AVL output file"

    mach_match = re.search(r'Mach\s*=\s*([\d.]+)', text)
    if not mach_match:
        return False, "Mach value not found"

    # Build info string with all detected pairable variables
    parts = [f"Mach={float(mach_match.group(1))}"]
    for var_name, pattern in PAIRABLE_VARS.items():
        m = re.search(pattern, text)
        if m:
            parts.append(f"{var_name}={float(m.group(1))}")
    return True, ", ".join(parts)


def process_files(filepaths, second_var='Alpha'):
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

    mat_data = {
        'Mach_values': np.array(machs),
        f'{second_var}_values': np.array(all_var_values, dtype=float),
    }

    for label in ALL_LABELS:
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
    }

    return mat_data, stats


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
