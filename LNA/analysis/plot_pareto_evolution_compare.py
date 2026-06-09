#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from optimization_data import apply_constraints, read_run, valid_records
from plot_pareto_evolution import (
    apply_axis_scales,
    axis_label,
    axis_limits,
    build_constraints,
    draw_constraint_region,
    draw_frontier_region,
    draw_frontier_step_line,
    infer_generation_checkpoints,
    history_slice_for_generation,
    load_generation_snapshots,
    metric_direction_map,
    pair_pareto_front,
    pair_slug,
    parse_pairs,
    select_checkpoints,
    select_generation_snapshots,
    values_for,
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
        "for example: /opt/homebrew/bin/python3 analysis/plot_pareto_evolution_compare.py ..."
    ) from exc


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Overlay per-generation 2D Pareto-frontier snapshots from two or "
            "more optimization runs. Saved generation files can be used to "
            "highlight exact per-generation populations."
        )
    )
    parser.add_argument("run_roots", nargs="+")
    parser.add_argument(
        "--labels",
        nargs="+",
        help="Optional labels for the run roots. Must match the number of runs.",
    )
    parser.add_argument("--output-dir", default="analysis/pareto_evolution_compare")
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
            "Records used to compute each run's 2D frontier after optional "
            "filters. With generation files, this applies to history records "
            "up to each generation's evaluation count."
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
        "--generations-dirs",
        nargs="+",
        help=(
            "Optional generation directories, one per run root. Defaults to "
            "run_root/generations for each run."
        ),
    )
    parser.add_argument(
        "--generation-step",
        type=int,
        default=1,
        help="Write one snapshot every N inferred generations.",
    )
    parser.add_argument(
        "--generation-mode",
        choices=("common", "union"),
        default="common",
        help=(
            "Use only generation numbers available in every run, or the union "
            "of available generation numbers."
        ),
    )
    parser.add_argument(
        "--max-generations",
        type=int,
        help="Stop after this inferred generation number.",
    )
    parser.add_argument(
        "--include-partial",
        action="store_true",
        help="Also include each run's partial current generation when available.",
    )
    parser.add_argument(
        "--hide-history",
        action="store_true",
        help="Do not draw per-run history scatter points.",
    )
    parser.add_argument(
        "--hide-valid-overlay",
        action="store_true",
        help="Do not draw the separate per-run valid-record overlay.",
    )
    parser.add_argument(
        "--hide-generation-population",
        action="store_true",
        help="Do not highlight the saved population from each generation file.",
    )
    parser.add_argument(
        "--filter-constraints",
        action="store_true",
        help="Use constraint limits to filter records before computing frontiers.",
    )
    parser.add_argument(
        "--shade-constraint-region",
        action="store_true",
        help="Shade the region allowed by constraints that apply to the plotted axes.",
    )
    parser.add_argument(
        "--shade-frontier-region",
        action="store_true",
        help="Shade each run's 2D Pareto-frontier dominated area.",
    )
    parser.add_argument(
        "--frontier-region-alpha",
        type=float,
        default=0.055,
        help="Opacity for each shaded Pareto-frontier dominated area.",
    )
    parser.add_argument("--max-nf-db", type=float)
    parser.add_argument("--max-power-dbm", "--max-power", dest="max_power_dbm", type=float)
    parser.add_argument("--min-s21-db", "--min-gain-db", dest="min_s21_db", type=float)
    parser.add_argument("--min-f-bw", type=float)
    parser.add_argument("--max-s11-db", type=float)
    parser.add_argument("--dpi", type=int, default=140)
    args = parser.parse_args()
    if len(args.run_roots) < 2:
        raise ValueError("At least two run roots are required")
    if args.labels is not None and len(args.labels) != len(args.run_roots):
        raise ValueError("--labels must have the same number of entries as run_roots")
    if args.generations_dirs is not None and len(args.generations_dirs) != len(args.run_roots):
        raise ValueError("--generations-dirs must have the same number of entries as run_roots")
    return args


def default_label(run_root, used_labels):
    candidate = Path(run_root).name or str(run_root)
    label = candidate
    suffix = 2
    while label in used_labels:
        label = f"{candidate}_{suffix}"
        suffix += 1
    used_labels.add(label)
    return label


def resolve_run_generation_source(run_root, generation_source, generations_dir):
    if generation_source == "history":
        return "history", []

    snapshots = load_generation_snapshots(run_root, generations_dir=generations_dir)
    if snapshots:
        return "files", snapshots

    if generation_source == "files":
        directory = Path(generations_dir) if generations_dir else Path(run_root) / "generations"
        raise FileNotFoundError(f"No generation_*.json files found in {directory}")

    return "history", []


