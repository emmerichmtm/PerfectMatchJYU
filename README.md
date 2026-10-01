# PerfectMatch JYU

Suggest one-to-one matches between students and local participants using **two CSV inputs**. Each successful run produces **one result CSV and one brief text report**.

## For programme staff

Start with the [A4 staff manual (PDF)](manual.pdf). Its [standalone LaTeX source](manual.tex) is included.

1. Get **PerfectMatchJYU-Windows.zip** from [Releases](https://github.com/emmerichmtm/PerfectMatchJYU/releases), or from your IT colleague, and choose **Extract All**.
2. Open the extracted `PerfectMatch` folder and double-click **PerfectMatch.exe**. Keep the `_internal` folder beside it. **Python and the solver are included; no installation is needed.**
3. Your browser opens at **http://localhost:8765** (or another available local port). Click **Try the included example**, then **Find matches**.
4. For real data, download the two templates, edit them in Excel, and save as **CSV UTF-8**. Replace the fictional participants with your programme's records.
5. Choose the settings CSV and participant CSV on the page, then click **Find matches**.
6. Review the pairs and report, then click **Download result.csv** and **Download report.txt**. Use **Close app** when finished.

The ready-to-run package targets **64-bit Windows**. GitHub's **Code / Download ZIP** is the source code, not this package. The executable is unsigned; if your organisation blocks it, ask IT to review it.

“Localhost” means your own computer. No account, Caddy server or internet connection is needed for matching. The app binds only to the loopback interface; participant data is processed in a temporary local folder and removed after the run. It is not uploaded to GitHub or any external service. The browser accepts up to 4 MB per CSV. Downloads usually go to your browser's Downloads folder. Save both outputs before reloading or closing the page, and keep both input files with them in a dated folder. Closing the tab alone does not stop the app: use **Close app**.

If you already have the source installation, double-click **start_browser.bat**. First-time source users run `setup_windows.bat` once with Python 3.12 and internet access. Opening `browser.html` directly is not sufficient: the local app must be running to calculate matches.

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

The existing `run_matching.bat` still supports that workflow. It overwrites the two outputs on success; a failure may leave earlier files in place. Check SUCCESS and the report timestamp.

### Local browser from source

After installing the dependencies:

```bash
.venv\Scripts\python browser_app.py
# macOS/Linux: .venv/bin/python browser_app.py
```

The page opens automatically. Use `--no-browser` to suppress opening it, or `--port 9000` to select a port. Port 8765 is the default, with an available-port fallback if occupied. The server accepts only loopback Host values and requires an Origin check and a random session token for matching and shutdown. It serves only its page, manual and templates. No extra web-framework dependency is required.

The CLI and browser call the same CSV validation and matching functions. Browser submissions are decoded as UTF-8 and re-encoded for the solver; report hashes describe those processed files and can differ from the original file's byte hash when a BOM is removed. Results in the page are cleared when an input changes or a run fails.

### Build the ready-to-run Windows ZIP

On 64-bit Windows with the source environment installed:

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
.\build_windows.ps1
```

This creates `dist/PerfectMatchJYU-Windows.zip`. The package includes the Python runtime, required libraries, CBC executable, templates, manual and dependency notices. `PerfectMatch.spec` controls the build; `build_windows.ps1` prepares the ZIP. Build on Windows, not by cross-compiling. The ready-to-run executable is unsigned.

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
