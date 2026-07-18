import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

import context as finance_context
import router


class TestContextDiscovery(unittest.TestCase):
    def test_unmarked_directory_does_not_inherit_parent_state(self):
        root = FIXTURES / "empty_context_project"
        self.assertEqual(finance_context.discover_project_root(root), root.resolve())

    def test_build_context_reads_saved_project_state(self):
        payload = finance_context.build_context(FIXTURES / "context_project")

        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["research_context_exists"])
        self.assertEqual(payload["config_status"], "loaded")
        self.assertEqual(payload["default_currency"], "EUR")
        self.assertEqual(payload["default_depth"], "deep")
        self.assertEqual(payload["tracked_companies"], ["NVDA"])
        self.assertEqual(payload["companies"]["NVDA"]["latest_snapshot_period"], "FY2026-Q1")
        self.assertEqual(payload["companies"]["NVDA"]["open_watchpoints"], 2)
        commands = [item["command"] for item in payload["recommended_commands"]]
        self.assertIn("/finance refresh NVDA", commands)
        self.assertIn("/finance challenge NVDA", commands)

    def test_init_preserves_existing_files_byte_for_byte(self):
        root = FIXTURES / "context_project"
        research = root / "RESEARCH.md"
        config = root / ".finance" / "config.json"
        before = (research.read_bytes(), config.read_bytes())

        payload = finance_context.initialize_project(root)

        self.assertEqual([item["status"] for item in payload["files"]], ["preserved", "preserved"])
        self.assertEqual((research.read_bytes(), config.read_bytes()), before)

    def test_init_creation_plan_uses_exclusive_create(self):
        root = FIXTURES / "empty_context_project"
        with mock.patch.object(
            finance_context,
            "_exclusive_create",
            side_effect=(True, True),
        ) as create:
            payload = finance_context.initialize_project(root)

        self.assertEqual(create.call_count, 2)
        self.assertEqual([item["status"] for item in payload["files"]], ["created", "created"])
        self.assertEqual(create.call_args_list[0].args[0], root / "RESEARCH.md")
        self.assertEqual(create.call_args_list[1].args[0], root / ".finance" / "config.json")

    def test_context_router_dispatches_json_contract(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = router.main(["context", "--format", "json"])

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["status"], "success")
        self.assertIn("recommended_commands", payload)


class TestDistributionEntryPoints(unittest.TestCase):
    def test_module_entry_exists(self):
        self.assertTrue((SCRIPTS / "__main__.py").is_file())

    def test_primary_console_alias_is_declared(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('finance = "finance_skills._entry:run"', pyproject)


if __name__ == "__main__":
    unittest.main()
