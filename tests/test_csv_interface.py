import csv
import itertools
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import match_solver as core
import run_matching as app

ROOT = Path(__file__).resolve().parents[1]


class CsvInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config.csv"
        self.problem = self.root / "problem.csv"
        self.result = self.root / "result.csv"
        self.report = self.root / "report.txt"
        self.config.write_bytes((ROOT / "examples/config.csv").read_bytes())
        self.problem.write_bytes((ROOT / "examples/problem.csv").read_bytes())

    def write(self, path, rows, delimiter=","):
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)

    def rows(self, path):
        with path.open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def configure(self, **changes):
        rows = self.rows(self.config)
        for row in rows:
            if row["setting"] in changes:
                row["value"] = str(changes[row["setting"]])
        self.write(self.config, rows)

    def run_case(self):
        return app.run(self.config, self.problem, self.result, self.report)

    def test_example_cli_has_exactly_two_outputs(self):
        command = [sys.executable, str(ROOT / "run_matching.py"), "--config", str(self.config),
                   "--problem", str(self.problem), "--result", str(self.result), "--report", str(self.report)]
        process = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        rows = self.rows(self.result)
        self.assertEqual([(r["student_id"], r["local_id"]) for r in rows],
                         [("S01", "L01"), ("S02", "L02"), ("S03", "L03")])
        self.assertEqual(len(list(self.root.iterdir())), 4)
        report = self.report.read_text(encoding="utf-8")
        self.assertIn("Status: SUCCESS", report)
        self.assertIn("L04:", report)

    def test_semicolon_excel_csv_and_decimal_comma(self):
        rows = self.rows(self.config)
        next(r for r in rows if r["setting"] == "minimum_score")["value"] = "0,70"
        self.write(self.config, rows, ";")
        rows = self.rows(self.problem)
        rows[0]["id"] = "0001"
        rows[0]["information"] = "Finnish ä; coffee, tea"
        self.write(self.problem, rows, ";")
        result = self.run_case()
        self.assertIn("0001", set(result.student_id))
        self.assertTrue((result.score >= 0.70).all())

    def test_no_matches_retains_result_headings(self):
        self.configure(minimum_score=1)
        self.assertTrue(self.run_case().empty)
        self.assertEqual(list(pd.read_csv(self.result).columns), app.RESULT_COLUMNS)
        self.assertIn("No matches were selected", self.report.read_text())

    def test_custom_weights_control_reported_scores(self):
        self.configure(**{f"weight_{k}": (10 if k == "hobbies" else 0) for k in core.DEFAULT_WEIGHTS})
        result = self.run_case()
        self.assertEqual(len(result), 3)
        self.assertTrue((result.score == result.hobbies_score).all())
        self.assertIn("hobbies 100.0%", self.report.read_text())

    def test_only_one_side_does_not_invent_partners(self):
        rows = [r for r in self.rows(self.problem) if r["side"] == "student"]
        self.write(self.problem, rows)
        self.assertTrue(self.run_case().empty)
        self.assertIn("Students: 3; locals: 0", self.report.read_text())

    def test_invalid_configuration(self):
        for setting, value in [("weight_profile", "-1"), ("weight_profile", "nan"),
                               ("weight_age", "infinity"), ("enforce_pets", "maybe"),
                               ("minimum_score", "1.1"), ("solver_time_limit_seconds", "0")]:
            with self.subTest(setting=setting, value=value):
                self.config.write_bytes((ROOT / "examples/config.csv").read_bytes())
                self.configure(**{setting: value})
                with self.assertRaises(ValueError):
                    app.load_config(self.config)
        self.config.write_bytes((ROOT / "examples/config.csv").read_bytes())
        self.configure(**{f"weight_{k}": 0 for k in core.DEFAULT_WEIGHTS})
        with self.assertRaisesRegex(ValueError, "At least one"):
            app.load_config(self.config)

    def test_unknown_duplicate_and_missing_settings(self):
        original = self.rows(self.config)
        for rows in [original[:-1], original + [original[0]],
                     original + [{"setting": "typo", "value": "1", "description": ""}]]:
            self.write(self.config, rows)
            with self.assertRaises(ValueError):
                app.load_config(self.config)

    def test_duplicate_ids_and_invalid_participants(self):
        original = self.rows(self.problem)
        for field, value in [("id", "S02"), ("side", "stduent"), ("age", "twenty"),
                             ("preferred_age", "40-20"), ("pets", "dog lover"),
                             ("must_match_1", "unknown"), ("must_match_1_values", "")]:
            with self.subTest(field=field):
                rows = [r.copy() for r in original]
                rows[0][field] = value
                self.write(self.problem, rows)
                with self.assertRaises(ValueError):
                    app.load_problem(self.problem)

    def test_malformed_and_missing_columns(self):
        self.problem.write_text("id,side\nS01,student\n")
        with self.assertRaisesRegex(ValueError, "column headings"):
            app.load_problem(self.problem)
        self.problem.write_bytes((ROOT / "examples/problem.csv").read_bytes())
        with self.problem.open("a", encoding="utf-8") as f:
            f.write("S99,student\n")
        with self.assertRaisesRegex(ValueError, "expected 20 cells"):
            app.load_problem(self.problem)

    def test_switches_and_two_must_match_criteria_use_or(self):
        rows = self.rows(self.problem)
        rows = [rows[0], rows[3]]
        rows[0].update(preferred_gender="man", pets="avoid pets", must_match_1="hobbies",
                       must_match_1_values="never shared", must_match_2="gender", must_match_2_values="woman")
        self.write(self.problem, rows)
        self.assertTrue(self.run_case().empty)
        self.configure(enforce_gender="FALSE", enforce_pets="FALSE")
        self.assertEqual(len(self.run_case()), 1)
        self.assertIn("Checks switched OFF", self.report.read_text())
        rows[0]["must_match_2_values"] = "never shared"
        self.write(self.problem, rows)
        self.assertTrue(self.run_case().empty)
        self.configure(enforce_must_match="FALSE")
        self.assertEqual(len(self.run_case()), 1)

    def test_inputs_cannot_be_overwritten(self):
        original = self.problem.read_bytes()
        with self.assertRaisesRegex(ValueError, "four different"):
            app.run(self.config, self.problem, self.problem, self.report)
        self.assertEqual(self.problem.read_bytes(), original)

    def test_failed_cli_no_traceback_or_new_results(self):
        self.configure(weight_age=-1)
        process = subprocess.run([sys.executable, str(ROOT / "run_matching.py"),
                                  "--config", str(self.config), "--problem", str(self.problem),
                                  "--result", str(self.result), "--report", str(self.report)],
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 1)
        self.assertIn("ERROR:", process.stderr)
        self.assertNotIn("Traceback", process.stderr)
        self.assertFalse(self.result.exists())


