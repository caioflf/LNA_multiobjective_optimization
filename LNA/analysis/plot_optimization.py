#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from optimization_data import (
    NETWORK_ROLES,
    RLC_AXES,
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
    ("NF_db", "S21_db", "nf_vs_s21.png"),
    ("NF_db", "power_dBm", "nf_vs_power.png"),
    ("NF_db", "F_BW", "nf_vs_bandwidth.png"),
    ("NF_db", "S11_db", "nf_vs_s11.png"),
    ("S21_db", "power_dBm", "s21_vs_power.png"),
    ("S21_db", "F_BW", "s21_vs_bandwidth.png"),
    ("S21_db", "S11_db", "s21_vs_s11.png"),
    ("power_dBm", "F_BW", "power_vs_bandwidth.png"),
    ("power_dBm", "S11_db", "power_vs_s11.png"),
    ("F_BW", "S11_db", "bandwidth_vs_s11.png"),
)
NETWORK_INDEX_COLOR_FIELDS = tuple(
    f"{role}_{axis}_index"
    for role in NETWORK_ROLES
    for axis in RLC_AXES
)
NETWORK_INDEX_COLOR_ALIASES = tuple(
    f"{role}_{axis}"
    for role in NETWORK_ROLES
    for axis in RLC_AXES
)
TRANSISTOR_INDEX_COLOR_FIELDS = (
    "device_type_index",
    "vt_index",
    "wtot_index",
    "length_index",
)
COLOR_BY_CHOICES = (
    "vg",
    "wtot_um",
    "length_um",
    *TRANSISTOR_INDEX_COLOR_FIELDS,
    *NETWORK_INDEX_COLOR_FIELDS,
    *NETWORK_INDEX_COLOR_ALIASES,
    "NF_db",
    "NFmin_db",
    "power_dBm",
    "S21_db",
    "F_BW",
    "S11_db",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create scatter plots from optimization_history.jsonl."
    )
    parser.add_argument("run_root", nargs="?", default="optimized_circuits")
    parser.add_argument("--output-dir", default="analysis_plots")
    parser.add_argument("--max-nf-db", type=float)
    parser.add_argument("--max-power-dbm", "--max-power", dest="max_power_dbm", type=float)
    parser.add_argument("--min-s21-db", "--min-gain-db", dest="min_s21_db", type=float)
    parser.add_argument("--min-f-bw", type=float)
    parser.add_argument("--max-s11-db", type=float)
    parser.add_argument(
        "--color-by",
        choices=COLOR_BY_CHOICES,
        default="vg",
    )
    parser.add_argument(
        "--record-scope",
        choices=("valid", "all"),
        default="valid",
        help=(
            "Use only valid records, or all history records that have finite "
            "x/y metrics for each plot."
        ),
    )
    return parser.parse_args()


def build_constraints(args):
    return {
        "max_nf_db": args.max_nf_db,
        "max_power_dbm": args.max_power_dbm,
        "min_s21_db": args.min_s21_db,
        "min_f_bw": args.min_f_bw,
        "max_s11_db": args.max_s11_db,
    }


def color_value(record, color_by):
    if color_by in NETWORK_INDEX_COLOR_ALIASES:
        color_by = f"{color_by}_index"
    if color_by in {"vg", "wtot_um", "length_um"}:
        candidate = record.get("candidate") or {}
        params = candidate.get("transistor_parameters") or {}
        value = candidate.get("vg") if color_by == "vg" else params.get(color_by)
        return None if value is None else float(value)
    if color_by in TRANSISTOR_INDEX_COLOR_FIELDS:
        candidate = record.get("candidate") or {}
        indexes = candidate.get("transistor_indexes") or {}
        value = indexes.get(color_by)
        return None if value is None else float(value)
    if color_by in NETWORK_INDEX_COLOR_FIELDS:
        role, axis, _ = color_by.split("_", 2)
        candidate = record.get("candidate") or {}
        networks = candidate.get("networks") or {}
        network = networks.get(role) or {}
        passive_indexes = network.get("passive_indexes") or {}
        value = passive_indexes.get(axis)
        return 0.0 if value is None else float(value)
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


def axis_label(metric_name):
    if metric_name == "F_BW":
        return "F_BW (%, log10 axis)"
    return metric_name


def apply_axis_scales(ax, x_metric, y_metric):
    if x_metric == "F_BW":
        ax.set_xscale("log", base=10, nonpositive="mask")
    if y_metric == "F_BW":
        ax.set_yscale("log", base=10, nonpositive="mask")


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
        scatter = ax.scatter(x_values, y_values, c=colors, s=30, alpha=0.65)
        fig.colorbar(scatter, ax=ax, label=color_by)
    else:
        ax.scatter(x_values, y_values, s=30, alpha=0.65)

    pareto_values = values_for(pareto, x_metric, y_metric, color_by)
    if pareto_values:
        ax.scatter(
            [item[0] for item in pareto_values],
            [item[1] for item in pareto_values],
            s=30,
            facecolors="none",
            edgecolors="black",
            linewidths=0.0,
            #label="Pareto",
        )
        handles, labels = ax.get_legend_handles_labels()
        if handles and labels:
            ax.legend()

    apply_axis_scales(ax, x_metric, y_metric)
    ax.set_xlabel(axis_label(x_metric))
    ax.set_ylabel(axis_label(y_metric))
    ax.grid(True, alpha=0.25)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return True


def main():
    args = parse_args()

    run = read_run(args.run_root)
    objectives = objective_specs_from_config(run["config"])
    source_records = (
        run["records"]
        if args.record_scope == "all"
        else valid_records(run["records"])
    )
    records = apply_constraints(source_records, build_constraints(args))
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

    scope_label = "history" if args.record_scope == "all" else "valid"
    print(f"{scope_label.capitalize()} filtered records considered: {len(records)}")
    print(f"Pareto records highlighted: {len(pareto)}")
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
