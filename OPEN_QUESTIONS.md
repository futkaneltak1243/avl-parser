# Open Questions & Edge Cases

## Variable Pairing Feature

### Edge Cases to Watch

1. **All files have the same value for the selected variable**
   - Example: every file has `Beta = 0.0` → the output matrix has only 1 row
   - The app handles this (exports a 1×N matrix) but it's probably not useful
   - Should we warn the user? e.g. "All files have Beta=0.0 — only 1 row in output"

2. **Selected variable missing in some files but not all**
   - Current behavior: files missing the variable are skipped with a reason
   - The skipped files are reported in the export popup
   - Is this the right behavior, or should we fill with NaN instead?

3. **Floating-point precision for pairing**
   - Alpha values like `-2.00000` become `-2.0` in Python
   - FLAP/AIL/ELEV/RUDD values like `0.00000` become `0.0`
   - If two files have ELEV=5.0000 and ELEV=5.0001 (rounding), they become different rows
   - Should we round to N decimal places before pairing?

4. **MATLAB variable naming**
   - Output uses `{var}_values` (e.g. `Alpha_values`, `FLAP_values`)
   - MATLAB is case-sensitive: `FLAP_values` vs `flap_values` matters
   - Current: uses the exact names from the dropdown (Alpha, Beta, FLAP, AIL, ELEV, RUDD)

5. **Very large number of unique values for a variable**
   - If the dataset has 100 unique ELEV deflections × 5 Machs = 500 files
   - The output matrix becomes 100×5 — works fine, but the .mat file gets large
   - No action needed, but worth knowing

6. **Negative zero (-0.0)**
   - AVL sometimes outputs `-0.00000` for control surfaces
   - Python `float('-0.00000')` is `-0.0`, which equals `0.0` in comparisons
   - `sorted()` may place -0.0 before 0.0 in the values array
   - Could cause duplicate-looking rows. Should we normalize `-0.0` → `0.0`?

### New Edge Cases for Testing

7. **File with Beta but no Alpha**
   - If user selects "Beta" pairing, this file should work even without Alpha
   - Current code: file is accepted (only Mach is required at validation)

8. **File with garbled value for the selected variable**
   - e.g. `FLAP = *****` (overflow in AVL solver)
   - Regex won't match → treated as "FLAP value not found" → file skipped

9. **Mixing files from different aircraft configurations**
   - File A: 5 control surfaces (FLAP, AIL, ELEV, RUDD, SPOILER)
   - File B: 4 control surfaces (FLAP, AIL, ELEV, RUDD)
   - SPOILER wouldn't be a pairable variable (only the 6 built-in ones are)
   - The coefficient labels (CLd05, etc.) might be missing → shows as warning

10. **Duplicate file with different variable value**
    - Two files with same Mach=0.1, same Alpha=2, but different FLAP values
    - If pairing by Alpha: duplicate (same key), second overwrites first
    - If pairing by FLAP: not a duplicate (different keys), both kept
    - This is correct behavior — just worth noting

### Future Improvements (Not Planned)

- Allow custom second variable name (not just the 6 built-in ones)
- Allow pairing with TWO variables (3D output: Mach × Alpha × FLAP)
- Auto-detect which variables actually vary across files and suggest the best pairing
- Export multiple .mat files (one per pairing) in a single operation
