"""Test: 2D mode skips files with non-zero control surfaces or opposite angle."""

import os
import glob
from parse_avl import process_files

BASE = os.path.dirname(__file__)
CLEAN_DIR = os.path.join(BASE, "test files")              # all surfaces = 0, Beta = 0
FLAP_DIR  = os.path.join(BASE, "test_files_new", "flap")  # FLAP varies
BETA_DIR  = os.path.join(BASE, "test_files_new", "beta")  # Beta varies

clean_files = sorted(f for f in glob.glob(os.path.join(CLEAN_DIR, "*")) if os.path.isfile(f))
flap_files  = sorted(f for f in glob.glob(os.path.join(FLAP_DIR, "*")) if os.path.isfile(f))
beta_files  = sorted(f for f in glob.glob(os.path.join(BETA_DIR, "*")) if os.path.isfile(f))

print(f"Clean files: {len(clean_files)},  Flap files: {len(flap_files)},  Beta files: {len(beta_files)}")
print()

# --- Test 1: Alpha mode, clean files only → all should be included ---
mat, stats = process_files(clean_files, second_var='Alpha')
print(f"TEST 1 – Alpha mode, clean files only")
print(f"  Parsed: {stats['parsed']},  Skipped: {len(stats['skipped'])}")
assert stats['parsed'] == len(clean_files), f"Expected all {len(clean_files)} parsed, got {stats['parsed']}"
assert len(stats['skipped']) == 0, f"Expected 0 skipped, got {stats['skipped']}"
print("  PASSED\n")

# --- Test 2: Alpha mode, mixed with flap files → non-zero FLAP skipped ---
mixed_files = clean_files + flap_files
mat, stats = process_files(mixed_files, second_var='Alpha')
skipped_names = [s[0] for s in stats['skipped']]
skipped_reasons = {s[0]: s[1] for s in stats['skipped']}

flap_nonzero_expected = [os.path.basename(f) for f in flap_files
                         if "F-10" in os.path.basename(f) or "F10" in os.path.basename(f)]

print(f"TEST 2 – Alpha mode, mixed with flap files")
print(f"  Parsed: {stats['parsed']},  Skipped: {len(stats['skipped'])}")
print(f"  Skipped: {stats['skipped']}")
for name in flap_nonzero_expected:
    assert name in skipped_names, f"Expected {name} to be skipped"
    assert "non-zero" in skipped_reasons[name], f"Wrong reason for {name}: {skipped_reasons[name]}"
print("  PASSED\n")

# --- Test 3: FLAP mode → no filtering at all ---
mat, stats = process_files(flap_files, second_var='FLAP')
print(f"TEST 3 – FLAP mode, flap files only")
print(f"  Parsed: {stats['parsed']},  Skipped: {len(stats['skipped'])}")
nonzero_skips = [s for s in stats['skipped'] if "non-zero" in s[1]]
assert len(nonzero_skips) == 0, f"FLAP mode should not filter, but got: {nonzero_skips}"
assert stats['parsed'] == len(flap_files), f"Expected all {len(flap_files)} parsed, got {stats['parsed']}"
print("  PASSED\n")

# --- Test 4: Alpha mode, mixed with beta files → non-zero Beta skipped ---
mixed_alpha_beta = clean_files + beta_files
mat, stats = process_files(mixed_alpha_beta, second_var='Alpha')
skipped_names = [s[0] for s in stats['skipped']]
skipped_reasons = {s[0]: s[1] for s in stats['skipped']}

# Beta files with non-zero Beta should be skipped in Alpha mode
beta_nonzero_expected = [os.path.basename(f) for f in beta_files
                         if "B0" not in os.path.basename(f)
                         or os.path.basename(f).endswith("B0") is False]
# More precise: files with non-zero beta values
beta_nonzero_expected = [os.path.basename(f) for f in beta_files
                         if "B-5" in os.path.basename(f) or "B5" in os.path.basename(f)]
beta_zero_expected = [os.path.basename(f) for f in beta_files
                      if os.path.basename(f).endswith("B0")]

print(f"TEST 4 – Alpha mode, mixed with beta files (non-zero Beta should be skipped)")
print(f"  Parsed: {stats['parsed']},  Skipped: {len(stats['skipped'])}")
print(f"  Expected skipped (non-zero Beta): {beta_nonzero_expected}")
print(f"  Skipped: {stats['skipped']}")
for name in beta_nonzero_expected:
    assert name in skipped_names, f"Expected {name} to be skipped (has non-zero Beta)"
    assert "Beta" in skipped_reasons[name], f"Expected Beta in reason for {name}: {skipped_reasons[name]}"
print("  PASSED\n")

# --- Test 5: Beta mode, mixed with beta files → Beta is the selected var, Alpha must be 0 ---
# Beta files have Alpha=0 so they should all pass. Clean files have Beta=0 and Alpha varies,
# so files with non-zero Alpha should be skipped.
mat, stats = process_files(mixed_alpha_beta, second_var='Beta')
skipped_names = [s[0] for s in stats['skipped']]
skipped_reasons = {s[0]: s[1] for s in stats['skipped']}

# Clean files have varying Alpha — those with Alpha != 0 should be skipped in Beta mode
alpha_nonzero_skipped = [s for s in stats['skipped'] if "Alpha" in s[1]]

print(f"TEST 5 – Beta mode, mixed with beta files (non-zero Alpha should be skipped)")
print(f"  Parsed: {stats['parsed']},  Skipped: {len(stats['skipped'])}")
print(f"  Skipped for non-zero Alpha: {len(alpha_nonzero_skipped)}")
# Clean files with Alpha=0 should pass, others should be skipped
assert len(alpha_nonzero_skipped) > 0, "Expected some clean files with non-zero Alpha to be skipped"
# Verify none of the skipped-for-Alpha files actually had Alpha=0
for name, reason in alpha_nonzero_skipped:
    assert "Alpha=" in reason and "Alpha=0.0" not in reason, \
        f"File {name} skipped for Alpha but had Alpha=0: {reason}"
print("  PASSED\n")

# --- Test 6: Beta mode, only beta files → all should pass (Alpha=0 in all) ---
mat, stats = process_files(beta_files, second_var='Beta')
print(f"TEST 6 – Beta mode, beta files only (all have Alpha=0)")
print(f"  Parsed: {stats['parsed']},  Skipped: {len(stats['skipped'])}")
assert stats['parsed'] == len(beta_files), f"Expected all {len(beta_files)} parsed, got {stats['parsed']}"
assert len(stats['skipped']) == 0, f"Expected 0 skipped, got {stats['skipped']}"
print("  PASSED\n")

print("ALL TESTS PASSED")
