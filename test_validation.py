"""Test: validation features — skip_conflicts in 2D mode, pre-export validation for 3D mode."""

import os
import glob
from parse_avl import process_files, parse_file

BASE = os.path.dirname(__file__)
DEMO_DIR = os.path.join(BASE, "demo_files")

demo_files = sorted(
    f for f in glob.glob(os.path.join(DEMO_DIR, "*")) if os.path.isfile(f)
)
demo_names = {os.path.basename(f) for f in demo_files}

print(f"Demo files: {len(demo_files)}")
print(f"  {sorted(demo_names)}\n")

# Helper: get skipped filenames from stats
def skipped_names(stats):
    return {s[0] for s in stats['skipped']}

def skipped_reasons(stats):
    return {s[0]: s[1] for s in stats['skipped']}


# ============================================================
# 2D MODE — skip_conflicts=True (default)
# ============================================================

# --- Test 1: Alpha mode, skip_conflicts=True ---
# M0.1A8B3 has Beta=3 → should be skipped (non-zero opposite angle)
# M0.1A5F10, M0.1A10L6, M0.1A-2E5, M0.1A12R8 have non-zero surfaces → skipped
# M0.1A0B0 and M0.1A3 are clean → should pass
mat, stats = process_files(demo_files, second_var='Alpha', skip_conflicts=True)
skipped = skipped_names(stats)
print("TEST 1 – Alpha mode, skip_conflicts=True")
print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
assert 'M0.1A8B3' in skipped, "M0.1A8B3 should be skipped (Beta=3)"
assert 'M0.1A5F10' in skipped, "M0.1A5F10 should be skipped (FLAP=10)"
assert 'M0.1A10L6' in skipped, "M0.1A10L6 should be skipped (AIL=6)"
assert 'M0.1A-2E5' in skipped, "M0.1A-2E5 should be skipped (ELEV=5)"
assert 'M0.1A12R8' in skipped, "M0.1A12R8 should be skipped (RUDD=8)"
assert 'M0.1A0B0' not in skipped, "M0.1A0B0 should NOT be skipped"
assert 'M0.1A3' not in skipped, "M0.1A3 should NOT be skipped"
print("  PASSED\n")

# --- Test 2: Alpha mode, skip_conflicts=False ---
# No files should be skipped for non-zero values (only for missing data etc.)
mat, stats = process_files(demo_files, second_var='Alpha', skip_conflicts=False)
skipped = skipped_names(stats)
reasons = skipped_reasons(stats)
nonzero_skips = {n for n, r in reasons.items() if "non-zero" in r}
print("TEST 2 – Alpha mode, skip_conflicts=False")
print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
assert len(nonzero_skips) == 0, f"No files should be skipped for non-zero values, got: {nonzero_skips}"
print("  PASSED\n")

# --- Test 3: Beta mode, skip_conflicts=True ---
# Most demo files have Alpha != 0 → should be skipped (non-zero opposite angle)
# M0.1A0B0 has Alpha=0, Beta=0 → passes but Beta=0 might cause issues
# M0.1A8B3 has Beta=3 but Alpha=8 → skipped for non-zero Alpha
mat, stats = process_files(demo_files, second_var='Beta', skip_conflicts=True)
skipped = skipped_names(stats)
print("TEST 3 – Beta mode, skip_conflicts=True")
print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
# Files with Alpha != 0 should be skipped
assert 'M0.1A3' in skipped, "M0.1A3 should be skipped (Alpha=3 in Beta mode)"
assert 'M0.1A8B3' in skipped, "M0.1A8B3 should be skipped (Alpha=8 in Beta mode)"
assert 'M0.1A5F10' in skipped, "M0.1A5F10 should be skipped (Alpha=5, FLAP=10)"
print("  PASSED\n")

# --- Test 4: FLAP mode, skip_conflicts=True ---
# M0.1A8B3 has Alpha=8 AND Beta=3 (both angles non-zero) → should be skipped
# M0.1A10L6 has AIL=6 (another surface non-zero) → should be skipped
# M0.1A5F10 has only FLAP=10 → should pass
# Files without FLAP value should be skipped for missing value
mat, stats = process_files(demo_files, second_var='FLAP', skip_conflicts=True)
skipped = skipped_names(stats)
reasons = skipped_reasons(stats)
print("TEST 4 – FLAP mode, skip_conflicts=True")
print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
for name, reason in sorted(reasons.items()):
    print(f"    {name}: {reason}")
