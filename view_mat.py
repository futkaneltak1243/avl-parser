"""
.mat File Viewer
Displays the contents of avl_data.mat as formatted tables in the terminal.
Supports both 2D (var x Mach) and 3D (angle x Mach x surface) matrices.

Usage:
    python view_mat.py                  # show all coefficients
    python view_mat.py CLtot CLa Cma    # show specific coefficients
    python view_mat.py --list           # list all available coefficients
    python view_mat.py --file path.mat  # use a specific .mat file
"""

import sys
import os
import numpy as np
from scipy.io import loadmat

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_avl import SURFACE_SUFFIX, SUFFIX_TO_SURFACE

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
MAT_PATH = os.path.join(OUTPUT_DIR, 'avl_data.mat')

# Surface suffixes for detecting which surface a coefficient belongs to
_SUFFIXES = sorted(SUFFIX_TO_SURFACE.keys(), key=len, reverse=True)  # longest first


def load_data(path=None):
    mat_path = path or MAT_PATH
    if not os.path.exists(mat_path):
        print(f"Error: {mat_path} not found. Run parse_avl.py or export from the app first.")
        sys.exit(1)
    return loadmat(mat_path), mat_path


def get_coefficients(data):
    """Return list of coefficient names (everything except axis arrays and metadata)."""
    skip = {'__header__', '__version__', '__globals__', 'Mach_values',
            'x_2d_surface_labels', 'Angle_var'}
    skip.update(k for k in data.keys() if k.endswith('_values'))
    return sorted(k for k in data.keys() if k not in skip)


def get_2d_surface_labels(data):
    """Return set of coefficient labels that are 2D(surface x Mach)."""
    if 'x_2d_surface_labels' in data:
        labels = set()
        for item in data['x_2d_surface_labels'].flatten():
            # loadmat wraps object arrays: each item may be a nested array
            s = str(item.flat[0]) if hasattr(item, 'flat') else str(item)
            labels.add(s)
        return labels
    return set()


def detect_mode(data):
    """Detect whether this is a 2D, 3D, or full-analysis .mat file.

    Returns:
        'full' if Alpha_Mach_values or Beta_Mach_values present,
        '3d' if any coefficient matrix has 3 dimensions, '2d' otherwise.
    """
    if 'Alpha_Mach_values' in data or 'Beta_Mach_values' in data:
        return 'full'
    for label in get_coefficients(data):
        if data[label].ndim == 3:
            return '3d'
    return '2d'


def detect_row_var(data):
    """Detect the row variable for a 2D .mat file (Alpha_values, Beta_values, etc.)."""
    for key in data.keys():
        if key.endswith('_values') and key != 'Mach_values':
            name = key.replace('_values', '')
            if name not in SURFACE_SUFFIX:
                return name, data[key].flatten()
    # Fallback: first non-Mach _values key
    for key in data.keys():
        if key.endswith('_values') and key != 'Mach_values':
            return key.replace('_values', ''), data[key].flatten()
    return 'Alpha', np.array([])


def detect_angle_var(data):
    """Detect the angle variable for a 3D .mat file (Alpha or Beta)."""
    for name in ('Alpha', 'Beta'):
        key = f'{name}_values'
        if key in data:
            return name, data[key].flatten()
    return None, np.array([])


def coeff_surface(label):
    """Return the surface name a coefficient belongs to, or None."""
    for suffix, surface in SUFFIX_TO_SURFACE.items():
        if suffix in label:
            return surface
    return None


def classify_full_coefficients(coeffs):
    """Classify coefficients into Alpha 2D, Beta 2D, and 3D sections.

    Returns:
        (alpha_coeffs, beta_coeffs, td_coeffs) — three sorted lists.
    """
    alpha_coeffs = []
    beta_coeffs = []
    td_coeffs = []

    for label in coeffs:
        if label.startswith('Beta_'):
            beta_coeffs.append(label)
        elif coeff_surface(label) is not None:
            td_coeffs.append(label)
        else:
            alpha_coeffs.append(label)

    return alpha_coeffs, beta_coeffs, td_coeffs


def format_val(v):
    """Format a number for display."""
    if abs(v) >= 0.01:
        return f'{v:.6f}'
    else:
        return f'{v:.6f}'


# --- 2D display (original) ---

