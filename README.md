# PerfectMatch JYU

Suggest one-to-one matches between students and local participants using **two CSV inputs**. Each successful run produces **one result CSV and one brief text report**.

## For programme staff

Start with the [A4 staff manual (PDF)](manual.pdf). Its [standalone LaTeX source](manual.tex) is included.

1. Download this repository as a ZIP and extract it.
2. On Windows, double-click `setup_windows.bat` once. Internet access and Python 3.12 are needed for setup; ask IT to install Python if it cannot be found.
3. Edit `input/config.csv` and `input/problem.csv` in Excel. Setup creates these from fictional examples and preserves existing input files.
4. Save as **CSV UTF-8** and close the files.
5. Double-click `run_matching.bat` and wait for **SUCCESS**.
6. Read `output/report.txt`, then review the pairs in `output/result.csv`.

No Python editing or command-line use is needed for routine Windows runs after setup. Runs are local. Each successful run overwrites the previous two outputs; copy the inputs and outputs to a dated folder to preserve a scenario. A failed run can leave earlier outputs in place: check SUCCESS and the report timestamp.

## CSV inputs

### Settings: config.csv

The [settings template](examples/config.csv) has `setting,value,description` columns. Keep every setting row. All eight `weight_*` values must be finite and non-negative, and at least one must be positive. They are normalized automatically; they do not need to sum to 100.

| Setting | Default | Effect |
| --- | ---: | --- |
| `weight_profile` | 34 | Shared profile tags |
| `weight_hobbies` | 23 | Hobbies versus the other person's preferred hobbies |
| `weight_appreciate` | 10 | Shared qualities appreciated in a friend |
| `weight_languages` | 9 | Shared native and daily-use language tags |
| `weight_age` | 9 | Age similarity and age preferences |
| `weight_info` | 7 | Shared information tags |
| `weight_degree` | 5 | Shared degree categories |
| `weight_field` | 3 | Shared fields of science |
| `enforce_gender` | TRUE | Respect both gender preferences |
| `enforce_pets` | TRUE | Reject `has pets` paired with `avoid pets` |
| `enforce_must_match` | TRUE | Require at least one supplied criterion from each person |
| `minimum_score` | 0 | Exclude pairs below this score, between 0 and 1 |
| `solver_time_limit_seconds` | 60 | Time limit per solving stage, between 1 and 86400 |

Use TRUE/FALSE for switches. Decimal points and decimal commas are accepted in numeric setting cells. Do not use percentage signs or thousands separators. Unknown, duplicate and missing settings are rejected.

### Participants: problem.csv

The [participant template](examples/problem.csv) has one person per row, with these headings:

```text
id,side,profile,hobbies,preferred_hobbies,gender,preferred_gender,native_languages,languages,age,preferred_age,pets,appreciate,information,degree,field,must_match_1,must_match_1_values,must_match_2,must_match_2_values
```

Keep all columns. `id` and `side` are required in every row. IDs are unique across both sides, start with a letter or digit, and contain only ASCII letters, digits, `_`, `-` or `.`. `side` is `student` or `local`. IDs are read as text, preserving leading zeroes if Excel has not already removed them.

- Separate tags inside a cell with semicolons. Comparison ignores case but does not translate or interpret prose. Blank scoring fields generally receive no similarity credit; missing ages start with an age component of 0.5.
- `age` is a whole number 1-120 or blank. `preferred_age` is a range such as `22-35`, `no preference`, or blank. Age affects scoring, not eligibility.
- A blank `preferred_gender` or `no preference` allows any gender. An unknown gender cannot satisfy a specific preference.
- `pets` is `none`, `has pets`, `avoid pets`, or `unknown`; blank means unknown. Unknown pets do not block a pair and generate a report note. Complex or animal-specific situations need staff review.
- Must-match criterion names are `profile`, `hobbies`, `gender`, `languages`, `degree`, and `field`. Fill in a criterion and its accepted values together, or leave both blank. With two criteria, **at least one must pass**, separately for each person. `languages` checks the partner's daily-use `languages` column.

Comma-, semicolon- and tab-separated UTF-8 CSVs are supported, with or without a BOM. Let the spreadsheet application quote cells containing separators. Invalid row lengths, headings and values produce an actionable error rather than a guessed interpretation.

## Outputs and matching priorities

`result.csv` contains `student_id`, `local_id`, `score` and eight unweighted component columns ending in `_score`. There is one row per selected pair; if no match is possible, the CSV contains headings only. Scores are similarities from 0 to 1, not probabilities.

`report.txt` records counts, unmatched IDs and reasons, score statistics, effective settings, disabled checks, input hashes and review notes. Pair rejection counts can overlap. No diagnostics CSV is generated by this interface.

The solver performs three successive optimizations:

1. Maximize the number of eligible pairs, with each person in at most one pair.
2. For that number of pairs, maximize the lowest selected score.
3. Among pairs meeting that minimum (numerical tolerance `1e-7`), maximize total score.

Every stage must finish optimally; a timeout is an error. Zero-score pairs are eligible when `minimum_score=0`. Unknown participant sides are rejected; participants are never silently moved between sides.

With the included CSVs, the result is S01-L01 (0.724), S02-L02 (0.662), and S03-L03 (0.794), rounded; L04 remains unmatched. There are 12 candidate pairs and 8 eligible pairs. Programme staff should review all suggestions before confirming them.

## Technical setup

Tested on Windows with Python 3.12. Setup uses a project-local `.venv`; PuLP is pinned to 3.3.0 because the solver uses its 3.x API and bundled CBC solver. Working inputs and outputs are ignored by Git.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run_matching.py --config examples/config.csv --problem examples/problem.csv --result output/result.csv --report output/report.txt
# macOS/Linux: use .venv/bin/python instead.
```

Without arguments, `run_matching.py` uses `input/config.csv`, `input/problem.csv`, `output/result.csv`, and `output/report.txt`, relative to the current working directory. The Windows launcher selects the project directory automatically. The two inputs and two outputs must be distinct paths.

Tests:

```bash
python -m unittest discover -s tests -v
```

Compile the self-contained A4 manual with `pdflatex manual.tex` twice or `tectonic manual.tex`. It uses standard LaTeX packages and no external images.

## Original interface

The original survey headings in `example_data.csv` still work with:

```bash
python match_solver.py --input example_data.csv --output matches.csv --diagnostics diagnostics.csv
```

That legacy interface retains optional XLSX input and per-pair diagnostics. Use `run_matching.py` and the two files under `examples/` for the colleague-facing CSV workflow. The malformed language heading in the original example has been corrected.
