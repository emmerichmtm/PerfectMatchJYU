#!/usr/bin/env python3
"""Two CSV inputs -> one result CSV and a plain-text report."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import match_solver as core


FIELDS = {
    "id": core.COL_ID,
    "side": core.COL_STATUS,
    "profile": core.COL_PROFILE,
    "hobbies": core.COL_HOBBIES,
    "preferred_hobbies": core.COL_HOBBIES_PREF,
    "gender": core.COL_GENDER_ME,
    "preferred_gender": core.COL_GENDER_PREF,
    "native_languages": core.COL_LANG_NATIVE,
    "languages": core.COL_LANG_USE,
    "age": core.COL_AGE_ME,
    "preferred_age": core.COL_AGE_PREF,
    "pets": core.COL_PETS,
    "appreciate": core.COL_APPRECIATE,
    "information": core.COL_INFO,
    "degree": core.COL_DEGREE,
    "field": core.COL_FIELD,
    "must_match_1": core.COL_MM1,
    "must_match_1_values": core.COL_MM1_SPEC,
    "must_match_2": core.COL_MM2,
    "must_match_2_values": core.COL_MM2_SPEC,
}
CHECKS = ("enforce_gender", "enforce_pets", "enforce_must_match")
SETTINGS = {**{f"weight_{k}": v for k, v in core.DEFAULT_WEIGHTS.items()},
            **{k: True for k in CHECKS}, "minimum_score": 0.0,
            "solver_time_limit_seconds": 60}
CRITERIA = {"profile", "hobbies", "gender", "languages", "degree", "field"}
RESULT_COLUMNS = ["student_id", "local_id", "score"] + [f"{k}_score" for k in core.DEFAULT_WEIGHTS]
# Extra settings columns such as value_interests define alternative solutions; blank cells repeat value.
VARIANT_COLUMN = r"value_([A-Za-z0-9][A-Za-z0-9_-]*)"
MAX_SOLUTIONS = 3


def read_csv(path: Path, required: set[str], optional: set[str] | None = None, pattern: str | None = None):
    """Read UTF-8 Excel CSVs without losing leading zeroes or guessing field types."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name}: save the file as CSV UTF-8 and try again.") from exc
    if not text.strip():
        raise ValueError(f"{path.name}: the file is empty.")
    delimiter = None
    for candidate in (",", ";", "\t"):
        header = next(csv.reader(io.StringIO(text), delimiter=candidate), [])
        if required <= {v.strip() for v in header}:
            delimiter = candidate
            break
    if delimiter is None:
        raise ValueError(f"{path.name}: missing or renamed column headings. "
                         f"Use the example template; required headings: {', '.join(sorted(required))}.")
    reader = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
    header = [v.strip() for v in next(reader)]
    if len(header) != len(set(header)):
        raise ValueError(f"{path.name}: duplicate column headings.")
    unknown = {h for h in set(header) - required - (optional or set())
               if not (pattern and re.fullmatch(pattern, h))}
    if unknown:
        raise ValueError(f"{path.name}: unrecognized column headings: {', '.join(sorted(unknown))}.")
    rows = []
    try:
        for row in reader:
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                raise ValueError(f"{path.name}, line {reader.line_num}: expected {len(header)} cells, "
                                 f"found {len(row)}. Save again from Excel; do not edit CSV commas manually.")
            rows.append((reader.line_num, dict(zip(header, (cell.strip() for cell in row)))))
    except csv.Error as exc:
        raise ValueError(f"{path.name}, line {reader.line_num}: invalid CSV: {exc}.") from exc
    return rows


def number(value: str, label: str) -> float:
    try:
        result = float(value.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{label}: enter a number, for example 23 or 0.25.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label}: the number must be finite.")
    return result


def load_configs(path: Path) -> list[tuple[str, dict]]:
    """Return (solution name, settings) for the value column and each value_<name> column."""
    rows = read_csv(path, {"setting", "value"}, {"description"}, VARIANT_COLUMN)
    columns = [c for c in (rows[0][1] if rows else {}) if re.fullmatch(VARIANT_COLUMN, c)]
    if len(columns) > MAX_SOLUTIONS - 1:
        raise ValueError(f"{path.name}: use at most {MAX_SOLUTIONS - 1} value_ columns "
                         f"({MAX_SOLUTIONS} solutions in one run).")
    names = ["main"] + [re.fullmatch(VARIANT_COLUMN, c)[1] for c in columns]
    if len({n.lower() for n in names}) != len(names):
        raise ValueError(f"{path.name}: every value_ column needs a different name, other than value_main.")
    return [(name, parse_settings(path, rows, column)) for name, column in zip(names, ["value"] + columns)]