def print_table_2d(data, label, row_name, row_vals, mach_key='Mach_values'):
    """Print a single 2D coefficient as a formatted table."""
    machs = data[mach_key].flatten()
    matrix = data[label]

    col_w = 14
    row_w = 8

    print()
    print(f'  {label}')
    print(f'  {row_name:<{row_w}}', end='')
    for m in machs:
        print(f'{"M=" + str(m):>{col_w}}', end='')
    print()
    print('  ' + '-' * (row_w + col_w * len(machs)))

    for i, v in enumerate(row_vals):
        print(f'  {v:<{row_w}.1f}', end='')
        for j in range(len(machs)):
            val = matrix[i, j]
            if np.isnan(val):
                print(f'{"--":>{col_w}}', end='')
            else:
                print(f'{format_val(val):>{col_w}}', end='')
        print()

    print()


def write_table_2d(f, data, label, row_name, row_vals, mach_key='Mach_values'):
    """Write a single 2D coefficient table to a file object."""
    machs = data[mach_key].flatten()
    matrix = data[label]

    col_w = 14
    row_w = 8

    f.write(f'\n  {label}\n')
    f.write(f'  {row_name:<{row_w}}')
    for m in machs:
        f.write(f'{"M=" + str(m):>{col_w}}')
    f.write('\n')
    f.write('  ' + '-' * (row_w + col_w * len(machs)) + '\n')

    for i, v in enumerate(row_vals):
        f.write(f'  {v:<{row_w}.1f}')
        for j in range(len(machs)):
            val = matrix[i, j]
            if np.isnan(val):
                f.write(f'{"--":>{col_w}}')
            else:
                f.write(f'{format_val(val):>{col_w}}')
        f.write('\n')

    f.write('\n')


# --- 3D display ---

def print_table_3d(data, label, angle_name, angle_vals, surface_name, surface_vals, mach_key='Mach_values'):
    """Print a 3D coefficient as sliced tables (one per angle value)."""
    machs = data[mach_key].flatten()
    matrix = data[label]  # shape: (n_angle, n_mach, n_surface)

    col_w = 14
    row_w = 8

    for i, angle in enumerate(angle_vals):
        print()
        print(f'  {label}  ({angle_name} = {angle:.1f})')
        print(f'  {surface_name:<{row_w}}', end='')
        for m in machs:
            print(f'{"M=" + str(m):>{col_w}}', end='')
        print()
        print('  ' + '-' * (row_w + col_w * len(machs)))

        for k, sval in enumerate(surface_vals):
            print(f'  {sval:<{row_w}.1f}', end='')
            for j in range(len(machs)):
                val = matrix[i, j, k]
                if np.isnan(val):
                    print(f'{"--":>{col_w}}', end='')
                else:
                    print(f'{format_val(val):>{col_w}}', end='')
            print()

    print()


def write_table_3d(f, data, label, angle_name, angle_vals, surface_name, surface_vals, mach_key='Mach_values'):
    """Write a 3D coefficient as sliced tables to a file object."""
    machs = data[mach_key].flatten()
    matrix = data[label]

    col_w = 14
    row_w = 8

    for i, angle in enumerate(angle_vals):
        f.write(f'\n  {label}  ({angle_name} = {angle:.1f})\n')
        f.write(f'  {surface_name:<{row_w}}')
        for m in machs:
            f.write(f'{"M=" + str(m):>{col_w}}')
        f.write('\n')
        f.write('  ' + '-' * (row_w + col_w * len(machs)) + '\n')

        for k, sval in enumerate(surface_vals):
            f.write(f'  {sval:<{row_w}.1f}')
            for j in range(len(machs)):
                val = matrix[i, j, k]
                if np.isnan(val):
                    f.write(f'{"--":>{col_w}}')
                else:
                    f.write(f'{format_val(val):>{col_w}}')
            f.write('\n')

    f.write('\n')


# --- Summary and listing ---

