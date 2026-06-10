# tfa_combined_csv_results

Approved version: `0.1.0-build.0001`

`tfa_combined_csv_results` combines many `run_results_summary.json` files into
one union CSV. It is schema-adaptive: every valid top-level JSON object is
flattened as data, and current TFA paths are examples only, not required fields.

For researcher-facing workflows and benefits, see
[`how-to-use-and-benefits.md`](how-to-use-and-benefits.md).

## Run

From the version folder:

```powershell
python tfa_combined_csv_results.py examples\tfa_combined_csv_results_config.example.json
python tfa_combined_csv_results.py examples\tfa_combined_csv_results_manifest.example.csv
```

The script accepts exactly one input file: `.json` config or `.csv` manifest.
It uses only the Python standard library.

## JSON Config

Minimum shape:

```json
{
  "run_folders": ["E:/path/to/run_1", "E:/path/to/run_2"],
  "output": {
    "folder": "E:/path/to/output",
    "name": "combined_results.csv"
  }
}
```

Supported options:

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

## CSV Manifest

Required headers:

```text
run_folder,output_folder,output_name
```

Optional headers match the JSON options above. Output fields must be identical
across all non-empty rows. Boolean cells accept `true`, `false`, `yes`, `no`,
`1`, or `0`.

## Flattening

Objects are flattened recursively. Literal dots in JSON keys are escaped as
`\.` and literal backslashes as `\\`. Empty keys become `_empty_key`. If two
distinct paths still collide, deterministic `__dupNN` suffixes are added and
recorded in the schema audit.

Arrays are serialized as compact JSON strings. Booleans are written as
`true`/`false`.

## Missing Values

Columns are inferred as numeric only when all present non-null values are
numbers, excluding booleans. Missing numeric values write the configured
`missing_numeric` string, default `NaN`. Missing text values and explicit JSON
nulls write the configured text placeholder, default `N/A`, unless the column
is numeric.

Missing fields, nulls, moved fields, new fields, removed fields, and type drift
do not stop the combine.

## Schema Audit

By default the script writes:

```text
<output_name_without_csv>.schema_audit.json
```

The audit reports input count, valid count, skipped folders, column count,
per-column `present_count`, `missing_count`, `null_count`, inferred `kind`,
observed types, and column-name collisions.

## BOM Safety

Config, manifest, and summary JSON inputs are read with `utf-8-sig`, so files
with a UTF-8 BOM are accepted. CSV and audit outputs are written as clean UTF-8
without a BOM.

## Exit Codes

| Code | Meaning |
|---:|---|
| `0` | Success |
| `1` | Valid config but no valid summaries, or error-stop input policy |
| `2` | Usage or config validation error |
| `3` | Output folder, overwrite, or write failure |
| `99` | Unexpected internal failure |

## Spreadsheet Note

Formula-like strings such as `=1+1`, `+SUM(A1:A2)`, or `@cmd` are preserved as
data. Some spreadsheet applications may interpret them when opening the CSV
directly.
