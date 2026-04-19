"""
Generate 3D test files for the AVL Parser 3D Tables feature.
Creates AVL-format output files with varying Alpha/Beta, Mach, and control surface values.

Usage:
    python generate_3d_tests.py
"""

import os
import itertools

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_files_new', '3d_tests')

# --- Base coefficient values (at Alpha=0, all surfaces=0, Mach=0.1) ---
BASE_COEFFS = {
    # Total forces
    'CXtot': -0.00141, 'Cltot': -0.02502, 'CYtot': 0.00537,
    'Cmtot': 0.00003, 'CZtot': 0.00001, 'Cntot': -0.00320,
    'CLtot': 0.15000, 'CDtot': 0.00541, 'CDvis': 0.0, 'CDind': 0.00541,
    'CLff': 0.15001, 'CDff': 0.005419, 'CYff': 0.00537, 'e': 0.5013,
    # Stability - alpha
    'CLa': 3.784003, 'CYa': 0.005731, 'CDa': -0.000016,
    'Cla': -0.003204, 'Cma': -1.213369, 'Cna': 0.017682,
    # Stability - beta
    'CLb': 0.006775, 'CYb': -0.218581, 'CDb': 0.006197,
    'Clb': -0.016048, 'Cmb': -0.003997, 'Cnb': 0.130805,
    # Rate - p
    'CLp': -0.000003, 'CYp': 0.013352, 'CDp': -0.012157,
    'Clp': -0.385791, 'Cmp': 0.000115, 'Cnp': -0.008001,
    # Rate - q
    'CLq': 7.034479, 'CYq': 0.011190, 'CDq': -0.0,
    'Clq': -0.000394, 'Cmq': -9.905187, 'Cnq': 0.001938,
    # Rate - r
    'CLr': -0.116364, 'CYr': 0.282495, 'CDr': -0.007472,
    'Clr': 0.020799, 'Cmr': 0.047084, 'Cnr': -0.169942,
    # Control derivatives - FLAP (d01)
    'CLd01': 0.012000, 'CYd01': 0.000100, 'CDd01': 0.000300,
    'Cld01': -0.000050, 'Cmd01': -0.008000, 'Cnd01': -0.000020,
    'CDffd01': 0.000250, 'ed01': 0.000100,
    # Control derivatives - AIL (d02)
    'CLd02': 0.000001, 'CYd02': -0.000737, 'CDd02': -0.000457,
    'Cld02': 0.003900, 'Cmd02': -0.0, 'Cnd02': 0.000441,
    'CDffd02': -0.000459, 'ed02': 0.000064,
    # Control derivatives - ELEV (d03)
    'CLd03': 0.005731, 'CYd03': 0.000016, 'CDd03': -0.0,
    'Cld03': 0.0, 'Cmd03': -0.016749, 'Cnd03': -0.000005,
    'CDffd03': -0.0, 'ed03': 0.000004,
    # Control derivatives - RUDD (d04)
    'CLd04': 0.000002, 'CYd04': -0.002583, 'CDd04': 0.000010,
    'Cld04': -0.000200, 'Cmd04': -0.000012, 'Cnd04': 0.001612,
    'CDffd04': 0.000009, 'ed04': -0.001253,
    # Misc
    'Xnp': 0.457480, 'spiral': 1.002457,
}

# Sensitivity factors: how coefficients change per unit of Alpha, Beta, FLAP, etc.
ALPHA_SENSITIVITY = {
    'CLtot': 0.066, 'CDtot': 0.0003, 'CXtot': -0.0001, 'CZtot': -0.066,
    'Cmtot': -0.02, 'CLff': 0.066, 'CDff': 0.0003,
    'CLa': 0.01, 'Cma': -0.005,
    'CLd01': 0.0001, 'CLd02': 0.00001, 'CLd03': 0.00005, 'CLd04': 0.00001,
    'Cmd01': -0.0002, 'Cmd03': -0.0001,
}

BETA_SENSITIVITY = {
    'CYtot': -0.004, 'Cntot': 0.002, 'Cltot': -0.001,
    'CYb': -0.01, 'Cnb': 0.001, 'Clb': -0.0005,
    'CYd04': -0.00005, 'Cnd04': 0.00003,
}

FLAP_SENSITIVITY = {
    'CLtot': 0.0012, 'CDtot': 0.00003, 'Cmtot': -0.0008,
    'CLd01': 0.00005, 'Cmd01': -0.00003, 'CDd01': 0.00001,
    'CDffd01': 0.00001, 'ed01': 0.000005,
}

