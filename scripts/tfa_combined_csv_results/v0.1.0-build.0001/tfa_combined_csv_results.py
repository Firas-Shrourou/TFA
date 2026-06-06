"""Combine arbitrary TFA run_results_summary.json files into one union CSV."""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


VERSION = "0.1.0-build.0001"
USAGE = "Usage: python tfa_combined_csv_results.py <config.json|manifest.csv>"

DEFAULTS = {
    "summary_filename": "run_results_summary.json",
    "missing_numeric": "NaN",
    "missing_text": "N/A",
    "path_style": "absolute",
    "include_source_metadata": True,
    "sort_columns": True,
    "array_mode": "json",
    "write_schema_audit": True,
    "overwrite": False,
    "on_missing_summary": "warn_skip",
    "on_invalid_json": "warn_skip",
}

REQUIRED_MANIFEST_HEADERS = {"run_folder", "output_folder", "output_name"}
OPTIONAL_KEYS = set(DEFAULTS)
CONFIG_KEYS = {"run_folders", "output"} | OPTIONAL_KEYS
OUTPUT_KEYS = {"folder", "name"}
BOOL_KEYS = {"include_source_metadata", "sort_columns", "write_schema_audit", "overwrite"}
METADATA_COLUMNS = ["run_folder", "summary_file", "summary_status"]


class UsageError(Exception):
    pass


class ConfigError(Exception):
    pass


class InputDataError(Exception):
    pass


class OutputWriteError(Exception):
    pass


def main(argv: list[str]) -> int:
    try:
        if len(argv) != 2:
            print_usage()
            return 2

        input_path = Path(argv[1])
        suffix = input_path.suffix.lower()
        if suffix not in {".json", ".csv"}:
            print_usage()
            return 2

        config = load_config(input_path)
        print(f"[INFO] Loaded config: {input_path}")
        print(f"[INFO] Run folders requested: {len(config['run_folders'])}")

        rows_with_paths, skipped = collect_rows(config)
        if not rows_with_paths:
            print("[ERROR] No valid run_results_summary.json files found.")
            return 1

        flattened_rows = [item["flattened"] for item in rows_with_paths]
        data_columns, name_info = make_column_names(flattened_rows)
        if config["sort_columns"]:
            data_columns = sorted(data_columns)
        path_to_column = name_info["path_to_column"]

        rows = []
        for item in rows_with_paths:
            row = {}
            if config["include_source_metadata"]:
                row.update(item["metadata"])
            for path_tuple, value in item["flattened"].items():
                row[path_to_column[path_tuple]] = normalize_cell_value(value)
            rows.append(row)

        columns = []
        if config["include_source_metadata"]:
            columns.extend(METADATA_COLUMNS)
        columns.extend(data_columns)

        column_kinds = infer_column_kinds(rows, columns)
        column_stats = collect_column_stats(
            rows,
            columns,
            column_kinds,
            {
                "input_summary_count": len(config["run_folders"]),
                "valid_summary_count": len(rows),
                "skipped": skipped,
                "column_name_collisions": name_info["column_name_collisions"],
            },
        )
        filled_rows = [fill_missing(row, columns, column_kinds, config) for row in rows]
        output_path, audit_path = write_outputs_atomic(filled_rows, columns, column_stats, config)
        emit_summary(len(filled_rows), skipped, output_path, audit_path)
        return 0
    except UsageError as exc:
        print(f"[ERROR] Config validation failed: {exc}")
        return 2
    except ConfigError as exc:
        print(f"[ERROR] Config validation failed: {exc}")
        return 2
    except InputDataError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except OutputWriteError as exc:
        print(f"[ERROR] Output write failed: {exc}")
        return 3
    except Exception as exc:
        print(f"[ERROR] Unexpected failure: {type(exc).__name__}: {exc}")
        return 99


def print_usage() -> None:
    print(USAGE)