def load_runs(
    run_roots,
    labels,
    include_partial,
    generation_step,
    max_generations,
    generation_source,
    generations_dirs,
):
    runs = []
    for index, (run_root, label) in enumerate(zip(run_roots, labels)):
        generations_dir = None if generations_dirs is None else generations_dirs[index]
        run = read_run(run_root)
        records = run["records"]
        source_mode, snapshots = resolve_run_generation_source(
            run_root,
            generation_source,
            generations_dir,
        )
        if source_mode == "files":
            selected = select_generation_snapshots(
                snapshots,
                generation_step,
                max_generations,
            )
            if not selected:
                raise ValueError(f"No generation files matched the requested selection for {run_root}")
            checkpoints = {
                snapshot["generation"]: snapshot
                for snapshot in selected
            }
        else:
            inferred = infer_generation_checkpoints(
                run["config"],
                len(records),
                include_partial=include_partial,
            )
            inferred = select_checkpoints(
                inferred,
                generation_step,
                max_generations,
            )
            if not inferred:
                raise ValueError(f"No generation checkpoints could be inferred for {run_root}")
            checkpoints = {
                generation: (end_index, partial)
                for generation, end_index, partial in inferred
            }
        runs.append(
            {
                "label": label,
                "run_root": run["run_root"],
                "config": run["config"],
                "records": records,
                "directions": metric_direction_map(run["config"]),
                "generation_source": source_mode,
                "checkpoints": checkpoints,
            }
        )
    return runs


def compatible_directions(runs, pairs):
    base = runs[0]["directions"]
    for run in runs[1:]:
        for x_metric, y_metric in pairs:
            for metric_name in (x_metric, y_metric):
                if base.get(metric_name) != run["directions"].get(metric_name):
                    raise ValueError(
                        "Cannot compare runs with different objective directions "
                        f"for {metric_name}: {runs[0]['label']} has {base.get(metric_name)}, "
                        f"{run['label']} has {run['directions'].get(metric_name)}"
                    )
    return base


def selected_generations(runs, generation_mode):
    generation_sets = [
        set(run["checkpoints"])
        for run in runs
    ]
    if generation_mode == "common":
        generations = set.intersection(*generation_sets)
    else:
        generations = set.union(*generation_sets)
    return sorted(generations)


def run_color(index, total):
    if total <= 10:
        cmap = plt.get_cmap("tab10")
        return cmap(index % 10)
    cmap = plt.get_cmap("tab20")
    return cmap(index % 20)


def run_slice(run, generation):
    checkpoint = run["checkpoints"].get(generation)
    if checkpoint is None:
        return None
    if run["generation_source"] == "files":
        payload = checkpoint["payload"]
        records = history_slice_for_generation(run["records"], payload)
        end_index = min(int(payload.get("evaluations") or len(records)), len(run["records"]))
        partial = False
        population = [
            record
            for record in payload.get("population", [])
            if record.get("metrics")
        ]
    else:
        end_index, partial = checkpoint
        records = run["records"][:end_index]
        population = []
    background = [
        record
        for record in records
        if record.get("metrics")
    ]
    valid = valid_records(records)
    return {
        "end_index": end_index,
        "partial": partial,
        "background": background,
        "valid": valid,
        "population": population,
    }