AIL_SENSITIVITY = {
    'Cltot': 0.0004, 'Cntot': -0.0001,
    'Cld02': 0.00002, 'Cnd02': 0.00001, 'CYd02': -0.00002,
}

ELEV_SENSITIVITY = {
    'CLtot': 0.0006, 'Cmtot': -0.0017,
    'CLd03': 0.00003, 'Cmd03': -0.00008,
}

RUDD_SENSITIVITY = {
    'Cntot': 0.0002, 'CYtot': -0.0003,
    'CYd04': -0.00005, 'Cnd04': 0.00003,
}

MACH_SENSITIVITY = {
    'CLtot': 0.02, 'CDtot': 0.001, 'CLa': 0.1, 'Cma': -0.02,
    'CLd01': 0.0005, 'CLd03': 0.0003,
}


def compute_coeffs(alpha, beta, mach, flap, ail, elev, rudd, scale=1.0):
    """Compute coefficient values given flight conditions."""
    c = dict(BASE_COEFFS)

    for key, sens in ALPHA_SENSITIVITY.items():
        c[key] = c.get(key, 0) + sens * alpha * scale

    for key, sens in BETA_SENSITIVITY.items():
        c[key] = c.get(key, 0) + sens * beta * scale

    for key, sens in FLAP_SENSITIVITY.items():
        c[key] = c.get(key, 0) + sens * flap * scale

    for key, sens in AIL_SENSITIVITY.items():
        c[key] = c.get(key, 0) + sens * ail * scale

    for key, sens in ELEV_SENSITIVITY.items():
        c[key] = c.get(key, 0) + sens * elev * scale

    for key, sens in RUDD_SENSITIVITY.items():
        c[key] = c.get(key, 0) + sens * rudd * scale

    # Mach sensitivity relative to base Mach=0.1
    for key, sens in MACH_SENSITIVITY.items():
        c[key] = c.get(key, 0) + sens * (mach - 0.1) * scale

    # Keep CDtot consistent
    c['CDind'] = c['CDtot'] - c['CDvis']
    c['CDff'] = c['CDtot'] * 1.001

    return c


def fmt(v, width=10):
    """Format a float for AVL output."""
    if v == 0.0:
        return f'{0.0:{width}.5f}'
    elif abs(v) >= 100:
        return f'{v:{width}.4f}'
    elif abs(v) >= 0.001:
        return f'{v:{width}.6f}'
    else:
        return f'{v:{width}.6f}'


