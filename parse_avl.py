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
    """Parse an AVL output file and return (mach, alpha, coefficients, warnings).

    Reads Mach and Alpha from inside the file content (not the filename).
    Returns:
        (mach, alpha, result, warnings) where result is a dict of
        {label: float_value} and warnings is a list of missing-label strings.
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

    # Extract Mach and Alpha from file content
    alpha_match = re.search(r'Alpha\s*=\s*([-\d.]+)', text)
    mach_match = re.search(r'Mach\s*=\s*([\d.]+)', text)

    if not alpha_match:
        raise AVLFormatError(filename, "Alpha value not found")
    if not mach_match:
        raise AVLFormatError(filename, "Mach value not found")

    mach = float(mach_match.group(1))
    alpha = float(alpha_match.group(1))

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

    return mach, alpha, result, warnings


def mach_to_varname(mach):
    """Convert Mach number to a valid MATLAB variable name, e.g. 0.05 -> 'M0_05'."""
    return 'M' + str(mach).replace('.', '_')


# --- Processing ---

def validate_file(filepath):
    """Quick-validate a single file without full coefficient parsing.

    Returns (True, info_string) if valid, (False, error_string) if not.
    The info string shows Mach and Alpha found inside.
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

    alpha_match = re.search(r'Alpha\s*=\s*([-\d.]+)', text)
    mach_match = re.search(r'Mach\s*=\s*([\d.]+)', text)

    if not alpha_match:
        return False, "Alpha value not found"
    if not mach_match:
        return False, "Mach value not found"

    mach = float(mach_match.group(1))
    alpha = float(alpha_match.group(1))
    return True, f"Mach={mach}, Alpha={alpha}"


def process_files(filepaths):
    """Parse a list of AVL file paths and return a dict ready for savemat().

    Reads Mach and Alpha values from inside each file (not from filenames).

    Returns:
        (mat_data, stats) where stats is a dict with:
            'parsed'     - number of successfully parsed files
            'skipped'    - list of (filename, reason) tuples
            'duplicates' - list of (filename, mach, alpha, replaced_filename) tuples
            'warnings'   - dict of {filename: [missing_labels]}
            'machs'      - sorted list of Mach values
            'alphas'     - sorted list of Alpha values
    Raises:
        ValueError if no valid AVL files were found.
    """
    mach_alphas = {}
    file_list = []
    skipped = []       # [(filename, reason)]
    duplicates = []    # [(filename, mach, alpha, replaced_filename)]
    file_warnings = {} # {filename: [missing_labels]}
    data = {}
    key_to_file = {}   # {(mach, alpha): filename} — track which file owns each slot

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        try:
            mach, alpha, coefficients, warnings = parse_file(filepath)
        except (FileReadError, AVLFormatError) as e:
            skipped.append((e.filename, e.reason))
            continue
        except Exception as e:
            skipped.append((filename, str(e)))
            continue

        # Track missing labels per file
        if warnings:
            file_warnings[filename] = warnings

        # Check for duplicate Mach/Alpha
        key = (mach, alpha)
        if key in data:
            old_file = key_to_file[key]
            duplicates.append((filename, mach, alpha, old_file))

        mach_alphas.setdefault(mach, set()).add(alpha)
        file_list.append((mach, alpha, filepath))
        data[key] = coefficients
        key_to_file[key] = filename

    # Fail if nothing was parsed
    if not file_list:
        if skipped:
            reasons = "\n".join(f"  {name}: {reason}" for name, reason in skipped)
            raise ValueError(f"No valid AVL files found.\n\n{reasons}")
        else:
            raise ValueError("No files to process.")

    machs = sorted(mach_alphas.keys())
    for mach in machs:
        mach_alphas[mach] = sorted(mach_alphas[mach])

    all_alphas = sorted(set(a for alphas in mach_alphas.values() for a in alphas))

    mat_data = {
        'Mach_values': np.array(machs),
        'Alpha_values': np.array(all_alphas, dtype=float),
    }

    for label in ALL_LABELS:
        matrix = np.full((len(all_alphas), len(machs)), float('nan'))
        for j, mach in enumerate(machs):
            for i, alpha in enumerate(all_alphas):
                entry = data.get((mach, alpha))
                if entry and entry.get(label) is not None:
                    matrix[i, j] = entry[label]
        mat_data[label] = matrix

    stats = {
        'parsed': len(file_list),
        'skipped': skipped,
        'duplicates': duplicates,
        'warnings': file_warnings,
        'machs': machs,
        'alphas': all_alphas,
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

    mat_data, stats = process_files(filepaths)

    print(f"Found {len(stats['machs'])} Mach numbers: {stats['machs']}")
    print(f"Parsed {stats['parsed']} files")
    if stats['skipped']:
        print(f"Skipped: {stats['skipped']}")

    output_path = os.path.join(OUTPUT_DIR, 'avl_data.mat')
    savemat(output_path, mat_data)

    n_a = len(stats['alphas'])
    n_m = len(stats['machs'])
    print(f"\nOutput: {output_path}")
    print(f"  Mach_values:  {stats['machs']}")
    print(f"  Alpha_values: {stats['alphas']}")
    print(f"  {len(ALL_LABELS)} coefficient matrices, each {n_a} x {n_m} (Alpha x Mach)")
    print(f"\nMATLAB usage:")
    print(f"  load('output/avl_data.mat')")
    print(f"  CLtot          % {n_a}x{n_m} matrix (rows=Alpha, cols=Mach)")
    print(f"  Alpha_values   % {n_a}x1 vector")
    print(f"  Mach_values    % 1x{n_m} vector")


if __name__ == '__main__':
    main()