class SolverTests(unittest.TestCase):
    def test_lexicographic_solution_against_enumeration(self):
        # Includes a total-score temptation that must lose to a higher minimum score.
        for scores in [[0.99, 0.7, 0.7, 0.6], [0.8, 0.8, 0.7, 0.9], [0, 0, 0, 0]]:
            students = pd.DataFrame({core.COL_ID: ["S-1", "S_1"]})
            locals_ = pd.DataFrame({core.COL_ID: ["L1", "L2"]})
            pairs = list(itertools.product(students[core.COL_ID], locals_[core.COL_ID]))
            edges = pd.DataFrame([dict(s_id=s, l_id=l, score=score) for (s, l), score in zip(pairs, scores)])
            possibilities = []
            for size in range(1, len(edges) + 1):
                for subset in itertools.combinations(edges.to_dict("records"), size):
                    if len({r["s_id"] for r in subset}) == size and len({r["l_id"] for r in subset}) == size:
                        possibilities.append((size, min(r["score"] for r in subset), sum(r["score"] for r in subset)))
            result = core.solve_lexi(students, locals_, edges)
            expected = max(possibilities)
            self.assertEqual(len(result), expected[0])
            self.assertAlmostEqual(result.score.min(), expected[1])
            self.assertAlmostEqual(result.score.sum(), expected[2])

    def test_nonoptimal_solver_status_is_not_reported_as_success(self):
        students = pd.DataFrame({core.COL_ID: ["S1"]})
        locals_ = pd.DataFrame({core.COL_ID: ["L1"]})
        edges = pd.DataFrame([dict(s_id="S1", l_id="L1", score=0.5)])
        with patch.object(core.pulp.LpProblem, "solve", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "optimally"):
                core.solve_lexi(students, locals_, edges)

    def test_missing_gender_and_literal_no_preference(self):
        self.assertFalse(core.gender_compatible("woman", None))
        self.assertTrue(core.gender_compatible("no preference", None))
        self.assertFalse(core.has_no_pref("Germany"))
        self.assertFalse(core.pets_compatible("avoid pets", "has pets"))


if __name__ == "__main__":
    unittest.main()