def load_config(path: Path) -> dict:
    return load_configs(path)[0][1]


def parse_settings(path: Path, rows, column: str) -> dict:
    config = {}
    for line, row in rows:
        key, value = row["setting"], row[column] or row["value"]
        label = f"{path.name}, line {line} ({key}{'' if column == 'value' else ', ' + column})"
        if key not in SETTINGS:
            raise ValueError(f"{label}: unknown setting. Keep the names in the example template.")
        if key in config:
            raise ValueError(f"{label}: this setting appears more than once.")
        if key in CHECKS:
            if value.lower() not in {"true", "false"}:
                raise ValueError(f"{label}: use TRUE or FALSE.")
            config[key] = value.lower() == "true"
        else:
            config[key] = number(value, label)
            if config[key] < 0:
                raise ValueError(f"{label}: negative numbers are not allowed.")
    missing = set(SETTINGS) - set(config)
    if missing:
        raise ValueError(f"{path.name}: missing settings: {', '.join(sorted(missing))}.")
    where = "" if column == "value" else f" ({column})"
    try:
        core.normalize_weights({k: config[f"weight_{k}"] for k in core.DEFAULT_WEIGHTS})
    except ValueError as exc:
        raise ValueError(f"{path.name}{where}: {exc}") from exc
    if config["minimum_score"] > 1:
        raise ValueError(f"minimum_score{where} must be between 0 and 1.")
    if not 1 <= config["solver_time_limit_seconds"] <= 86400:
        raise ValueError(f"solver_time_limit_seconds{where} must be between 1 and 86400 (per solving stage).")
    return config


def load_problem(path: Path):
    rows = read_csv(path, set(FIELDS))
    if not rows:
        raise ValueError(f"{path.name}: add at least one participant below the headings.")
    seen, records = set(), []
    warnings = []
    for line, row in rows:
        label = f"{path.name}, line {line} ({row['id'] or 'missing ID'})"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", row["id"]):
            raise ValueError(f"{label}: id must start with a letter or digit and use only letters, digits, _, - or .")
        if row["id"] in seen:
            raise ValueError(f"{label}: duplicate ID. Every participant needs a different ID.")
        seen.add(row["id"])
        row["side"] = row["side"].lower()
        if row["side"] not in {"student", "local"}:
            raise ValueError(f"{label}: side must be student or local.")
        if row["age"] and (not re.fullmatch(r"\d{1,3}", row["age"]) or not 1 <= int(row["age"]) <= 120):
            raise ValueError(f"{label}: age must be a whole number from 1 to 120, or blank.")
        if not core.has_no_pref(row["preferred_age"]):
            age_range = re.fullmatch(r"(\d{1,3})\s*[-–]\s*(\d{1,3})", row["preferred_age"])
            if not age_range or not 1 <= int(age_range[1]) <= int(age_range[2]) <= 120:
                raise ValueError(f"{label}: preferred_age must be a range such as 22-35, no preference, or blank.")
        row["pets"] = row["pets"].lower() or "unknown"
        if row["pets"] not in {"none", "has pets", "avoid pets", "unknown"}:
            raise ValueError(f"{label}: pets must be none, has pets, avoid pets, or unknown.")
        if row["pets"] == "unknown":
            warnings.append(f"{row['id']}: pet situation is unknown; check before confirming a match.")
        if not row["gender"]:
            warnings.append(f"{row['id']}: gender is blank; review any specific partner gender preference.")
        for i in (1, 2):
            criterion = row[f"must_match_{i}"].lower()
            values = row[f"must_match_{i}_values"]
            if bool(criterion) != bool(values):
                raise ValueError(f"{label}: fill in both must_match_{i} and must_match_{i}_values, or leave both blank.")
            if criterion and criterion not in CRITERIA:
                raise ValueError(f"{label}: must_match_{i} must be one of {', '.join(sorted(CRITERIA))}.")
            row[f"must_match_{i}"] = "field of science" if criterion == "field" else criterion
        records.append({FIELDS[key]: (value if value else None) for key, value in row.items()})
    frame = pd.DataFrame(records, columns=list(FIELDS.values()))
    return frame, warnings