def plot_snapshot(
    *,
    runs,
    generation,
    x_metric,
    y_metric,
    directions,
    constraints,
    filter_constraints,
    shade_constraint_region,
    shade_frontier_region,
    frontier_region_alpha,
    hide_history,
    hide_valid_overlay,
    hide_generation_population,
    record_scope,
    limits,
    output_path,
    dpi,
):
    plotted = []
    for run_index, run in enumerate(runs):
        sliced = run_slice(run, generation)
        if sliced is None:
            continue
        front_base = sliced["background"]
        if record_scope == "valid":
            front_source = valid_records(front_base)
        else:
            front_source = front_base
        if filter_constraints:
            front_source = apply_constraints(front_source, constraints)
        front = pair_pareto_front(front_source, x_metric, y_metric, directions)
        if not values_for(sliced["background"], x_metric, y_metric):
            continue
        plotted.append((run_index, run, sliced, front))

    if not plotted:
        return False

    fig, ax = plt.subplots(figsize=(8.8, 5.4), constrained_layout=True)
    apply_axis_scales(ax, x_metric, y_metric)
    if limits:
        ax.set_xlim(*limits[0])
        ax.set_ylim(*limits[1])
    if shade_constraint_region:
        draw_constraint_region(ax, x_metric, y_metric, constraints)

    for run_index, run, sliced, front in plotted:
        color = run_color(run_index, len(runs))
        if shade_frontier_region:
            draw_frontier_region(
                ax,
                front,
                x_metric,
                y_metric,
                directions,
                color=color,
                alpha=frontier_region_alpha,
                label=f"{run['label']} dominated area",
            )

        if not hide_history:
            history_values = values_for(sliced["background"], x_metric, y_metric)
            if history_values:
                ax.scatter(
                    [item[0] for item in history_values],
                    [item[1] for item in history_values],
                    s=7,
                    color=color,
                    alpha=0.12,
                    linewidths=0,
                    label=f"{run['label']} history",
                )

        if sliced["population"] and not hide_generation_population:
            population_values = values_for(sliced["population"], x_metric, y_metric)
            if population_values:
                ax.scatter(
                    [item[0] for item in population_values],
                    [item[1] for item in population_values],
                    s=20,
                    facecolors="none",
                    edgecolors=color,
                    alpha=0.92,
                    linewidths=0.75,
                    zorder=2.25,
                    label=f"{run['label']} population",
                )

        valid_source = sliced["valid"]
        if filter_constraints:
            valid_source = apply_constraints(valid_source, constraints)
        valid_values = values_for(valid_source, x_metric, y_metric)
        if valid_values and not hide_valid_overlay:
            ax.scatter(
                [item[0] for item in valid_values],
                [item[1] for item in valid_values],
                s=10,
                color=color,
                alpha=0.28,
                linewidths=0,
                label=f"{run['label']} valid",
            )

        draw_frontier_step_line(
            ax,
            front,
            x_metric,
            y_metric,
            directions,
            color=color,
            label=f"{run['label']} frontier",
        )

    ax.set_xlabel(axis_label(x_metric, directions))
    ax.set_ylabel(axis_label(y_metric, directions))
    record_text = ", ".join(
        f"{run['label']} {sliced['end_index']:,}{' partial' if sliced['partial'] else ''}"
        for _, run, sliced, _ in plotted
    )
    ax.set_title(f"Generation {generation:04d} | {record_text}")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return True


def main():
    args = parse_args()
    pairs = parse_pairs(args.pairs)
    constraints = build_constraints(args)
    used_labels = set()
    labels = args.labels or [
        default_label(run_root, used_labels)
        for run_root in args.run_roots
    ]
    runs = load_runs(
        args.run_roots,
        labels,
        args.include_partial,
        args.generation_step,
        args.max_generations,
        args.generation_source,
        args.generations_dirs,
    )
    directions = compatible_directions(runs, pairs)
    generations = selected_generations(runs, args.generation_mode)
    if not generations:
        raise SystemExit("No comparable generation checkpoints were found")

    all_records = []
    for run in runs:
        all_records.extend(run["records"])
    limits = axis_limits(all_records, pairs)
    output_root = Path(args.output_dir)

    written = []
    for generation in generations:
        for x_metric, y_metric in pairs:
            output_path = (
                output_root
                / pair_slug(x_metric, y_metric)
                / f"generation_{generation:04d}.png"
            )
            if plot_snapshot(
                runs=runs,
                generation=generation,
                x_metric=x_metric,
                y_metric=y_metric,
                directions=directions,
                constraints=constraints,
                filter_constraints=args.filter_constraints,
                shade_constraint_region=args.shade_constraint_region,
                shade_frontier_region=args.shade_frontier_region,
                frontier_region_alpha=args.frontier_region_alpha,
                hide_history=args.hide_history,
                hide_valid_overlay=args.hide_valid_overlay,
                hide_generation_population=args.hide_generation_population,
                record_scope=args.record_scope,
                limits=limits.get((x_metric, y_metric)),
                output_path=output_path,
                dpi=args.dpi,
            ):
                written.append(output_path)

    print(f"Runs compared: {len(runs):,}")
    for run in runs:
        print(
            f"- {run['label']}: {run['run_root']} "
            f"({len(run['records']):,} history records, "
            f"{len(run['checkpoints']):,} {run['generation_source']} checkpoints)"
        )
    print(f"Generation mode: {args.generation_mode}")
    print(f"Generations plotted: {len(generations):,}")
    print(f"Metric pairs plotted: {len(pairs):,}")
    print(f"Snapshots written: {len(written):,}")
    if written:
        print(f"Output root: {output_root}")


if __name__ == "__main__":
    main()
