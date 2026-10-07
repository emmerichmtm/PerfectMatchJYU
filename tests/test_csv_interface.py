import csv
import itertools
from pathlib import Path
import random
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
        self.assertIn("hobbies 1.000", self.report.read_text())

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

    def test_round_of_21_students_and_28_locals_matches_every_student(self):
        self.problem.write_bytes((ROOT / "examples/problem_21x28.csv").read_bytes())
        result = self.run_case()
        students = {r["id"] for r in self.rows(self.problem) if r["side"] == "student"}
        self.assertEqual(len(students), 21)
        self.assertEqual(set(result.student_id), students)
        self.assertEqual(result.attrs["summary"]["unmatched_locals"], 7)
        self.assertIn("All 21 students are matched.", self.report.read_text(encoding="utf-8"))

    def test_unmatched_student_report_names_competing_group(self):
        rows = self.rows(self.problem)
        for row in rows:
            if row["id"] in {"S01", "S03"}:  # Only L03 lists art.
                row.update(must_match_1="hobbies", must_match_1_values="art",
                           must_match_2="", must_match_2_values="")
        self.write(self.problem, rows)
        (left_out,) = {"S01", "S03"} - set(self.run_case().student_id)
        rival = ({"S01", "S03"} - {left_out}).pop()
        report = self.report.read_text(encoding="utf-8")
        self.assertIn("ATTENTION: 1 of 3 students could not be matched", report)
        self.assertIn(f"{left_out}: competes with {rival} for the same locals; these 2 students can only "
                      "be paired with L03, so 1 of them must remain unmatched", report)

    def test_unmatched_student_without_partners_lists_failed_checks(self):
        rows = self.rows(self.problem)
        rows[0]["preferred_gender"] = "agender"
        self.write(self.problem, rows)
        self.assertNotIn("S01", set(self.run_case().student_id))
        self.assertIn("S01: no eligible partner under these settings; of 4 locals, failed checks: gender 4,",
                      self.report.read_text(encoding="utf-8"))

    def test_three_solutions_from_value_columns(self):
        self.config.write_bytes((ROOT / "examples/config_three_solutions.csv").read_bytes())
        self.problem.write_bytes((ROOT / "examples/problem_21x28.csv").read_bytes())
        result = self.run_case()
        solutions = result.attrs["solutions"]
        self.assertEqual([s["name"] for s in solutions], ["main", "interests", "background"])
        self.assertEqual(list(pd.read_csv(self.result).columns), ["solution"] + app.RESULT_COLUMNS)
        for s in solutions:
            with self.subTest(solution=s["name"]):
                self.assertEqual(s["matches"], 21)
                self.assertEqual(set(result[result.solution == s["name"]].student_id), set(result.student_id))
                self.assertAlmostEqual(sum(s["weights"].values()), 1)
                self.assertTrue(all(0 <= v <= 1 for v in s["achieved"].values()))
                # The overall score is linear in the criteria, so its average is the weighted average.
                self.assertAlmostEqual(s["score_mean"], sum(s["weights"][k] * s["achieved"][k] for k in s["weights"]))
        self.assertEqual(solutions[0]["shared_with_main"], 21)
        self.assertAlmostEqual(solutions[1]["weights"]["hobbies"], 0.35)
        report = self.report.read_text(encoding="utf-8")
        self.assertIn("Solutions: main, interests, background", report)
        self.assertIn("SUMMARY - SOLUTION interests", report)
        self.assertIn("WEIGHTS (INPUT) AND ACHIEVED SCORES (OUTPUT)", report)

    def test_blank_solution_cells_repeat_value_and_bad_columns_are_rejected(self):
        rows = [dict(r, value_strict="", value_open="") for r in self.rows(self.config)]
        next(r for r in rows if r["setting"] == "enforce_gender")["value_open"] = "FALSE"
        next(r for r in rows if r["setting"] == "weight_age")["value_strict"] = "0,5"
        self.write(self.config, rows)
        (_, main), (strict, s), (open_, o) = app.load_configs(self.config)
        self.assertEqual((strict, open_), ("strict", "open"))
        self.assertEqual(s["weight_age"], 0.5)
        self.assertEqual({k: v for k, v in s.items() if k != "weight_age"}, {k: v for k, v in main.items() if k != "weight_age"})
        self.assertFalse(o["enforce_gender"])
        self.run_case()
        self.assertIn("Checks switched OFF in solution open: enforce_gender", self.report.read_text(encoding="utf-8"))
        for extra in [{"value_b": "", "value_c": "", "value_d": ""}, {"value_main": ""}, {"variant": ""}]:
            with self.subTest(extra=extra):
                self.write(self.config, [dict(r, **extra) for r in self.rows(ROOT / "examples/config.csv")])
                with self.assertRaises(ValueError):
                    app.load_configs(self.config)
        rows = [dict(r, value_b="") for r in self.rows(ROOT / "examples/config.csv")]
        rows[0]["value_b"] = "-1"
        self.write(self.config, rows)
        with self.assertRaisesRegex(ValueError, "value_b"):
            app.load_configs(self.config)

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

    def test_competing_groups_have_fewer_locals_than_students(self):
        rng = random.Random(7)
        s_ids, l_ids = [f"S{i}" for i in range(6)], [f"L{i}" for i in range(5)]
        for _ in range(8):
            edges = pd.DataFrame([dict(s_id=s, l_id=l, score=rng.random())
                                  for s in s_ids for l in l_ids if rng.random() < 0.3])
            result = core.solve_lexi(pd.DataFrame({core.COL_ID: s_ids}), pd.DataFrame({core.COL_ID: l_ids}), edges)
            selected = list(zip(result.s_id, result.l_id))
            stranded = set(edges.s_id) - {s for s, _ in selected}
            groups = core.competing_groups(edges, selected)
            explained = [s for group, _ in groups for s in group]
            self.assertEqual(len(explained), len(set(explained)))
            self.assertLessEqual(stranded, set(explained))
            for group, options in groups:
                self.assertEqual(set(edges[edges.s_id.isin(group)].l_id), options)
                self.assertEqual(len(options), len(group) - len(group & stranded))

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
