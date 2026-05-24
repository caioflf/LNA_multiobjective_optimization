from __future__ import annotations

from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics


METRIC_NAMES = (
    "NF_db",
    "NFmin_db",
    "power_dBm",
    "S21_db",
    "F_BW",
    "S11_db",
)
NETWORK_ROLES = ("gate", "source", "load", "feedback")
RLC_AXES = ("r", "l", "c")
DEFAULT_OBJECTIVES = (
    {"name": "NF_db", "direction": "min"},
    {"name": "power_dBm", "direction": "min"},
    {"name": "S21_db", "direction": "max"},
    {"name": "F_BW", "direction": "max"},
    {"name": "S11_db", "direction": "min"},
)


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def load_history(run_root):
    history_path = Path(run_root) / "optimization_history.jsonl"
    if not history_path.exists():
        raise FileNotFoundError(f"Missing optimization history: {history_path}")

    records = []
    skipped_lines = []
    for line_number, line in enumerate(history_path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            skipped_lines.append({"line": line_number, "error": str(exc)})
    return records, skipped_lines


def read_run(run_root):
    run_root = Path(run_root)
    records, skipped_lines = load_history(run_root)
    return {
        "run_root": run_root,
        "records": records,
        "skipped_history_lines": skipped_lines,
        "config": load_json(run_root / "optimization_config.json", default={}) or {},
        "summary": load_json(run_root / "optimization_summary.json", default={}) or {},
        "saved_pareto": load_json(run_root / "pareto_front.json", default=[]) or [],
    }


def canonical_metric_name(metric_name):
    if metric_name in {"power", "power_mw"}:
        return "power_dBm"
    if metric_name == "gain_db":
        return "S21_db"
    return metric_name


def objective_specs_from_config(config):
    objectives = config.get("objectives") or DEFAULT_OBJECTIVES
    return [
        {
            "name": canonical_metric_name(item["name"]),
            "direction": item.get("direction", "min"),
        }
        for item in objectives
    ]


def safe_float(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def metric_value(record, metric_name):
    metrics = record.get("metrics") or {}
    value = safe_float(metrics.get(metric_name))
    if value is not None:
        return value

    # Compatibility with older runs that wrote gain_db and power in watts.
    if metric_name == "S21_db":
        return safe_float(metrics.get("gain_db"))
    if metric_name == "gain_db":
        return safe_float(metrics.get("S21_db"))
    if metric_name == "power_mw":
        value = safe_float(metrics.get("power_dBm"))
        if value is not None:
            return 10 ** (value / 10.0)
        value = safe_float(metrics.get("power"))
        return None if value is None else value * 1000.0
    if metric_name == "power_dBm":
        value = safe_float(metrics.get("power_mw"))
        if value is None:
            value = safe_float(metrics.get("power"))
            value = None if value is None else value * 1000.0
        if value is None or value <= 0:
            return None
        return 10 * math.log10(value)
    if metric_name == "power":
        value = safe_float(metrics.get("power_mw"))
        return None if value is None else value / 1000.0
    return None


def status_counts(records):
    return dict(sorted(Counter(record.get("status", "unknown") for record in records).items()))


def valid_records(records):
    return [record for record in records if record.get("valid") is True]


def metric_stats(records, metric_names=METRIC_NAMES):
    stats = {}
    for metric_name in metric_names:
        values = [
            metric_value(record, metric_name)
            for record in records
        ]
        values = [value for value in values if value is not None]
        if not values:
            stats[metric_name] = {"count": 0}
            continue
        stats[metric_name] = {
            "count": len(values),
            "min": min(values),
            "median": statistics.median(values),
            "max": max(values),
        }
    return stats


def objective_vector(record, objectives):
    vector = []
    for objective in objectives:
        value = metric_value(record, objective["name"])
        if value is None:
            return None
        if objective.get("direction", "min") == "max":
            value = -value
        vector.append(value)
    return tuple(vector)


def dominates(left_vector, right_vector):
    return (
        all(left <= right for left, right in zip(left_vector, right_vector))
        and any(left < right for left, right in zip(left_vector, right_vector))
    )


def non_dominated_front(records, objectives):
    vectors = {
        index: objective_vector(record, objectives)
        for index, record in enumerate(records)
    }
    vectors = {
        index: vector
        for index, vector in vectors.items()
        if vector is not None
    }
    front = []
    for left_index, left_vector in vectors.items():
        dominated = False
        for right_index, right_vector in vectors.items():
            if left_index == right_index:
                continue
            if dominates(right_vector, left_vector):
                dominated = True
                break
        if not dominated:
            front.append(records[left_index])
    return front


def constraint_limit(constraints, *names):
    for name in names:
        value = constraints.get(name)
        if value is not None:
            return value
    return None


def passes_constraints(record, constraints):
    checks = (
        (("max_nf_db",), "NF_db", lambda value, limit: value <= limit),
        (("max_power_dbm", "max_power"), "power_dBm", lambda value, limit: value <= limit),
        (("min_s21_db", "min_gain_db"), "S21_db", lambda value, limit: value >= limit),
        (("min_f_bw",), "F_BW", lambda value, limit: value >= limit),
        (("max_s11_db",), "S11_db", lambda value, limit: value <= limit),
    )
    for constraint_names, metric_name, predicate in checks:
        limit = constraint_limit(constraints, *constraint_names)
        if limit is None:
            continue
        value = metric_value(record, metric_name)
        if value is None or not predicate(value, limit):
            return False
    return True


def apply_constraints(records, constraints):
    return [
        record
        for record in records
        if passes_constraints(record, constraints)
    ]


def _best_by_metric(records, metric_name, *, maximize=False):
    candidates = [
        (metric_value(record, metric_name), record)
        for record in records
    ]
    candidates = [
        item
        for item in candidates
        if item[0] is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1] if maximize else min(candidates, key=lambda item: item[0])[1]


def _balanced_candidate(records, objectives):
    scored = []
    values_by_objective = []
    for objective in objectives:
        values = []
        for record in records:
            value = metric_value(record, objective["name"])
            if value is not None and objective.get("direction", "min") == "max":
                value = -value
            if value is not None:
                values.append(value)
        values_by_objective.append(values)

    for record in records:
        score = 0.0
        valid = True
        for objective, values in zip(objectives, values_by_objective):
            value = metric_value(record, objective["name"])
            if value is None:
                valid = False
                break
            if objective.get("direction", "min") == "max":
                value = -value
            low = min(values)
            high = max(values)
            score += 0.0 if high == low else (value - low) / (high - low)
        if valid:
            scored.append((score, record))
    if not scored:
        return None
    return min(scored, key=lambda item: item[0])[1]


def shortlist_records(records, objectives):
    picks = [
        ("lowest_nf", _best_by_metric(records, "NF_db")),
        ("lowest_power", _best_by_metric(records, "power_dBm")),
        ("highest_s21", _best_by_metric(records, "S21_db", maximize=True)),
        ("widest_bandwidth", _best_by_metric(records, "F_BW", maximize=True)),
        ("best_s11", _best_by_metric(records, "S11_db")),
        ("balanced", _balanced_candidate(records, objectives)),
    ]
    selected = []
    seen = set()
    for label, record in picks:
        if record is None:
            continue
        evaluation_id = record.get("evaluation_id")
        if evaluation_id in seen:
            continue
        seen.add(evaluation_id)
        selected.append({"label": label, "record": record})
    return selected


def normalized_objective_score(record, records, objectives):
    score = 0.0
    used = 0
    for objective in objectives:
        metric_name = objective["name"]
        values = [
            metric_value(candidate, metric_name)
            for candidate in records
        ]
        values = [value for value in values if value is not None]
        value = metric_value(record, metric_name)
        if value is None or not values:
            continue
        if objective.get("direction", "min") == "max":
            value = -value
            values = [-candidate for candidate in values]
        low = min(values)
        high = max(values)
        score += 0.0 if high == low else (value - low) / (high - low)
        used += 1
    if used == 0:
        return None
    return score / used


def ranked_records(records, objectives):
    ranked = []
    for record in records:
        score = normalized_objective_score(record, records, objectives)
        if score is None:
            continue
        ranked.append((score, record))
    ranked.sort(key=lambda item: item[0])
    return ranked


def top_ranked_records(records, objectives, count):
    return ranked_records(records, objectives)[:count]


def flatten_record(record, *, tag=None, score=None, rank=None):
    candidate = record.get("candidate") or {}
    transistor_indexes = candidate.get("transistor_indexes") or {}
    transistor_parameters = candidate.get("transistor_parameters") or {}
    networks = candidate.get("networks") or {}

    row = {
        "tag": tag,
        "rank": rank,
        "score": score,
        "evaluation_id": record.get("evaluation_id"),
        "status": record.get("status"),
        "valid": record.get("valid"),
        "constraint_violation_score": record.get("constraint_violation_score"),
        "constraint_violation_count": record.get("constraint_violation_count"),
        "circuit_dir": record.get("circuit_dir"),
        "error": record.get("error"),
        "transistor": candidate.get("transistor"),
        "transistor_available": candidate.get("transistor_available"),
        "device_type_index": transistor_indexes.get("device_type_index"),
        "vt_index": transistor_indexes.get("vt_index"),
        "wtot_index": transistor_indexes.get("wtot_index"),
        "length_index": transistor_indexes.get("length_index"),
        "device_type": transistor_parameters.get("device_type"),
        "threshold": transistor_parameters.get("threshold"),
        "wtot_um": transistor_parameters.get("wtot_um"),
        "length_um": transistor_parameters.get("length_um"),
        "m": transistor_parameters.get("m"),
        "unit_width_um": transistor_parameters.get("unit_width_um"),
        "vg": candidate.get("vg"),
    }
    for metric_name in METRIC_NAMES:
        row[metric_name] = metric_value(record, metric_name)
    for role in NETWORK_ROLES:
        network = networks.get(role) or {}
        passive_indexes = network.get("passive_indexes") or {}
        row[f"{role}_identifier"] = network.get("identifier")
        for axis in RLC_AXES:
            row[f"{role}_{axis}_index"] = passive_indexes.get(axis)
    return row


def write_csv(path, records, *, tag=None):
    rows = [flatten_record(record, tag=tag) for record in records]
    if not rows:
        Path(path).write_text("")
        return
    fieldnames = list(rows[0])
    with Path(path).open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
