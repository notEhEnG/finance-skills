"""finance-skills — analyst-style equity research over one shared engine.

Installed, this directory is the importable `finance_skills` package (the sources
live in `scripts/` and are remapped at build time — see pyproject.toml). Run in
place, the same files work as standalone scripts via `python3 scripts/<mod>.py`,
which is the path the packaged agent skill (SKILL.md / install.sh) uses.

Kept intentionally light: importing the package must not require yfinance or the
network. Submodules pull their dependencies in lazily when actually used.
"""

__version__ = "0.9.0"
