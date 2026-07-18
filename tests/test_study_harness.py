from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import study_harness


class TestStudyHarness(unittest.TestCase):
    def test_manifest_covers_every_provider_mode_and_prompt(self):
        prompts = [{"id": "p1", "prompt": "Analyze TEST."}]
        manifest = study_harness.build_manifest(
            prompts,
            study_id="v014-test",
            created_at="2026-07-18T00:00:00+00:00",
        )
        expected = len(study_harness.COMMAND_TEMPLATES) * len(study_harness.MODES)
        self.assertEqual(len(manifest["cases"]), expected)
        self.assertTrue(
            all(case["result_status"] == "unpublished" for case in manifest["cases"])
        )
        self.assertEqual(manifest["human_review_status"], "pending")

    def test_review_packet_is_deterministic_and_blinded(self):
        records = [
            {
                "case_id": "claude:base:p1",
                "provider": "claude",
                "mode": "base",
                "prompt": "Prompt one",
                "response": "Response one",
            },
            {
                "case_id": "gemini:redesigned:p1",
                "provider": "gemini",
                "mode": "redesigned_skill",
                "prompt": "Prompt two",
                "response": "Response two",
            },
        ]
        first = study_harness.randomized_review_packet(records, study_id="study-a")
        second = study_harness.randomized_review_packet(records, study_id="study-a")
        self.assertEqual(first, second)
        self.assertNotIn("provider", first["blinded_records"][0])
        self.assertEqual(len(first["answer_key"]), 2)

    def test_human_scores_are_validated_and_aggregated(self):
        ratings = dict.fromkeys(study_harness.RATING_DIMENSIONS, 4)
        result = study_harness.aggregate_human_scores(
            [{"mode": "redesigned_skill", "ratings": ratings}]
        )
        self.assertEqual(result["review_type"], "blinded_human")
        self.assertEqual(
            result["aggregates"]["redesigned_skill"]["usefulness"],
            4.0,
        )
        with self.assertRaises(ValueError):
            study_harness.aggregate_human_scores(
                [{"mode": "base", "ratings": {**ratings, "clarity": 6}}]
            )

    def test_prepare_is_creation_only(self):
        root = Path("/tmp") / f"finance-skills-study-{uuid.uuid4().hex}"
        prompts_path = root / "eval" / "prompts.v0.14.0.json"
        prompts_path.parent.mkdir(parents=True)
        with prompts_path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps([{"id": "p1", "prompt": "Analyze TEST."}]))
        result = study_harness.prepare_study(root, "study-001")
        self.assertEqual(result["status"], "prepared")
        self.assertFalse(result["external_runs_completed"])
        with self.assertRaises(FileExistsError):
            study_harness.prepare_study(root, "study-001")


if __name__ == "__main__":
    unittest.main()
