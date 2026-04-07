#!/usr/bin/env python3
from __future__ import annotations
import argparse
import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    import pulp
except Exception as e:
    raise SystemExit("PuLP is required. Install with: pip install pulp pandas openpyxl") from e

COL_ID = "Identification"
COL_STATUS = "My status"
COL_PROFILE = "My profile"
COL_HOBBIES = "My hobbies and interests"
COL_HOBBIES_PREF = "Hobbies and interests I/we appreciate"
COL_GENDER_ME = "My gender identity"
COL_GENDER_PREF = "Friend's gender identity"
COL_LANG_NATIVE = "My native languages"
COL_LANG_USE = "Languages, I can use in daily life"
COL_AGE_ME = "My age"
COL_AGE_PREF = "Friend's age"
COL_PETS = "Pet allergies and preferences"
COL_APPRECIATE = "Things I appreciate in a friend (a student or a local)."
COL_INFO = "Additional information that can assist us in matching me with a student/local friend."
COL_DEGREE = "My degree and program at JYU"
COL_FIELD = "Field of Science"
COL_MM1 = "The must match criteria 1"
COL_MM1_SPEC = "Specs for my criteria 1"
COL_MM2 = "The must match criteria 2"
COL_MM2_SPEC = "Specs for my criteria 2"

DEFAULT_WEIGHTS = {
    "profile": 34,
    "hobbies": 23,
    "appreciate": 10,
    "languages": 9,
    "age": 9,
    "info": 7,
    "degree": 5,
    "field": 3,
}

MUST_MATCH_MAP = {
    "field of science": COL_FIELD,
    "profile type": COL_PROFILE,
    "profile": COL_PROFILE,
    "language": COL_LANG_USE,
    "languages": COL_LANG_USE,
    "degree": COL_DEGREE,
    "student degree": COL_DEGREE,
    "hobbies & interests": COL_HOBBIES,
    "hobbies and interests": COL_HOBBIES,
    "hobbies": COL_HOBBIES,
    "gender": COL_GENDER_ME,
    "gender identity": COL_GENDER_ME,
}


def parse_weights_arg(s: Optional[str]) -> Dict[str, float]:
    if not s:
        return {}
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    try:
        d = json.loads(s)
        if isinstance(d, dict):
            return {str(k): float(v) for k, v in d.items()}
    except Exception:
        pass
    if s.startswith("{") and s.endswith("}") and ":" in s:
        out = {}
        for piece in s[1:-1].split(","):
            if ":" in piece:
                k, v = piece.split(":", 1)
                out[k.strip().strip("'\"")] = float(v.strip().strip("'\""))
        if out:
            return out
    try:
        d = ast.literal_eval(s)
        if isinstance(d, dict):
            return {str(k): float(v) for k, v in d.items()}
    except Exception:
        pass
    if "=" in s and "{" not in s and "}" not in s:
        out = {}
        for piece in s.split(","):
            k, v = piece.split("=", 1)
            out[k.strip()] = float(v.strip())
        return out
    raise ValueError(f"Could not parse --weights: {s!r}")


def clean_text(val):
    if pd.isna(val):
        return val
    s = str(val).replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", s)


def norm_set(x) -> set:
    if pd.isna(x):
        return set()
    return {p.strip().lower() for p in re.split(r"[;,/|]+", clean_text(x)) if p.strip()}


def has_no_pref(x) -> bool:
    if pd.isna(x):
        return True
    t = clean_text(x).lower()
    return "no preference" in t or "no preferences" in t or "any" in t


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def numeric_age(x) -> Optional[int]:
    if pd.isna(x):
        return None
    m = re.search(r"\d{1,3}", clean_text(x))
    return int(m.group()) if m else None