def load_config(input_path: Path) -> dict[str, Any]:
    input_path = input_path.resolve()
    if not input_path.exists():
        raise ConfigError(f"input file does not exist: {input_path}")
    if input_path.suffix.lower() == ".json":
        return load_json_config(input_path)
    if input_path.suffix.lower() == ".csv":
        return load_csv_manifest(input_path)
    raise UsageError("unsupported config file suffix")


def load_json_config(input_path: Path) -> dict[str, Any]:
    try:
        with input_path.open("r", encoding="utf-8-sig") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON config: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config root must be a JSON object")
    return normalize_config(raw, input_path.parent)


def load_csv_manifest(input_path: Path) -> dict[str, Any]:
    try:
        with input_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                raise ConfigError("manifest has no header row")
            headers = {header.strip() for header in reader.fieldnames if header is not None}
            missing = sorted(REQUIRED_MANIFEST_HEADERS - headers)
            if missing:
                raise ConfigError(f"manifest missing required headers: {', '.join(missing)}")
            unsupported = sorted(headers - REQUIRED_MANIFEST_HEADERS - OPTIONAL_KEYS)
            if unsupported:
                raise ConfigError(f"unsupported manifest headers: {', '.join(unsupported)}")
            manifest_rows = []
            for row in reader:
                if any((value or "").strip() for value in row.values()):
                    manifest_rows.append(row)
    except UnicodeError as exc:
        raise ConfigError(f"could not read CSV manifest: {exc}") from exc

    if not manifest_rows:
        raise ConfigError("manifest has no non-empty data rows")

    run_folders = []
    output_folder = None
    output_name = None
    options: dict[str, Any] = {}

    for row_number, row in enumerate(manifest_rows, start=2):
        run_folder = (row.get("run_folder") or "").strip()
        if not run_folder:
            raise ConfigError(f"manifest row {row_number} has empty run_folder")
        run_folders.append(run_folder)

        row_output_folder = (row.get("output_folder") or "").strip()
        row_output_name = (row.get("output_name") or "").strip()
        if not row_output_folder or not row_output_name:
            raise ConfigError(f"manifest row {row_number} has empty output fields")
        if output_folder is None:
            output_folder = row_output_folder
        elif output_folder != row_output_folder:
            raise ConfigError("output_folder must be identical across all manifest rows")
        if output_name is None:
            output_name = row_output_name
        elif output_name != row_output_name:
            raise ConfigError("output_name must be identical across all manifest rows")

        for key in OPTIONAL_KEYS:
            value = (row.get(key) or "").strip()
            if value == "":
                continue
            parsed = parse_manifest_option(key, value)
            if key in options and options[key] != parsed:
                raise ConfigError(f"conflicting manifest option: {key}")
            options[key] = parsed

    raw = {
        "run_folders": run_folders,
        "output": {"folder": output_folder, "name": output_name},
        **options,
    }
    return normalize_config(raw, input_path.parent)


def parse_manifest_option(key: str, value: str) -> Any:
    if key in BOOL_KEYS:
        lowered = value.lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        raise ConfigError(f"manifest option {key} must be a boolean")
    return value


