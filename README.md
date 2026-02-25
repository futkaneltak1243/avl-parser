# AVL Parser

A desktop application that parses [AVL (Athena Vortex Lattice)](https://web.mit.edu/drela/Public/web/avl/) output files and exports aerodynamic coefficients to `.mat` files for MATLAB.

## Features

- Parses 77 aerodynamic coefficients from AVL output files (total forces, stability derivatives, control surface derivatives, and more)
- Exports data as MATLAB `.mat` files with 2D matrices (variable x Mach)
- Configurable variable pairing: Mach crossed with Alpha, Beta, FLAP, AIL, ELEV, or RUDD
- File validation on import with detailed error messages
- Duplicate detection, missing coefficient warnings, and per-file error reporting
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

### Pre-built Windows executable

Download `AVLParser.exe` from the [Releases](https://github.com/futkaneltak1243/avl-parser/releases) page.

## Usage

### GUI Application

```bash
python app.py
```

1. Click **Add Files** to select AVL output files
2. Choose the variable to pair with Mach (Alpha, Beta, FLAP, etc.)
3. Click **Export .mat** to save the data

### Command Line

```bash
python parse_avl.py
```

Reads all files from the `test files/` directory and writes `output/avl_data.mat`.

### MATLAB

```matlab
load('avl_data.mat')
Alpha_values         % e.g. [-4, -2, 0, ..., 20]
Mach_values          % e.g. [0.02, 0.05, 0.1, 0.15, 0.2]
CLtot                % 13x5 matrix (Alpha rows x Mach columns)
plot(Alpha_values, CLtot(:,3))   % CL vs Alpha at Mach 0.1
```

### View exported data

```bash
python view_mat.py              # write all coefficient tables to output/avl_data_tables.txt
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
.github/workflows/  # GitHub Actions CI (Windows .exe build)
test files/         # Sample AVL output files
test_edge_cases/    # Edge case test files
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

The `.exe` artifact is available under Actions or on the Releases page.
