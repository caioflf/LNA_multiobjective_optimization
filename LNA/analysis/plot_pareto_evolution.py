#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from optimization_data import (
    DEFAULT_OBJECTIVES,
    METRIC_NAMES,
    apply_constraints,
    metric_value,
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
        "for example: /opt/homebrew/bin/python3 analysis/plot_pareto_evolution.py ..."
    ) from exc


DEFAULT_PAIRS = (
    ("NF_db", "S21_db"),
    ("NF_db", "power_dBm"),
    ("NF_db", "F_BW"),
    ("NF_db", "S11_db"),
    ("S21_db", "power_dBm"),
    ("S21_db", "F_BW"),
    ("S21_db", "S11_db"),
    ("power_dBm", "F_BW"),
    ("power_dBm", "S11_db"),
    ("F_BW", "S11_db"),
)
METRIC_ALIASES = {
    "nf": "NF_db",
    "nf_db": "NF_db",
    "nfmin": "NFmin_db",
    "nfmin_db": "NFmin_db",
    "power": "power_dBm",
    "power_dbm": "power_dBm",
    "gain": "S21_db",
    "gain_db": "S21_db",
    "s21": "S21_db",
    "s21_db": "S21_db",
    "bw": "F_BW",
    "f_bw": "F_BW",
    "bandwidth": "F_BW",
    "s11": "S11_db",
    "s11_db": "S11_db",
}
DEFAULT_DIRECTIONS = {
    item["name"]: item["direction"]
    for item in DEFAULT_OBJECTIVES
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Create per-generation 2D Pareto-frontier snapshots from "
            "optimization history, optionally using saved generation files "
            "to highlight each generation's current population."
        )
    )
    parser.add_argument("run_root", nargs="?", default="optimized_circuits")
    parser.add_argument("--output-dir", default="analysis_pareto_evolution")
    parser.add_argument(
        "--pairs",
        default="NF_db:S21_db",
        help=(
            "Metric pairs as 'X:Y,X:Y', or 'all'. Short aliases like "
            "nf:s21 and power:bw are accepted."
        ),
    )
    parser.add_argument(
        "--record-scope",
        choices=("all", "valid"),
        default="all",
        help=(
            "Records used to compute the 2D frontier after optional filters. "
            "With generation files, this applies to history records up to "
            "that generation's evaluation count."
        ),
    )
    parser.add_argument(
        "--generation-source",
        choices=("auto", "files", "history"),
        default="files",
        help=(
            "Use saved generations/generation_XXXX.json files, inferred "
            "history checkpoints, or generation files when available. "
            "Generation files provide the exact current population overlay."
        ),
    )
    parser.add_argument(
        "--generations-dir",
        help="Directory containing generation_XXXX.json files. Default: run_root/generations.",
    )
    parser.add_argument(
        "--generation-step",
        type=int,
        default=1,
        help="Write one snapshot every N inferred generations.",
    )
    parser.add_argument(
        "--max-generations",
        type=int,
        help="Stop after this inferred generation number.",
    )
    parser.add_argument(
        "--include-partial",
        action="store_true",
        help="Also write one snapshot for the partial current generation.",
    )
    parser.add_argument(
        "--hide-valid-overlay",
        action="store_true",
        help="Do not draw the separate valid-record overlay.",
    )
    parser.add_argument(
        "--hide-generation-population",
        action="store_true",
        help="Do not highlight the saved population from each generation file.",
    )
    parser.add_argument(
        "--filter-constraints",
        action="store_true",
        help="Use constraint limits to filter records before computing the frontier.",
    )
    parser.add_argument(
        "--shade-constraint-region",
        action="store_true",
        help="Shade the region allowed by constraints that apply to the plotted axes.",
    )
    parser.add_argument(
        "--shade-frontier-region",
        action="store_true",
        help="Shade the dominated area implied by the 2D Pareto frontier.",
    )
    parser.add_argument(
        "--frontier-region-alpha",
        type=float,
        default=0.055,
        help="Opacity for the shaded Pareto-frontier dominated area.",
    )
    parser.add_argument("--max-nf-db", type=float)
    parser.add_argument("--max-power-dbm", "--max-power", dest="max_power_dbm", type=float)
    parser.add_argument("--min-s21-db", "--min-gain-db", dest="min_s21_db", type=float)
    parser.add_argument("--min-f-bw", type=float)
    parser.add_argument("--max-s11-db", type=float)
    parser.add_argument("--dpi", type=int, default=140)
    return parser.parse_args()