def generate_avl_file(filepath, alpha, beta, mach, flap, ail, elev, rudd,
                      run_case=None, coeff_override=None):
    """Generate a single AVL output file."""
    if run_case is None:
        run_case = os.path.basename(filepath)

    c = compute_coeffs(alpha, beta, mach, flap, ail, elev, rudd)
    if coeff_override:
        c.update(coeff_override)

    content = f""" ---------------------------------------------------------------
 Vortex Lattice Output -- Total Forces

 Configuration: UAV_FTC_from_DATCOM_EX55
     # Surfaces =   5
     # Strips   = 106
     # Vortices =1300

  Sref = 0.45000       Cref = 0.30400       Bref =  1.5000
  Xref = 0.36000       Yref =  0.0000       Zref =  0.0000

 Standard axis orientation,  X fwd, Z down

 Run case: {run_case}

  Alpha ={alpha:>10.5f}     pb/2V =  -0.00000     p'b/2V =  -0.00000
  Beta  ={beta:>10.5f}     qc/2V =   0.00000
  Mach  =  {mach:>10.4f}     rb/2V =  -0.00000     r'b/2V =  -0.00000

  CXtot ={fmt(c['CXtot'])}     Cltot ={fmt(c['Cltot'])}     Cl'tot ={fmt(c['Cltot'])}
  CYtot ={fmt(c['CYtot'])}     Cmtot ={fmt(c['Cmtot'])}
  CZtot ={fmt(c['CZtot'])}     Cntot ={fmt(c['Cntot'])}     Cn'tot ={fmt(c['Cntot'])}

  CLtot ={fmt(c['CLtot'])}
  CDtot ={fmt(c['CDtot'])}
  CDvis ={fmt(c['CDvis'])}     CDind ={fmt(c['CDind'], 10)}
  CLff  ={fmt(c['CLff'])}     CDff  ={fmt(c['CDff'], 10)}    | Trefftz
  CYff  ={fmt(c['CYff'])}         e ={fmt(c['e'], 10)}    | Plane

   FLAP            ={flap:>10.5f}
   AIL             ={ail:>10.5f}
   ELEV            ={elev:>10.5f}
   RUDD            ={rudd:>10.5f}

 ---------------------------------------------------------------

 Stability-axis derivatives...

                             alpha                beta
                  ----------------    ----------------
 z' force CL |    CLa ={fmt(c['CLa'])}    CLb ={fmt(c['CLb'])}
 y  force CY |    CYa ={fmt(c['CYa'])}    CYb ={fmt(c['CYb'])}
 x  force CD |    CDa ={fmt(c['CDa'])}    CDb ={fmt(c['CDb'])}
 x' mom.  Cl'|    Cla ={fmt(c['Cla'])}    Clb ={fmt(c['Clb'])}
 y  mom.  Cm |    Cma ={fmt(c['Cma'])}    Cmb ={fmt(c['Cmb'])}
 z' mom.  Cn'|    Cna ={fmt(c['Cna'])}    Cnb ={fmt(c['Cnb'])}

                     roll rate  p'      pitch rate  q'        yaw rate  r'
                  ----------------    ----------------    ----------------
 z' force CL |    CLp ={fmt(c['CLp'])}    CLq ={fmt(c['CLq'])}    CLr ={fmt(c['CLr'])}
 y  force CY |    CYp ={fmt(c['CYp'])}    CYq ={fmt(c['CYq'])}    CYr ={fmt(c['CYr'])}
 x  force CD |    CDp ={fmt(c['CDp'])}    CDq ={fmt(c['CDq'])}    CDr ={fmt(c['CDr'])}
 x' mom.  Cl'|    Clp ={fmt(c['Clp'])}    Clq ={fmt(c['Clq'])}    Clr ={fmt(c['Clr'])}
 y  mom.  Cm |    Cmp ={fmt(c['Cmp'])}    Cmq ={fmt(c['Cmq'])}    Cmr ={fmt(c['Cmr'])}
 z' mom.  Cn'|    Cnp ={fmt(c['Cnp'])}    Cnq ={fmt(c['Cnq'])}    Cnr ={fmt(c['Cnr'])}

                  FLAP         d01     AIL          d02     ELEV         d03     RUDD         d04
                  ----------------    ----------------    ----------------    ----------------
 z' force CL |   CLd01 ={fmt(c['CLd01'])}   CLd02 ={fmt(c['CLd02'])}   CLd03 ={fmt(c['CLd03'])}   CLd04 ={fmt(c['CLd04'])}
 y  force CY |   CYd01 ={fmt(c['CYd01'])}   CYd02 ={fmt(c['CYd02'])}   CYd03 ={fmt(c['CYd03'])}   CYd04 ={fmt(c['CYd04'])}
 x  force CD |   CDd01 ={fmt(c['CDd01'])}   CDd02 ={fmt(c['CDd02'])}   CDd03 ={fmt(c['CDd03'])}   CDd04 ={fmt(c['CDd04'])}
 x' mom.  Cl'|   Cld01 ={fmt(c['Cld01'])}   Cld02 ={fmt(c['Cld02'])}   Cld03 ={fmt(c['Cld03'])}   Cld04 ={fmt(c['Cld04'])}
 y  mom.  Cm |   Cmd01 ={fmt(c['Cmd01'])}   Cmd02 ={fmt(c['Cmd02'])}   Cmd03 ={fmt(c['Cmd03'])}   Cmd04 ={fmt(c['Cmd04'])}
 z' mom.  Cn'|   Cnd01 ={fmt(c['Cnd01'])}   Cnd02 ={fmt(c['Cnd02'])}   Cnd03 ={fmt(c['Cnd03'])}   Cnd04 ={fmt(c['Cnd04'])}
 Trefftz drag| CDffd01 ={fmt(c['CDffd01'])} CDffd02 ={fmt(c['CDffd02'])} CDffd03 ={fmt(c['CDffd03'])} CDffd04 ={fmt(c['CDffd04'])}
 span eff.   |    ed01 ={fmt(c['ed01'])}    ed02 ={fmt(c['ed02'])}    ed03 ={fmt(c['ed03'])}    ed04 ={fmt(c['ed04'])}



 Neutral point  Xnp ={fmt(c['Xnp'])}

 Clb Cnr / Clr Cnb  ={fmt(c['spiral'])}    (  > 1 if spirally stable )
"""

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        f.write(content)


