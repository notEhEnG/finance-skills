"""Enforce the read-only / no-trading architecture from SECURITY.md.

These are *structural* invariants checked on the AST, not English keyword scans:

- **One IO boundary.** Only `data.py` may import a networking client — the real
  fetch shell. Any other module importing one fails the build.
- **Never trades.** No brokerage/trading SDK is imported anywhere in the package.
- **No dynamic execution or shell-out.** No `eval`/`exec`, no `subprocess`
  import, no `os.system` — the escape hatches an English denylist would miss.
- **Pure engine.** Importing `metrics` pulls in no networking client.

The point is architecture, not vocabulary: analysis text is free to say
"withdraw" or "brokerage"; code is not free to import a broker or open a socket
outside the one shell.
"""

import ast
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

# The single module allowed to reach the network.
NETWORK_SHELL = "data.py"
# Third-party networking clients (not stdlib generics like `http`/`socket`, which
# have innocent non-network uses and would false-positive).
NETWORK_CLIENTS = {"yfinance", "requests", "httpx", "aiohttp", "urllib3"}
# Brokerage / trading SDKs — must not be imported by ANY module.
BROKER_SDKS = {"alpaca", "alpaca_trade_api", "ib_insync", "ibapi", "ccxt",
               "robin_stocks", "tda", "schwab", "kiteconnect"}


def _py_files():
    return sorted(SCRIPTS.glob("*.py"))


def _top_level_imports(tree: ast.AST) -> set[str]:
    """Top-level package name of every absolute import in the tree."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


class TestReadOnlyArchitecture(unittest.TestCase):
    def test_network_clients_only_in_the_data_shell(self):
        offenders = {}
        for path in _py_files():
            if path.name == NETWORK_SHELL:
                continue
            hits = _top_level_imports(ast.parse(path.read_text("utf-8"))) & NETWORK_CLIENTS
            if hits:
                offenders[path.name] = sorted(hits)
        self.assertEqual(offenders, {}, f"network client imported outside {NETWORK_SHELL}: {offenders}")

    def test_no_broker_or_trading_sdk_anywhere(self):
        offenders = {}
        for path in _py_files():
            hits = _top_level_imports(ast.parse(path.read_text("utf-8"))) & BROKER_SDKS
            if hits:
                offenders[path.name] = sorted(hits)
        self.assertEqual(offenders, {}, f"brokerage/trading SDK imported: {offenders}")

    def test_no_subprocess_import(self):
        offenders = [p.name for p in _py_files()
                     if "subprocess" in _top_level_imports(ast.parse(p.read_text("utf-8")))]
        self.assertEqual(offenders, [], f"subprocess imported (shell-out hatch): {offenders}")

    def test_no_eval_exec_or_os_system(self):
        offenders = {}
        for path in _py_files():
            tree = ast.parse(path.read_text("utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id in {"eval", "exec"}:
                    offenders.setdefault(path.name, []).append(fn.id)
                elif isinstance(fn, ast.Attribute) and fn.attr == "system" \
                        and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                    offenders.setdefault(path.name, []).append("os.system")
        self.assertEqual(offenders, {}, f"dynamic-exec / shell-out call found: {offenders}")

    def test_metrics_engine_imports_no_network_client(self):
        for lib in NETWORK_CLIENTS:
            sys.modules.pop(lib, None)
        import metrics  # noqa: F401
        leaked = sorted(lib for lib in NETWORK_CLIENTS if lib in sys.modules)
        self.assertEqual(leaked, [], f"metrics.py pulled in a network client: {leaked}")

    def test_no_destructive_file_writes(self):
        offenders = {}
        for path in _py_files():
            tree = ast.parse(path.read_text("utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr in {
                    "write_text", "unlink", "rmdir", "remove", "rmtree",
                }:
                    offenders.setdefault(path.name, []).append(fn.attr)
                if isinstance(fn, ast.Attribute) and fn.attr == "open" and node.args:
                    mode = node.args[0]
                    if isinstance(mode, ast.Constant) and mode.value in {"w", "wb", "w+"}:
                        offenders.setdefault(path.name, []).append(f"open({mode.value!r})")
        self.assertEqual(offenders, {}, f"destructive file API found: {offenders}")

    def test_installer_contains_no_delete_or_overwrite_commands(self):
        installer = (SCRIPTS.parent / "install.sh").read_text("utf-8")
        for prohibited in ("rm -", "-delete", "--delete", "cp -f", "cp -R", "cp -r"):
            self.assertNotIn(prohibited, installer, prohibited)


if __name__ == "__main__":
    unittest.main()
