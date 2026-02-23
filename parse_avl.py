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


# --- Parsing ---

def parse_filename(filename):
    """Extract Mach number and angle of attack from filename like 'M0.05A-4'."""
    m = re.match(r'^M([\d.]+)A(-?\d+)$', filename)
    if not m:
        raise ValueError(f"Cannot parse filename: {filename}")
    return float(m.group(1)), int(m.group(2))


def parse_file(filepath):
    """Parse an AVL output file and return (mach, alpha, coefficients).

    Reads Mach and Alpha from inside the file content (not the filename).
    Returns:
        (mach, alpha, result) where result is a dict of {label: float_value}.
    Raises ValueError if Mach or Alpha cannot be found in the file.
    """
    with open(filepath, 'r') as f:
        text = f.read()

    # Extract Mach and Alpha from file content
    alpha_match = re.search(r'Alpha\s*=\s*([-\d.]+)', text)
    mach_match = re.search(r'Mach\s*=\s*([\d.]+)', text)

    if not alpha_match or not mach_match:
        raise ValueError(f"Cannot find Mach/Alpha in {os.path.basename(filepath)}")

    mach = float(mach_match.group(1))
    alpha = float(alpha_match.group(1))

    result = {}

    # Standard labels: use lookbehind to prevent partial matches
    for label in STANDARD_LABELS:
        pattern = r'(?<![A-Za-z])' + re.escape(label) + r'\s*=\s*([-\d.]+)'
        m = re.search(pattern, text)
        if m:
            result[label] = float(m.group(1))
        else:
            print(f"  WARNING: {label} not found in {os.path.basename(filepath)}")
            result[label] = None

    # Special labels with custom patterns
    for label, pattern in SPECIAL_PATTERNS.items():
        m = re.search(pattern, text)
        if m:
            result[label] = float(m.group(1))
        else:
            print(f"  WARNING: {label} not found in {os.path.basename(filepath)}")
            result[label] = None

    return mach, alpha, result


def mach_to_varname(mach):
    """Convert Mach number to a valid MATLAB variable name, e.g. 0.05 -> 'M0_05'."""
    return 'M' + str(mach).replace('.', '_')


# --- Processing ---

def process_files(filepaths):
    """Parse a list of AVL file paths and return a dict ready for savemat().

    Reads Mach and Alpha values from inside each file (not from filenames).

    Returns:
        (mat_data, stats) where stats is a dict with 'parsed', 'skipped',
        'machs', 'alphas' info.
    """
    mach_alphas = {}
    file_list = []
    skipped = []
    data = {}

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        try:
            mach, alpha, coefficients = parse_file(filepath)
        except ValueError:
            skipped.append(filename)
            continue
        mach_alphas.setdefault(mach, set()).add(alpha)
        file_list.append((mach, alpha, filepath))
        data[(mach, alpha)] = coefficients

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
