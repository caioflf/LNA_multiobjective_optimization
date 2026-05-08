#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from optimization_data import (
    apply_constraints,
    flatten_record,
    metric_stats,
    non_dominated_front,
    objective_specs_from_config,
    read_run,
    ranked_records,
    shortlist_records,
    status_counts,
    top_ranked_records,
    valid_records,
    write_csv,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Summarize an optimization run and optionally export CSV/JSON reports."
    )
    parser.add_argument("run_root", nargs="?", default="optimized_circuits")
    parser.add_argument(
        "--output-dir",
        help="Optional directory for CSV/JSON outputs. If omitted, only prints a summary.",
    )
    parser.add_argument("--max-nf-db", type=float)
    parser.add_argument("--max-power", type=float)
    parser.add_argument("--min-gain-db", type=float)
    parser.add_argument("--min-f-bw", type=float)
    parser.add_argument(
        "--max-s11-db",
        type=float,
        help="Require S11_db <= this value, e.g. -10 for better than -10 dB.",
    )
    parser.add_argument(
        "--top-count",
        type=int,
        default=200,
        help="Number of ranked candidates to export.",
    )
    return parser.parse_args()


def build_constraints(args):
    return {
        "max_nf_db": args.max_nf_db,
        "max_power": args.max_power,
        "min_gain_db": args.min_gain_db,
        "min_f_bw": args.min_f_bw,
        "max_s11_db": args.max_s11_db,
    }


def print_metric_stats(title, stats):
    print(title)
    for metric_name, values in stats.items():
        if values["count"] == 0:
            print(f"  {metric_name}: no finite values")
            continue
        print(
            f"  {metric_name}: count={values['count']} "
            f"min={values['min']:.6g} median={values['median']:.6g} "
            f"max={values['max']:.6g}"
        )


def compact_shortlist(shortlist):
    compact = []
    for item in shortlist:
        row = flatten_record(item["record"], tag=item["label"])
        compact.append(row)
    return compact


def compact_ranked(ranked):
    compact = []
    for rank, (score, record) in enumerate(ranked, start=1):
        compact.append(flatten_record(record, rank=rank, score=score))
    return compact


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def export_ranked_csv(path, ranked):
    rows = compact_ranked(ranked)
    if not rows:
        Path(path).write_text("")
        return
    import csv

    with Path(path).open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_outputs(
    output_dir,
    records,
    valid,
    filtered,
    pareto,
    filtered_pareto,
    shortlist,
    top_ranked,
    report,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "evaluations.csv", records)
    write_csv(output_dir / "valid_evaluations.csv", valid)
    write_csv(output_dir / "filtered_valid_evaluations.csv", filtered)
    write_csv(output_dir / "pareto_front.csv", pareto, tag="pareto")
    write_csv(output_dir / "filtered_pareto_front.csv", filtered_pareto, tag="filtered_pareto")
    write_csv(
        output_dir / "shortlist.csv",
        [item["record"] for item in shortlist],
    )
    export_ranked_csv(output_dir / "ranked_candidates.csv", top_ranked)
    write_json(output_dir / "shortlist.json", compact_shortlist(shortlist))
    write_json(output_dir / "ranked_candidates.json", compact_ranked(top_ranked))
    write_json(output_dir / "report.json", report)


def main():
    args = parse_args()
    constraints = build_constraints(args)
    run = read_run(args.run_root)
    records = run["records"]
    valid = valid_records(records)
    filtered = apply_constraints(valid, constraints)
    objectives = objective_specs_from_config(run["config"])
    pareto = non_dominated_front(valid, objectives)
    filtered_pareto = apply_constraints(pareto, constraints)
    shortlist_pool = filtered_pareto or filtered or pareto or valid
    shortlist = shortlist_records(shortlist_pool, objectives)
    top_ranked = top_ranked_records(shortlist_pool, objectives, args.top_count)

    counts = status_counts(records)
    report = {
        "run_root": str(run["run_root"]),
        "algorithm": run["config"].get("algorithm"),
        "planned_simulations": run["config"].get("planned_simulations"),
        "total_records": len(records),
        "valid_records": len(valid),
        "filtered_valid_records": len(filtered),
        "pareto_records": len(pareto),
        "filtered_pareto_records": len(filtered_pareto),
        "status_counts": counts,
        "skipped_history_lines": run["skipped_history_lines"],
        "constraints": constraints,
        "valid_metric_stats": metric_stats(valid),
        "filtered_metric_stats": metric_stats(filtered),
        "failure_counts": dict(
            sorted(
                Counter(record.get("error") or record.get("status") for record in records if not record.get("valid")).items()
            )
        ),
        "shortlist": compact_shortlist(shortlist),
        "top_ranked": compact_ranked(top_ranked),
    }

    print(f"Run root: {run['run_root']}")
    if report["algorithm"]:
        print(f"Algorithm: {report['algorithm']}")
    if report["planned_simulations"] is not None:
        print(f"Planned simulations: {report['planned_simulations']}")
    print(f"History records: {len(records)}")
    print(f"Valid records: {len(valid)}")
    print(f"Filtered valid records: {len(filtered)}")
    print(f"Pareto records: {len(pareto)}")
    print(f"Filtered Pareto records: {len(filtered_pareto)}")
    if run["skipped_history_lines"]:
        print(f"Skipped partial/invalid history lines: {len(run['skipped_history_lines'])}")
    print("Status counts:")
    for status, count in counts.items():
        print(f"  {status}: {count}")
    print_metric_stats("Valid metric ranges:", report["valid_metric_stats"])
    if any(value is not None for value in constraints.values()):
        print_metric_stats("Filtered metric ranges:", report["filtered_metric_stats"])
    print("Shortlist:")
    for item in shortlist:
        row = flatten_record(item["record"])
        print(
            f"  {item['label']}: evaluation_id={row['evaluation_id']} "
            f"gain_db={row['gain_db']} NF_db={row['NF_db']} "
            f"power={row['power']} F_BW={row['F_BW']} S11_db={row['S11_db']}"
        )

    if args.output_dir:
        export_outputs(
            args.output_dir,
            records,
            valid,
            filtered,
            pareto,
            filtered_pareto,
            shortlist,
            top_ranked,
            report,
        )
        print(f"Wrote analysis outputs to: {Path(args.output_dir)}")


if __name__ == "__main__":
    main()
