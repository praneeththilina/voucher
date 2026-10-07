# Google Antigravity Rules for Python Workspace

## File Inspection & Tool Performance (Gemini Flash Optimization)
- Always read files in complete blocks or from line 1 to EOF in a single tool call.
- NEVER scan, paginate, or inspect code files in small 15-100 line slices unless explicitly instructed.
- When inspecting target code, execute a single `view_file` or `read_range` covering the entire function, class, or module.
- Avoid repetitive terminal loops or repeated incremental searches before proposing changes.

## Python Development Standards
- Python environment: Always respect the project virtual environment (`.venv`, `venv`, or `env`).
- Never run global package installations; execute pip commands within the active virtualenv.
- Follow PEP 8 standards with clear type hinting (`typing` module / modern Python 3.10+ union syntax `|`).
- Use clean docstrings and preserve existing logic unless explicitly requested to refactor.

## System Resource & Memory Protections
- Avoid triggering unnecessary background watchers, long-running processes, or infinite loops in the terminal.
- Do not inspect generated or heavy cache directories: ignore `__pycache__/`, `.pytest_cache/`, `dist/`, `build/`, `.venv/`, and `.git/`.
- Present concise plans before executing large multi-file diffs.