def output_table(solution: pd.DataFrame) -> pd.DataFrame:
    if solution.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    rename = {"s_id": "student_id", "l_id": "local_id",
              **{f"comp_{k}": f"{k}_score" for k in core.DEFAULT_WEIGHTS}}
    return solution[["s_id", "l_id", "score"] + [f"comp_{k}" for k in core.DEFAULT_WEIGHTS]].rename(
        columns=rename)[RESULT_COLUMNS].sort_values(["student_id", "local_id"])


def solve(frame: pd.DataFrame, config: dict) -> dict:
    """Score, filter and solve one solution's settings."""
    weights = {k: config[f"weight_{k}"] for k in core.DEFAULT_WEIGHTS}
    students, locals_, diagnostics, edges = core.build_diagnostics_and_edges(
        frame, weights, relax_gender=not config["enforce_gender"],
        relax_pets=not config["enforce_pets"], relax_mustmatch=not config["enforce_must_match"])
    if not edges.empty:
        edges = edges[edges.score >= config["minimum_score"]].copy()
    solution = core.solve_lexi(students, locals_, edges, config["solver_time_limit_seconds"])
    return {"config": config, "students": students, "locals": locals_, "diagnostics": diagnostics,
            "edges": edges, "result": output_table(solution)}


def describe(name: str, solved: dict, main_pairs: set) -> dict:
    """Inputs and outputs of one solution, on the 0-1 scale used by the report and the browser chart."""
    config, result = solved["config"], solved["result"]

    def mean(column):
        return float(result[column].mean()) if len(result) else None

    return {
        "name": name,
        "weights": core.normalize_weights({k: config[f"weight_{k}"] for k in core.DEFAULT_WEIGHTS}),
        "achieved": {k: mean(f"{k}_score") for k in core.DEFAULT_WEIGHTS},
        "rules": {**{k: config[k] for k in CHECKS}, "minimum_score": config["minimum_score"]},
        "students": len(solved["students"]), "locals": len(solved["locals"]), "matches": len(result),
        "unmatched_students": len(solved["students"]) - len(result),
        "unmatched_locals": len(solved["locals"]) - len(result), "eligible_pairs": len(solved["edges"]),
        "score_mean": mean("score"), "score_min": float(result.score.min()) if len(result) else None,
        "shared_with_main": len(set(zip(result.student_id, result.local_id)) & main_pairs),
    }


def weights_table(solutions: list[dict]) -> list[str]:
    """Plain-text version of the browser chart: weights (input) left, achieved scores (output) right."""
    info = [s["info"] for s in solutions]
    names = [i["name"] for i in info]
    width = max([7] + [len(n) + 1 for n in names])
    half = width * len(names)

    def cells(values):
        return "".join(f"{'-' if v is None else v:>{width}}" for v in values)

    def three(value):
        return None if value is None else f"{value:.3f}"

    def row(label, left, right):
        return f"{label:<24}{left:>{half}} |{right:>{half}}"

    lines = ["WEIGHTS (INPUT) AND ACHIEVED SCORES (OUTPUT)",
             "Weights are normalized to sum to 1. Achieved: average criterion score of the selected pairs (0 to 1).",
             row("", "input", "output")]
    if len(names) > 1:
        lines.append(row("", cells(names), cells(names)))
    for k in core.DEFAULT_WEIGHTS:
        lines.append(row(f"{k}", cells(three(i["weights"][k]) for i in info),
                         cells(three(i["achieved"][k]) for i in info)))
    lines.append(row("overall score (average)", "", cells(three(i["score_mean"]) for i in info)))
    lines.append(row("minimum_score / lowest", cells(three(i["rules"]["minimum_score"]) for i in info),
                     cells(three(i["score_min"]) for i in info)))
    lines.append(row("students matched", "", cells(f"{i['matches']}/{i['students']}" for i in info)))
    if len(names) > 1:
        lines.append(row("pairs shared with main", "", cells(str(i["shared_with_main"]) for i in info)))
    return lines


