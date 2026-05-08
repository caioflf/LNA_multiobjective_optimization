#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from optimization_data import (
    apply_constraints,
    metric_value,
    non_dominated_front,
    objective_specs_from_config,
    read_run,
    valid_records,
)

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(__file__).resolve().parent / ".matplotlib-cache"),
)
os.environ.setdefault(
    "XDG_CACHE_HOME",
    str(Path(__file__).resolve().parent / ".cache"),
)
os.environ.setdefault("MPLBACKEND", "Agg")

try:
    import matplotlib.pyplot as plt
except ImportError as exc:
    raise SystemExit(
        "matplotlib is required. Use a Python environment with matplotlib, "
        "for example: /opt/homebrew/bin/python3 analysis/plot_optimization.py ..."
    ) from exc


PLOTS = (
    ("NF_db", "gain_db", "nf_vs_gain.png"),
    ("NF_db", "power", "nf_vs_power.png"),
    ("NF_db", "F_BW", "nf_vs_bandwidth.png"),
    ("NF_db", "S11_db", "nf_vs_s11.png"),
    ("gain_db", "power", "gain_vs_power.png"),
    ("gain_db", "F_BW", "gain_vs_bandwidth.png"),
    ("gain_db", "S11_db", "gain_vs_s11.png"),
    ("power", "F_BW", "power_vs_bandwidth.png"),
    ("power", "S11_db", "power_vs_s11.png"),
    ("F_BW", "S11_db", "bandwidth_vs_s11.png"),
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create scatter plots from optimization_history.jsonl."
    )
    parser.add_argument("run_root", nargs="?", default="optimized_circuits")
    parser.add_argument("--output-dir", default="analysis_plots")
    parser.add_argument("--max-nf-db", type=float)
    parser.add_argument("--max-power", type=float)
    parser.add_argument("--min-gain-db", type=float)
    parser.add_argument("--min-f-bw", type=float)
    parser.add_argument("--max-s11-db", type=float)
    parser.add_argument(
        "--color-by",
        choices=("vg", "wtot_um", "length_um", "NF_db", "power", "gain_db", "F_BW", "S11_db"),
        default="vg",
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


def color_value(record, color_by):
    if color_by in {"vg", "wtot_um", "length_um"}:
        candidate = record.get("candidate") or {}
        params = candidate.get("transistor_parameters") or {}
        value = candidate.get("vg") if color_by == "vg" else params.get(color_by)
        return None if value is None else float(value)
    return metric_value(record, color_by)


def values_for(records, x_metric, y_metric, color_by):
    values = []
    for record in records:
        x_value = metric_value(record, x_metric)
        y_value = metric_value(record, y_metric)
        color = color_value(record, color_by)
        if x_value is None or y_value is None:
            continue
        values.append((x_value, y_value, color))
    return values


def plot_one(records, pareto, x_metric, y_metric, color_by, output_path):
    values = values_for(records, x_metric, y_metric, color_by)
    if not values:
        return False

    x_values = [item[0] for item in values]
    y_values = [item[1] for item in values]
    colors = [item[2] for item in values]
    has_color = all(color is not None for color in colors)

    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    if has_color:
        scatter = ax.scatter(x_values, y_values, c=colors, s=18, alpha=0.65)
        fig.colorbar(scatter, ax=ax, label=color_by)
    else:
        ax.scatter(x_values, y_values, s=18, alpha=0.65)

    pareto_values = values_for(pareto, x_metric, y_metric, color_by)
    if pareto_values:
        ax.scatter(
            [item[0] for item in pareto_values],
            [item[1] for item in pareto_values],
            s=55,
            facecolors="none",
            edgecolors="black",
            linewidths=1.2,
            label="Pareto",
        )
        ax.legend()

    ax.set_xlabel(x_metric)
    ax.set_ylabel(y_metric)
    ax.grid(True, alpha=0.25)
    if x_metric == "power" and all(value > 0 for value in x_values):
        ax.set_xscale("log")
    if y_metric == "power" and all(value > 0 for value in y_values):
        ax.set_yscale("log")
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return True


def main():
    args = parse_args()

    run = read_run(args.run_root)
    objectives = objective_specs_from_config(run["config"])
    records = apply_constraints(valid_records(run["records"]), build_constraints(args))
    pareto = apply_constraints(
        non_dominated_front(valid_records(run["records"]), objectives),
        build_constraints(args),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for x_metric, y_metric, filename in PLOTS:
        output_path = output_dir / filename
        if plot_one(records, pareto, x_metric, y_metric, args.color_by, output_path):
            written.append(output_path)

    print(f"Valid filtered records plotted: {len(records)}")
    print(f"Pareto records highlighted: {len(pareto)}")
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
