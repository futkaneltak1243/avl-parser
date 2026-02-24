# Project Notes

## v2.0 Checkpoint (2026-02-24)

### What's done
- AVL output parser (`parse_avl.py`) — reads 77 aerodynamic coefficients
- Desktop GUI app (`app.py`) — customtkinter, dark theme, file picker, .mat export
- Mach & Alpha extracted from **file content** (not filenames)
- Full error handling:
  - Binary files → rejected: "not a text file (binary?)"
  - Non-AVL text files → rejected: "not an AVL output file"
  - Missing Mach/Alpha → rejected with specific reason
  - Duplicate Mach/Alpha pairs → warning shown, last file wins
  - Missing coefficients → warning with list of missing labels
  - All files invalid → export blocked with per-file error details
- Files validated at add-time (immediate feedback)
- Export popup uses warning icon when issues exist, info icon when clean
- Windows .exe built via GitHub Actions (Windows 2022, Python 3.11 x64)
- GitHub Release: https://github.com/futkaneltak1243/avl-parser/releases/tag/v1.0
- Edge case test files in `test_edge_cases/` (6 folders)

### Files
- `parse_avl.py` — parser + `process_files()` + `validate_file()`
- `app.py` — GUI app (customtkinter)
- `view_mat.py` — .mat file viewer (writes formatted tables)
- `setup_windows.bat` — manual Windows setup script
- `.github/workflows/build-exe.yml` — GitHub Actions workflow

### Tags
- `v1.0` — first working release with Windows .exe
- `v2.0` — robust error handling + file content parsing

### How to rebuild the .exe
Push to `main` branch → GitHub Actions builds automatically.
Or manually: `gh workflow run build-exe.yml`
Download from: Actions → latest run → Artifacts, or from the Release page.

### Environment notes
- Use `python` (not `python3`) — conda base environment
- `GH_CONFIG_DIR=/tmp/gh_config` needed for gh CLI (root owns ~/.config)