def normalize_config(raw: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    unsupported = sorted(set(raw) - CONFIG_KEYS)
    if unsupported:
        raise ConfigError(f"unsupported config options: {', '.join(unsupported)}")
    output = raw.get("output")
    if not isinstance(output, dict):
        raise ConfigError("output must be an object")
    unsupported_output = sorted(set(output) - OUTPUT_KEYS)
    if unsupported_output:
        raise ConfigError(f"unsupported output options: {', '.join(unsupported_output)}")

    config = dict(DEFAULTS)
    config["run_folders_raw"] = raw.get("run_folders")
    config["output_folder_raw"] = output.get("folder")
    config["output_name"] = output.get("name")
    for key in OPTIONAL_KEYS:
        if key in raw:
            config[key] = raw[key]

    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))

    run_folder_strings = config.pop("run_folders_raw")
    output_folder_string = config.pop("output_folder_raw")
    path_style = config["path_style"]

    run_folders = [resolve_user_path(item, base_dir) for item in run_folder_strings]
    config["run_folders"] = run_folders
    config["run_folder_labels"] = [
        make_path_label(original, resolved, base_dir, path_style)
        for original, resolved in zip(run_folder_strings, run_folders)
    ]
    config["output_folder"] = resolve_user_path(output_folder_string, base_dir)
    config["base_dir"] = base_dir
    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    errors = []
    run_folders = config.get("run_folders_raw")
    if not isinstance(run_folders, list) or not run_folders:
        errors.append("run_folders must be a non-empty list")
    elif not all(isinstance(item, str) and item for item in run_folders):
        errors.append("run_folders must contain only non-empty strings")

    output_folder = config.get("output_folder_raw")
    output_name = config.get("output_name")
    if not isinstance(output_folder, str) or not output_folder:
        errors.append("output.folder must be a non-empty string")
    if not isinstance(output_name, str) or not output_name:
        errors.append("output.name must be a non-empty string")
    elif Path(output_name).name != output_name or "/" in output_name or "\\" in output_name:
        errors.append("output.name must not contain path separators")
    elif not output_name.lower().endswith(".csv"):
        errors.append("output.name must end in .csv")

    summary_filename = config.get("summary_filename")
    if not isinstance(summary_filename, str) or not summary_filename:
        errors.append("summary_filename must be a non-empty filename")
    elif Path(summary_filename).name != summary_filename or "/" in summary_filename or "\\" in summary_filename:
        errors.append("summary_filename must not contain path separators")

    for key in ("missing_numeric", "missing_text"):
        if not isinstance(config.get(key), str):
            errors.append(f"{key} must be a string")
    if config.get("path_style") not in {"absolute", "relative_to_config", "as_provided"}:
        errors.append("path_style must be absolute, relative_to_config, or as_provided")
    if config.get("array_mode") != "json":
        errors.append("array_mode must be json for v0.1.0")
    for key in BOOL_KEYS:
        if not isinstance(config.get(key), bool):
            errors.append(f"{key} must be a boolean")
    if config.get("on_missing_summary") not in {"warn_skip", "error_stop"}:
        errors.append("on_missing_summary must be warn_skip or error_stop")
    if config.get("on_invalid_json") not in {"warn_skip", "error_stop"}:
        errors.append("on_invalid_json must be warn_skip or error_stop")
    return errors