def solution_sections(solved: dict, suffix: str) -> list[str]:
    config, students, locals_ = solved["config"], solved["students"], solved["locals"]
    diagnostics, edges, result = solved["diagnostics"], solved["edges"], solved["result"]
    groups = core.competing_groups(edges, zip(result.student_id, result.local_id)) if not edges.empty else []

    def blocked(identifier, column, others):
        rows = diagnostics[diagnostics[column] == identifier] if not diagnostics.empty else diagnostics
        if rows.empty:
            return "no eligible partner under these settings"
        gender = ~(rows.gender_ok_s_pref_vs_l & rows.gender_ok_l_pref_vs_s)
        must = ~(rows.mustmatch_ok_student_vs_local & rows.mustmatch_ok_local_vs_student)
        low = rows.mandatory_pass & (rows.score < config["minimum_score"])
        return (f"no eligible partner under these settings; of {len(rows)} {others}, failed checks: "
                f"gender {int(gender.sum())}, pets {int((~rows.pets_ok).sum())}, "
                f"must-match {int(must.sum())}, below minimum_score {int(low.sum())}")

    def competing(identifier):
        group, options = next(g for g in groups if identifier in g[0])
        return (f"competes with {', '.join(sorted(group - {identifier}))} for the same locals; "
                f"these {len(group)} students can only be paired with {', '.join(sorted(options))}, "
                f"so {len(group) - len(options)} of them must remain unmatched under these rules")

    def unmatched(frame, column, edge_column, others):
        selected = set(result[column])
        eligible = set(edges[edge_column]) if not edges.empty else set()
        remaining = [v for v in frame[core.COL_ID].tolist() if v not in selected]
        lines = []
        for identifier in remaining:
            if identifier not in eligible:
                reason = blocked(identifier, column, others)
            elif column == "student_id":
                reason = competing(identifier)
            else:
                reason = "eligible partners existed; one-to-one allocation left this person unmatched"
            lines.append(f"  {identifier}: {reason}")
        return remaining, lines

    unmatched_s, details_s = unmatched(students, "student_id", "s_id", "locals")
    unmatched_l, details_l = unmatched(locals_, "local_id", "l_id", "students")
    if unmatched_s:
        details_s.append("  To match every student: relax a must-match, gender or pets rule for a student "
                         "named above, lower minimum_score, or add a suitable local.")
    weights = core.normalize_weights({k: config[f"weight_{k}"] for k in core.DEFAULT_WEIGHTS})
    lines = ["", "SUMMARY" + suffix, f"Students: {len(students)}; locals: {len(locals_)}",
             f"Candidate pairs: {len(diagnostics)}; eligible pairs: {len(edges)}",
             f"Selected matches: {len(result)}",
             f"Unmatched students: {len(unmatched_s)}; unmatched locals: {len(unmatched_l)}"]
    if unmatched_s:
        lines.append(f"ATTENTION: {len(unmatched_s)} of {len(students)} students could not be matched "
                     "under these rules. See UNMATCHED PARTICIPANTS.")
    elif len(students):
        lines.append(f"All {len(students)} students are matched.")
    if not result.empty:
        lines.append(f"Score minimum / average / maximum: {result.score.min():.3f} / {result.score.mean():.3f} / {result.score.max():.3f}")
    else:
        lines.append("No matches were selected. The result CSV contains headings only.")
    lines += ["", "UNMATCHED PARTICIPANTS" + suffix] + (details_s + details_l or ["  None."])
    lines += ["", "SETTINGS USED" + suffix,
              "Weights (normalized to sum to 1): " + "; ".join(f"{k} {v:.3f}" for k, v in weights.items())]
    for key in CHECKS:
        lines.append(f"{key}: {str(config[key]).upper()}")
    lines += [f"minimum_score: {config['minimum_score']:g}",
              f"solver_time_limit_seconds: {config['solver_time_limit_seconds']:g} per stage",
              "", "PAIR CHECKS (counts may overlap)" + suffix]
    if diagnostics.empty:
        lines.append("No student-local pairs exist. Add participants on the missing side.")
    else:
        lines += [f"Failed gender check: {int((~(diagnostics.gender_ok_s_pref_vs_l & diagnostics.gender_ok_l_pref_vs_s)).sum())}",
                  f"Failed pets check: {int((~diagnostics.pets_ok).sum())}",
                  f"Failed must-match check: {int((~(diagnostics.mustmatch_ok_student_vs_local & diagnostics.mustmatch_ok_local_vs_student)).sum())}",
                  f"Passed mandatory checks but below minimum_score: {int((diagnostics.mandatory_pass & (diagnostics.score < config['minimum_score'])).sum())}"]
    return lines