def build_constraints(args):
    return {
        "max_nf_db": args.max_nf_db,
        "max_power_dbm": args.max_power_dbm,
        "min_s21_db": args.min_s21_db,
        "min_f_bw": args.min_f_bw,
        "max_s11_db": args.max_s11_db,
    }


def canonical_metric(metric_name):
    normalized = metric_name.strip()
    return METRIC_ALIASES.get(normalized.lower(), normalized)


def parse_pairs(pair_text):
    pair_text = pair_text.strip()
    if pair_text.lower() == "all":
        return DEFAULT_PAIRS

    pairs = []
    for item in pair_text.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            left, right = item.split(":", 1)
        elif "_vs_" in item:
            left, right = item.split("_vs_", 1)
        else:
            raise ValueError(
                f"Invalid pair '{item}'. Use X:Y, X_vs_Y, or all."
            )
        pairs.append((canonical_metric(left), canonical_metric(right)))
    if not pairs:
        raise ValueError("At least one metric pair is required")
    return tuple(pairs)


def metric_direction_map(config):
    directions = dict(DEFAULT_DIRECTIONS)
    for objective in objective_specs_from_config(config):
        directions[objective["name"]] = objective.get("direction", "min")
    for metric_name in METRIC_NAMES:
        directions.setdefault(metric_name, DEFAULT_DIRECTIONS.get(metric_name, "min"))
    return directions


def direction_for(metric_name, directions):
    return directions.get(metric_name, DEFAULT_DIRECTIONS.get(metric_name, "min"))


def objective_value(record, metric_name, directions):
    value = metric_value(record, metric_name)
    if value is None:
        return None
    return -value if direction_for(metric_name, directions) == "max" else value


def values_for(records, x_metric, y_metric):
    values = []
    for record in records:
        x_value = metric_value(record, x_metric)
        y_value = metric_value(record, y_metric)
        if x_value is None or y_value is None:
            continue
        if (x_metric == "F_BW" and x_value <= 0) or (
            y_metric == "F_BW" and y_value <= 0
        ):
            continue
        values.append((x_value, y_value))
    return values


def pair_pareto_front(records, x_metric, y_metric, directions):
    candidates = []
    for order, record in enumerate(records):
        x_obj = objective_value(record, x_metric, directions)
        y_obj = objective_value(record, y_metric, directions)
        if x_obj is None or y_obj is None:
            continue
        x_plot = metric_value(record, x_metric)
        y_plot = metric_value(record, y_metric)
        if (x_metric == "F_BW" and x_plot <= 0) or (
            y_metric == "F_BW" and y_plot <= 0
        ):
            continue
        candidates.append((x_obj, y_obj, order, record))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    front = []
    best_y = None
    for x_obj, y_obj, _, record in candidates:
        if best_y is None or y_obj < best_y:
            front.append(record)
            best_y = y_obj
    return sorted(front, key=lambda record: metric_value(record, x_metric))


def infer_generation_checkpoints(config, record_count, *, include_partial=False):
    algorithm = str(config.get("algorithm") or "").upper()
    if algorithm == "MOPSO":
        initial_size = int(config.get("swarm_size") or config.get("population_size") or 0)
        step_size = int(config.get("swarm_size") or config.get("population_size") or 0)
        generation_count = int(config.get("iterations") or config.get("generations") or 0)
    else:
        initial_size = int(config.get("population_size") or 0)
        step_size = int(config.get("offspring_size") or initial_size or 0)
        generation_count = int(config.get("generations") or 0)

    if initial_size <= 0 or step_size <= 0:
        raise ValueError(
            "Cannot infer generation checkpoints from optimization_config.json"
        )

    checkpoints = []
    for generation in range(generation_count + 1):
        end_index = initial_size + generation * step_size
        if end_index <= record_count:
            checkpoints.append((generation, end_index, False))
            continue
        if include_partial and record_count > 0:
            checkpoints.append((generation, record_count, True))
        break
    return checkpoints


