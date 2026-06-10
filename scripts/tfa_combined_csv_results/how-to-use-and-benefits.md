# tfa_combined_csv_results - How to Use and Expected Benefits

`tfa_combined_csv_results` combines many TFA run summaries into one CSV file.
It is useful when you want to compare routes, check reproducibility, or study a
large parameter sweep without manually opening each run folder.

The script reads one file from each selected run folder:

```text
run_results_summary.json
```

It then creates:

```text
combined_results.csv
combined_results.schema_audit.json
```

The CSV is the main comparison table. The schema audit explains which columns
were present, missing, null, type-changed, or skipped.

---

## Why This Helps

Without this utility, a researcher may need to inspect many JSON files by hand,
copy fields into a spreadsheet, align columns manually, and decide what to do
when one run has fields that another run does not.

This script automates that work.

It uses a union-column approach:

- If a field appears in any run, it becomes a CSV column.
- If that field is missing from another run, the cell is filled with `NaN` or
  `N/A`.
- If future TFA versions add new fields, those fields become new columns.
- If old runs do not contain newer fields, the script still succeeds.

This makes the output suitable for spreadsheet review, statistical analysis,
and reproducibility checks.

---

## Basic Workflow

1. Choose the run folders you want to compare.
2. Create a JSON config or CSV manifest listing those folders.
3. Choose an output folder and CSV filename.
4. Run the combiner.
5. Open the CSV in Excel, LibreOffice, Python, R, or another analysis tool.

Example command:

```powershell
python tfa_combined_csv_results.py tfa_combined_csv_results_config.json
```

The script accepts exactly one input file:

```text
config.json
manifest.csv
```

It does not use long command-line option lists.

---

## Minimal JSON Config

```json
{
  "run_folders": [
    "E:/path/to/run_1",
    "E:/path/to/run_2",
    "E:/path/to/run_3"
  ],
  "output": {
    "folder": "E:/path/to/combined-output",
    "name": "combined_results.csv"
  }
}
```

Run:

```powershell
python tfa_combined_csv_results.py E:\path\to\tfa_combined_csv_results_config.json
```

Expected outputs:

```text
E:\path\to\combined-output\combined_results.csv
E:\path\to\combined-output\combined_results.schema_audit.json
```

---

## CSV Manifest Option

A CSV manifest is useful when the run list is long or maintained in a
spreadsheet.

Minimum manifest:

```csv
run_folder,output_folder,output_name
E:/path/to/run_1,E:/path/to/combined-output,combined_results.csv
E:/path/to/run_2,E:/path/to/combined-output,combined_results.csv
E:/path/to/run_3,E:/path/to/combined-output,combined_results.csv
```

Run:

```powershell
python tfa_combined_csv_results.py E:\path\to\tfa_combined_csv_results_manifest.csv
```

Each row contributes one run folder. The output folder and output filename must
be the same across all rows.

---

## Use Case 1: Compare Several Routes

When testing several candidate routes, the combiner creates one table where
each row is a run and each column is a discovered summary field.

This lets the researcher compare values such as:

```text
H0_X
band
BAO chi2
RSD chi2
sigma8_X
growth_ratio
z_eq_route
delta_z_eq
guard results
specialist statuses
```

Expected benefit:

- Faster route comparison.
- Less manual copy/paste.
- Fewer transcription mistakes.
- Easier sorting and filtering by physics outputs.
- One durable CSV artifact for later review.

In a blind test, three run folders were combined successfully into one CSV with
three rows, 154 columns, and no skipped summaries.

---

## Use Case 2: Reproducibility Check

To check reproducibility, run the same route twice and combine the two output
folders.

The CSV should show identical scientific result values. Some runtime fields are
expected to differ, such as:

```text
run_folder
summary_file
run.created_utc
run.run_folder
run.run_id
calls
```

These fields identify when and where each run happened. They are not scientific
result differences.

Expected benefit:

- Confirms that independent runs produce the same scientific outputs.
- Separates expected runtime metadata differences from result differences.
- Gives collaborators or reviewers a simple CSV artifact to inspect.

In a WLI_3 consistency test, two independent runs produced:

```text
Rows: 2
Columns: 152
Result-related columns checked: 133
Result-related differences: 0
```

This supports a reproducibility claim for that route.

---

## Use Case 3: Parameter Sweeps and Trajectory Fine-Tuning

For trajectory tuning, a researcher may run TFA many times while changing one
parameter at a time.

Example:

```text
run_001: alpha = 1.00
run_002: alpha = 1.05
run_003: alpha = 1.10
...
run_100: alpha = 2.00
```

After the runs finish, list the 100 run folders in a config or manifest and
create one combined CSV.

Expected benefit:

- Turns many independent runs into one parameter-sweep table.
- Helps identify which parameter direction improves the route.
- Makes outliers and failures easier to find.
- Keeps future diagnostic fields automatically.
- Makes follow-up plotting or statistical analysis much easier.

This is especially useful when fine-tuning a thawing trajectory against several
validators at once.

---

## Handling Old and New Runs Together

The script does not require every `run_results_summary.json` file to have the
same structure.

This matters because older runs may not contain newer diagnostic blocks, and
future runs may contain fields that do not exist today.

The combiner handles this by:

- Building columns from the union of all fields.
- Filling missing numeric values with `NaN`.
- Filling missing text or unknown values with `N/A`.
- Recording missing/null/type information in the schema audit.

The combine operation should not fail just because one run is older, newer, or
less complete than another.

---

## What the Schema Audit Tells You

The schema audit is a JSON sidecar file. It helps explain the CSV.

It reports:

- How many summaries were requested.
- How many valid summaries were combined.
- How many inputs were skipped.
- Which columns were present or missing in each row.
- Which fields were explicitly `null`.
- Which types were observed for each column.
- Whether any flattened column names needed collision-safe suffixes.

Use the audit when you need to understand why a CSV cell is `NaN` or `N/A`, or
when comparing runs from different TFA versions.

---

## Practical Notes

- Config, manifest, and summary inputs tolerate UTF-8 BOM files.
- Outputs are written as clean UTF-8.
- The script uses only the Python standard library.
- Arrays and complex values are written as compact JSON strings in CSV cells.
- Formula-like strings are preserved as data. Spreadsheet applications may
  interpret them if opened directly.
- Existing outputs are protected by default. Enable overwrite only when you are
  intentionally replacing previous combined files.

---

## Summary

`tfa_combined_csv_results` gives researchers one repeatable way to turn many TFA
run folders into one analysis-ready CSV.

The main benefits are:

1. Faster multi-route comparison.
2. Clearer reproducibility checks.
3. Practical parameter-sweep analysis for trajectory fine-tuning.
4. Better handling of old/new schema differences.
5. Fewer manual spreadsheet errors.