# M0.1A8B3 has both angles non-zero
assert 'M0.1A8B3' in skipped, "M0.1A8B3 should be skipped (both angles non-zero)"
assert "non-zero" in reasons.get('M0.1A8B3', ''), "M0.1A8B3 skip reason should mention non-zero"
# M0.1A10L6 has AIL=6 (another surface)
assert 'M0.1A10L6' in skipped, "M0.1A10L6 should be skipped (AIL non-zero)"
# M0.1A-2E5 has ELEV=5 (another surface)
assert 'M0.1A-2E5' in skipped, "M0.1A-2E5 should be skipped (ELEV non-zero)"
# M0.1A12R8 has RUDD=8 (another surface)
assert 'M0.1A12R8' in skipped, "M0.1A12R8 should be skipped (RUDD non-zero)"
print("  PASSED\n")

# --- Test 5: FLAP mode, skip_conflicts=False ---
# No files skipped for non-zero conflicts
mat, stats = process_files(demo_files, second_var='FLAP', skip_conflicts=False)
reasons = skipped_reasons(stats)
nonzero_skips = {n for n, r in reasons.items() if "non-zero" in r}
print("TEST 5 – FLAP mode, skip_conflicts=False")
print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
assert len(nonzero_skips) == 0, f"No files should be skipped for non-zero values, got: {nonzero_skips}"
print("  PASSED\n")

# --- Test 6: AIL mode, skip_conflicts=True ---
# M0.1A10L6 has AIL=6 → should pass
# M0.1A5F10 has FLAP=10 (another surface) → should be skipped
# M0.1A8B3 has both angles non-zero → should be skipped
mat, stats = process_files(demo_files, second_var='AIL', skip_conflicts=True)
skipped = skipped_names(stats)
reasons = skipped_reasons(stats)
print("TEST 6 – AIL mode, skip_conflicts=True")
print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
for name, reason in sorted(reasons.items()):
    print(f"    {name}: {reason}")
assert 'M0.1A5F10' in skipped, "M0.1A5F10 should be skipped (FLAP non-zero in AIL mode)"
assert 'M0.1A8B3' in skipped, "M0.1A8B3 should be skipped (both angles non-zero)"
print("  PASSED\n")


# ============================================================
# 3D MODE — _validate_files_pre_export logic (tested directly)
# ============================================================

# Replicate the validation logic from app.py without needing the GUI

def validate_files(filepaths, check_angle=True, check_defl=True):
    """Standalone version of _validate_files_pre_export()."""
    angle_violations = []
    defl_violations = []

    for filepath in filepaths:
        filename = os.path.basename(filepath)
        try:
            _mach, run_vars, _coeffs, _warns = parse_file(filepath)
        except Exception:
            continue

        if check_angle:
            alpha = run_vars.get('Alpha')
            beta = run_vars.get('Beta')
            if alpha is not None and alpha != 0 and beta is not None and beta != 0:
                angle_violations.append((filename, f"Alpha={alpha}, Beta={beta}"))

        if check_defl:
            nonzero = []
            for surface in ('FLAP', 'AIL', 'ELEV', 'RUDD'):
                val = run_vars.get(surface)
                if val is not None and val != 0:
                    nonzero.append(f"{surface}={val}")
            if len(nonzero) > 1:
                defl_violations.append((filename, ", ".join(nonzero)))

    ok = not angle_violations and not defl_violations
    return ok, angle_violations, defl_violations


# --- Test 7: Both checks ON — only M0.1A8B3 has angle conflict ---
ok, angle_v, defl_v = validate_files(demo_files, check_angle=True, check_defl=True)
angle_names = {v[0] for v in angle_v}
defl_names = {v[0] for v in defl_v}
print("TEST 7 – 3D validation, both checks ON")
print(f"  OK: {ok}")
print(f"  Angle violations: {angle_v}")
print(f"  Defl violations:  {defl_v}")
assert not ok, "Should NOT be ok (M0.1A8B3 has both angles non-zero)"
assert 'M0.1A8B3' in angle_names, "M0.1A8B3 should have angle violation"
assert len(defl_v) == 0, "No demo file has multiple surfaces non-zero"
# Clean files should NOT be flagged
assert 'M0.1A0B0' not in angle_names, "M0.1A0B0 should not be flagged"
assert 'M0.1A3' not in angle_names, "M0.1A3 should not be flagged"
assert 'M0.1A5F10' not in angle_names, "M0.1A5F10 should not be flagged (Beta=0)"
print("  PASSED\n")