def print_summary(data, mat_path):
    """Print a summary of what's in the file."""
    coeffs = get_coefficients(data)
    mode = detect_mode(data)

    filename = os.path.basename(mat_path)
    print()
    print(f'  {filename}')
    print('  ' + '=' * 50)

    if mode == 'full':
        alpha_coeffs, beta_coeffs, td_coeffs = classify_full_coefficients(coeffs)

        if 'Alpha_Mach_values' in data:
            alpha_machs = data['Alpha_Mach_values'].flatten()
            alpha_vals = data['Alpha_values'].flatten()
            print(f'  --- Alpha x Mach (2D) ---')
            print(f'  Alpha values:      {alpha_vals}')
            print(f'  Alpha Mach values: {alpha_machs}')
            print(f'  Coefficients:      {len(alpha_coeffs)}')

        if 'Beta_Mach_values' in data:
            beta_machs = data['Beta_Mach_values'].flatten()
            beta_vals = data['Beta_values'].flatten()
            print(f'  --- Beta x Mach (2D) ---')
            print(f'  Beta values:       {beta_vals}')
            print(f'  Beta Mach values:  {beta_machs}')
            print(f'  Coefficients:      {len(beta_coeffs)}')

        if 'Mach_values' in data:
            machs = data['Mach_values'].flatten()
            print(f'  --- Control Surfaces ---')
            print(f'  Mach values:   {machs}')
            if 'Angle_values' in data:
                angle_var = str(data['Angle_var'].flat[0]) if 'Angle_var' in data else 'Alpha'
                angle_vals = data['Angle_values'].flatten()
                print(f'  {angle_var} values: {angle_vals}')

            surface_2d = get_2d_surface_labels(data)
            n_3d = sum(1 for l in td_coeffs if data[l].ndim == 3)
            n_2d_surface = sum(1 for l in td_coeffs if data[l].ndim == 2 and l in surface_2d)
            n_2d_angle = sum(1 for l in td_coeffs if data[l].ndim == 2 and l not in surface_2d)

            for surface_name in SURFACE_SUFFIX:
                key = f'{surface_name}_values'
                if key in data:
                    svals = data[key].flatten()
                    if len(svals) > 1:
                        print(f'  {surface_name} values: {svals}')
                    else:
                        print(f'  {surface_name} values: {svals}  (constant)')

            print(f'  Coefficients:  {len(td_coeffs)} ({n_3d} 3D + {n_2d_angle} 2D-angle + {n_2d_surface} 2D-surface)')

    elif mode == '3d':
        machs = data['Mach_values'].flatten()
        print(f'  Mach values:   {machs}')
        angle_name, angle_vals = detect_angle_var(data)
        if angle_name:
            print(f'  {angle_name} values: {angle_vals}')

        surface_2d = get_2d_surface_labels(data)
        n_3d = sum(1 for l in coeffs if data[l].ndim == 3)
        n_2d_surface = sum(1 for l in coeffs if data[l].ndim == 2 and l in surface_2d)
        n_2d_angle = sum(1 for l in coeffs if data[l].ndim == 2 and l not in surface_2d)

        for surface_name in SURFACE_SUFFIX:
            key = f'{surface_name}_values'
            if key in data:
                svals = data[key].flatten()
                if len(svals) > 1:
                    print(f'  {surface_name} values: {svals}')
                else:
                    print(f'  {surface_name} values: {svals}  (constant \u2014 tables skipped)')

        print(f'  Coefficients:  {len(coeffs)} ({n_3d} 3D + {n_2d_angle} 2D-angle + {n_2d_surface} 2D-surface)')
    else:
        machs = data['Mach_values'].flatten()
        print(f'  Mach values:   {machs}')
        row_name, row_vals = detect_row_var(data)
        print(f'  {row_name} values: {row_vals}')
        print(f'  Coefficients:  {len(coeffs)}')
        print(f'  Matrix size:   {len(row_vals)} x {len(machs)} ({row_name} x Mach)')

    print()