def select_checkpoints(checkpoints, generation_step, max_generations):
    if generation_step < 1:
        raise ValueError("--generation-step must be at least 1")
    selected = []
    for generation, end_index, partial in checkpoints:
        if max_generations is not None and generation > max_generations:
            continue
        if generation % generation_step == 0 or generation == checkpoints[-1][0]:
            selected.append((generation, end_index, partial))
    return selected


def parse_generation_number(path):
    stem = path.stem
    try:
        return int(stem.rsplit("_", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Cannot parse generation number from {path}") from exc


def generation_directory(run_root, generations_dir=None):
    if generations_dir:
        return Path(generations_dir)
    return Path(run_root) / "generations"


def load_generation_snapshots(run_root, *, generations_dir=None):
    directory = generation_directory(run_root, generations_dir)
    paths = sorted(directory.glob("generation_*.json"))
    snapshots = []
    for path in paths:
        payload = json.loads(path.read_text())
        generation = payload.get("generation")
        if generation is None:
            generation = parse_generation_number(path)
        snapshots.append(
            {
                "generation": int(generation),
                "path": path,
                "payload": payload,
            }
        )
    snapshots.sort(key=lambda item: item["generation"])
    return snapshots


def select_generation_snapshots(snapshots, generation_step, max_generations):
    if generation_step < 1:
        raise ValueError("--generation-step must be at least 1")
    selected = []
    last_generation = snapshots[-1]["generation"] if snapshots else None
    for snapshot in snapshots:
        generation = snapshot["generation"]
        if max_generations is not None and generation > max_generations:
            continue
        if generation % generation_step == 0 or generation == last_generation:
            selected.append(snapshot)
    return selected


def resolve_generation_mode(run_root, generation_source, generations_dir=None):
    if generation_source == "history":
        return "history", []

    snapshots = load_generation_snapshots(run_root, generations_dir=generations_dir)
    if snapshots:
        return "files", snapshots

    if generation_source == "files":
        directory = generation_directory(run_root, generations_dir)
        raise FileNotFoundError(f"No generation_*.json files found in {directory}")

    return "history", []


def history_slice_for_generation(records, payload):
    evaluation_count = payload.get("evaluations")
    if evaluation_count is None:
        return records
    return records[: min(int(evaluation_count), len(records))]


def pair_slug(x_metric, y_metric):
    return f"{x_metric.lower()}_vs_{y_metric.lower()}".replace("/", "_")


def axis_label(metric_name, directions):
    direction = direction_for(metric_name, directions)
    suffix = "maximize" if direction == "max" else "minimize"
    if metric_name == "F_BW":
        return f"{metric_name} ({suffix}, log10 axis)"
    return f"{metric_name} ({suffix})"


def apply_axis_scales(ax, x_metric, y_metric):
    if x_metric == "F_BW":
        ax.set_xscale("log", base=10, nonpositive="mask")
    if y_metric == "F_BW":
        ax.set_yscale("log", base=10, nonpositive="mask")


def constraint_for_metric(metric_name, constraints):
    mapping = {
        "NF_db": ("<=", constraints.get("max_nf_db")),
        "power_dBm": ("<=", constraints.get("max_power_dbm")),
        "S21_db": (">=", constraints.get("min_s21_db")),
        "F_BW": (">=", constraints.get("min_f_bw")),
        "S11_db": ("<=", constraints.get("max_s11_db")),
    }
    operator, limit = mapping.get(metric_name, (None, None))
    if limit is None:
        return None
    return operator, float(limit)


def constrained_interval(metric_name, constraint, limits):
    if constraint is None:
        return limits
    operator, limit = constraint
    low, high = limits
    if metric_name == "F_BW" and limit <= 0:
        return None
    if operator == "<=":
        if limit < low:
            return None
        return low, min(limit, high)
    if operator == ">=":
        if limit > high:
            return None
        return max(limit, low), high
    return limits


def draw_constraint_region(ax, x_metric, y_metric, constraints):
    x_constraint = constraint_for_metric(x_metric, constraints)
    y_constraint = constraint_for_metric(y_metric, constraints)
    if x_constraint is None and y_constraint is None:
        return

    x_limits = ax.get_xlim()
    y_limits = ax.get_ylim()
    x_interval = constrained_interval(x_metric, x_constraint, x_limits)
    y_interval = constrained_interval(y_metric, y_constraint, y_limits)
    if x_interval is None or y_interval is None:
        return

    if x_constraint is not None and y_constraint is not None:
        ax.fill_between(
            [x_interval[0], x_interval[1]],
            [y_interval[0], y_interval[0]],
            [y_interval[1], y_interval[1]],
            color="#a8dca8",
            alpha=0.52,
            zorder=0.2,
            label="constraint region",
        )
    elif x_constraint is not None:
        ax.axvspan(
            x_interval[0],
            x_interval[1],
            color="#a8dca8",
            alpha=0.52,
            zorder=0.2,
            label="constraint region",
        )
    else:
        ax.axhspan(
            y_interval[0],
            y_interval[1],
            color="#a8dca8",
            alpha=0.52,
            zorder=0.2,
            label="constraint region",
        )


def metric_to_minimized_value(value, metric_name, directions):
    if direction_for(metric_name, directions) == "max":
        return -value
    return value


def metric_from_minimized_value(value, metric_name, directions):
    if direction_for(metric_name, directions) == "max":
        return -value
    return value


def minimized_limits(limits, metric_name, directions):
    values = [
        metric_to_minimized_value(value, metric_name, directions)
        for value in limits
    ]
    return min(values), max(values)


def frontier_points_minimized(front_records, x_metric, y_metric, directions):
    points = []
    for record in front_records:
        x_value = metric_value(record, x_metric)
        y_value = metric_value(record, y_metric)
        if x_value is None or y_value is None:
            continue
        if (x_metric == "F_BW" and x_value <= 0) or (
            y_metric == "F_BW" and y_value <= 0
        ):
            continue
        points.append(
            (
                metric_to_minimized_value(x_value, x_metric, directions),
                metric_to_minimized_value(y_value, y_metric, directions),
            )
        )
    points.sort(key=lambda point: (point[0], point[1]))
    return points


def minimized_point_to_plot(point, x_metric, y_metric, directions):
    x_obj, y_obj = point
    return (
        metric_from_minimized_value(x_obj, x_metric, directions),
        metric_from_minimized_value(y_obj, y_metric, directions),
    )


def frontier_step_path(points, x_metric, y_metric, directions, reference_x):
    if not points:
        return [], []

    path = [points[0]]
    for index, (_, y_obj) in enumerate(points[:-1]):
        next_x, next_y = points[index + 1]
        path.append((next_x, y_obj))
        path.append((next_x, next_y))

    last_x, last_y = points[-1]
    if reference_x > last_x:
        path.append((reference_x, last_y))

    plot_points = [
        minimized_point_to_plot(point, x_metric, y_metric, directions)
        for point in path
    ]
    return (
        [point[0] for point in plot_points],
        [point[1] for point in plot_points],
    )


def draw_frontier_region(
    ax,
    front_records,
    x_metric,
    y_metric,
    directions,
    *,
    color,
    alpha,
    label,
):
    points = frontier_points_minimized(front_records, x_metric, y_metric, directions)
    if not points:
        return

    x_limits = minimized_limits(ax.get_xlim(), x_metric, directions)
    y_limits = minimized_limits(ax.get_ylim(), y_metric, directions)
    reference_x = x_limits[1]
    reference_y = y_limits[1]
    rectangle_count = 0

    for index, (x_obj, y_obj) in enumerate(points):
        next_x = points[index + 1][0] if index + 1 < len(points) else reference_x
        x_left = max(x_obj, x_limits[0])
        x_right = min(next_x, reference_x)
        y_bottom = max(y_obj, y_limits[0])
        y_top = reference_y
        if x_right <= x_left or y_top <= y_bottom:
            continue

        x0 = metric_from_minimized_value(x_left, x_metric, directions)
        x1 = metric_from_minimized_value(x_right, x_metric, directions)
        y0 = metric_from_minimized_value(y_bottom, y_metric, directions)
        y1 = metric_from_minimized_value(y_top, y_metric, directions)
        x_plot = sorted((x0, x1))
        y_plot = sorted((y0, y1))
        ax.fill_between(
            x_plot,
            [y_plot[0], y_plot[0]],
            [y_plot[1], y_plot[1]],
            color=color,
            alpha=alpha,
            linewidth=0,
            zorder=0.35,
            label=label if rectangle_count == 0 else "_nolegend_",
        )
        rectangle_count += 1


def draw_frontier_step_line(
    ax,
    front_records,
    x_metric,
    y_metric,
    directions,
    *,
    color,
    label,
):
    points = frontier_points_minimized(front_records, x_metric, y_metric, directions)
    if not points:
        return

    x_limits = minimized_limits(ax.get_xlim(), x_metric, directions)
    x_values, y_values = frontier_step_path(
        points,
        x_metric,
        y_metric,
        directions,
        x_limits[1],
    )
    ax.plot(
        x_values,
        y_values,
        color=color,
        linewidth=1.9,
        label=label,
        zorder=3,
    )

    marker_points = [
        minimized_point_to_plot(point, x_metric, y_metric, directions)
        for point in points
    ]
    ax.scatter(
        [point[0] for point in marker_points],
        [point[1] for point in marker_points],
        s=16,
        color=color,
        linewidths=0,
        zorder=3.1,
        label="_nolegend_",
    )


def axis_limits(records, pairs):
    limits = {}
    for x_metric, y_metric in pairs:
        values = values_for(records, x_metric, y_metric)
        if not values:
            continue
        x_values = [item[0] for item in values]
        y_values = [item[1] for item in values]
        limits[(x_metric, y_metric)] = (
            padded_limits(x_values, log_scale=x_metric == "F_BW"),
            padded_limits(y_values, log_scale=y_metric == "F_BW"),
        )
    return limits


def padded_limits(values, *, log_scale=False):
    low = min(values)
    high = max(values)
    if low == high:
        if log_scale:
            return low * 0.9, high * 1.1
        padding = abs(low) * 0.05 or 1.0
        return low - padding, high + padding

    if log_scale:
        return low * 0.9, high * 1.1

    padding = (high - low) * 0.05
    return low - padding, high + padding


def plot_snapshot(
    *,
    background_records,
    valid_overlay_records,
    front_records,
    generation_population_records,
    x_metric,
    y_metric,
    directions,
    generation,
    end_index,
    partial,
    limits,
    constraint_region,
    shade_frontier_region,
    frontier_region_alpha,
    output_path,
    dpi,
):
    background_values = values_for(background_records, x_metric, y_metric)
    if not background_values:
        return False
    valid_values = values_for(valid_overlay_records, x_metric, y_metric)
    population_values = values_for(generation_population_records, x_metric, y_metric)

    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    apply_axis_scales(ax, x_metric, y_metric)
    if limits:
        ax.set_xlim(*limits[0])
        ax.set_ylim(*limits[1])
    if constraint_region:
        draw_constraint_region(ax, x_metric, y_metric, constraint_region)
    if shade_frontier_region:
        draw_frontier_region(
            ax,
            front_records,
            x_metric,
            y_metric,
            directions,
            color="#d62728",
            alpha=frontier_region_alpha,
            label="frontier dominated area",
        )

    ax.scatter(
        [item[0] for item in background_values],
        [item[1] for item in background_values],
        s=8,
        color="#b8b8b8",
        alpha=0.22,
        linewidths=0,
        label="history with metrics",
    )
    if valid_values:
        ax.scatter(
            [item[0] for item in valid_values],
            [item[1] for item in valid_values],
            s=11,
            color="#2f6fbb",
            alpha=0.45,
            linewidths=0,
            label="valid",
        )
    if population_values:
        ax.scatter(
            [item[0] for item in population_values],
            [item[1] for item in population_values],
            s=22,
            color="#ffb000",
            edgecolors="#222222",
            linewidths=0.25,
            alpha=0.86,
            zorder=2.2,
            label="generation population",
        )
    draw_frontier_step_line(
        ax,
        front_records,
        x_metric,
        y_metric,
        directions,
        color="#d62728",
        label="2D Pareto frontier",
    )

    ax.set_xlabel(axis_label(x_metric, directions))
    ax.set_ylabel(axis_label(y_metric, directions))
    title_suffix = " partial" if partial else ""
    ax.set_title(
        f"Generation {generation:04d}{title_suffix} | first {end_index:,} history records"
    )
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return True


def main():
    args = parse_args()
    pairs = parse_pairs(args.pairs)
    run = read_run(args.run_root)
    records = run["records"]
    constraints = build_constraints(args)
    directions = metric_direction_map(run["config"])
    generation_mode, snapshots = resolve_generation_mode(
        args.run_root,
        args.generation_source,
        args.generations_dir,
    )
    if generation_mode == "files":
        checkpoints = select_generation_snapshots(
            snapshots,
            args.generation_step,
            args.max_generations,
        )
        if not checkpoints:
            raise SystemExit("No generation files matched the requested selection")
    else:
        checkpoints = infer_generation_checkpoints(
            run["config"],
            len(records),
            include_partial=args.include_partial,
        )
        checkpoints = select_checkpoints(
            checkpoints,
            args.generation_step,
            args.max_generations,
        )
        if not checkpoints:
            raise SystemExit("No generation checkpoints could be inferred")

    output_root = Path(args.output_dir)
    limits = axis_limits(records, pairs)
    written = []
    for checkpoint in checkpoints:
        if generation_mode == "files":
            generation = checkpoint["generation"]
            payload = checkpoint["payload"]
            history_slice = history_slice_for_generation(records, payload)
            end_index = min(int(payload.get("evaluations") or len(history_slice)), len(records))
            partial = False
            generation_population_records = [
                record
                for record in payload.get("population", [])
                if record.get("metrics")
            ]
        else:
            generation, end_index, partial = checkpoint
            history_slice = records[:end_index]
            generation_population_records = []

        background_records = [
            record
            for record in history_slice
            if record.get("metrics")
        ]
        valid_overlay_records = valid_records(history_slice)
        front_base = background_records

        if args.record_scope == "valid":
            front_source = valid_records(front_base)
        else:
            front_source = front_base
        if args.filter_constraints:
            front_source = apply_constraints(front_source, constraints)

        for x_metric, y_metric in pairs:
            front = pair_pareto_front(
                front_source,
                x_metric,
                y_metric,
                directions,
            )
            output_path = (
                output_root
                / pair_slug(x_metric, y_metric)
                / f"generation_{generation:04d}.png"
            )
            overlay_records = []
            if not args.hide_valid_overlay:
                overlay_records = valid_overlay_records
                if args.filter_constraints:
                    overlay_records = apply_constraints(overlay_records, constraints)

            if plot_snapshot(
                background_records=background_records,
                valid_overlay_records=overlay_records,
                front_records=front,
                generation_population_records=[]
                if args.hide_generation_population
                else generation_population_records,
                x_metric=x_metric,
                y_metric=y_metric,
                directions=directions,
                generation=generation,
                end_index=end_index,
                partial=partial,
                limits=limits.get((x_metric, y_metric)),
                constraint_region=constraints
                if args.shade_constraint_region
                else None,
                shade_frontier_region=args.shade_frontier_region,
                frontier_region_alpha=args.frontier_region_alpha,
                output_path=output_path,
                dpi=args.dpi,
            ):
                written.append(output_path)

    print(f"Run root: {run['run_root']}")
    print(f"Generation source: {generation_mode}")
    print(f"History records: {len(records):,}")
    print(f"Checkpoints plotted: {len(checkpoints):,}")
    print(f"Metric pairs plotted: {len(pairs):,}")
    print(f"Snapshots written: {len(written):,}")
    if written:
        print(f"Output root: {output_root}")


if __name__ == "__main__":
    main()