def gen_filename(mach, alpha=None, beta=None, flap=None, ail=None, elev=None, rudd=None):
    """Generate a filename from parameters."""
    parts = [f'M{mach}']
    if alpha is not None:
        parts.append(f'A{alpha:g}')
    if beta is not None:
        parts.append(f'B{beta:g}')
    if flap is not None:
        parts.append(f'F{flap:g}')
    if ail is not None:
        parts.append(f'AIL{ail:g}')
    if elev is not None:
        parts.append(f'E{elev:g}')
    if rudd is not None:
        parts.append(f'R{rudd:g}')
    return ''.join(parts)


def generate_alpha_flap():
    """1. Core 3D test: 3 Alpha × 2 Mach × 3 FLAP = 18 files."""
    d = os.path.join(BASE_DIR, 'alpha_flap')
    alphas = [-5, 0, 10]
    machs = [0.1, 0.2]
    flaps = [-10, 0, 10]
    count = 0
    for alpha, mach, flap in itertools.product(alphas, machs, flaps):
        name = gen_filename(mach, alpha=alpha, flap=flap)
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0)
        count += 1
    return 'alpha_flap', count


def generate_alpha_multi_surface():
    """2. Two surfaces active: 2 Alpha × 1 Mach × 2 FLAP × 2 AIL = 8 files."""
    d = os.path.join(BASE_DIR, 'alpha_multi_surface')
    alphas = [0, 5]
    machs = [0.15]
    flaps = [-10, 10]
    ails = [-15, 15]
    count = 0
    for alpha, mach, flap, ail in itertools.product(alphas, machs, flaps, ails):
        name = gen_filename(mach, alpha=alpha, flap=flap, ail=ail)
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=ail, elev=0, rudd=0)
        count += 1
    return 'alpha_multi_surface', count


def generate_beta_elev():
    """3. Beta as angle var: 3 Beta × 2 Mach × 3 ELEV = 18 files."""
    d = os.path.join(BASE_DIR, 'beta_elev')
    betas = [-5, 0, 5]
    machs = [0.1, 0.2]
    elevs = [-10, 0, 10]
    count = 0
    for beta, mach, elev in itertools.product(betas, machs, elevs):
        name = gen_filename(mach, beta=beta, elev=elev)
        generate_avl_file(os.path.join(d, name),
                          alpha=0, beta=beta, mach=mach,
                          flap=0, ail=0, elev=elev, rudd=0)
        count += 1
    return 'beta_elev', count


def generate_single_mach():
    """4. Degenerate Mach axis: 3 Alpha × 1 Mach × 3 FLAP = 9 files."""
    d = os.path.join(BASE_DIR, 'single_mach')
    alphas = [-5, 0, 5]
    machs = [0.3]
    flaps = [-10, 0, 10]
    count = 0
    for alpha, mach, flap in itertools.product(alphas, machs, flaps):
        name = gen_filename(mach, alpha=alpha, flap=flap)
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0)
        count += 1
    return 'single_mach', count


def generate_single_angle():
    """5. Single angle value: 1 Alpha × 2 Mach × 3 FLAP = 6 files."""
    d = os.path.join(BASE_DIR, 'single_angle')
    alphas = [0]
    machs = [0.1, 0.2]
    flaps = [-10, 0, 10]
    count = 0
    for alpha, mach, flap in itertools.product(alphas, machs, flaps):
        name = gen_filename(mach, alpha=alpha, flap=flap)
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0)
        count += 1
    return 'single_angle', count


def generate_single_surface_val():
    """6. Single surface deflection: 3 Alpha × 2 Mach × 1 FLAP = 6 files."""
    d = os.path.join(BASE_DIR, 'single_surface_val')
    alphas = [-5, 0, 5]
    machs = [0.1, 0.2]
    flaps = [0]
    count = 0
    for alpha, mach, flap in itertools.product(alphas, machs, flaps):
        name = gen_filename(mach, alpha=alpha, flap=flap)
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0)
        count += 1
    return 'single_surface_val', count


def generate_large_grid():
    """7. Scaling test: 4 Alpha × 3 Mach × 5 FLAP = 60 files."""
    d = os.path.join(BASE_DIR, 'large_grid')
    alphas = [-10, -5, 0, 5]
    machs = [0.05, 0.15, 0.25]
    flaps = [-20, -10, 0, 10, 20]
    count = 0
    for alpha, mach, flap in itertools.product(alphas, machs, flaps):
        name = gen_filename(mach, alpha=alpha, flap=flap)
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0)
        count += 1
    return 'large_grid', count