def print_list(data):
    """Print all available coefficient names in columns."""
    coeffs = get_coefficients(data)
    mode = detect_mode(data)

    print()
    print(f'  {len(coeffs)} coefficients available:')
    print('  ' + '-' * 50)

    if mode == 'full':
        alpha_coeffs, beta_coeffs, td_coeffs = classify_full_coefficients(coeffs)

        if alpha_coeffs:
            print(f'  Alpha 2D ({len(alpha_coeffs)}):')
            _print_cols(alpha_coeffs)
        if beta_coeffs:
            print(f'  Beta 2D ({len(beta_coeffs)}):')
            _print_cols(beta_coeffs)
        if td_coeffs:
            surface_2d = get_2d_surface_labels(data)
            cs_3d = [l for l in td_coeffs if data[l].ndim == 3]
            cs_2d_angle = [l for l in td_coeffs if data[l].ndim == 2 and l not in surface_2d]
            cs_2d_surface = [l for l in td_coeffs if data[l].ndim == 2 and l in surface_2d]

            if cs_3d:
                print(f'  CS 3D ({len(cs_3d)}):')
                _print_cols(cs_3d)
            if cs_2d_angle:
                print(f'  CS 2D-angle ({len(cs_2d_angle)}):')
                _print_cols(cs_2d_angle)
            if cs_2d_surface:
                print(f'  CS 2D-surface ({len(cs_2d_surface)}):')
                _print_cols(cs_2d_surface)

    elif mode == '3d':
        surface_2d = get_2d_surface_labels(data)
        coeffs_3d = [l for l in coeffs if data[l].ndim == 3]
        coeffs_2d_angle = [l for l in coeffs if data[l].ndim == 2 and l not in surface_2d]
        coeffs_2d_surface = [l for l in coeffs if data[l].ndim == 2 and l in surface_2d]

        if coeffs_3d:
            print(f'  3D ({len(coeffs_3d)}):')
            _print_cols(coeffs_3d)
        if coeffs_2d_angle:
            print(f'  2D-angle ({len(coeffs_2d_angle)}):')
            _print_cols(coeffs_2d_angle)
        if coeffs_2d_surface:
            print(f'  2D-surface ({len(coeffs_2d_surface)}):')
            _print_cols(coeffs_2d_surface)
    else:
        _print_cols(coeffs)

    print()
    print('  Usage: python view_mat.py CLtot CLa Cma')
    print()


def _print_cols(names, cols=4):
    """Print a list of names in columns."""
    rows = (len(names) + cols - 1) // cols
    for r in range(rows):
        print('    ', end='')
        for c in range(cols):
            idx = r + c * rows
            if idx < len(names):
                print(f'{names[idx]:<20}', end='')
        print()


# --- Main ---

def find_mat_files():
    """Find all .mat files in the output directory."""
    if not os.path.isdir(OUTPUT_DIR):
        return []
    return sorted(
        os.path.join(OUTPUT_DIR, f)
        for f in os.listdir(OUTPUT_DIR)
        if f.endswith('.mat')
    )


def process_mat_file(mat_path, requested=None, list_mode=False):
    """Process a single .mat file: print tables and write to _tables.txt."""
    data, mat_path = load_data(mat_path)
    coeffs = get_coefficients(data)
    mode = detect_mode(data)

    if list_mode:
        print_summary(data, mat_path)
        print_list(data)
        return

    if requested:
        invalid = [r for r in requested if r not in coeffs]
        if invalid:
            print(f"Error: unknown coefficients: {', '.join(invalid)}")
            print(f"Use --list to see available coefficients.")
            return
        coeffs = requested

    print_summary(data, mat_path)

    output_dir = os.path.dirname(mat_path)
    base = os.path.splitext(os.path.basename(mat_path))[0]
    output_path = os.path.join(output_dir, f'{base}_tables.txt')

    machs = data['Mach_values'].flatten() if 'Mach_values' in data else np.array([])

    _write_tables(data, coeffs, mode, machs, output_path)

    print(f'Written {len(coeffs)} tables to {output_path}')


def main():
    # Parse arguments
    args = sys.argv[1:]
    mat_path = None
    requested = []
    list_mode = False

    i = 0
    while i < len(args):
        if args[i] == '--file' and i + 1 < len(args):
            mat_path = args[i + 1]
            i += 2
        elif args[i] == '--list':
            list_mode = True
            i += 1
        else:
            requested.append(args[i])
            i += 1

    if mat_path:
        # Specific file requested
        process_mat_file(mat_path, requested, list_mode)
    else:
        # Process all .mat files in output directory
        mat_files = find_mat_files()
        if not mat_files:
            print(f"Error: no .mat files found in {OUTPUT_DIR}")
            sys.exit(1)
        for mf in mat_files:
            process_mat_file(mf, requested, list_mode)
            if mf != mat_files[-1]:
                print('\n' + '~' * 80 + '\n')

    return  # early return — table writing moved to _write_tables