def make_report(config_path, problem_path, solutions, warnings):
    several = len(solutions) > 1
    lines = ["PERFECTMATCH JYU - MATCHING REPORT", "Status: SUCCESS",
             f"Run time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
             f"Participants file: {problem_path.name}", f"Settings file: {config_path.name}",
             f"Input SHA-256: {hashlib.sha256(problem_path.read_bytes()).hexdigest()}",
             f"Settings SHA-256: {hashlib.sha256(config_path.read_bytes()).hexdigest()}"]
    if several:
        lines.append("Solutions: " + ", ".join(s["info"]["name"] for s in solutions))
    lines += [""] + weights_table(solutions)
    for s in solutions:
        lines += solution_sections(s, f" - SOLUTION {s['info']['name']}" if several else "")
    notes = []
    for s in solutions:
        disabled = [key for key in CHECKS if not s["config"][key]]
        if disabled:
            where = f" in solution {s['info']['name']}" if several else ""
            notes.append(f"Checks switched OFF{where}: " + ", ".join(disabled) + ". Review these preferences manually.")
    if notes or warnings:
        lines += ["", "REVIEW NOTES"] + notes + warnings
    lines += ["", "HOW TO READ THIS RUN",
              "Each person appears in at most one selected pair.",
              "The solver first finds the most matches, then improves the lowest selected",
              "score, then the total score (minimum-score numerical tolerance: 0.0000001).",
              "A score is a weighted similarity from 0 to 1, not a probability or guarantee.",
              "Text items are compared by exact wording, ignoring case; prose is not interpreted.",
              "If two must-match criteria are supplied, at least ONE must pass for that person.",
              "Unknown pets do not block a pair. Age preferences affect scores, not eligibility."]
    if several:
        lines += ["Each solution uses its own settings column; blank cells repeat the value column.",
                  "result.csv lists the pairs of every solution; its solution column says which."]
    lines.append("Programme staff should review the suggestions before confirming any match.")
    return "\n".join(lines) + "\n"


def run(config_path: Path, problem_path: Path, result_path: Path, report_path: Path, *, quiet=False):
    paths = [p.resolve() for p in (config_path, problem_path, result_path, report_path)]
    if len(set(paths)) != 4:
        raise ValueError("The two inputs and two outputs must use four different file paths.")
    configs = load_configs(config_path)
    frame, warnings = load_problem(problem_path)
    solutions = [solve(frame, config) for _, config in configs]
    main_pairs = set(zip(solutions[0]["result"].student_id, solutions[0]["result"].local_id))
    for (name, _), solved in zip(configs, solutions):
        solved["info"] = describe(name, solved, main_pairs)
    report = make_report(config_path, problem_path, solutions, warnings)
    if len(solutions) == 1:
        result = solutions[0]["result"]
    else:
        parts = [s["result"].assign(solution=s["info"]["name"]) for s in solutions if not s["result"].empty]
        result = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=RESULT_COLUMNS)
        result = result.reindex(columns=["solution"] + RESULT_COLUMNS)
    for path in (result_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(result_path, index=False, encoding="utf-8-sig", float_format="%.6f")
    report_path.write_text(report, encoding="utf-8")
    main = solutions[0]["info"]
    result.attrs["summary"] = {k: main[k] for k in ("students", "locals", "matches", "unmatched_students",
                                                    "unmatched_locals", "eligible_pairs")}
    result.attrs["solutions"] = [s["info"] for s in solutions]
    if not quiet:
        several = len(solutions) > 1
        if several:
            print(f"SUCCESS: {len(solutions)} solutions.")
        for s in solutions:
            i = s["info"]
            prefix = f"  {i['name']}: " if several else "SUCCESS: "
            print(f"{prefix}{i['matches']} matches; {i['unmatched_students']} unmatched students; "
                  f"{i['unmatched_locals']} unmatched locals.")
        for s in solutions:
            missing = s["info"]["unmatched_students"]
            if missing:
                where = f" in solution {s['info']['name']}" if several else ""
                print(f"ATTENTION: {missing} student{'s' if missing > 1 else ''} could not be matched{where}; "
                      "the report explains why.")
        print(f"Results: {result_path.resolve()}\nReport:  {report_path.resolve()}")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("input/config.csv"))
    parser.add_argument("--problem", type=Path, default=Path("input/problem.csv"))
    parser.add_argument("--result", type=Path, default=Path("output/result.csv"))
    parser.add_argument("--report", type=Path, default=Path("output/report.txt"))
    args = parser.parse_args(argv)
    try:
        run(args.config, args.problem, args.result, args.report)
    except (ValueError, OSError, RuntimeError, csv.Error, core.pulp.PulpSolverError) as exc:
        print(f"ERROR: {exc}\nThis run did not finish successfully. Previous output files may still be present.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
