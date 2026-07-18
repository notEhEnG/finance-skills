from __future__ import annotations

import io
import json
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import build_distributions


def _new_tree() -> tuple[Path, Path, Path]:
    root = Path(tempfile.gettempdir()) / f"finance-skills-distribution-test-{uuid.uuid4().hex}"
    source = root / "skill" / "SKILL.src.md"
    dist = root / "dist"
    fixtures = {
        source: "---\nname: finance-skills\nallowed-tools: Bash\n---\n\n# Finance Skills\n",
        root / "skill" / "reference" / "provider.md": "# Provider\n",
        root / "skill" / "reference" / "shared" / "evidence.md": "# Evidence\n",
        root / "skill" / "agents" / "codex.md": "# Codex\n",
    }
    for path, content in fixtures.items():
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    return root, source, dist


class TestBuildDistributions(unittest.TestCase):
    def test_adapters_preserve_claude_permissions_and_add_portable_note(self):
        source = "---\nallowed-tools: Bash\n---\nbody\n"
        claude = build_distributions._adapter("claude", source)
        codex = build_distributions._adapter("codex", source)

        self.assertIn("allowed-tools: Bash", claude)
        self.assertNotIn("allowed-tools: Bash", codex)
        self.assertIn("Runtime permission note", codex)

    def test_exclusive_is_idempotent_and_refuses_different_content(self):
        root, _, _ = _new_tree()
        target = root / "output.txt"

        build_distributions._exclusive(target, "same\n")
        build_distributions._exclusive(target, "same\n")
        with self.assertRaisesRegex(RuntimeError, "cannot be overwritten"):
            build_distributions._exclusive(target, "different\n")

    def test_generate_creates_all_provider_outputs_checksums_and_sbom(self):
        root, source, dist = _new_tree()
        with (
            patch.object(build_distributions, "ROOT", root),
            patch.object(build_distributions, "SOURCE", source),
            patch.object(build_distributions, "DIST", dist),
        ):
            result = build_distributions.generate()
            repeated = build_distributions.generate()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result, repeated)
        self.assertTrue((dist / "SHA256SUMS").is_file())
        self.assertTrue((dist / "SHA256SUMS.v2").is_file())
        sbom = json.loads((dist / "sbom.v2.json").read_text(encoding="utf-8"))
        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        for provider in build_distributions.PROVIDERS:
            self.assertTrue((dist / provider / "SKILL.md").is_file())
            self.assertTrue((dist / provider / "reference" / "provider.md").is_file())

    def test_generate_versioned_validates_version_and_creates_immutable_tree(self):
        root, source, dist = _new_tree()
        with (
            patch.object(build_distributions, "ROOT", root),
            patch.object(build_distributions, "SOURCE", source),
            patch.object(build_distributions, "DIST", dist),
        ):
            with self.assertRaisesRegex(ValueError, "invalid distribution version"):
                build_distributions.generate_versioned("v0.14")
            result = build_distributions.generate_versioned("0.14.0")

        self.assertEqual(result["version"], "0.14.0")
        self.assertTrue((dist / "0.14.0" / "SHA256SUMS").is_file())
        sbom = json.loads(
            (dist / "0.14.0" / "sbom.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sbom["versionInfo"], "0.14.0")

    def test_main_routes_default_and_versioned_generation(self):
        output = io.StringIO()
        with (
            patch.object(
                build_distributions,
                "generate",
                return_value={"status": "success", "outputs": []},
            ) as generate,
            redirect_stdout(output),
        ):
            self.assertEqual(build_distributions.main([]), 0)
        generate.assert_called_once_with()
        self.assertEqual(json.loads(output.getvalue())["status"], "success")

        output = io.StringIO()
        with (
            patch.object(
                build_distributions,
                "generate_versioned",
                return_value={
                    "status": "success",
                    "version": "0.14.0",
                    "outputs": [],
                },
            ) as generate_versioned,
            redirect_stdout(output),
        ):
            self.assertEqual(
                build_distributions.main(["--version", "0.14.0"]),
                0,
            )
        generate_versioned.assert_called_once_with("0.14.0")

        with self.assertRaisesRegex(SystemExit, "usage:"):
            build_distributions.main(["unexpected"])


if __name__ == "__main__":
    unittest.main()