def _write_tables_full(data, coeffs, output_path):
    """Write Full Analysis tables (Alpha 2D + Beta 2D + 3D) to terminal and file."""
    alpha_coeffs, beta_coeffs, td_coeffs = classify_full_coefficients(coeffs)

    alpha_vals = data['Alpha_values'].flatten() if 'Alpha_values' in data else np.array([])
    beta_vals = data['Beta_values'].flatten() if 'Beta_values' in data else np.array([])

    angle_var = str(data['Angle_var'].flat[0]) if 'Angle_var' in data else 'Alpha'
    angle_vals = data['Angle_values'].flatten() if 'Angle_values' in data else np.array([])

    surface_2d_labels = get_2d_surface_labels(data)

    surface_vals = {}
    for surface_name in SURFACE_SUFFIX:
        key = f'{surface_name}_values'
        if key in data:
            surface_vals[surface_name] = data[key].flatten()
    active_surfaces = {s for s, v in surface_vals.items() if len(v) > 1}

    # Group 3D-section coefficients by type and surface
    grouped_3d = {}
    for surface_name in SURFACE_SUFFIX:
        if surface_name not in active_surfaces:
            continue
        labels = [l for l in td_coeffs
                  if coeff_surface(l) == surface_name and data[l].ndim == 3]
        if labels:
            grouped_3d[surface_name] = labels

    cs_2d_angle = [l for l in td_coeffs
                   if data[l].ndim == 2 and l not in surface_2d_labels]

    grouped_2d_surface = {}
    for surface_name in SURFACE_SUFFIX:
        if surface_name not in active_surfaces:
            continue
        labels = [l for l in td_coeffs
                  if coeff_surface(l) == surface_name
                  and data[l].ndim == 2
                  and l in surface_2d_labels]
        if labels:
            grouped_2d_surface[surface_name] = labels

    # === PRINT TO TERMINAL ===

    # Alpha 2D section
    if alpha_coeffs and 'Alpha_Mach_values' in data:
        print()
        print(f'  {"=" * 50}')
        print(f'  Alpha x Mach (2D) \u2014 {len(alpha_coeffs)} coefficients')
        print(f'  {"=" * 50}')
        for label in alpha_coeffs:
            print_table_2d(data, label, 'Alpha', alpha_vals,
                           mach_key='Alpha_Mach_values')

    # Beta 2D section
    if beta_coeffs and 'Beta_Mach_values' in data:
        print()
        print(f'  {"=" * 50}')
        print(f'  Beta x Mach (2D) \u2014 {len(beta_coeffs)} coefficients')
        print(f'  {"=" * 50}')
        for label in beta_coeffs:
            print_table_2d(data, label, 'Beta', beta_vals,
                           mach_key='Beta_Mach_values')

    # 3D section
    if td_coeffs and 'Mach_values' in data:
        if grouped_3d:
            for surface_name, labels in grouped_3d.items():
                svals = surface_vals[surface_name]
                print()
                print(f'  {"=" * 50}')
                print(f'  {surface_name} \u2014 3D tables ({angle_var} x Mach x {surface_name})')
                print(f'  {surface_name} values: {svals}')
                print(f'  {"=" * 50}')
                for label in labels:
                    print_table_3d(data, label, angle_var, angle_vals,
                                   surface_name, svals)

        if cs_2d_angle and len(angle_vals) > 0:
            print()
            print(f'  {"=" * 50}')
            print(f'  CS 2D tables ({angle_var} x Mach)')
            print(f'  {"=" * 50}')
            for label in cs_2d_angle:
                print_table_2d(data, label, angle_var, angle_vals)

        if grouped_2d_surface:
            print()
            print(f'  {"=" * 50}')
            print(f'  CS 2D tables (\u03b4 x Mach)')
            print(f'  {"=" * 50}')
            for surface_name, labels in grouped_2d_surface.items():
                svals = surface_vals[surface_name]
                for label in labels:
                    print_table_2d(data, label, surface_name, svals)

    # === WRITE TO FILE ===
    with open(output_path, 'w') as f:
        f.write('=' * 80 + '\n')
        f.write('  AVL DATA (Full Analysis)\n')
        f.write('=' * 80 + '\n\n')

        # Alpha section
        if alpha_coeffs and 'Alpha_Mach_values' in data:
            a_machs = data['Alpha_Mach_values'].flatten()
            f.write(f'  --- Alpha x Mach (2D) ---\n')
            f.write(f'  Alpha values:      {alpha_vals}\n')
            f.write(f'  Alpha Mach values: {a_machs}\n')
            f.write(f'  Coefficients:      {len(alpha_coeffs)}\n')
            f.write(f'  Matrix size:       {len(alpha_vals)} x {len(a_machs)} (Alpha x Mach)\n\n')
            for label in alpha_coeffs:
                write_table_2d(f, data, label, 'Alpha', alpha_vals,
                               mach_key='Alpha_Mach_values')

        # Beta section
        if beta_coeffs and 'Beta_Mach_values' in data:
            b_machs = data['Beta_Mach_values'].flatten()
            f.write(f'\n  --- Beta x Mach (2D) ---\n')
            f.write(f'  Beta values:       {beta_vals}\n')
            f.write(f'  Beta Mach values:  {b_machs}\n')
            f.write(f'  Coefficients:      {len(beta_coeffs)}\n')
            f.write(f'  Matrix size:       {len(beta_vals)} x {len(b_machs)} (Beta x Mach)\n\n')
            for label in beta_coeffs:
                write_table_2d(f, data, label, 'Beta', beta_vals,
                               mach_key='Beta_Mach_values')

        # 3D section
        if td_coeffs and 'Mach_values' in data:
            td_machs = data['Mach_values'].flatten()
            n_3d = sum(1 for l in td_coeffs if data[l].ndim == 3)
            n_2d_a = len(cs_2d_angle)
            n_2d_s = sum(len(v) for v in grouped_2d_surface.values())

            f.write(f'\n  --- Control Surfaces ---\n')
            f.write(f'  Mach values:   {td_machs}\n')
            if len(angle_vals) > 0:
                f.write(f'  {angle_var} values: {angle_vals}\n')
            for sname in SURFACE_SUFFIX:
                if sname in active_surfaces:
                    f.write(f'  {sname} values: {surface_vals[sname]}\n')
            f.write(f'  Coefficients:  {len(td_coeffs)} '
                    f'({n_3d} 3D + {n_2d_a} 2D-angle + {n_2d_s} 2D-surface)\n\n')

            if grouped_3d:
                for surface_name, labels in grouped_3d.items():
                    svals = surface_vals[surface_name]
                    f.write(f'  {"=" * 50}\n')
                    f.write(f'  {surface_name} \u2014 3D tables ({angle_var} x Mach x {surface_name})\n')
                    f.write(f'  {surface_name} values: {svals}\n')
                    f.write(f'  {"=" * 50}\n')
                    for label in labels:
                        write_table_3d(f, data, label, angle_var, angle_vals,
                                       surface_name, svals)

            if cs_2d_angle and len(angle_vals) > 0:
                f.write(f'\n  {"=" * 50}\n')
                f.write(f'  CS 2D tables ({angle_var} x Mach)\n')
                f.write(f'  {"=" * 50}\n')
                for label in cs_2d_angle:
                    write_table_2d(f, data, label, angle_var, angle_vals)

            if grouped_2d_surface:
                f.write(f'\n  {"=" * 50}\n')
                f.write(f'  CS 2D tables (\u03b4 x Mach)\n')
                f.write(f'  {"=" * 50}\n')
                for surface_name, labels in grouped_2d_surface.items():
                    svals = surface_vals[surface_name]
                    for label in labels:
                        write_table_2d(f, data, label, surface_name, svals)


