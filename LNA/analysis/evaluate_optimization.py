#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path

from optimization_data import (
    objective_specs_from_config,
    objective_vector,
    passes_constraints,
    read_run,
    valid_records,
)


DEFAULT_REFERENCE_MARGIN = 0.1


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Compare optimization Pareto-front quality across multiple run roots. "
            "Indicators are computed in normalized minimization objective space."
        )
    )
    parser.add_argument("run_roots", nargs="+")
    parser.add_argument(
        "--labels",
        nargs="+",
        help="Optional labels for the run roots. Must match the number of runs.",
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--max-nf-db", type=float)
    parser.add_argument("--max-power-dbm", "--max-power", dest="max_power_dbm", type=float)
    parser.add_argument("--min-s21-db", "--min-gain-db", dest="min_s21_db", type=float)
    parser.add_argument("--min-f-bw", type=float)
    parser.add_argument("--max-s11-db", type=float)
    parser.add_argument(
        "--record-scope",
        choices=("valid", "all"),
        default="valid",
        help=(
            "Use optimizer-valid records only, or use all history records that "
            "have finite objective metrics and let analysis constraints decide "
            "which records are feasible."
        ),
    )
    parser.add_argument(
        "--hypervolume-samples",
        "--hv-samples",
        dest="hypervolume_samples",
        type=int,
        default=50000,
        help=(
            "Monte Carlo samples for hypervolume when there are more than two "
            "objectives. Use a larger value for a more stable estimate."
        ),
    )
    parser.add_argument("--hypervolume-seed", "--hv-seed", dest="hypervolume_seed", type=int, default=1)
    parser.add_argument(
        "--reference-point",
        help=(
            "Comma-separated normalized minimization reference point. "
            "Default is 1.1 on every objective."
        ),
    )
    parser.add_argument(
        "--gd-power",
        type=float,
        default=2.0,
        help="Distance power for GD and IGD. The default computes RMS distance.",
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


def default_label(run_root, used):
    label = Path(run_root).name or str(run_root)
    if label not in used:
        used.add(label)
        return label
    suffix = 2
    while f"{label}_{suffix}" in used:
        suffix += 1
    label = f"{label}_{suffix}"
    used.add(label)
    return label


def dominates_vector(left, right):
    return (
        all(left_value <= right_value for left_value, right_value in zip(left, right))
        and any(left_value < right_value for left_value, right_value in zip(left, right))
    )


def pareto_items(items):
    front = []
    for item in items:
        vector = item["vector"]
        if any(dominates_vector(existing["vector"], vector) for existing in front):
            continue
        front = [
            existing
            for existing in front
            if not dominates_vector(vector, existing["vector"])
        ]
        front.append(item)
    return front


def squared_distance(left, right):
    return sum((left_value - right_value) ** 2 for left_value, right_value in zip(left, right))


def distance(left, right):
    return math.sqrt(squared_distance(left, right))


def unique_points(points):
    seen = set()
    unique = []
    for point in points:
        key = tuple(round(value, 15) for value in point)
        if key in seen:
            continue
        seen.add(key)
        unique.append(point)
    return unique


def normalize_point(point, ideal, nadir):
    normalized = []
    for value, low, high in zip(point, ideal, nadir):
        span = high - low
        normalized.append(0.0 if span == 0 else (value - low) / span)
    return tuple(normalized)


def normalization_bounds(points):
    objective_count = len(points[0])
    ideal = [
        min(point[index] for point in points)
        for index in range(objective_count)
    ]
    nadir = [
        max(point[index] for point in points)
        for index in range(objective_count)
    ]
    return ideal, nadir


def exact_hypervolume_1d(points, reference_point):
    best = min(point[0] for point in points)
    return max(0.0, reference_point[0] - best)


def exact_hypervolume_2d(points, reference_point):
    front = pareto_items([{"vector": point} for point in points])
    ordered = sorted((item["vector"] for item in front), key=lambda point: point[0])
    volume = 0.0
    previous_y = reference_point[1]
    for x_value, y_value in ordered:
        if y_value >= previous_y:
            continue
        volume += max(0.0, reference_point[0] - x_value) * max(0.0, previous_y - y_value)
        previous_y = y_value
    return volume


def monte_carlo_hypervolume(points, reference_point, sample_count, rng):
    if sample_count <= 0:
        return None
    box_volume = math.prod(reference_point)
    dominated = 0
    for _ in range(sample_count):
        sample = tuple(rng.random() * limit for limit in reference_point)
        if any(
            all(point_value <= sample_value for point_value, sample_value in zip(point, sample))
            for point in points
        ):
            dominated += 1
    return box_volume * dominated / sample_count


def hypervolume(points, reference_point, sample_count, rng):
    points = [
        point
        for point in unique_points(points)
        if all(value <= limit for value, limit in zip(point, reference_point))
    ]
    if not points:
        return None
    dimensions = len(reference_point)
    if dimensions == 1:
        return exact_hypervolume_1d(points, reference_point)
    if dimensions == 2:
        return exact_hypervolume_2d(points, reference_point)
    return monte_carlo_hypervolume(points, reference_point, sample_count, rng)


def nearest_distances(points, reference_points):
    if not points or not reference_points:
        return []
    return [
        min(distance(point, reference) for reference in reference_points)
        for point in points
    ]


def generational_distance(points, reference_points, power):
    distances = nearest_distances(points, reference_points)
    if not distances:
        return None
    return (sum(value ** power for value in distances) / len(distances)) ** (1.0 / power)


def spacing(points):
    points = unique_points(points)
    if len(points) < 2:
        return None, None
    nearest = [
        min(distance(point, other) for other in points if other is not point)
        for point in points
    ]
    mean = sum(nearest) / len(nearest)
    if len(nearest) == 1:
        return 0.0, mean
    variance = sum((value - mean) ** 2 for value in nearest) / (len(nearest) - 1)
    return math.sqrt(variance), mean


def extreme_points(reference_points):
    if not reference_points:
        return []
    extremes = []
    for index in range(len(reference_points[0])):
        best = min(reference_points, key=lambda point: point[index])
        if best not in extremes:
            extremes.append(best)
    return extremes


def spread_delta(points, reference_points):
    points = unique_points(points)
    reference_points = unique_points(reference_points)
    if len(points) < 2 or not reference_points:
        return None

    nearest = [
        min(distance(point, other) for other in points if other is not point)
        for point in points
    ]
    mean_nearest = sum(nearest) / len(nearest)
    extreme_distance_sum = sum(
        min(distance(extreme, point) for point in points)
        for extreme in extreme_points(reference_points)
    )
    numerator = extreme_distance_sum + sum(abs(value - mean_nearest) for value in nearest)
    denominator = extreme_distance_sum + len(nearest) * mean_nearest
    if denominator == 0:
        return 0.0
    return numerator / denominator


def parse_reference_point(text, objective_count):
    if not text:
        return tuple(1.0 + DEFAULT_REFERENCE_MARGIN for _ in range(objective_count))
    values = tuple(float(item.strip()) for item in text.split(",") if item.strip())
    if len(values) != objective_count:
        raise ValueError(
            f"--reference-point has {len(values)} values, expected {objective_count}"
        )
    if any(value <= 0 for value in values):
        raise ValueError("--reference-point values must be positive in normalized space")
    return values


def record_pool(records, constraints, objectives, record_scope):
    if record_scope == "valid":
        candidates = valid_records(records)
    else:
        candidates = records

    feasible = []
    for record in candidates:
        vector = objective_vector(record, objectives)
        if vector is None:
            continue
        if not passes_constraints(record, constraints):
            continue
        feasible.append((record, vector))
    return feasible


def load_run_front(run_root, label, constraints, record_scope, expected_objectives=None):
    run = read_run(run_root)
    objectives = objective_specs_from_config(run["config"])
    if expected_objectives is not None and objectives != expected_objectives:
        raise ValueError(
            f"Objective mismatch for {run_root}. Expected {expected_objectives}, got {objectives}"
        )

    feasible = record_pool(run["records"], constraints, objectives, record_scope)
    items = []
    for record, vector in feasible:
        item = {
            "label": label,
            "run_root": str(run["run_root"]),
            "record": record,
            "vector": vector,
        }
        items.append(item)

    front = pareto_items(items)
    return {
        "label": label,
        "run_root": str(run["run_root"]),
        "algorithm": run["config"].get("algorithm"),
        "planned_simulations": run["config"].get("planned_simulations"),
        "records": run["records"],
        "optimizer_valid_records": valid_records(run["records"]),
        "feasible_records": [record for record, _ in feasible],
        "front": front,
        "objectives": objectives,
    }


def format_number(value):
    if value is None:
        return "None"
    return f"{value:.6g}"


def write_outputs(output_dir, report, rows):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "front_quality_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    if rows:
        with (output_dir / "front_quality_summary.csv").open("w", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main():
    args = parse_args()
    if args.labels is not None and len(args.labels) != len(args.run_roots):
        raise ValueError("--labels must have the same number of entries as run_roots")
    if args.hypervolume_samples < 0:
        raise ValueError("--hypervolume-samples must be non-negative")
    if args.gd_power <= 0:
        raise ValueError("--gd-power must be positive")

    constraints = build_constraints(args)
    used_labels = set()
    labels = args.labels or [
        default_label(run_root, used_labels)
        for run_root in args.run_roots
    ]

    runs = []
    expected_objectives = None
    for run_root, label in zip(args.run_roots, labels):
        run = load_run_front(
            run_root,
            label,
            constraints,
            args.record_scope,
            expected_objectives,
        )
        expected_objectives = run["objectives"]
        runs.append(run)

    all_front_items = [
        item
        for run in runs
        for item in run["front"]
    ]
    if not all_front_items:
        raise ValueError("No valid Pareto-front records found in the provided runs")

    combined_front = pareto_items(all_front_items)
    all_points = [item["vector"] for item in all_front_items]
    ideal, nadir = normalization_bounds(all_points)
    reference_point = parse_reference_point(args.reference_point, len(expected_objectives))
    reference_points = [
        normalize_point(item["vector"], ideal, nadir)
        for item in combined_front
    ]
    reference_points = unique_points(reference_points)

    combined_ids = {
        (item["label"], item["record"].get("evaluation_id"))
        for item in combined_front
    }

    rows = []
    report_runs = []
    for run_index, run in enumerate(runs):
        rng = random.Random(args.hypervolume_seed + run_index)
        points = [
            normalize_point(item["vector"], ideal, nadir)
            for item in run["front"]
        ]
        points = unique_points(points)
        spacing_value, mean_nearest = spacing(points)
        hv = hypervolume(points, reference_point, args.hypervolume_samples, rng)
        gd = generational_distance(points, reference_points, args.gd_power)
        igd = generational_distance(reference_points, points, args.gd_power)
        spread = spread_delta(points, reference_points)
        contribution = sum(
            1
            for item in run["front"]
            if (item["label"], item["record"].get("evaluation_id")) in combined_ids
        )

        row = {
            "label": run["label"],
            "run_root": run["run_root"],
            "algorithm": run["algorithm"],
            "planned_simulations": run["planned_simulations"],
            "history_records": len(run["records"]),
            "optimizer_valid_records": len(run["optimizer_valid_records"]),
            "feasible_records": len(run["feasible_records"]),
            "pareto_records": len(run["front"]),
            "combined_pareto_contribution": contribution,
            "hypervolume": hv,
            "generational_distance": gd,
            "inverse_generational_distance": igd,
            "spacing": spacing_value,
            "mean_nearest_neighbor_distance": mean_nearest,
            "spread_delta": spread,
        }
        rows.append(row)
        report_runs.append(row)

    report = {
        "objectives": expected_objectives,
        "constraints": constraints,
        "record_scope": args.record_scope,
        "normalization": {
            "space": "minimization",
            "ideal": ideal,
            "nadir": nadir,
            "reference_point": reference_point,
        },
        "hypervolume": {
            "method": "exact" if len(reference_point) <= 2 else "monte_carlo",
            "samples": args.hypervolume_samples if len(reference_point) > 2 else None,
            "seed": args.hypervolume_seed if len(reference_point) > 2 else None,
            "larger_is_better": True,
        },
        "generational_distance": {
            "power": args.gd_power,
            "reference_front": "combined non-dominated front from all provided runs",
            "smaller_is_better": True,
        },
        "spread": {
            "spacing": "standard deviation of nearest-neighbor distances; smaller is more uniform",
            "spread_delta": "Deb-style spread using combined-front extremes; smaller is better",
        },
        "combined_pareto_size": len(combined_front),
        "runs": report_runs,
    }

    print("Reference front: combined non-dominated front from provided runs")
    objective_text = ", ".join(
        f"{item['name']}:{item['direction']}"
        for item in expected_objectives
    )
    print(f"Objectives: {objective_text}")
    print(f"Combined Pareto size: {len(combined_front)}")
    if len(reference_point) > 2:
        print(f"Hypervolume: Monte Carlo estimate with {args.hypervolume_samples} samples")
    print("")
    print(
        "label | feasible | opt_valid | pareto | combined | hypervolume | GD | IGD | spacing | spread_delta"
    )
    for row in rows:
        print(
            f"{row['label']} | "
            f"{row['feasible_records']} | "
            f"{row['optimizer_valid_records']} | "
            f"{row['pareto_records']} | "
            f"{row['combined_pareto_contribution']} | "
            f"{format_number(row['hypervolume'])} | "
            f"{format_number(row['generational_distance'])} | "
            f"{format_number(row['inverse_generational_distance'])} | "
            f"{format_number(row['spacing'])} | "
            f"{format_number(row['spread_delta'])}"
        )

    if args.output_dir:
        write_outputs(args.output_dir, report, rows)
        print(f"Wrote performance outputs to: {Path(args.output_dir)}")


if __name__ == "__main__":
    main()
