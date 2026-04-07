# Matching Solver Example

This package contains a small Python program for one-to-one matching between **students** and **locals** using an **integer linear programming** model.

## Files
- `match_solver.py` – solver
- `example_data.csv` – small demo dataset
- `README.md` – usage notes

## Model idea
The solver:
1. reads a CSV or XLSX file,
2. splits rows into students and locals,
3. filters infeasible pairs using hard constraints,
4. scores feasible pairs with weighted similarities,
5. solves an ILP that
   - maximizes the number of matches,
   - then maximizes the minimum selected score (Chebyshev style),
   - then uses total score as a tiny tie-break.

## Hard constraints
A pair must satisfy:
- gender compatibility in both directions,
- pets/allergy compatibility,
- at least one must-match criterion from each side.

You can relax them for debugging:
- `--relax-gender`
- `--relax-pets`
- `--relax-mustmatch`

## Weights
Default weights are:
- profile 34
- hobbies 23
- appreciate 10
- languages 9
- age 9
- info 7
- degree 5
- field 3

Override them, for example:
```bash
python match_solver.py --input example_data.csv --weights hobbies=30,profile=28
```

## Install
```bash
pip install pandas openpyxl pulp
```

## Run
```bash
python match_solver.py --input example_data.csv --output matches.csv --diagnostics diagnostics.csv
```

## Input format
The example CSV shows the expected columns. Important ones are:
- `Identification`
- `My status`
- `My profile`
- `My hobbies and interests`
- `Hobbies and interests I/we appreciate`
- `My gender identity`
- `Friend's gender identity`
- `My native languages`
- `Languages, I can use in daily life`
- `My age`
- `Friend's age`
- `Pet allergies and preferences`
- `Things I appreciate in a friend (a student or a local).`
- `Additional information that can assist us in matching me with a student/local friend.`
- `My degree and program at JYU`
- `Field of Science`
- must-match columns 1 and 2 with specs

## Output files
### `matches.csv`
Selected pairs with columns such as:
- `s_id`, `l_id`, `score`
- component scores: `comp_profile`, `comp_hobbies`, `comp_appreciate`, `comp_languages`, `comp_age`, `comp_info`, `comp_degree`, `comp_field`

### `diagnostics.csv`
All student-local candidate pairs, including:
- whether the pair passed hard constraints,
- which mandatory checks passed,
- the weighted score and component scores.

## Read the results
- Higher `score` means a better overall weighted match.
- `diagnostics.csv` is useful if no matches are found or too many people remain unmatched.
- Compare `mandatory_pass` and the individual boolean columns to see which hard constraint blocks candidate pairs.

## Example expected behavior
With the provided example data, the script should find several feasible pairs and print counts for:
- students,
- locals,
- candidate pairs,
- selected matches,
- unmatched students and locals,
- score min / average / max.
