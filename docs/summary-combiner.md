# Summary Combiner Utility

`tfa_combined_csv_results` combines many TFA `run_results_summary.json` files
into one analysis-ready CSV. It is useful for comparing routes, checking
reproducibility, and reviewing parameter sweeps without manually opening each
run folder.

The utility uses only the Python standard library.

## Location

Current approved build:

```text
scripts/tfa_combined_csv_results/v0.1.0-build.0001/
```

Example command from that folder:

```powershell
python tfa_combined_csv_results.py examples\tfa_combined_csv_results_config.example.json
```

The script accepts exactly one input file:

```text
config.json
manifest.csv
```

It does not use long command-line option lists.

## Outputs

The standard output pair is:

```text
combined_results.csv
combined_results.schema_audit.json
```

The CSV is the main comparison table. The schema audit explains which columns
were present, missing, explicitly null, type-changed, or skipped.

## Minimal JSON config

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

Supported options include:

```json
{
  "summary_filename": "run_results_summary.json",
  "missing_numeric": "NaN",
  "missing_text": "N/A",
  "path_style": "absolute",
  "include_source_metadata": true,
  "sort_columns": true,
  "array_mode": "json",
  "write_schema_audit": true,
  "overwrite": false,
  "on_missing_summary": "warn_skip",
  "on_invalid_json": "warn_skip"
}
```

`path_style` can be `absolute`, `relative_to_config`, or `as_provided`.
`array_mode` is `json` in this release.

## CSV manifest

A CSV manifest is useful when the run list is long or maintained in a
spreadsheet.

Required headers:

```text
run_folder,output_folder,output_name
```

Example:

```csv
run_folder,output_folder,output_name
E:/path/to/run_1,E:/path/to/combined-output,combined_results.csv
E:/path/to/run_2,E:/path/to/combined-output,combined_results.csv
E:/path/to/run_3,E:/path/to/combined-output,combined_results.csv
```

Optional headers match the JSON options above. Output fields must be identical
across all non-empty rows. Boolean cells accept `true`, `false`, `yes`, `no`,
`1`, or `0`.

## Flattening and missing values

Each valid top-level JSON object is flattened recursively. If a field appears in
any run, it becomes a CSV column. If that field is absent from another run, the
cell is filled with the configured missing-value placeholder.

Rules:

- Literal dots in JSON keys are escaped as `\.`.
- Literal backslashes are escaped as `\\`.
- Empty keys become `_empty_key`.
- If distinct paths still collide, deterministic `__dupNN` suffixes are added.
- Arrays are serialized as compact JSON strings.
- Booleans are written as `true` or `false`.

Columns are inferred as numeric only when all present non-null values are
numbers, excluding booleans. Missing numeric values write `NaN` by default.
Missing text values and explicit JSON nulls write `N/A` by default unless the
column is numeric.

Old and new runs can be combined together. Missing fields, nulls, moved fields,
new fields, removed fields, and type drift do not stop the combine operation.

## Schema audit

By default, the utility writes:

```text
<output_name_without_csv>.schema_audit.json
```

The audit reports input count, valid count, skipped folders, column count,
per-column presence, missing count, null count, inferred kind, observed types,
and column-name collisions.

Use the audit when you need to explain why a CSV cell is `NaN` or `N/A`, or
when comparing runs from different TFA versions.

## Typical uses

Use the combiner to:

- Compare several candidate routes in one table.
- Confirm that repeated runs produce the same scientific outputs.
- Review parameter sweeps or trajectory fine-tuning runs.
- Preserve newer diagnostic fields without breaking older run comparisons.
- Reduce manual spreadsheet copy/paste errors.

Runtime metadata such as run folder, run ID, and creation time is expected to
differ between repeated runs. Scientific result fields should match when the
same route and settings are rerun.

## Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success |
| `1` | Valid config but no valid summaries, or error-stop input policy |
| `2` | Usage or config validation error |
| `3` | Output folder, overwrite, or write failure |
| `99` | Unexpected internal failure |

## Notes

Config, manifest, and summary JSON inputs are read with UTF-8 BOM tolerance.
CSV and audit outputs are written as clean UTF-8 without a BOM.

Formula-like strings such as `=1+1`, `+SUM(A1:A2)`, or `@cmd` are preserved as
data. Some spreadsheet applications may interpret them when opening the CSV
directly.
