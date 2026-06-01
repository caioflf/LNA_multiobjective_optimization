from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.scripts.circuit_database import (
    DEFAULT_CIRCUIT_DATABASE_PATH,
    initialize_database,
    netlist_context_from_config,
    upsert_history_record,
)


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def resolve_history_source(source):
    source = Path(source)
    if source.is_dir():
        run_root = source
        history_path = run_root / "optimization_history.jsonl"
        config_path = run_root / "optimization_config.json"
    else:
        history_path = source
        run_root = history_path.parent
        config_path = run_root / "optimization_config.json"

    if not history_path.exists():
        raise FileNotFoundError(f"Missing optimization history: {history_path}")

    return {
        "run_root": run_root,
        "history_path": history_path,
        "config_path": config_path,
        "config": load_json(config_path),
    }


def iter_history(path):
    with Path(path).open() as fp:
        for line_number, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError as exc:
                yield line_number, {
                    "_parse_error": str(exc),
                    "_raw_line": line[:240],
                }


def build_database(sources, output_path, *, overwrite=False, skip_missing=False):
    output_path = Path(output_path)
    mode = "append"
    if output_path.exists() and overwrite:
        output_path.unlink()
        mode = "rebuild"
    elif not output_path.exists():
        mode = "create"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    started_at = time.time()
    stats = {
        "mode": mode,
        "sources": [],
        "records": 0,
        "imported": 0,
        "already_imported": 0,
        "skipped": 0,
        "skipped_missing_source": 0,
        "skipped_no_candidate": 0,
        "skipped_no_metrics": 0,
        "parse_errors": 0,
        "new_unique_circuits": 0,
        "new_source_records": 0,
    }

    conn = sqlite3.connect(output_path)
    conn.row_factory = sqlite3.Row
    try:
        initialize_database(conn)
        start_unique = conn.execute(
            "SELECT COUNT(*) FROM circuits"
        ).fetchone()[0]
        start_sources = conn.execute(
            "SELECT COUNT(*) FROM circuit_sources"
        ).fetchone()[0]
        for source in sources:
            try:
                resolved = resolve_history_source(source)
            except FileNotFoundError:
                if not skip_missing:
                    raise
                stats["skipped_missing_source"] += 1
                stats["sources"].append(
                    {
                        "source": str(source),
                        "skipped": True,
                        "reason": "missing_history",
                    }
                )
                continue
            run_root = resolved["run_root"]
            history_path = resolved["history_path"]
            netlist_context = netlist_context_from_config(resolved["config"])
            before_unique = conn.execute(
                "SELECT COUNT(*) FROM circuits"
            ).fetchone()[0]
            source_stats = {
                "run_root": str(run_root),
                "history_path": str(history_path),
                "records": 0,
                "imported": 0,
                "already_imported": 0,
                "skipped": 0,
                "skipped_no_candidate": 0,
                "skipped_no_metrics": 0,
                "parse_errors": 0,
                "netlist_context": netlist_context,
            }

            with conn:
                for line_number, record in iter_history(history_path):
                    stats["records"] += 1
                    source_stats["records"] += 1
                    if "_parse_error" in record:
                        stats["parse_errors"] += 1
                        source_stats["parse_errors"] += 1
                        continue

                    if not isinstance(record.get("candidate"), dict):
                        stats["skipped"] += 1
                        stats["skipped_no_candidate"] += 1
                        source_stats["skipped"] += 1
                        source_stats["skipped_no_candidate"] += 1
                        continue
                    if not record.get("metrics"):
                        stats["skipped"] += 1
                        stats["skipped_no_metrics"] += 1
                        source_stats["skipped"] += 1
                        source_stats["skipped_no_metrics"] += 1
                        continue

                    result = upsert_history_record(
                        conn,
                        record,
                        netlist_context=netlist_context,
                        source_run=str(run_root),
                        source_history=str(history_path),
                        source_line=line_number,
                    )
                    if result is None:
                        stats["skipped"] += 1
                        source_stats["skipped"] += 1
                    elif result["already_imported"]:
                        stats["already_imported"] += 1
                        source_stats["already_imported"] += 1
                    else:
                        stats["imported"] += 1
                        source_stats["imported"] += 1

            after_unique = conn.execute(
                "SELECT COUNT(*) FROM circuits"
            ).fetchone()[0]
            source_stats["new_unique_circuits"] = after_unique - before_unique
            stats["sources"].append(source_stats)

        unique_circuits = conn.execute(
            "SELECT COUNT(*) FROM circuits"
        ).fetchone()[0]
        source_rows = conn.execute(
            "SELECT COUNT(*) FROM circuit_sources"
        ).fetchone()[0]
        duplicate_records = max(0, source_rows - unique_circuits)
        stats["unique_circuits"] = unique_circuits
        stats["source_rows"] = source_rows
        stats["duplicate_records"] = duplicate_records
        stats["new_unique_circuits"] = unique_circuits - start_unique
        stats["new_source_records"] = source_rows - start_sources
        stats["elapsed_seconds"] = time.time() - started_at

        conn.execute(
            """
            INSERT OR REPLACE INTO metadata(key, value)
            VALUES('build_summary', ?)
            """,
            (
                json.dumps(
                    stats,
                    sort_keys=True,
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build a simulated-circuit database from optimizer "
            "optimization_history.jsonl files."
        )
    )
    parser.add_argument(
        "sources",
        nargs="+",
        help="Run directories or optimization_history.jsonl files.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_CIRCUIT_DATABASE_PATH),
        help="SQLite database path to write.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output database.",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip sources whose optimization_history.jsonl is missing.",
    )
    args = parser.parse_args()

    stats = build_database(
        args.sources,
        args.output,
        overwrite=args.overwrite,
        skip_missing=args.skip_missing,
    )
    print(f"[build_circuit_database] output: {args.output}", flush=True)
    print(f"[build_circuit_database] mode: {stats['mode']}", flush=True)
    print(
        "[build_circuit_database] records: "
        f"{stats['records']:,} read, "
        f"{stats['imported']:,} new source record(s), "
        f"{stats['already_imported']:,} already imported, "
        f"{stats['unique_circuits']:,} unique circuits, "
        f"{stats['duplicate_records']:,} duplicate source records",
        flush=True,
    )
    print(
        "[build_circuit_database] appended: "
        f"{stats['new_unique_circuits']:,} new unique circuit(s), "
        f"{stats['new_source_records']:,} new source record(s)",
        flush=True,
    )
    if stats["skipped"]:
        print(
            "[build_circuit_database] skipped: "
            f"{stats['skipped']:,} "
            f"(no candidate={stats['skipped_no_candidate']:,}, "
            f"no metrics={stats['skipped_no_metrics']:,})",
            flush=True,
        )
    if stats["skipped_missing_source"]:
        print(
            "[build_circuit_database] missing sources skipped: "
            f"{stats['skipped_missing_source']:,}",
            flush=True,
        )
    if stats["parse_errors"]:
        print(
            "[build_circuit_database] parse errors: "
            f"{stats['parse_errors']:,}",
            flush=True,
        )
    print(
        "[build_circuit_database] elapsed: "
        f"{stats['elapsed_seconds']:.3f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