# --- Test 8: Angle check OFF — should pass (no deflection conflicts in demo) ---
ok, angle_v, defl_v = validate_files(demo_files, check_angle=False, check_defl=True)
print("TEST 8 – 3D validation, angle check OFF")
print(f"  OK: {ok}")
assert ok, "Should be ok (angle check disabled, no multi-deflection files)"
assert len(angle_v) == 0, "Angle violations should be empty when check is off"
print("  PASSED\n")

# --- Test 9: Deflection check OFF — still catches angle conflict ---
ok, angle_v, defl_v = validate_files(demo_files, check_angle=True, check_defl=False)
print("TEST 9 – 3D validation, deflection check OFF")
print(f"  OK: {ok}")
assert not ok, "Should NOT be ok (angle check still catches M0.1A8B3)"
assert 'M0.1A8B3' in {v[0] for v in angle_v}
assert len(defl_v) == 0, "Defl violations should be empty when check is off"
print("  PASSED\n")

# --- Test 10: Both checks OFF — everything passes ---
ok, angle_v, defl_v = validate_files(demo_files, check_angle=False, check_defl=False)
print("TEST 10 – 3D validation, both checks OFF")
print(f"  OK: {ok}")
assert ok, "Should be ok (both checks disabled)"
assert len(angle_v) == 0
assert len(defl_v) == 0
print("  PASSED\n")


# ============================================================
# EDGE CASE: synthetic file with multiple non-zero surfaces
# ============================================================

# Create a temporary file with FLAP=10, AIL=6 to test deflection violation
import tempfile

