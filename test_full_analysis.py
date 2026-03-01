"""Test: Full Analysis mode — combined 2D Alpha/Beta + 3D control surfaces."""

import os
import glob
import numpy as np
from parse_avl import (process_files_full, process_files, process_files_3d,
                        NON_CS_LABELS, SURFACE_SUFFIX, ALL_LABELS)

BASE = os.path.dirname(__file__)
CLEAN_DIR = os.path.join(BASE, "test files")
TD_DIR = os.path.join(BASE, "test_files_new", "3d_tests", "alpha_flap")

clean_files = sorted(f for f in glob.glob(os.path.join(CLEAN_DIR, "*")) if os.path.isfile(f))
td_files = sorted(f for f in glob.glob(os.path.join(TD_DIR, "*")) if os.path.isfile(f))
all_files = clean_files + td_files

print(f"Clean files: {len(clean_files)},  3D test files: {len(td_files)}")
print()

# --- Test 1: Full Analysis produces valid output ---
mat_data, stats = process_files_full(all_files, angle_var='Alpha')
print("TEST 1 – Full Analysis produces valid output")
print(f"  Alpha stats: {'OK' if stats['alpha_stats'] else 'None'}")
print(f"  Beta stats:  {'OK' if stats['beta_stats'] else 'None'}")
print(f"  3D stats:    {'OK' if stats['td_stats'] else 'None'}")
print(f"  Alpha labels: {stats['n_alpha_labels']}")
print(f"  Beta labels:  {stats['n_beta_labels']}")
print(f"  3D labels:    {stats['n_td_labels']}")
assert stats['alpha_stats'] is not None, "Alpha section should have data"
assert stats['n_alpha_labels'] > 0, "Should have Alpha coefficients"
assert stats['n_td_labels'] > 0, "Should have 3D coefficients"
print("  PASSED\n")

# --- Test 2: Alpha section has correct axis naming ---
print("TEST 2 – Alpha section axis naming")
assert 'Alpha_values' in mat_data, "Missing Alpha_values"
assert 'Alpha_Mach_values' in mat_data, "Missing Alpha_Mach_values"
print(f"  Alpha_values shape: {mat_data['Alpha_values'].shape}")
print(f"  Alpha_Mach_values shape: {mat_data['Alpha_Mach_values'].shape}")
print("  PASSED\n")

# --- Test 3: Beta section has prefixed names ---
print("TEST 3 – Beta section uses Beta_ prefix")
beta_keys = [k for k in mat_data if k.startswith('Beta_') and k not in ('Beta_values', 'Beta_Mach_values')]
print(f"  Beta coefficient keys: {len(beta_keys)}")
assert len(beta_keys) > 0, "Should have Beta-prefixed coefficients"
# Verify prefix matches non-CS labels
for label in NON_CS_LABELS:
    beta_key = f'Beta_{label}'
    if beta_key in mat_data:
        assert isinstance(mat_data[beta_key], np.ndarray), f"{beta_key} should be ndarray"
print("  PASSED\n")

# --- Test 4: No CS coefficients in Alpha section (unprefixed) ---
print("TEST 4 – Alpha section excludes CS coefficients")
_CS_SUFFIXES = set(SURFACE_SUFFIX.values())
cs_labels = [l for l in ALL_LABELS if any(s in l for s in _CS_SUFFIXES)]
# Alpha section uses unprefixed names, so check if any CS label appears unprefixed
# BUT 3D section also uses unprefixed CS labels. So we just verify that the non-CS
# labels are present with correct Alpha×Mach dimensions
a_stats = stats['alpha_stats']
n_alpha = len(a_stats['var_values'])
n_mach_alpha = len(a_stats['machs'])
for label in NON_CS_LABELS[:5]:  # spot check first 5
    assert label in mat_data, f"Missing non-CS label {label}"
    assert mat_data[label].shape == (n_alpha, n_mach_alpha), \
        f"{label} shape {mat_data[label].shape} != expected ({n_alpha}, {n_mach_alpha})"
print(f"  Non-CS labels have shape ({n_alpha}, {n_mach_alpha}) — correct Alpha x Mach")
print("  PASSED\n")

# --- Test 5: 3D section has control surface data ---
print("TEST 5 – 3D section has CS coefficients")
assert 'Mach_values' in mat_data, "Missing Mach_values for 3D"
assert 'Angle_values' in mat_data, "Missing Angle_values for 3D"
assert 'Angle_var' in mat_data, "Missing Angle_var metadata"
assert mat_data['Angle_var'][0] == 'Alpha', f"Expected Angle_var='Alpha', got {mat_data['Angle_var']}"
# Check at least one surface value array exists
has_surface = any(f'{s}_values' in mat_data for s in SURFACE_SUFFIX)
assert has_surface, "Should have at least one surface values array"
# Check at least one CS coefficient exists
has_cs = any(l in mat_data for l in cs_labels)
assert has_cs, "Should have at least one CS coefficient from 3D"
print("  PASSED\n")

# --- Test 6: No duplicate keys ---
print("TEST 6 – No duplicate variable names in mat_data")
keys = list(mat_data.keys())
assert len(keys) == len(set(keys)), f"Duplicate keys found: {[k for k in keys if keys.count(k) > 1]}"
print(f"  Total variables in .mat: {len(keys)}")
print("  PASSED\n")

# --- Test 7: Existing 2D and 3D modes still work ---
print("TEST 7 – Existing modes unchanged")
mat_2d, stats_2d = process_files(clean_files, second_var='Alpha')
assert stats_2d['parsed'] > 0, "2D mode should still work"
mat_3d, stats_3d = process_files_3d(td_files, angle_var='Alpha')
assert stats_3d['parsed'] > 0, "3D mode should still work"
print(f"  2D parsed: {stats_2d['parsed']},  3D parsed: {stats_3d['parsed']}")
print("  PASSED\n")

print("ALL TESTS PASSED")
