import argparse
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import blast_analyzer
from blast_analyzer import BlastRadiusAnalyzer


class BlastAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = BlastRadiusAnalyzer(project_path="project")
        cls.analyzer.build_graph()

    def test_graph_contains_expected_call_edges(self) -> None:
        graph = self.analyzer.graph

        post_user = "function:api.user_api.post_user"
        create_user = "function:services.user_service.create_user"
        validate_user = "function:utils.validation.validate_user"
        user_class = "class:models.user_model.User"

        self.assertTrue(graph.has_edge(post_user, create_user))
        self.assertEqual(graph[post_user][create_user]["relation"], "CALLS")
        self.assertTrue(graph.has_edge(create_user, validate_user))
        self.assertEqual(graph[create_user][validate_user]["relation"], "CALLS")
        self.assertTrue(graph.has_edge(create_user, user_class))
        self.assertEqual(graph[create_user][user_class]["relation"], "DEPENDS_ON")

    def test_validate_and_normalize_intent(self) -> None:
        raw = {
            "change_type": "api_modification",
            "target": "function:api.user_api.post_user",
            "modification": "add_optional_field",
        }
        intent, target = self.analyzer.validate_and_normalize_intent(raw)

        self.assertEqual(intent.change_type, "api_modification")
        self.assertEqual(target, "function:api.user_api.post_user")

    def test_report_has_direct_and_indirect_sections(self) -> None:
        raw = {
            "change_type": "function_logic_change",
            "target": "function:services.user_service.create_user",
            "modification": "adjust validation flow",
        }
        intent, target = self.analyzer.validate_and_normalize_intent(raw)
        report = self.analyzer.generate_report(intent, target)

        self.assertIn("direct_impacts", report)
        self.assertIn("indirect_impacts", report)
        self.assertIn("risk_areas", report)
        self.assertIn("severity", report)
        self.assertGreaterEqual(len(report["direct_impacts"]), 1)

    def test_inheritance_edges_use_inherits_relation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            pkg = Path(tmpdir)
            (pkg / "sample.py").write_text(
                "class Parent:\n"
                "    pass\n\n"
                "class Child(Parent):\n"
                "    pass\n",
                encoding="utf-8",
            )

            analyzer = BlastRadiusAnalyzer(project_path=tmpdir)
            analyzer.build_graph()
            graph = analyzer.graph

            child = "class:sample.Child"
            parent = "class:sample.Parent"
            self.assertTrue(graph.has_edge(child, parent))
            self.assertEqual(graph[child][parent]["relation"], "INHERITS")

    def test_symbol_target_requires_opt_in(self) -> None:
        raw = {
            "change_type": "function_logic_change",
            "target": "create_user",
            "modification": "adjust validation flow",
        }
        with self.assertRaises(ValueError):
            self.analyzer.validate_and_normalize_intent(raw)

        relaxed = BlastRadiusAnalyzer(project_path="project", allow_symbol_target=True)
        relaxed.build_graph()
        _, target = relaxed.validate_and_normalize_intent(raw)
        self.assertEqual(target, "function:services.user_service.create_user")

    def _openai_args(self, client_change_file: str) -> argparse.Namespace:
        return argparse.Namespace(
            project_path="project",
            allow_symbol_target=False,
            intent_file=None,
            intent_json=None,
            intent_from_openai=True,
            client_change_file=client_change_file,
            openai_model="gpt-4o-mini-test",
            openai_debug=False,
            list_targets=False,
            output_json="blast_report.json",
            output_md="blast_report.md",
        )

    def test_load_intent_from_openai_success_path(self) -> None:
        with TemporaryDirectory() as tmpdir:
            change_file = Path(tmpdir) / "client.diff"
            change_file.write_text("rename age -> user_age in request payload", encoding="utf-8")
            args = self._openai_args(str(change_file))
            inferred = {
                "change_type": "function_logic_change",
                "target": "function:services.user_service.create_user",
                "modification": "adjust validation flow",
            }

            with patch(
                "blast_analyzer._infer_intent_with_openai_attempt",
                return_value=(inferred, json.dumps(inferred)),
            ) as mocked:
                raw = blast_analyzer.load_intent(args, self.analyzer)

            self.assertEqual(raw, inferred)
            self.assertEqual(mocked.call_count, 1)

    def test_load_intent_from_openai_retries_after_validation_error(self) -> None:
        with TemporaryDirectory() as tmpdir:
            change_file = Path(tmpdir) / "client.diff"
            change_file.write_text("client contract update", encoding="utf-8")
            args = self._openai_args(str(change_file))

            invalid = {
                "change_type": "function_logic_change",
                "target": "function:does.not.exist",
                "modification": "adjust validation flow",
            }
            valid = {
                "change_type": "function_logic_change",
                "target": "function:services.user_service.create_user",
                "modification": "adjust validation flow",
            }

            with patch(
                "blast_analyzer._infer_intent_with_openai_attempt",
                side_effect=[(invalid, json.dumps(invalid)), (valid, json.dumps(valid))],
            ) as mocked:
                raw = blast_analyzer.load_intent(args, self.analyzer)

            self.assertEqual(raw, valid)
            self.assertEqual(mocked.call_count, 2)

    def test_load_intent_from_openai_falls_back_to_default_in_non_interactive_mode(self) -> None:
        with TemporaryDirectory() as tmpdir:
            change_file = Path(tmpdir) / "client.diff"
            change_file.write_text("client contract update", encoding="utf-8")
            args = self._openai_args(str(change_file))

            with patch(
                "blast_analyzer._infer_intent_with_openai_attempt",
                side_effect=[ValueError("bad response"), ValueError("still bad")],
            ):
                with patch("sys.stdin.isatty", return_value=False):
                    raw = blast_analyzer.load_intent(args, self.analyzer)

            self.assertEqual(raw, blast_analyzer._default_intent())

    def test_load_intent_from_openai_invalid_target_reports_clear_error(self) -> None:
        with TemporaryDirectory() as tmpdir:
            change_file = Path(tmpdir) / "client.diff"
            change_file.write_text("client contract update", encoding="utf-8")
            args = self._openai_args(str(change_file))

            invalid = {
                "change_type": "function_logic_change",
                "target": "function:does.not.exist",
                "modification": "adjust validation flow",
            }

            with patch(
                "blast_analyzer._infer_intent_with_openai_attempt",
                side_effect=[(invalid, json.dumps(invalid)), (invalid, json.dumps(invalid))],
            ):
                with self.assertRaises(ValueError) as ctx:
                    blast_analyzer._load_intent_from_openai(args, self.analyzer)

            message = str(ctx.exception)
            self.assertIn("OpenAI intent inference failed after 2 attempts", message)
            self.assertIn("Target 'function:does.not.exist' not found in graph.", message)


if __name__ == "__main__":
    unittest.main()
