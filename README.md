# AVL Parser

A desktop application that parses [AVL (Athena Vortex Lattice)](https://web.mit.edu/drela/Public/web/avl/) output files and exports aerodynamic coefficients to `.mat` files for MATLAB.

## Download

**Windows:** Download `AVLParser.exe` from the [Releases](https://github.com/futkaneltak1243/avl-parser/releases/tag/latest) page.
Sample test files are also available as `AVL-Test-Files.zip`.

## Features

- Parses 77 aerodynamic coefficients from AVL output files (total forces, stability derivatives, control surface derivatives, and more)
- **Single Table mode:** exports 2D matrices (variable × Mach) for any pairing — Alpha, Beta, FLAP, AIL, ELEV, or RUDD
- **3D Tables mode:** exports control surface derivatives with per-coefficient mode selection:
  - **3D** — `angle × Mach × surface deflection` (true 3D MATLAB arrays)
  - **2D(α,M)** — `angle × Mach`
  - **2D(δ,M)** — `surface deflection × Mach`
- Collapsible Control Derivatives panel with segmented button toggles and "Set All" per surface
- Descriptive auto-generated filenames (e.g. `avl_3d_3Alpha_2Mach_3FLAP.mat`)
- File validation, duplicate detection, and missing coefficient warnings
- Dark-themed GUI built with CustomTkinter
- Cross-platform: runs on macOS and Windows
- Pre-built Windows `.exe` via GitHub Actions

## Installation

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
pip install customtkinter scipy numpy
```

### Windows (one-click setup)

Run `setup_windows.bat` to install dependencies, build the `.exe`, and copy it to your Desktop.

## Usage

### GUI Application

```bash
python app.py
```

#### Single Table mode
1. Click **Add Files** to select AVL output files
2. Choose the variable to pair with Mach (Alpha, Beta, FLAP, etc.)
3. Click **Export .mat** to save the data

#### 3D Tables mode
1. Click **Add Files** to select AVL output files (must contain surface deflection sweeps)
2. Choose the angle axis (Alpha or Beta)
3. Set each control derivative to **3D**, **2D(α,M)**, or **2D(δ,M)** using the toggles
4. Click **Export .mat** to save the data

### Command Line

```bash
python parse_avl.py
```

Reads all files from the `test files/` directory and writes `output/avl_data.mat`.

### MATLAB

```matlab
% Single Table mode
load('avl_5Alpha_x_2Mach.mat')
Alpha_values         % e.g. [-4, -2, 0, ..., 20]
Mach_values          % e.g. [0.02, 0.05, 0.1, 0.15, 0.2]
CLtot                % 13x5 matrix (Alpha rows x Mach columns)
plot(Alpha_values, CLtot(:,3))   % CL vs Alpha at Mach 0.1

% 3D Tables mode
load('avl_3d_3Alpha_2Mach_3FLAP.mat')
Alpha_values         % e.g. [-5, 0, 10]
Mach_values          % e.g. [0.1, 0.2]
FLAP_values          % e.g. [-10, 0, 10]
CLd01                % 3x2x3 array (Alpha x Mach x FLAP)
squeeze(CLd01(:,1,:))  % CL vs Alpha vs FLAP at Mach 0.1
```

### View exported data

```bash
python view_mat.py              # write all coefficient tables to output/*_tables.txt
python view_mat.py --list       # list available coefficients
python view_mat.py CLtot CLa    # display specific coefficients
```

## Project Structure

```
app.py              # GUI application (CustomTkinter)
parse_avl.py        # AVL output parser and .mat export logic
view_mat.py         # .mat file viewer (formatted tables)
setup_windows.bat   # Windows one-click build script
AVL Parser.spec     # PyInstaller spec for macOS .app bundle
.github/workflows/  # GitHub Actions CI (Windows .exe build + release)
test_files_new/     # Sample AVL output files (2D and 3D test data)
```

## Exported Coefficients

| Category | Labels |
|---|---|
| Total forces | CLtot, CDtot, CYtot, CXtot, CZtot, Cmtot, Cltot, Cntot, CDind, CDff, CLff, CYff |
| Stability (alpha) | CLa, CYa, CDa, Cla, Cma, Cna |
| Stability (beta) | CLb, CYb, CDb, Clb, Cmb, Cnb |
| Roll rate (p) | CLp, CYp, CDp, Clp, Cmp, Cnp |
| Pitch rate (q) | CLq, CYq, CDq, Clq, Cmq, Cnq |
| Yaw rate (r) | CLr, CYr, CDr, Clr, Cmr, Cnr |
| Control surfaces (d01-d04) | CL/CY/CD/Cl/Cm/Cn for FLAP, AIL, ELEV, RUDD |
| Other | Xnp, e (span efficiency), spiral stability |

## Building the Windows Executable

Pushes to `main` trigger a GitHub Actions build automatically. To trigger manually:

```bash
gh workflow run build-exe.yml
```

The `.exe` and test files are available on the [Releases](https://github.com/futkaneltak1243/avl-parser/releases/tag/latest) page.