def parse_age_pref(s) -> Optional[Tuple[int, int]]:
    if pd.isna(s) or has_no_pref(s):
        return None
    text = clean_text(s)
    m = re.search(r"(\d{1,3})\s*[-–]\s*(\d{1,3})", text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = re.search(r"(\d{1,3})", text)
    if m:
        v = int(m.group(1))
        return (v - 2, v + 2)
    return None


def normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    s = sum(weights.values())
    return {k: float(v) / s for k, v in weights.items()}


def gender_compatible(pref, me, relax=False) -> bool:
    if relax or has_no_pref(pref) or pd.isna(me):
        return True
    return bool(norm_set(pref) & norm_set(me)) or ("any" in norm_set(pref))


def pets_compatible(a, b, relax=False) -> bool:
    if relax or has_no_pref(a) or has_no_pref(b) or (pd.isna(a) and pd.isna(b)):
        return True
    aset, bset = norm_set(a), norm_set(b)
    bad_words = {"severe allergies", "anaphylaxis", "cannot have pets", "no pets at home"}
    has_pets_words = {"has cat", "has dog", "has pets", "cat", "dog", "pets at home", "pets are welcome"}
    return not ((aset & bad_words and bset & has_pets_words) or (bset & bad_words and aset & has_pets_words))


def resolve_mustmatch_column(crit: str) -> Optional[str]:
    for key, col in MUST_MATCH_MAP.items():
        if key in crit:
            return col
    return None


def _mm_check_one(crit, spec, partner_row) -> bool:
    if pd.isna(crit) or pd.isna(spec):
        return False
    col = resolve_mustmatch_column(clean_text(crit).lower())
    if col is None:
        return True
    return bool(norm_set(spec) & norm_set(partner_row.get(col))) or has_no_pref(spec)


def must_match_ok(seeker_row: pd.Series, partner_row: pd.Series, relax=False) -> bool:
    if relax:
        return True
    if pd.isna(seeker_row.get(COL_MM1)) and pd.isna(seeker_row.get(COL_MM2)):
        return True
    return _mm_check_one(seeker_row.get(COL_MM1), seeker_row.get(COL_MM1_SPEC), partner_row) or _mm_check_one(seeker_row.get(COL_MM2), seeker_row.get(COL_MM2_SPEC), partner_row)


def pair_score(s: pd.Series, l: pd.Series, w: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
    prof = jaccard(norm_set(s.get(COL_PROFILE)), norm_set(l.get(COL_PROFILE)))
    hob = 0.5 * (
        jaccard(norm_set(s.get(COL_HOBBIES)), norm_set(l.get(COL_HOBBIES_PREF))) +
        jaccard(norm_set(l.get(COL_HOBBIES)), norm_set(s.get(COL_HOBBIES_PREF)))
    )
    appreciate = jaccard(norm_set(s.get(COL_APPRECIATE)), norm_set(l.get(COL_APPRECIATE)))
    langs_s = norm_set(s.get(COL_LANG_NATIVE)) | norm_set(s.get(COL_LANG_USE))
    langs_l = norm_set(l.get(COL_LANG_NATIVE)) | norm_set(l.get(COL_LANG_USE))
    languages = jaccard(langs_s, langs_l)

    s_age, l_age = numeric_age(s.get(COL_AGE_ME)), numeric_age(l.get(COL_AGE_ME))
    s_pref, l_pref = parse_age_pref(s.get(COL_AGE_PREF)), parse_age_pref(l.get(COL_AGE_PREF))
    if s_age is not None and l_age is not None:
        age = max(0.0, 1.0 - abs(s_age - l_age) / 20.0)
    else:
        age = 0.5
    if s_pref and l_age is not None and not (s_pref[0] <= l_age <= s_pref[1]):
        age *= 0.5
    if l_pref and s_age is not None and not (l_pref[0] <= s_age <= l_pref[1]):
        age *= 0.5

    info = jaccard(norm_set(s.get(COL_INFO)), norm_set(l.get(COL_INFO)))
    degree = jaccard(norm_set(s.get(COL_DEGREE)), norm_set(l.get(COL_DEGREE)))
    field = jaccard(norm_set(s.get(COL_FIELD)), norm_set(l.get(COL_FIELD)))

    comp = {
        "profile": prof,
        "hobbies": hob,
        "appreciate": appreciate,
        "languages": languages,
        "age": age,
        "info": info,
        "degree": degree,
        "field": field,
    }
    total = sum(w[k] * comp[k] for k in w)
    return float(total), comp


def classify_side(text: str) -> str:
    t = clean_text(text or "").lower()
    if re.search(r"\bi am a\b.*\blocal resident\b", t):
        return "local"
    if re.search(r"\bi am an?\b.*\binternational\b.*\bjyu\b.*\bdegree student\b", t) or re.search(r"\bi am an?\b.*\bdegree student\b", t):
        return "student"
    return "unknown"


def load_data(path: Path, sheet: str) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, sheet_name=sheet)
    else:
        df = pd.read_csv(path)
    df.columns = [clean_text(c) for c in df.columns]
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].apply(clean_text)
    if len(df) > 0 and str(df.iloc[0].get(COL_ID, "")).lower().startswith("id code"):
        df = df.iloc[1:].copy()
    if COL_STATUS in df.columns:
        df = df[df[COL_STATUS].notna()]
        df = df[df[COL_STATUS].str.contains("REMOVED", na=False) == False]
    return df