def generate_negative_zero():
    """8. Sign edge case: files with -0.0 values."""
    d = os.path.join(BASE_DIR, 'negative_zero')
    # Use exact -0.0 and 0.0 to test deduplication
    cases = [
        (-0.0, 0.1, -0.0),
        (-0.0, 0.1, 0.0),
        (0.0, 0.1, -0.0),
        (0.0, 0.1, 0.0),
    ]
    count = 0
    for alpha, mach, flap in cases:
        # Use explicit names to preserve the -0 distinction in filenames
        a_str = 'An0' if str(alpha).startswith('-') else 'A0'
        f_str = 'Fn0' if str(flap).startswith('-') else 'F0'
        name = f'M{mach}{a_str}{f_str}'
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0)
        count += 1
    return 'negative_zero', count


def generate_extreme_values():
    """9. Extreme coefficient values."""
    d = os.path.join(BASE_DIR, 'extreme_values')
    cases = [
        (0, 0.1, -30),
        (0, 0.1, 30),
        (45, 0.1, -30),
        (45, 0.1, 30),
    ]
    count = 0
    for alpha, mach, flap in cases:
        name = gen_filename(mach, alpha=alpha, flap=flap)
        # Use large scale factor to push coefficients to extremes
        overrides = {}
        if alpha == 45:
            overrides.update({
                'CLtot': 2.95 + 0.0012 * flap,
                'CDtot': 0.85 + 0.0001 * abs(flap),
                'Cmtot': -0.95 - 0.0008 * flap,
                'CLa': 1.200000,  # Reduced at high alpha (stall)
                'CLd01': 0.002000,  # Reduced effectiveness at high alpha
            })
        if abs(flap) == 30:
            overrides.update({
                'CDd01': 0.005000,  # High drag at large deflection
                'CDffd01': 0.004500,
            })
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0,
                          coeff_override=overrides)
        count += 1
    return 'extreme_values', count


def generate_alpha_beta():
    """11. Beta as 3D dim (surface-like): 3 Alpha × 2 Mach × 3 Beta = 18 files.

    All surfaces held at 0; Beta sweeps as a surface-like dim. Parser with
    angle_var='Alpha' should produce Beta_CLb, Beta_CYb, ... 3D tables.
    """
    d = os.path.join(BASE_DIR, 'alpha_beta')
    alphas = [-5, 0, 10]
    machs = [0.1, 0.2]
    betas = [-5, 0, 5]
    count = 0
    for alpha, mach, beta in itertools.product(alphas, machs, betas):
        # Omit 'B0' from filename for the zero-beta case (matches run_generator)
        name = gen_filename(mach, alpha=alpha,
                            beta=(beta if beta != 0 else None))
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=beta, mach=mach,
                          flap=0, ail=0, elev=0, rudd=0)
        count += 1
    return 'alpha_beta', count


def generate_partial_overlap():
    """10. Incomplete grid: only 6 of 18 possible points."""
    d = os.path.join(BASE_DIR, 'partial_overlap')
    # Full grid would be: Alpha(-5,0,5) × Mach(0.1,0.2) × FLAP(-10,0,10) = 18
    # We only provide these 6 scattered points:
    sparse_points = [
        (-5, 0.1, -10),
        (-5, 0.2, 10),
        (0, 0.1, 0),
        (0, 0.2, -10),
        (5, 0.1, 10),
        (5, 0.2, 0),
    ]
    count = 0
    for alpha, mach, flap in sparse_points:
        name = gen_filename(mach, alpha=alpha, flap=flap)
        generate_avl_file(os.path.join(d, name),
                          alpha=alpha, beta=0, mach=mach,
                          flap=flap, ail=0, elev=0, rudd=0)
        count += 1
    return 'partial_overlap', count


def main():
    generators = [
        generate_alpha_flap,
        generate_alpha_multi_surface,
        generate_beta_elev,
        generate_single_mach,
        generate_single_angle,
        generate_single_surface_val,
        generate_large_grid,
        generate_negative_zero,
        generate_extreme_values,
        generate_alpha_beta,
        generate_partial_overlap,
    ]

    total = 0
    print(f'Generating 3D test files in {BASE_DIR}\n')

    for gen in generators:
        name, count = gen()
        print(f'  {name:25s}  {count:3d} files')
        total += count

    print(f'\n  {"TOTAL":25s}  {total:3d} files')
    print(f'\nDone! Files created in {BASE_DIR}')


if __name__ == '__main__':
    main()