def resolve_user_path(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def make_path_label(original: str, resolved: Path, base_dir: Path, path_style: str) -> str:
    if path_style == "as_provided":
        return original
    if path_style == "relative_to_config":
        try:
            return os.path.relpath(str(resolved), str(base_dir))
        except ValueError:
            return str(resolved)
    return str(resolved)


def collect_rows(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows = []
    skipped = []
    seen_duplicates = set()
    seen_run_folders = set()

    for run_folder, label in zip(config["run_folders"], config["run_folder_labels"]):
        run_key = str(run_folder)
        if run_key in seen_run_folders and run_key not in seen_duplicates:
            print(f"[WARN] Duplicate run folder requested: {run_folder}")
            seen_duplicates.add(run_key)
        seen_run_folders.add(run_key)

        summary_path = run_folder / config["summary_filename"]
        summary_label = make_summary_label(summary_path, config)
        if not run_folder.is_dir():
            message = f"not a directory: {run_folder}"
            print(f"[WARN] Not a directory, skipped: {run_folder}")
            skipped.append(make_skip(label, summary_label, "not_directory", message))
            continue
        if not summary_path.exists():
            action = apply_input_policy(
                config["on_missing_summary"],
                "missing_summary",
                summary_path,
                f"missing summary: {summary_path}",
            )
            if action == "error":
                raise InputDataError(f"Missing summary: {summary_path}")
            skipped.append(make_skip(label, summary_label, "missing_summary", f"missing summary: {summary_path}"))
            continue

        summary, error = read_summary(summary_path, config)
        if error is not None:
            action = apply_input_policy(config["on_invalid_json"], "invalid_json", summary_path, error)
            if action == "error":
                raise InputDataError(f"Invalid JSON: {summary_path} ({error})")
            skipped.append(make_skip(label, summary_label, "invalid_json", error))
            continue
        if not isinstance(summary, dict):
            message = f"top-level JSON is {json_type_name(summary)}, not object"
            print(f"[WARN] Invalid JSON, skipped: {summary_path} ({message})")
            skipped.append(make_skip(label, summary_label, "non_object_json", message))
            continue

        metadata = {
            "run_folder": label,
            "summary_file": summary_label,
            "summary_status": "ok",
        }
        rows.append({"metadata": metadata, "flattened": flatten_json(summary)})

    return rows, skipped


def make_summary_label(summary_path: Path, config: dict[str, Any]) -> str:
    if config["path_style"] == "relative_to_config":
        try:
            return os.path.relpath(str(summary_path), str(config["base_dir"]))
        except ValueError:
            return str(summary_path)
    return str(summary_path)


def make_skip(run_folder: str, summary_file: str, reason: str, message: str) -> dict[str, str]:
    return {
        "run_folder": run_folder,
        "summary_file": summary_file,
        "reason": reason,
        "message": message,
    }


def read_summary(summary_path: Path, config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with summary_path.open("r", encoding="utf-8-sig") as f:
            return json.load(f), None
    except json.JSONDecodeError as exc:
        return None, str(exc)
    except OSError as exc:
        return None, str(exc)


def apply_input_policy(policy: str, reason: str, path: Path, message: str) -> str:
    if reason == "missing_summary":
        if policy == "warn_skip":
            print(f"[WARN] Missing summary, skipped: {path}")
            return "skip"
        return "error"
    if reason == "invalid_json":
        if policy == "warn_skip":
            print(f"[WARN] Invalid JSON, skipped: {path} ({message})")
            return "skip"
        return "error"
    return "skip"


def encode_key_segment(segment: object) -> str:
    text = str(segment)
    if text == "":
        text = "_empty_key"
    return text.replace("\\", "\\\\").replace(".", "\\.")


def flatten_json(value: object, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], object]:
    if isinstance(value, dict):
        if not value:
            return {prefix: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}
        flattened = {}
        for key, child in value.items():
            flattened.update(flatten_json(child, prefix + (str(key),)))
        return flattened
    if isinstance(value, list):
        return {prefix: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}
    return {prefix: value}


def make_column_names(flattened_rows: list[dict[tuple[str, ...], object]]) -> tuple[list[str], dict[str, Any]]:
    ordered_paths = []
    seen_paths = set()
    for row in flattened_rows:
        for path_tuple in row:
            if path_tuple not in seen_paths:
                ordered_paths.append(path_tuple)
                seen_paths.add(path_tuple)

    raw_names: dict[tuple[str, ...], str] = {
        path_tuple: ".".join(encode_key_segment(segment) for segment in path_tuple) if path_tuple else "_root"
        for path_tuple in ordered_paths
    }
    name_counts: dict[str, int] = {}
    for raw_name in raw_names.values():
        name_counts[raw_name] = name_counts.get(raw_name, 0) + 1

    path_to_column = {}
    collisions = []
    per_name_index: dict[str, int] = {}
    for path_tuple in ordered_paths:
        raw_name = raw_names[path_tuple]
        if name_counts[raw_name] == 1:
            column = raw_name
        else:
            index = per_name_index.get(raw_name, 0)
            per_name_index[raw_name] = index + 1
            column = raw_name if index == 0 else f"{raw_name}__dup{index:02d}"
            collisions.append(
                {
                    "column": column,
                    "base_column": raw_name,
                    "path": list(path_tuple),
                }
            )
        path_to_column[path_tuple] = column

    columns = [path_to_column[path_tuple] for path_tuple in ordered_paths]
    return columns, {"path_to_column": path_to_column, "column_name_collisions": collisions}


def normalize_cell_value(value: object) -> str | int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def infer_column_kinds(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, str]:
    kinds = {}
    for column in columns:
        saw_numeric = False
        saw_text = False
        for row in rows:
            if column not in row or row[column] is None:
                continue
            value = row[column]
            if isinstance(value, bool):
                saw_text = True
            elif isinstance(value, (int, float)):
                saw_numeric = True
            else:
                saw_text = True
        kinds[column] = "numeric" if saw_numeric and not saw_text else "text"
    return kinds


def collect_column_stats(
    rows: list[dict[str, Any]],
    columns: list[str],
    column_kinds: dict[str, str],
    context: dict[str, Any],
) -> dict[str, Any]:
    column_stats = {}
    for column in columns:
        present_count = 0
        missing_count = 0
        null_count = 0
        observed_types = set()
        for row in rows:
            if column in row:
                present_count += 1
                value = row[column]
                observed_types.add(json_type_name(value))
                if value is None:
                    null_count += 1
            else:
                missing_count += 1
        column_stats[column] = {
            "present_count": present_count,
            "missing_count": missing_count,
            "null_count": null_count,
            "kind": column_kinds[column],
            "observed_types": sorted(observed_types),
        }

    return {
        "input_summary_count": context["input_summary_count"],
        "valid_summary_count": context["valid_summary_count"],
        "skipped_count": len(context["skipped"]),
        "column_count": len(columns),
        "columns": column_stats,
        "column_name_collisions": context["column_name_collisions"],
        "skipped": context["skipped"],
    }


def json_type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def fill_missing(row: dict[str, Any], columns: list[str], column_kinds: dict[str, str], config: dict[str, Any]) -> dict[str, Any]:
    filled = {}
    for column in columns:
        value = row.get(column)
        if value is None:
            filled[column] = config["missing_numeric"] if column_kinds[column] == "numeric" else config["missing_text"]
        else:
            filled[column] = value
    return filled


def write_combined_csv(rows: list[dict[str, Any]], columns: list[str], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_schema_audit(column_stats: dict[str, Any], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(column_stats, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def write_outputs_atomic(
    rows: list[dict[str, Any]],
    columns: list[str],
    column_stats: dict[str, Any],
    config: dict[str, Any],
) -> tuple[Path, Path | None]:
    output_folder = config["output_folder"]
    output_name = config["output_name"]
    try:
        output_folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputWriteError(f"could not create output folder {output_folder}: {exc}") from exc

    output_path = (output_folder / output_name).resolve()
    audit_path = output_path.with_suffix(".schema_audit.json") if config["write_schema_audit"] else None
    planned_paths = [output_path] + ([audit_path] if audit_path is not None else [])

    for path in planned_paths:
        if path.is_dir():
            raise OutputWriteError(f"planned output path is a directory: {path}")
        if path.exists() and not config["overwrite"]:
            raise OutputWriteError(f"output exists and overwrite=false: {path}")

    temp_paths: list[Path] = []
    try:
        csv_temp = make_temp_path(output_folder, ".csv")
        temp_paths.append(csv_temp)
        write_combined_csv(rows, columns, csv_temp)
        audit_temp = None
        if audit_path is not None:
            audit_temp = make_temp_path(output_folder, ".json")
            temp_paths.append(audit_temp)
            write_schema_audit(column_stats, audit_temp)
        os.replace(csv_temp, output_path)
        temp_paths.remove(csv_temp)
        if audit_path is not None and audit_temp is not None:
            os.replace(audit_temp, audit_path)
            temp_paths.remove(audit_temp)
    except OSError as exc:
        for temp_path in list(temp_paths):
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
        raise OutputWriteError(str(exc)) from exc

    return output_path, audit_path


def make_temp_path(output_folder: Path, suffix: str) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=output_folder,
        prefix=".tfa_combined_csv_results.",
        suffix=f".tmp{suffix}",
        delete=False,
    )
    temp_name = handle.name
    handle.close()
    return Path(temp_name)


def emit_summary(valid_count: int, skipped: list[dict[str, str]], output_path: Path, audit_path: Path | None) -> None:
    print(f"[OK] Combined {valid_count} summaries into {output_path}")
    if output_path.exists():
        with output_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, [])
        print(f"[OK] Columns written: {len(header)}")
    if audit_path is not None:
        print(f"[OK] Schema audit written: {audit_path}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