def build_diagnostics_and_edges(df: pd.DataFrame, weights: Dict[str, float], relax_gender=False, relax_pets=False, relax_mustmatch=False):
    side = df[COL_STATUS].apply(classify_side)
    students = df[side == "student"].copy()
    locals_ = df[side == "local"].copy()
    unknown = df[side == "unknown"].copy()
    if not unknown.empty:
        bias_student = unknown[COL_DEGREE].notna() & (unknown[COL_DEGREE].astype(str).str.strip() != "")
        students = pd.concat([students, unknown[bias_student]])
        locals_ = pd.concat([locals_, unknown[~bias_student]])
    if students.empty and not locals_.empty:
        half = len(locals_) // 2
        students = locals_.iloc[:half].copy()
        locals_ = locals_.iloc[half:].copy()
    elif locals_.empty and not students.empty:
        half = len(students) // 2
        locals_ = students.iloc[:half].copy()
        students = students.iloc[half:].copy()

    def ensure_id(series, prefix):
        vals = []
        for i, v in enumerate(series.tolist()):
            vals.append(str(v) if pd.notna(v) and str(v).strip() else f"{prefix}_{i:03d}")
        return pd.Series(vals, index=series.index)

    students[COL_ID] = ensure_id(students[COL_ID], "S")
    locals_[COL_ID] = ensure_id(locals_[COL_ID], "L")
    w = normalize_weights(weights)

    diag_rows, edges = [], []
    for _, s in students.iterrows():
        for _, l in locals_.iterrows():
            g1 = gender_compatible(s.get(COL_GENDER_PREF), l.get(COL_GENDER_ME), relax=relax_gender)
            g2 = gender_compatible(l.get(COL_GENDER_PREF), s.get(COL_GENDER_ME), relax=relax_gender)
            p = pets_compatible(s.get(COL_PETS), l.get(COL_PETS), relax=relax_pets)
            mm1 = must_match_ok(s, l, relax=relax_mustmatch)
            mm2 = must_match_ok(l, s, relax=relax_mustmatch)
            score, comp = pair_score(s, l, w)
            ok = g1 and g2 and p and mm1 and mm2
            row = {
                "student_id": s[COL_ID], "local_id": l[COL_ID], "mandatory_pass": ok, "score": score,
                "gender_ok_s_pref_vs_l": g1, "gender_ok_l_pref_vs_s": g2, "pets_ok": p,
                "mustmatch_ok_student_vs_local": mm1, "mustmatch_ok_local_vs_student": mm2,
                **{f"comp_{k}": v for k, v in comp.items()},
            }
            diag_rows.append(row)
            if ok and score > 0:
                edges.append({"s_id": s[COL_ID], "l_id": l[COL_ID], **row})
    return students, locals_, pd.DataFrame(diag_rows), pd.DataFrame(edges)


def print_stats(students, locals_, diag_df, sol=None):
    print(f"Students: {len(students)} | Locals: {len(locals_)} | Candidate pairs: {len(diag_df)}")
    if not diag_df.empty:
        for col in ["gender_ok_s_pref_vs_l", "gender_ok_l_pref_vs_s", "pets_ok", "mustmatch_ok_student_vs_local", "mustmatch_ok_local_vs_student", "mandatory_pass"]:
            passed = int(diag_df[col].sum())
            print(f"{col}: {passed}/{len(diag_df)}")
    if sol is not None:
        print(f"Matches selected: {len(sol)}")
        matched_s = set(sol["s_id"].tolist()) if not sol.empty else set()
        matched_l = set(sol["l_id"].tolist()) if not sol.empty else set()
        print(f"Unmatched students: {len([x for x in students[COL_ID] if x not in matched_s])}")
        print(f"Unmatched locals: {len([x for x in locals_[COL_ID] if x not in matched_l])}")
        if not sol.empty:
            print(f"Score min/avg/max: {sol['score'].min():.3f} / {sol['score'].mean():.3f} / {sol['score'].max():.3f}")