def _write_tables(data, coeffs, mode, machs, output_path):
    """Write tables to terminal and file."""
    if mode == 'full':
        _write_tables_full(data, coeffs, output_path)

    elif mode == '2d':
        row_name, row_vals = detect_row_var(data)

        for label in coeffs:
            print_table_2d(data, label, row_name, row_vals)

        with open(output_path, 'w') as f:
            f.write('=' * 80 + '\n')
            f.write('  AVL DATA\n')
            f.write('=' * 80 + '\n\n')
            f.write(f'  Mach values:   {machs}\n')
            f.write(f'  {row_name} values: {row_vals}\n')
            f.write(f'  Coefficients:  {len(coeffs)}\n')
            f.write(f'  Matrix size:   {len(row_vals)} x {len(machs)} ({row_name} x Mach)\n\n')
            for label in coeffs:
                write_table_2d(f, data, label, row_name, row_vals)

    else:
        angle_name, angle_vals = detect_angle_var(data)
        surface_2d_labels = get_2d_surface_labels(data)

        surface_vals = {}
        for surface_name in SURFACE_SUFFIX:
            key = f'{surface_name}_values'
            if key in data:
                surface_vals[surface_name] = data[key].flatten()

        active_surfaces = {s for s, v in surface_vals.items() if len(v) > 1}

        # Group coefficients into three categories
        grouped_3d = {}
        for surface_name in SURFACE_SUFFIX:
            if surface_name not in active_surfaces:
                continue
            labels = [l for l in coeffs if coeff_surface(l) == surface_name and data[l].ndim == 3]
            if labels:
                grouped_3d[surface_name] = labels

        coeffs_2d_angle = [l for l in coeffs
                           if data[l].ndim == 2 and l not in surface_2d_labels]
        # Group 2D-surface coefficients by their surface
        grouped_2d_surface = {}
        for surface_name in SURFACE_SUFFIX:
            if surface_name not in active_surfaces:
                continue
            labels = [l for l in coeffs
                      if coeff_surface(l) == surface_name
                      and data[l].ndim == 2
                      and l in surface_2d_labels]
            if labels:
                grouped_2d_surface[surface_name] = labels

        # Print to terminal
        if grouped_3d:
            for surface_name, labels in grouped_3d.items():
                svals = surface_vals[surface_name]
                print()
                print(f'  {"=" * 50}')
                print(f'  {surface_name} \u2014 3D tables ({angle_name} x Mach x {surface_name})')
                print(f'  {surface_name} values: {svals}')
                print(f'  {"=" * 50}')
                for label in labels:
                    if angle_name:
                        print_table_3d(data, label, angle_name, angle_vals,
                                       surface_name, svals)

        if coeffs_2d_angle and angle_name:
            print()
            print(f'  {"=" * 50}')
            print(f'  2D tables ({angle_name} x Mach)')
            print(f'  {"=" * 50}')
            for label in coeffs_2d_angle:
                print_table_2d(data, label, angle_name, angle_vals)

        if grouped_2d_surface:
            print()
            print(f'  {"=" * 50}')
            print(f'  2D tables (\u03b4 x Mach)')
            print(f'  {"=" * 50}')
            for surface_name, labels in grouped_2d_surface.items():
                svals = surface_vals[surface_name]
                for label in labels:
                    print_table_2d(data, label, surface_name, svals)

        # Write to file
        with open(output_path, 'w') as f:
            n_3d = sum(1 for l in coeffs if data[l].ndim == 3)
            n_2d_a = len(coeffs_2d_angle)
            n_2d_s = sum(len(v) for v in grouped_2d_surface.values())

            f.write('=' * 80 + '\n')
            f.write('  AVL DATA (3D Mode)\n')
            f.write('=' * 80 + '\n\n')
            f.write(f'  Mach values:   {machs}\n')
            if angle_name:
                f.write(f'  {angle_name} values: {angle_vals}\n')
            for sname, svals in surface_vals.items():
                if sname in active_surfaces:
                    f.write(f'  {sname} values: {svals}\n')
            f.write(f'  Coefficients:  {len(coeffs)} '
                    f'({n_3d} 3D + {n_2d_a} 2D-angle + {n_2d_s} 2D-surface)\n\n')

            if grouped_3d:
                for surface_name, labels in grouped_3d.items():
                    svals = surface_vals[surface_name]
                    f.write(f'  {"=" * 50}\n')
                    f.write(f'  {surface_name} \u2014 3D tables ({angle_name} x Mach x {surface_name})\n')
                    f.write(f'  {surface_name} values: {svals}\n')
                    f.write(f'  {"=" * 50}\n')
                    for label in labels:
                        if angle_name:
                            write_table_3d(f, data, label, angle_name, angle_vals,
                                           surface_name, svals)

            if coeffs_2d_angle and angle_name:
                f.write(f'\n  {"=" * 50}\n')
                f.write(f'  2D tables ({angle_name} x Mach)\n')
                f.write(f'  {"=" * 50}\n')
                for label in coeffs_2d_angle:
                    write_table_2d(f, data, label, angle_name, angle_vals)

            if grouped_2d_surface:
                f.write(f'\n  {"=" * 50}\n')
                f.write(f'  2D tables (\u03b4 x Mach)\n')
                f.write(f'  {"=" * 50}\n')
                for surface_name, labels in grouped_2d_surface.items():
                    svals = surface_vals[surface_name]
                    for label in labels:
                        write_table_2d(f, data, label, surface_name, svals)


if __name__ == '__main__':
    main()
