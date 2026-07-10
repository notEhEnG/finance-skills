"""Console-script entry point for the `finance-skills` command.

`[project.scripts]` maps `finance-skills` to `finance_skills._entry:run`.
setuptools console-scripts call a zero-argument function, so this thin wrapper
reads argv itself and forwards it to `router.main`, mirroring the module's own
`if __name__ == "__main__"` path (`router.main(sys.argv[1:])`).
"""

from __future__ import annotations

import sys

try:  # installed as the `finance_skills` package…
    from finance_skills import router
except ImportError:  # …or imported from the in-repo `scripts/` dir (tests, dev)
    import router


def run() -> None:
    raise SystemExit(router.main(sys.argv[1:]))


if __name__ == "__main__":
    run()