def solve_lexi(students, locals_, edges_df):
    if edges_df.empty:
        return pd.DataFrame()
    s_ids = students[COL_ID].tolist()
    l_ids = locals_[COL_ID].tolist()

    prob1 = pulp.LpProblem("MaxCardinality", pulp.LpMaximize)
    X1 = {(r.s_id, r.l_id): pulp.LpVariable(f"x1__{r.s_id}__{r.l_id}", cat="Binary") for r in edges_df.itertuples()}
    for s in s_ids:
        prob1 += pulp.lpSum(X1[(s, l)] for l in l_ids if (s, l) in X1) <= 1
    for l in l_ids:
        prob1 += pulp.lpSum(X1[(s, l)] for s in s_ids if (s, l) in X1) <= 1
    total1 = pulp.lpSum(X1.values())
    prob1 += total1
    prob1.solve(pulp.PULP_CBC_CMD(msg=False))
    best_count = int(round(total1.value() or 0))
    if best_count == 0:
        return pd.DataFrame()

    prob2 = pulp.LpProblem("ChebyshevWithinMaxCardinality", pulp.LpMaximize)
    X2 = {(r.s_id, r.l_id): pulp.LpVariable(f"x2__{r.s_id}__{r.l_id}", cat="Binary") for r in edges_df.itertuples()}
    t = pulp.LpVariable("t_min_score", lowBound=0.0, upBound=1.0)
    for s in s_ids:
        prob2 += pulp.lpSum(X2[(s, l)] for l in l_ids if (s, l) in X2) <= 1
    for l in l_ids:
        prob2 += pulp.lpSum(X2[(s, l)] for s in s_ids if (s, l) in X2) <= 1
    total2 = pulp.lpSum(X2.values())
    prob2 += total2 >= best_count
    score_lookup = {(r.s_id, r.l_id): float(r.score) for r in edges_df.itertuples()}
    for key, var in X2.items():
        prob2 += t <= score_lookup[key] + (1 - var)
    total_score = pulp.lpSum(score_lookup[key] * var for key, var in X2.items())
    prob2 += 1000.0 * t + 0.001 * total_score
    prob2.solve(pulp.PULP_CBC_CMD(msg=False))

    chosen = []
    for key, var in X2.items():
        if var.value() and var.value() > 0.5:
            row = edges_df[(edges_df.s_id == key[0]) & (edges_df.l_id == key[1])].iloc[0].to_dict()
            chosen.append(row)
    return pd.DataFrame(chosen)


def main():
    ap = argparse.ArgumentParser(description="ILP matching solver with Chebyshev scoring")
    ap.add_argument("--input", required=True, help="CSV or XLSX input file")
    ap.add_argument("--sheet", default="the refined data", help="Sheet name for Excel inputs")
    ap.add_argument("--output", default="matches.csv", help="Selected matches CSV")
    ap.add_argument("--diagnostics", default="diagnostics.csv", help="All pair diagnostics CSV")
    ap.add_argument("--weights", default=None, help="Override weights, e.g. hobbies=30,profile=28")
    ap.add_argument("--relax-gender", action="store_true")
    ap.add_argument("--relax-pets", action="store_true")
    ap.add_argument("--relax-mustmatch", action="store_true")
    args = ap.parse_args()

    weights = DEFAULT_WEIGHTS.copy()
    weights.update(parse_weights_arg(args.weights))
    df = load_data(Path(args.input), args.sheet)
    students, locals_, diag_df, edges_df = build_diagnostics_and_edges(
        df, weights, args.relax_gender, args.relax_pets, args.relax_mustmatch
    )
    diag_df.to_csv(args.diagnostics, index=False)
    print_stats(students, locals_, diag_df)
    sol = solve_lexi(students, locals_, edges_df)
    if not sol.empty:
        sol = sol[[
            "s_id", "l_id", "score", "comp_profile", "comp_hobbies", "comp_appreciate",
            "comp_languages", "comp_age", "comp_info", "comp_degree", "comp_field"
        ]]
    sol.to_csv(args.output, index=False)
    print_stats(students, locals_, diag_df, sol)
    print(f"Wrote {args.output} and {args.diagnostics}")


if __name__ == "__main__":
    main()