MULTI_DEFL_CONTENT = """\
 ---------------------------------------------------------------
 Vortex Lattice Output -- Total Forces

 Configuration: Test

 Standard axis orientation,  X fwd, Z down

 Run case: M0.1A5F10L6

  Alpha =   5.00000     pb/2V =  -0.00000     p'b/2V =  -0.00000
  Beta  =   0.00000     qc/2V =   0.00000
  Mach  =     0.100     rb/2V =  -0.00000     r'b/2V =  -0.00000

  CXtot =   0.01250     Cltot =  -0.02510     Cl'tot =  -0.02510
  CYtot =   0.00550     Cmtot =  -0.32000
  CZtot =  -0.33500     Cntot =  -0.00325     Cn'tot =  -0.00325

  CLtot =   0.33600
  CDtot =   0.01600
  CDvis =   0.00000     CDind = 0.0160000
  CLff  =   0.33500     CDff  = 0.0159000    | Trefftz
  CYff  =   0.00550         e =    0.8600    | Plane

   FLAP            =  10.00000
   AIL             =   6.00000
   ELEV            =   0.00000
   RUDD            =   0.00000

 ---------------------------------------------------------------

 Stability-axis derivatives...

                             alpha                beta
                  ----------------    ----------------
 z' force CL |    CLa =   3.820000    CLb =   0.007100
 y  force CY |    CYa =   0.005850    CYb =  -0.221000
 x  force CD |    CDa =   0.029000    CDb =   0.006300
 x' mom.  Cl'|    Cla =  -0.003210    Clb =  -0.016200
 y  mom.  Cm |    Cma =  -1.225000    Cmb =  -0.004100
 z' mom.  Cn'|    Cna =   0.017800    Cnb =   0.131500

                     roll rate  p'      pitch rate  q'        yaw rate  r'
                  ----------------    ----------------    ----------------
 z' force CL |    CLp =  -0.000110    CLq =   7.060000    CLr =  -0.117500
 y  force CY |    CYp =   0.013350    CYq =   0.011250    CYr =   0.283500
 x  force CD |    CDp =  -0.012350    CDq =  -0.000110    CDr =  -0.007550
 x' mom.  Cl'|    Clp =  -0.386500    Clq =  -0.000405    Clr =   0.021100
 y  mom.  Cm |    Cmp =   0.000125    Cmq =  -9.910000    Cmr =   0.047100
 z' mom.  Cn'|    Cnp =  -0.008050    Cnq =   0.002050    Cnr =  -0.170500

                  FLAP         d01     AIL          d02     ELEV         d03     RUDD         d04
                  ----------------    ----------------    ----------------    ----------------
 z' force CL |   CLd01 =   0.000150   CLd02 =   0.000002   CLd03 =   0.005820   CLd04 =   0.000003
 y  force CY |   CYd01 =   0.000003   CYd02 =  -0.000745   CYd03 =   0.000017   CYd04 =  -0.002610
 x  force CD |   CDd01 =   0.000003   CDd02 =  -0.000465   CDd03 =  -0.000001   CDd04 =   0.000011
 x' mom.  Cl'|   Cld01 =  -0.000003   Cld02 =   0.003905   Cld03 =   0.000001   Cld04 =  -0.000205
 y  mom.  Cm |   Cmd01 =   0.000003   Cmd02 =   0.000001   Cmd03 =  -0.016820   Cmd04 =  -0.000013
 z' mom.  Cn'|   Cnd01 =  -0.000003   Cnd02 =   0.000442   Cnd03 =  -0.000006   Cnd04 =   0.001625
 Trefftz drag| CDffd01 =   0.000003 CDffd02 =  -0.000462 CDffd03 =  -0.000001 CDffd04 =   0.000010
 span eff.   |    ed01 =   0.000003    ed02 =   0.000065    ed03 =   0.000005    ed04 =  -0.001265



 Neutral point  Xnp =   0.457600

 Clb Cnr / Clr Cnb  =   1.003500    (  > 1 if spirally stable )
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='', prefix='M0.1A5F10L6_',
                                  delete=False, dir=DEMO_DIR) as f:
    f.write(MULTI_DEFL_CONTENT)
    temp_path = f.name
    temp_name = os.path.basename(temp_path)

try:
    test_files = demo_files + [temp_path]

    # --- Test 11: Deflection violation detected ---
    ok, angle_v, defl_v = validate_files(test_files, check_angle=True, check_defl=True)
    defl_names = {v[0] for v in defl_v}
    print("TEST 11 – 3D validation with multi-deflection file")
    print(f"  OK: {ok}")
    print(f"  Defl violations: {defl_v}")
    assert not ok, "Should NOT be ok (multi-deflection file exists)"
    assert temp_name in defl_names, f"{temp_name} should have deflection violation"
    # Check detail string mentions both FLAP and AIL
    detail = next(v[1] for v in defl_v if v[0] == temp_name)
    assert "FLAP" in detail and "AIL" in detail, f"Detail should mention FLAP and AIL: {detail}"
    print("  PASSED\n")

    # --- Test 12: 2D FLAP mode skips multi-deflection file ---
    mat, stats = process_files(test_files, second_var='FLAP', skip_conflicts=True)
    skipped = skipped_names(stats)
    print("TEST 12 – 2D FLAP mode skips multi-deflection file")
    print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
    assert temp_name in skipped, f"{temp_name} should be skipped (AIL also non-zero)"
    print("  PASSED\n")

    # --- Test 13: 2D FLAP mode, skip_conflicts=False — includes multi-deflection file ---
    mat, stats = process_files(test_files, second_var='FLAP', skip_conflicts=False)
    skipped = skipped_names(stats)
    reasons = skipped_reasons(stats)
    nonzero_skips = {n for n, r in reasons.items() if "non-zero" in r}
    print("TEST 13 – 2D FLAP mode, skip_conflicts=False")
    print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
    assert temp_name not in nonzero_skips, f"{temp_name} should NOT be skipped for non-zero"
    print("  PASSED\n")

    # --- Test 14: 2D Alpha mode skips multi-deflection file (has FLAP+AIL non-zero) ---
    mat, stats = process_files(test_files, second_var='Alpha', skip_conflicts=True)
    skipped = skipped_names(stats)
    print("TEST 14 – 2D Alpha mode skips multi-deflection file")
    print(f"  Parsed: {stats['parsed']}, Skipped: {len(stats['skipped'])}")
    assert temp_name in skipped, f"{temp_name} should be skipped (FLAP+AIL non-zero in Alpha mode)"
    print("  PASSED\n")

finally:
    os.unlink(temp_path)

print("ALL 14 TESTS PASSED")
