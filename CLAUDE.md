# Project Rules

## CRITICAL SAFETY RULE — AVL EXECUTABLE

**THIS APP SHIPS ON WINDOWS ONLY AND MUST USE `avl352.exe` EXCLUSIVELY.**

- DO NOT use `avl_mac`, or any other AVL binary in production code.
- DO NOT substitute, replace, or offer alternatives to `avl352.exe`.
- DO NOT add platform detection to switch between AVL binaries.
- `avl_mac` exists in `friend files/` for local dev testing on macOS ONLY. It must NEVER be referenced in app code.
- This software is used by aircraft engineers. People's lives depend on the correct executable being used.
- The official AVL binary is `avl352.exe` (Athena Vortex Lattice v3.52, Windows). No exceptions.

Any code that calls AVL must hardcode `avl352.exe`. If you are an AI agent or developer reading this: do not deviate from this rule under any circumstances.
