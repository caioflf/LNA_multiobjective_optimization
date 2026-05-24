from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import math
import random
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.database.transistors import GROUPS as TRANSISTOR_GROUPS
from src.scripts.netlist_generator import (
    DEFAULT_NETWORK_DATABASE_PATH,
    OPEN_RLC_PARALLEL_IDENTIFIER,
    create_circuit_bundle,
    load_network_database,
    resolve_ac_sweep_bounds,
)
from src.scripts.simulate_circuits import (
    DEFAULT_ANALYSIS_FILENAME,
    DEFAULT_LOG_FILENAME,
    DEFAULT_MEASURE_FILENAME,
    DEFAULT_SIMULATION_PRIORITY,
    PRIORITY_NICE_VALUES,
    analyze_circuit_measures,
    run_circuit_simulation,
)


DEFAULT_OBJECTIVES = "NF_db:min,power_dBm:min,S21_db:max,F_BW:max,S11_db:min"
GENE_NAMES = (
    "device_type",
    "vt",
    "wtot",
    "length",
    "vg",
    "gate",
    "source",
    "load",
    "feedback",
)
NETWORK_ROLES = ("gate", "source", "load", "feedback")
RLC_AXES = ("r", "l", "c")
PENALTY_OBJECTIVE = 1e99
DEVICE_TYPES = ("nmos", "pmos")
THRESHOLDS = ("standard", "lvt")

TRANSISTOR_GROUP_ALIASES = {
    "nmos": "nmos",
    "nmos_lvt": "nmos_lvt",
    "lvt": "nmos_lvt",
    "nmos_and_lvt": "nmos_and_lvt",
    "all": "all",
}


def current_timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def format_elapsed(seconds):
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def resolve_transistor_group(group_name):
    normalized = TRANSISTOR_GROUP_ALIASES[group_name]
    if normalized == "nmos_and_lvt":
        return TRANSISTOR_GROUPS["nmos"] + TRANSISTOR_GROUPS["nmos_lvt"]
    return TRANSISTOR_GROUPS[normalized]


def transistor_total_width_um(transistor):
    return round(float(transistor.fingers) * float(transistor.width_um), 12)


def transistor_key(transistor, transistor_axes):
    return (
        transistor_axes["device_type_lookup"][transistor.device_type],
        transistor_axes["threshold_lookup"][transistor.threshold],
        transistor_axes["wtot_lookup"][transistor_total_width_um(transistor)],
        transistor_axes["length_lookup"][transistor.length_um],
    )


def build_transistor_axes(transistors):
    wtot_values = sorted({transistor_total_width_um(transistor) for transistor in transistors})
    length_values = sorted({float(transistor.length_um) for transistor in transistors})
    axes = {
        "device_type": [
            {"index": index, "value": value}
            for index, value in enumerate(DEVICE_TYPES)
        ],
        "threshold": [
            {"index": index, "value": value, "is_lvt": value == "lvt"}
            for index, value in enumerate(THRESHOLDS)
        ],
        "wtot_um": [
            {"index": index, "value": value}
            for index, value in enumerate(wtot_values)
        ],
        "length_um": [
            {"index": index, "value": value}
            for index, value in enumerate(length_values)
        ],
        "device_type_lookup": {value: index for index, value in enumerate(DEVICE_TYPES)},
        "threshold_lookup": {value: index for index, value in enumerate(THRESHOLDS)},
        "wtot_lookup": {value: index for index, value in enumerate(wtot_values)},
        "length_lookup": {value: index for index, value in enumerate(length_values)},
    }
    models_by_key = {}
    model_entries = []
    for transistor in transistors:
        key = transistor_key(transistor, axes)
        if key in models_by_key:
            raise ValueError(f"Duplicate transistor parameter key for {transistor.name}")
        models_by_key[key] = transistor
        model_entries.append(
            {
                "name": transistor.name,
                "device_type": transistor.device_type,
                "threshold": transistor.threshold,
                "m": transistor.fingers,
                "width_um": transistor.width_um,
                "wtot_um": transistor_total_width_um(transistor),
                "length_um": transistor.length_um,
                "parameter_indexes": {
                    "device_type_index": key[0],
                    "vt_index": key[1],
                    "wtot_index": key[2],
                    "length_index": key[3],
                },
            }
        )
    axes["models"] = model_entries
    axes["models_by_key"] = models_by_key
    axes["valid_model_keys"] = sorted(models_by_key)
    return axes


def build_float_sweep(start, stop, step, *, ndigits=12):
    if step <= 0:
        raise ValueError("Sweep step must be positive")
    if stop < start:
        raise ValueError("Sweep stop must be greater than or equal to start")

    values = []
    current = start
    tolerance = step * 1e-9
    while current <= stop + tolerance:
        values.append(round(current, ndigits))
        current += step
    return values


def parse_objectives(objective_text):
    objectives = []
    for item in objective_text.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            name, direction = item.split(":", 1)
        else:
            name, direction = item, "min"
        name = name.strip()
        direction = direction.strip().lower()
        if direction not in {"min", "max"}:
            raise ValueError(f"Invalid direction for objective {name}: {direction}")
        objectives.append({"name": name, "direction": direction})
    if not objectives:
        raise ValueError("At least one objective is required")
    return objectives


def objective_vector(metrics, objectives):
    vector = []
    missing = []
    for objective in objectives:
        name = objective["name"]
        raw_value = metrics.get(name)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            vector.append(PENALTY_OBJECTIVE)
            missing.append(name)
            continue
        if not math.isfinite(value):
            vector.append(PENALTY_OBJECTIVE)
            missing.append(name)
            continue
        vector.append(value if objective["direction"] == "min" else -value)
    return vector, missing


def violation_amount(value, operator, limit):
    try:
        value = float(value)
        limit = float(limit)
    except (TypeError, ValueError):
        return PENALTY_OBJECTIVE
    if value is None or not math.isfinite(value):
        return PENALTY_OBJECTIVE
    if not math.isfinite(limit):
        return PENALTY_OBJECTIVE
    if operator in {"<", "<="}:
        amount = max(0.0, value - limit)
        return 1e-30 if operator == "<" and amount == 0 else amount
    if operator in {">", ">="}:
        amount = max(0.0, limit - value)
        return 1e-30 if operator == ">" and amount == 0 else amount
    return PENALTY_OBJECTIVE


def total_constraint_violation(violations):
    total = 0.0
    for violation in violations:
        amount = violation.get("violation_amount")
        if amount is None:
            amount = violation_amount(
                violation.get("value"),
                violation.get("operator"),
                violation.get("limit"),
            )
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = PENALTY_OBJECTIVE
        if not math.isfinite(amount):
            amount = PENALTY_OBJECTIVE
        total += amount
    return total


def record_constraint_violation_score(record):
    if record.get("valid") is True:
        return 0.0
    raw_score = record.get("constraint_violation_score")
    if raw_score is not None:
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = PENALTY_OBJECTIVE
        if math.isfinite(score):
            return score
    violations = record.get("constraint_violations") or []
    if violations:
        return total_constraint_violation(violations)
    return PENALTY_OBJECTIVE


def build_hard_constraints(args):
    constraints = [
        {"name": "NF_db", "operator": "<=", "limit": args.max_nf_db},
        {"name": "power_dBm", "operator": "<=", "limit": args.max_power_dbm},
        {"name": "S21_db", "operator": ">=", "limit": args.min_s21_db},
        {"name": "F_BW", "operator": ">=", "limit": args.min_f_bw},
        {"name": "S11_db", "operator": "<=", "limit": args.max_s11_db},
    ]
    return [
        constraint
        for constraint in constraints
        if constraint["limit"] is not None
    ]


def hard_constraint_violations(metrics, constraints):
    violations = []
    for constraint in constraints:
        name = constraint["name"]
        operator = constraint["operator"]
        limit = float(constraint["limit"])
        raw_value = metrics.get(name)
        value = None
        if raw_value is not None:
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                value = None
        if value is None or not math.isfinite(value):
            violations.append(
                {
                    "name": name,
                    "operator": operator,
                    "limit": limit,
                    "value": raw_value,
                    "reason": "missing_or_nonfinite",
                    "violation_amount": PENALTY_OBJECTIVE,
                }
            )
            continue
        passed = value <= limit if operator == "<=" else value >= limit
        if not passed:
            violations.append(
                {
                    "name": name,
                    "operator": operator,
                    "limit": limit,
                    "value": value,
                    "reason": "outside_limit",
                    "violation_amount": violation_amount(value, operator, limit),
                }
            )
    return violations


def load_network_payload(database_path):
    database_path = Path(database_path)
    payload = json.loads(database_path.read_text())
    if isinstance(payload, dict):
        return payload, payload["networks"]
    return {"networks": payload}, payload


def ensure_open_rlc_network(networks):
    if any(network["identifier"] == OPEN_RLC_PARALLEL_IDENTIFIER for network in networks):
        return networks
    return [
        {
            "identifier": OPEN_RLC_PARALLEL_IDENTIFIER,
            "topology": "rlc_parallel",
            "netlist": "open",
            "estimated_area_um2": 0.0,
            "elements": [],
            "passive_indexes": {"r": 0, "l": 0, "c": 0},
        },
        *networks,
    ]


def available_index_values(payload, networks):
    index_definitions = payload.get("index_definitions") or {}
    available = {}
    for axis in RLC_AXES:
        if axis in index_definitions:
            available[axis] = sorted(int(entry["index"]) for entry in index_definitions[axis])
        else:
            available[axis] = sorted(
                {
                    int((network.get("passive_indexes") or {}).get(axis, 0))
                    for network in networks
                }
            )
    return available


def parse_index_set(spec, available):
    available = set(int(value) for value in available)
    if spec is None or spec.strip().lower() == "all":
        return available

    selected = set()
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if ":" in token:
            start_text, stop_text = token.split(":", 1)
            start = min(available) if not start_text else int(start_text)
            stop = max(available) if not stop_text else int(stop_text)
            selected.update(range(start, stop + 1))
        else:
            selected.add(int(token))

    unknown = selected - available
    if unknown:
        raise ValueError(f"Unknown passive index value(s): {sorted(unknown)}")
    return selected


def network_matches_role_filter(network, role_filter):
    indexes = network.get("passive_indexes")
    if indexes is None:
        return True
    return all(int(indexes.get(axis, 0)) in role_filter[axis] for axis in RLC_AXES)


def build_role_filters(args, available):
    filters = {}
    for role in NETWORK_ROLES:
        filters[role] = {
            axis: parse_index_set(getattr(args, f"{role}_{axis}_indexes"), available[axis])
            for axis in RLC_AXES
        }
    return filters


def network_identifier(selection):
    if selection is None:
        return None
    if selection == "default":
        return "default"
    return selection["identifier"]


def network_passive_indexes(selection):
    if not isinstance(selection, dict):
        return None
    indexes = selection.get("passive_indexes")
    if indexes is None:
        return None
    return {axis: int(indexes.get(axis, 0)) for axis in RLC_AXES}


def is_open_rlc_network(selection):
    return (
        isinstance(selection, dict)
        and selection.get("identifier") == OPEN_RLC_PARALLEL_IDENTIFIER
    )


def build_role_choices(networks, role_filters, *, include_default, allow_source_none, allow_feedback_none):
    choices = {}
    for role in NETWORK_ROLES:
        role_choices = [
            network
            for network in networks
            if network_matches_role_filter(network, role_filters[role])
        ]
        if include_default and role in {"gate", "source", "load"}:
            role_choices.insert(0, "default")
        if role == "source" and allow_source_none:
            role_choices.insert(0, None)
        if role == "feedback" and allow_feedback_none:
            role_choices = [
                network
                for network in role_choices
                if not is_open_rlc_network(network)
            ]
            role_choices.insert(0, None)
        if not role_choices:
            raise ValueError(f"No choices available for {role} after optimizer constraints")
        choices[role] = role_choices
    return choices


def random_genome(space_sizes, rng):
    return tuple(rng.randrange(size) for size in space_sizes)


def mutate_genome(genome, space_sizes, mutation_probability, rng):
    mutated = list(genome)
    changed = False
    for index, size in enumerate(space_sizes):
        if size <= 1:
            continue
        if rng.random() <= mutation_probability:
            old_value = mutated[index]
            new_value = rng.randrange(size)
            while new_value == old_value and size > 1:
                new_value = rng.randrange(size)
            mutated[index] = new_value
            changed = True

    if not changed:
        mutable_indexes = [index for index, size in enumerate(space_sizes) if size > 1]
        if mutable_indexes:
            index = rng.choice(mutable_indexes)
            old_value = mutated[index]
            new_value = rng.randrange(space_sizes[index])
            while new_value == old_value and space_sizes[index] > 1:
                new_value = rng.randrange(space_sizes[index])
            mutated[index] = new_value
    return tuple(mutated)


def crossover_genomes(first, second, crossover_probability, rng):
    if rng.random() > crossover_probability:
        return first, second
    child_a = []
    child_b = []
    for left, right in zip(first, second):
        if rng.random() < 0.5:
            child_a.append(left)
            child_b.append(right)
        else:
            child_a.append(right)
            child_b.append(left)
    return tuple(child_a), tuple(child_b)


def dominates(first, second):
    first_valid = first.get("valid") is True
    second_valid = second.get("valid") is True
    if first_valid != second_valid:
        return first_valid
    if not first_valid and not second_valid:
        first_violation = record_constraint_violation_score(first)
        second_violation = record_constraint_violation_score(second)
        if first_violation != second_violation:
            return first_violation < second_violation

    first_vector = first["objectives"]
    second_vector = second["objectives"]
    return (
        all(left <= right for left, right in zip(first_vector, second_vector))
        and any(left < right for left, right in zip(first_vector, second_vector))
    )


def non_dominated_sort(records):
    dominates_map = {index: [] for index in range(len(records))}
    dominated_count = {index: 0 for index in range(len(records))}
    fronts = [[]]

    for left_index, left in enumerate(records):
        for right_index, right in enumerate(records):
            if left_index == right_index:
                continue
            if dominates(left, right):
                dominates_map[left_index].append(right_index)
            elif dominates(right, left):
                dominated_count[left_index] += 1
        if dominated_count[left_index] == 0:
            fronts[0].append(left_index)

    front_index = 0
    while fronts[front_index]:
        next_front = []
        for left_index in fronts[front_index]:
            for right_index in dominates_map[left_index]:
                dominated_count[right_index] -= 1
                if dominated_count[right_index] == 0:
                    next_front.append(right_index)
        front_index += 1
        fronts.append(next_front)

    return [[records[index] for index in front] for front in fronts if front]


def crowding_distances(front):
    if not front:
        return {}
    distances = {record["evaluation_id"]: 0.0 for record in front}
    objective_count = len(front[0]["objectives"])
    if len(front) <= 2:
        return {record["evaluation_id"]: math.inf for record in front}

    for objective_index in range(objective_count):
        ordered = sorted(front, key=lambda record: record["objectives"][objective_index])
        distances[ordered[0]["evaluation_id"]] = math.inf
        distances[ordered[-1]["evaluation_id"]] = math.inf
        low = ordered[0]["objectives"][objective_index]
        high = ordered[-1]["objectives"][objective_index]
        span = high - low
        if span == 0:
            continue
        for index in range(1, len(ordered) - 1):
            previous_value = ordered[index - 1]["objectives"][objective_index]
            next_value = ordered[index + 1]["objectives"][objective_index]
            distances[ordered[index]["evaluation_id"]] += (next_value - previous_value) / span
    return distances


def rank_and_crowding(records):
    fronts = non_dominated_sort(records)
    ranks = {}
    crowding = {}
    for rank, front in enumerate(fronts):
        front_crowding = crowding_distances(front)
        for record in front:
            ranks[record["evaluation_id"]] = rank
            crowding[record["evaluation_id"]] = front_crowding[record["evaluation_id"]]
    return ranks, crowding


def tournament_select(population, ranks, crowding, rng):
    first = rng.choice(population)
    second = rng.choice(population)
    first_rank = ranks[first["evaluation_id"]]
    second_rank = ranks[second["evaluation_id"]]
    if first_rank != second_rank:
        return first if first_rank < second_rank else second
    first_crowding = crowding[first["evaluation_id"]]
    second_crowding = crowding[second["evaluation_id"]]
    if first_crowding != second_crowding:
        return first if first_crowding > second_crowding else second
    return first if rng.random() < 0.5 else second


def generate_reference_directions(objective_count, partitions):
    if partitions <= 0:
        return [[1.0 / objective_count for _ in range(objective_count)]]

    directions = []

    def visit(remaining, slots, prefix):
        if slots == 1:
            directions.append(prefix + [remaining / partitions])
            return
        for value in range(remaining + 1):
            visit(remaining - value, slots - 1, prefix + [value / partitions])

    visit(partitions, objective_count, [])
    return directions


def normalize_objectives(records):
    objective_count = len(records[0]["objectives"])
    ideal = [
        min(record["objectives"][index] for record in records)
        for index in range(objective_count)
    ]
    nadir = [
        max(record["objectives"][index] for record in records)
        for index in range(objective_count)
    ]
    normalized = {}
    for record in records:
        values = []
        for index, value in enumerate(record["objectives"]):
            span = nadir[index] - ideal[index]
            values.append(0.0 if span == 0 else (value - ideal[index]) / span)
        normalized[record["evaluation_id"]] = values
    return normalized


def perpendicular_distance(point, direction):
    direction_norm = math.sqrt(sum(value * value for value in direction))
    if direction_norm == 0:
        return math.inf
    unit = [value / direction_norm for value in direction]
    projection = sum(value * axis for value, axis in zip(point, unit))
    residual = [
        value - projection * axis
        for value, axis in zip(point, unit)
    ]
    return math.sqrt(sum(value * value for value in residual))


def associate_reference_direction(record, normalized_objectives, reference_directions):
    point = normalized_objectives[record["evaluation_id"]]
    distances = [
        perpendicular_distance(point, direction)
        for direction in reference_directions
    ]
    best_index = min(range(len(distances)), key=lambda index: distances[index])
    return best_index, distances[best_index]


def select_split_front_by_reference_niching(selected, split_front, slots, partitions, rng):
    if slots <= 0:
        return []
    objective_count = len(split_front[0]["objectives"])
    reference_directions = generate_reference_directions(objective_count, partitions)
    normalized = normalize_objectives(selected + split_front)

    niche_counts = {index: 0 for index in range(len(reference_directions))}
    for record in selected:
        reference_index, _ = associate_reference_direction(
            record,
            normalized,
            reference_directions,
        )
        niche_counts[reference_index] += 1

    buckets = {index: [] for index in range(len(reference_directions))}
    for record in split_front:
        reference_index, distance = associate_reference_direction(
            record,
            normalized,
            reference_directions,
        )
        buckets[reference_index].append((distance, record))
    for bucket in buckets.values():
        bucket.sort(key=lambda item: item[0])

    chosen = []
    while len(chosen) < slots and any(buckets.values()):
        available_refs = [index for index, bucket in buckets.items() if bucket]
        min_count = min(niche_counts[index] for index in available_refs)
        least_crowded = [
            index for index in available_refs if niche_counts[index] == min_count
        ]
        rng.shuffle(least_crowded)
        picked_ref = least_crowded[0]
        if niche_counts[picked_ref] == 0:
            _, picked = buckets[picked_ref].pop(0)
        else:
            picked_index = rng.randrange(len(buckets[picked_ref]))
            _, picked = buckets[picked_ref].pop(picked_index)
        chosen.append(picked)
        niche_counts[picked_ref] += 1
    return chosen


def select_survivors_ngsa_iv(records, population_size, partitions, rng):
    records = unique_records(records)
    fronts = non_dominated_sort(records)
    selected = []
    for front in fronts:
        if len(selected) + len(front) <= population_size:
            selected.extend(front)
            continue
        slots = population_size - len(selected)
        selected.extend(
            select_split_front_by_reference_niching(
                selected,
                front,
                slots,
                partitions,
                rng,
            )
        )
        break
    return selected


def unique_records(records):
    unique = []
    seen = set()
    for record in records:
        genome = tuple(record["genome"])
        if genome in seen:
            continue
        seen.add(genome)
        unique.append(record)
    return unique


def compact_record(record):
    return {
        "evaluation_id": record["evaluation_id"],
        "status": record["status"],
        "valid": record["valid"],
        "genome": record["genome"],
        "candidate": record["candidate"],
        "metrics": record["metrics"],
        "objectives": record["objectives"],
        "missing_metrics": record["missing_metrics"],
        "constraint_violations": record.get("constraint_violations", []),
        "constraint_violation_score": record.get("constraint_violation_score", 0.0),
        "constraint_violation_count": record.get("constraint_violation_count", 0),
        "circuit_dir": record["circuit_dir"],
        "error": record.get("error"),
    }


class NgsaIvOptimizer:
    def __init__(
        self,
        *,
        output_root,
        transistor_axes,
        vg_values,
        role_choices,
        objectives,
        hard_constraints,
        netlist_kwargs,
        simulation_priority,
        simulation_timeout_seconds,
        fail_fast,
        rng,
        preserve_history=False,
    ):
        self.output_root = Path(output_root)
        self.transistor_axes = transistor_axes
        self.vg_values = vg_values
        self.role_choices = role_choices
        self.objectives = objectives
        self.hard_constraints = hard_constraints
        self.netlist_kwargs = netlist_kwargs
        self.simulation_priority = simulation_priority
        self.simulation_timeout_seconds = simulation_timeout_seconds
        self.fail_fast = fail_fast
        self.rng = rng
        self.cache = {}
        self.next_circuit_index = 1
        self.history_path = self.output_root / "optimization_history.jsonl"
        self._state_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._print_lock = threading.Lock()
        self.output_root.mkdir(parents=True, exist_ok=True)
        if not preserve_history:
            self.history_path.write_text("")

    @property
    def space_sizes(self):
        return (
            len(self.transistor_axes["device_type"]),
            len(self.transistor_axes["threshold"]),
            len(self.transistor_axes["wtot_um"]),
            len(self.transistor_axes["length_um"]),
            len(self.vg_values),
            len(self.role_choices["gate"]),
            len(self.role_choices["source"]),
            len(self.role_choices["load"]),
            len(self.role_choices["feedback"]),
        )

    def random_genome(self):
        transistor_key = self.rng.choice(self.transistor_axes["valid_model_keys"])
        return (
            *transistor_key,
            self.rng.randrange(len(self.vg_values)),
            self.rng.randrange(len(self.role_choices["gate"])),
            self.rng.randrange(len(self.role_choices["source"])),
            self.rng.randrange(len(self.role_choices["load"])),
            self.rng.randrange(len(self.role_choices["feedback"])),
        )

    def repair_genome(self, genome):
        genome = tuple(genome)
        transistor_key = genome[:4]
        if transistor_key in self.transistor_axes["models_by_key"]:
            return genome
        replacement_key = self.rng.choice(self.transistor_axes["valid_model_keys"])
        return (*replacement_key, *genome[4:])

    def decode_genome(self, genome):
        transistor_key = (genome[0], genome[1], genome[2], genome[3])
        transistor = self.transistor_axes["models_by_key"].get(transistor_key)
        return {
            "transistor": transistor,
            "transistor_key": transistor_key,
            "device_type_index": genome[0],
            "device_type": self.transistor_axes["device_type"][genome[0]]["value"],
            "vt_index": genome[1],
            "threshold": self.transistor_axes["threshold"][genome[1]]["value"],
            "wtot_index": genome[2],
            "wtot_um": self.transistor_axes["wtot_um"][genome[2]]["value"],
            "length_index": genome[3],
            "length_um": self.transistor_axes["length_um"][genome[3]]["value"],
            "vg": self.vg_values[genome[4]],
            "gate": self.role_choices["gate"][genome[5]],
            "source": self.role_choices["source"][genome[6]],
            "load": self.role_choices["load"][genome[7]],
            "feedback": self.role_choices["feedback"][genome[8]],
        }

    def candidate_summary(self, decoded):
        transistor = decoded["transistor"]
        return {
            "transistor": None if transistor is None else transistor.name,
            "transistor_available": transistor is not None,
            "transistor_indexes": {
                "device_type_index": decoded["device_type_index"],
                "vt_index": decoded["vt_index"],
                "wtot_index": decoded["wtot_index"],
                "length_index": decoded["length_index"],
            },
            "transistor_parameters": {
                "device_type": decoded["device_type"],
                "threshold": decoded["threshold"],
                "wtot_um": decoded["wtot_um"],
                "length_um": decoded["length_um"],
                "m": None if transistor is None else transistor.fingers,
                "unit_width_um": None if transistor is None else transistor.width_um,
            },
            "vg": decoded["vg"],
            "networks": {
                role: {
                    "identifier": network_identifier(decoded[role]),
                    "passive_indexes": network_passive_indexes(decoded[role]),
                }
                for role in NETWORK_ROLES
            },
        }

    def append_history(self, record):
        with self._history_lock:
            with self.history_path.open("a") as fp:
                fp.write(json.dumps(record) + "\n")

    def import_cached_records(self, records, *, write_history=True):
        imported = 0
        max_evaluation_id = self.next_circuit_index - 1
        with self._state_lock:
            with self._history_lock:
                fp = self.history_path.open("a") if write_history else None
                try:
                    for record in records:
                        genome = tuple(record["genome"])
                        if genome in self.cache:
                            continue
                        self.cache[genome] = record
                        imported += 1
                        max_evaluation_id = max(
                            max_evaluation_id,
                            int(record["evaluation_id"]),
                        )
                        if fp is not None:
                            fp.write(json.dumps(record) + "\n")
                finally:
                    if fp is not None:
                        fp.close()
            self.next_circuit_index = max(
                self.next_circuit_index,
                max_evaluation_id + 1,
            )
        return imported

    def print_timeout(self, circuit_index, circuit_dir, error):
        timeout_text = (
            "none"
            if self.simulation_timeout_seconds is None
            else f"{self.simulation_timeout_seconds:g}s"
        )
        with self._print_lock:
            print(
                "[optimize_circuits] simulation timed out: "
                f"evaluation_id={circuit_index} "
                f"circuit={circuit_dir.name} "
                f"timeout={timeout_text} "
                f"error={error}",
                flush=True,
            )

    def evaluate(self, genome):
        genome = tuple(genome)
        with self._state_lock:
            if genome in self.cache:
                return self.cache[genome]
            circuit_index = self.next_circuit_index
            self.next_circuit_index += 1

        decoded = self.decode_genome(genome)
        if decoded["transistor"] is None:
            record = {
                "evaluation_id": circuit_index,
                "status": "invalid_transistor",
                "valid": False,
                "genome": list(genome),
                "candidate": self.candidate_summary(decoded),
                "metrics": {},
                "objectives": [PENALTY_OBJECTIVE for _ in self.objectives],
                "objective_specs": self.objectives,
                "missing_metrics": [objective["name"] for objective in self.objectives],
                "constraint_violations": [],
                "constraint_violation_score": PENALTY_OBJECTIVE,
                "constraint_violation_count": 0,
                "circuit_dir": None,
                "error": "No transistor model exists for the selected parameter indexes",
                "created_at_unix": time.time(),
            }
            self.append_history(record)
            with self._state_lock:
                self.cache[genome] = record
            return record

        circuit_dir = create_circuit_bundle(
            output_root=self.output_root,
            circuit_index=circuit_index,
            transistor_model=decoded["transistor"],
            gate_network=decoded["gate"],
            source_network=decoded["source"],
            load_network=decoded["load"],
            feedback_network=decoded["feedback"],
            vg=decoded["vg"],
            **self.netlist_kwargs,
        )

        status = "ok"
        error = None
        metrics = {}
        missing_metrics = []
        constraint_violations = []
        constraint_violation_score = 0.0
        try:
            run_circuit_simulation(
                circuit_dir,
                measure_filename=DEFAULT_MEASURE_FILENAME,
                log_filename=DEFAULT_LOG_FILENAME,
                priority=self.simulation_priority,
                timeout_seconds=self.simulation_timeout_seconds,
            )
            analysis = analyze_circuit_measures(
                circuit_dir,
                measure_filename=DEFAULT_MEASURE_FILENAME,
                analysis_filename=DEFAULT_ANALYSIS_FILENAME,
            )
            metrics = analysis["derived_metrics"]
            objectives, missing_metrics = objective_vector(metrics, self.objectives)
            if missing_metrics:
                status = "missing_metrics"
            constraint_violations = hard_constraint_violations(
                metrics,
                self.hard_constraints,
            )
            if constraint_violations:
                status = (
                    "missing_metrics"
                    if status == "missing_metrics"
                    else "constraint_failed"
                )
                objectives = [PENALTY_OBJECTIVE for _ in self.objectives]
            constraint_violation_score = total_constraint_violation(
                constraint_violations,
            )
            if missing_metrics:
                constraint_violation_score += (
                    PENALTY_OBJECTIVE * len(missing_metrics)
                )
        except TimeoutError as exc:
            self.print_timeout(circuit_index, circuit_dir, exc)
            if self.fail_fast:
                raise
            status = "timed_out"
            error = str(exc)
            objectives = [PENALTY_OBJECTIVE for _ in self.objectives]
            missing_metrics = [objective["name"] for objective in self.objectives]
            constraint_violations = []
            constraint_violation_score = PENALTY_OBJECTIVE
        except Exception as exc:
            if self.fail_fast:
                raise
            status = "failed"
            error = str(exc)
            objectives = [PENALTY_OBJECTIVE for _ in self.objectives]
            missing_metrics = [objective["name"] for objective in self.objectives]
            constraint_violations = []
            constraint_violation_score = PENALTY_OBJECTIVE

        record = {
            "evaluation_id": circuit_index,
            "status": status,
            "valid": status == "ok",
            "genome": list(genome),
            "candidate": self.candidate_summary(decoded),
            "metrics": metrics,
            "objectives": objectives,
            "objective_specs": self.objectives,
            "missing_metrics": missing_metrics,
            "constraint_violations": constraint_violations,
            "constraint_violation_score": constraint_violation_score,
            "constraint_violation_count": len(constraint_violations),
            "circuit_dir": str(circuit_dir.relative_to(self.output_root)),
            "error": error,
            "created_at_unix": time.time(),
        }
        (circuit_dir / "optimization_evaluation.json").write_text(
            json.dumps(record, indent=2) + "\n"
        )
        self.append_history(record)
        with self._state_lock:
            self.cache[genome] = record
        return record

    def evaluate_many(self, genomes, simulation_threads):
        genomes = [tuple(genome) for genome in genomes]
        if simulation_threads <= 1:
            return [self.evaluate(genome) for genome in genomes]

        pending = []
        seen = set()
        for genome in genomes:
            with self._state_lock:
                cached = genome in self.cache
            if cached or genome in seen:
                continue
            seen.add(genome)
            pending.append(genome)

        if pending:
            with ThreadPoolExecutor(max_workers=simulation_threads) as executor:
                futures = {
                    executor.submit(self.evaluate, genome): genome
                    for genome in pending
                }
                for future in as_completed(futures):
                    future.result()

        return [self.evaluate(genome) for genome in genomes]


def initial_population(optimizer, population_size, simulation_threads):
    genomes = []
    seen = set()
    max_attempts = max(1000, population_size * 100)
    attempts = 0
    while len(genomes) < population_size and attempts < max_attempts:
        attempts += 1
        genome = optimizer.random_genome()
        if genome in seen:
            continue
        seen.add(genome)
        genomes.append(genome)
    if len(genomes) < population_size:
        raise RuntimeError("Could not build a unique initial population")
    return optimizer.evaluate_many(list(genomes), simulation_threads)


def make_offspring_genomes(
    population,
    offspring_size,
    space_sizes,
    crossover_probability,
    mutation_probability,
    rng,
):
    ranks, crowding = rank_and_crowding(population)
    offspring = []
    while len(offspring) < offspring_size:
        parent_a = tournament_select(population, ranks, crowding, rng)
        parent_b = tournament_select(population, ranks, crowding, rng)
        child_a, child_b = crossover_genomes(
            tuple(parent_a["genome"]),
            tuple(parent_b["genome"]),
            crossover_probability,
            rng,
        )
        child_a = mutate_genome(child_a, space_sizes, mutation_probability, rng)
        child_b = mutate_genome(child_b, space_sizes, mutation_probability, rng)
        offspring.append(child_a)
        if len(offspring) < offspring_size:
            offspring.append(child_b)
    return offspring


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def write_generation(output_root, generation, population, all_records, pareto_source_records=None):
    pareto_source_records = all_records if pareto_source_records is None else pareto_source_records
    valid_records = [record for record in pareto_source_records if record["valid"]]
    pareto = non_dominated_sort(valid_records)[0] if valid_records else []
    payload = {
        "generation": generation,
        "population_size": len(population),
        "evaluations": len(all_records),
        "valid_evaluations": len([record for record in all_records if record["valid"]]),
        "pareto_size": len(pareto),
        "population": [compact_record(record) for record in population],
        "current_pareto": [compact_record(record) for record in pareto],
    }
    write_json(Path(output_root) / "generations" / f"generation_{generation:04d}.json", payload)


def _safe_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_imported_metrics(metrics):
    metrics = dict(metrics or {})

    if "S21_db" not in metrics and "gain_db" in metrics:
        metrics["S21_db"] = metrics["gain_db"]

    if "power_dBm" not in metrics:
        power_mw = _safe_float(metrics.get("power_mw"))
        if power_mw is None:
            power_w = _safe_float(metrics.get("power"))
            power_mw = None if power_w is None else power_w * 1000.0
        if power_mw is not None and power_mw > 0:
            metrics["power_dBm"] = 10 * math.log10(power_mw)

    return metrics


def _source_circuit_dir(source_root, circuit_dir):
    if not circuit_dir:
        return circuit_dir
    path = Path(circuit_dir)
    if path.is_absolute():
        return str(path)
    return str(Path(source_root) / path)


def normalize_resume_record(
    record,
    source_root,
    objectives,
    hard_constraints,
    *,
    preserve_relative_circuit_dir=False,
):
    genome = record.get("genome")
    evaluation_id = record.get("evaluation_id")
    if genome is None or evaluation_id is None:
        return None
    try:
        genome = tuple(int(value) for value in genome)
        evaluation_id = int(evaluation_id)
    except (TypeError, ValueError):
        return None
    if len(genome) != len(GENE_NAMES):
        return None

    imported = dict(record)
    imported["evaluation_id"] = evaluation_id
    imported["genome"] = list(genome)
    imported["metrics"] = normalize_imported_metrics(imported.get("metrics") or {})
    imported["objective_specs"] = objectives
    imported["imported_from"] = str(source_root)
    imported["source_evaluation_id"] = evaluation_id
    if imported.get("circuit_dir") and not preserve_relative_circuit_dir:
        imported["circuit_dir"] = _source_circuit_dir(source_root, imported["circuit_dir"])

    metrics = imported["metrics"]
    objectives_vector, missing_metrics = objective_vector(metrics, objectives)
    constraint_violations = hard_constraint_violations(metrics, hard_constraints)

    if not metrics:
        imported["status"] = imported.get("status") or "failed"
        imported["valid"] = False
        imported["objectives"] = [PENALTY_OBJECTIVE for _ in objectives]
        imported["missing_metrics"] = [objective["name"] for objective in objectives]
        imported["constraint_violations"] = []
        imported["constraint_violation_score"] = PENALTY_OBJECTIVE
        imported["constraint_violation_count"] = 0
        return imported

    if missing_metrics:
        imported["status"] = "missing_metrics"
        imported["valid"] = False
        imported["objectives"] = [PENALTY_OBJECTIVE for _ in objectives]
    elif constraint_violations:
        imported["status"] = "constraint_failed"
        imported["valid"] = False
        imported["objectives"] = [PENALTY_OBJECTIVE for _ in objectives]
    else:
        imported["status"] = "ok"
        imported["valid"] = True
        imported["objectives"] = objectives_vector

    imported["missing_metrics"] = missing_metrics
    imported["constraint_violations"] = constraint_violations
    imported["constraint_violation_score"] = total_constraint_violation(
        constraint_violations,
    ) + (PENALTY_OBJECTIVE * len(missing_metrics))
    imported["constraint_violation_count"] = len(constraint_violations)
    return imported


def load_json_if_exists(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def load_history_records(
    run_root,
    objectives,
    hard_constraints,
    *,
    preserve_relative_circuit_dir=False,
):
    history_path = Path(run_root) / "optimization_history.jsonl"
    if not history_path.exists():
        return [], [{"line": None, "error": f"missing {history_path}"}]

    records = []
    skipped = []
    for line_number, line in enumerate(history_path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw_record = json.loads(line)
        except json.JSONDecodeError as exc:
            skipped.append({"line": line_number, "error": str(exc)})
            continue
        record = normalize_resume_record(
            raw_record,
            run_root,
            objectives,
            hard_constraints,
            preserve_relative_circuit_dir=preserve_relative_circuit_dir,
        )
        if record is None:
            skipped.append({"line": line_number, "error": "record missing genome/evaluation_id"})
            continue
        records.append(record)
    return records, skipped


def latest_generation_path(run_root):
    generation_dir = Path(run_root) / "generations"
    paths = sorted(generation_dir.glob("generation_*.json"))
    if not paths:
        raise FileNotFoundError(f"No generation files found in {generation_dir}")
    return max(paths, key=lambda path: int(path.stem.rsplit("_", 1)[1]))


def validate_resume_compatibility(source_config, current_config):
    if not source_config:
        return ["source run has no optimization_config.json; compatibility was not checked"]

    mismatches = []
    for key in ("search_space", "role_filters", "available_passive_indexes"):
        if source_config.get(key) != current_config.get(key):
            mismatches.append(key)

    source_network_database = source_config.get("network_database")
    current_network_database = current_config.get("network_database")
    if source_network_database and source_network_database != current_network_database:
        mismatches.append("network_database")

    source_axes = source_config.get("transistor_axes") or {}
    current_axes = current_config.get("transistor_axes") or {}
    for key in ("device_type", "threshold", "wtot_um", "length_um"):
        if source_axes.get(key) != current_axes.get(key):
            mismatches.append(f"transistor_axes.{key}")

    if mismatches:
        raise ValueError(
            "Cannot resume from this run because genome indexes would not map "
            "to the same search space. Mismatched field(s): "
            + ", ".join(mismatches)
        )

    return []


def load_resume_data(
    run_root,
    objectives,
    hard_constraints,
    *,
    preserve_relative_circuit_dir=False,
):
    run_root = Path(run_root)
    generation_path = latest_generation_path(run_root)
    generation_payload = json.loads(generation_path.read_text())
    history_records, skipped_history_lines = load_history_records(
        run_root,
        objectives,
        hard_constraints,
        preserve_relative_circuit_dir=preserve_relative_circuit_dir,
    )

    records_by_genome = {}
    for record in history_records:
        records_by_genome[tuple(record["genome"])] = record

    imported_from_generation = 0
    for raw_record in generation_payload.get("population") or []:
        record = normalize_resume_record(
            raw_record,
            run_root,
            objectives,
            hard_constraints,
            preserve_relative_circuit_dir=preserve_relative_circuit_dir,
        )
        if record is None:
            continue
        genome = tuple(record["genome"])
        if genome not in records_by_genome:
            records_by_genome[genome] = record
            imported_from_generation += 1

    seed_population = []
    seen = set()
    for raw_record in generation_payload.get("population") or []:
        genome = raw_record.get("genome")
        if genome is None:
            continue
        genome = tuple(int(value) for value in genome)
        if genome in seen:
            continue
        record = records_by_genome.get(genome)
        if record is None:
            continue
        seen.add(genome)
        seed_population.append(record)

    return {
        "run_root": run_root,
        "generation_path": generation_path,
        "generation": generation_payload.get("generation"),
        "history_records": list(records_by_genome.values()),
        "seed_population": seed_population,
        "skipped_history_lines": skipped_history_lines,
        "imported_from_generation": imported_from_generation,
        "source_config": load_json_if_exists(run_root / "optimization_config.json", default={}),
    }


def genome_within_space(genome, space_sizes):
    if len(genome) != len(space_sizes):
        return False
    return all(0 <= int(value) < int(size) for value, size in zip(genome, space_sizes))


def optimize(args):
    started_at_unix = time.time()
    started_at = current_timestamp()
    rng = random.Random(args.seed)
    objectives = parse_objectives(args.objectives)
    hard_constraints = build_hard_constraints(args)

    network_payload, _ = load_network_payload(args.network_database)
    networks = ensure_open_rlc_network(load_network_database(args.network_database))
    available_indexes = available_index_values(network_payload, networks)
    role_filters = build_role_filters(args, available_indexes)
    role_choices = build_role_choices(
        networks,
        role_filters,
        include_default=args.include_default_networks,
        allow_source_none=not args.no_source_none,
        allow_feedback_none=not args.no_feedback_none,
    )

    if args.vg_values is not None:
        vg_values = list(args.vg_values)
    else:
        vg_values = build_float_sweep(args.vg_start, args.vg_stop, args.vg_step)

    transistors = resolve_transistor_group(args.transistor_group)
    transistor_axes = build_transistor_axes(transistors)
    ac_start, ac_stop = resolve_ac_sweep_bounds(args.f0, args.ac_start, args.ac_stop)
    netlist_kwargs = {
        "corner": args.corner,
        "pdk_root": args.pdk_root,
        "process_lib_path": args.process_lib_path,
        "temperature_c": args.temperature_c,
        "f0": args.f0,
        "vdd": args.vdd,
        "ac_start": ac_start,
        "ac_stop": ac_stop,
        "print_useful_data": True,
    }

    search_space = {
        "device_types": len(transistor_axes["device_type"]),
        "thresholds": len(transistor_axes["threshold"]),
        "wtot_values": len(transistor_axes["wtot_um"]),
        "length_values": len(transistor_axes["length_um"]),
        "vg_values": len(vg_values),
        "gate_networks": len(role_choices["gate"]),
        "source_networks": len(role_choices["source"]),
        "load_networks": len(role_choices["load"]),
        "feedback_networks": len(role_choices["feedback"]),
    }
    total_designs = math.prod(search_space.values())
    valid_seed_designs = (
        len(transistor_axes["valid_model_keys"])
        * len(vg_values)
        * len(role_choices["gate"])
        * len(role_choices["source"])
        * len(role_choices["load"])
        * len(role_choices["feedback"])
    )
    if args.population_size > valid_seed_designs:
        raise ValueError(
            f"Population size {args.population_size} exceeds valid initial search "
            f"space size {valid_seed_designs}"
        )
    transistor_axes_config = {
        "device_type": transistor_axes["device_type"],
        "threshold": transistor_axes["threshold"],
        "wtot_um": transistor_axes["wtot_um"],
        "length_um": transistor_axes["length_um"],
        "models": transistor_axes["models"],
    }
    role_filter_config = {
        role: {axis: sorted(values) for axis, values in filters.items()}
        for role, filters in role_filters.items()
    }
    current_resume_config = {
        "search_space": search_space,
        "available_passive_indexes": available_indexes,
        "role_filters": role_filter_config,
        "network_database": str(args.network_database),
        "transistor_axes": transistor_axes_config,
    }
    resume_data = None
    resume_warnings = []
    planned_initial_simulations = args.population_size
    resume_from = args.resume_from
    if args.resume_in_place and resume_from is None:
        resume_from = args.output_root
    if resume_from:
        resume_root = Path(resume_from)
        if not resume_root.exists():
            raise FileNotFoundError(f"--resume-from does not exist: {resume_root}")
        same_resume_root = Path(args.output_root).resolve() == resume_root.resolve()
        if args.resume_in_place and not same_resume_root:
            raise ValueError(
                "--resume-in-place requires --resume-from to match --output-root, "
                "or omit --resume-from and set --output-root to the run directory."
            )
        if same_resume_root and not args.resume_in_place:
            raise ValueError(
                "--resume-from must be different from --output-root. "
                "Use --resume-in-place if you want to append to the same run directory."
            )
        resume_data = load_resume_data(
            resume_root,
            objectives,
            hard_constraints,
            preserve_relative_circuit_dir=args.resume_in_place,
        )
        resume_warnings = validate_resume_compatibility(
            resume_data["source_config"],
            current_resume_config,
        )
        invalid_seed_genomes = [
            record["genome"]
            for record in resume_data["seed_population"]
            if not genome_within_space(record["genome"], (
                len(transistor_axes["device_type"]),
                len(transistor_axes["threshold"]),
                len(transistor_axes["wtot_um"]),
                len(transistor_axes["length_um"]),
                len(vg_values),
                len(role_choices["gate"]),
                len(role_choices["source"]),
                len(role_choices["load"]),
                len(role_choices["feedback"]),
            ))
        ]
        if invalid_seed_genomes:
            raise ValueError(
                "Cannot resume because at least one seed genome is outside "
                f"the current search space: {invalid_seed_genomes[0]}"
            )
        planned_initial_simulations = max(
            0,
            args.population_size - min(args.population_size, len(resume_data["seed_population"])),
        )
    planned_simulations = planned_initial_simulations + args.offspring_size * args.generations

    output_root = Path(args.output_root)
    existing_run_markers = [
        output_root / "optimization_history.jsonl",
        output_root / "optimization_config.json",
        output_root / "generations",
    ]
    if resume_data is None and not args.overwrite_output:
        existing = [path for path in existing_run_markers if path.exists()]
        if existing:
            raise ValueError(
                f"Output root already contains optimization data: {output_root}. "
                "Use --resume-in-place to append to it, choose a new --output-root, "
                "or pass --overwrite-output to intentionally start over there."
            )

    optimizer = NgsaIvOptimizer(
        output_root=args.output_root,
        transistor_axes=transistor_axes,
        vg_values=vg_values,
        role_choices=role_choices,
        objectives=objectives,
        hard_constraints=hard_constraints,
        netlist_kwargs=netlist_kwargs,
        simulation_priority=args.sim_priority,
        simulation_timeout_seconds=args.sim_timeout,
        fail_fast=args.fail_fast,
        rng=rng,
        preserve_history=args.resume_in_place,
    )
    imported_evaluations = 0
    if resume_data is not None:
        imported_evaluations = optimizer.import_cached_records(
            resume_data["history_records"],
            write_history=not args.resume_in_place,
        )
    generation_offset = (
        int(resume_data["generation"] or 0)
        if resume_data is not None and args.resume_in_place
        else 0
    )

    configuration = {
        "algorithm": "NGSA-IV",
        "population_size": args.population_size,
        "offspring_size": args.offspring_size,
        "generations": args.generations,
        "seed": args.seed,
        "started_at": started_at,
        "started_at_unix": started_at_unix,
        "objectives": objectives,
        "hard_constraints": hard_constraints,
        "search_space": search_space,
        "total_designs": total_designs,
        "planned_simulations": planned_simulations,
        "planned_initial_simulations": planned_initial_simulations,
        "valid_seed_designs": valid_seed_designs,
        "available_transistor_models": len(transistors),
        "transistor_axes": transistor_axes_config,
        "available_passive_indexes": available_indexes,
        "role_filters": role_filter_config,
        "network_database": str(args.network_database),
        "netlist_parameters": netlist_kwargs,
        "simulation_threads": args.sim_threads,
        "simulation_timeout_seconds": args.sim_timeout,
    }
    if resume_data is not None:
        configuration["resume"] = {
            "source_run_root": str(resume_data["run_root"]),
            "mode": "in_place" if args.resume_in_place else "import",
            "source_generation": resume_data["generation"],
            "source_generation_file": str(resume_data["generation_path"]),
            "source_population_size": len(resume_data["seed_population"]),
            "imported_evaluations": imported_evaluations,
            "generation_offset": generation_offset,
            "imported_from_generation": resume_data["imported_from_generation"],
            "skipped_history_lines": resume_data["skipped_history_lines"],
            "compatibility_warnings": resume_warnings,
        }
    if args.resume_in_place:
        config_path = (
            Path(args.output_root)
            / "resume_sessions"
            / f"resume_{int(started_at_unix)}_config.json"
        )
    else:
        config_path = Path(args.output_root) / "optimization_config.json"
    write_json(config_path, configuration)

    print(f"[optimize_circuits] started at: {started_at}", flush=True)
    print(
        "[optimize_circuits] search space sizes: "
        + ", ".join(f"{key}={value}" for key, value in search_space.items()),
        flush=True,
    )
    print(
        "[optimize_circuits] search space total: "
        f"{total_designs:,} index combinations "
        f"({valid_seed_designs:,} valid initial transistor/network/bias combinations)",
        flush=True,
    )
    print(
        "[optimize_circuits] planned new simulations: "
        f"{planned_simulations:,} = initial {planned_initial_simulations:,} + "
        f"offspring {args.offspring_size:,} * generations {args.generations:,}",
        flush=True,
    )
    if resume_data is not None:
        print(
            "[optimize_circuits] resume: "
            f"source={resume_data['run_root']} "
            f"generation={resume_data['generation']} "
            f"seed_population={len(resume_data['seed_population']):,} "
            f"imported_evaluations={imported_evaluations:,}",
            flush=True,
        )
        if resume_data["skipped_history_lines"]:
            print(
                "[optimize_circuits] resume skipped history lines: "
                f"{len(resume_data['skipped_history_lines'])}",
                flush=True,
            )
    if hard_constraints:
        print(
            "[optimize_circuits] hard constraints: "
            + ", ".join(
                f"{item['name']} {item['operator']} {item['limit']}"
                for item in hard_constraints
            ),
            flush=True,
        )
    if args.sim_timeout is not None:
        print(
            f"[optimize_circuits] simulation timeout: {args.sim_timeout:g} second(s)",
            flush=True,
        )
    print(
        f"[optimize_circuits] simulation workers: {args.sim_threads}",
        flush=True,
    )
    print(f"[optimize_circuits] config written to: {config_path}", flush=True)
    if resume_data is None:
        population = initial_population(
            optimizer,
            args.population_size,
            args.sim_threads,
        )
    else:
        population = unique_records(resume_data["seed_population"])
        if len(population) > args.population_size:
            population = select_survivors_ngsa_iv(
                population,
                args.population_size,
                args.reference_partitions,
                rng,
            )
        fill_attempts = 0
        max_fill_attempts = max(1000, args.population_size * 100)
        while len(population) < args.population_size and fill_attempts < max_fill_attempts:
            fill_attempts += 1
            genome = optimizer.random_genome()
            if genome in optimizer.cache:
                continue
            population.append(optimizer.evaluate_many([genome], args.sim_threads)[0])
            population = select_survivors_ngsa_iv(
                population,
                args.population_size,
                args.reference_partitions,
                rng,
            )
        if len(population) < args.population_size:
            raise RuntimeError("Could not refill the resumed population with unique candidates")
    generation_pareto_source = None
    if not args.resume_in_place:
        write_generation(
            args.output_root,
            0,
            population,
            list(optimizer.cache.values()),
            pareto_source_records=generation_pareto_source,
        )

    for generation_step in range(1, args.generations + 1):
        generation = generation_offset + generation_step
        if generation_offset:
            print(
                f"[optimize_circuits] generation {generation} "
                f"(resume step {generation_step}/{args.generations})",
                flush=True,
            )
        else:
            print(
                f"[optimize_circuits] generation {generation_step}/{args.generations}",
                flush=True,
            )
        offspring_genomes = make_offspring_genomes(
            population,
            args.offspring_size,
            optimizer.space_sizes,
            args.crossover_probability,
            args.mutation_probability,
            rng,
        )
        offspring_genomes = [
            optimizer.repair_genome(genome)
            for genome in offspring_genomes
        ]
        offspring = optimizer.evaluate_many(offspring_genomes, args.sim_threads)
        population = select_survivors_ngsa_iv(
            population + offspring,
            args.population_size,
            args.reference_partitions,
            rng,
        )
        fill_attempts = 0
        max_fill_attempts = max(1000, args.population_size * 100)
        while len(population) < args.population_size and fill_attempts < max_fill_attempts:
            fill_attempts += 1
            genome = optimizer.random_genome()
            if genome in optimizer.cache:
                continue
            population.append(optimizer.evaluate_many([genome], args.sim_threads)[0])
            population = select_survivors_ngsa_iv(
                population,
                args.population_size,
                args.reference_partitions,
                rng,
            )
        if len(population) < args.population_size:
            raise RuntimeError("Could not refill the population with unique candidates")
        write_generation(
            args.output_root,
            generation,
            population,
            list(optimizer.cache.values()),
            pareto_source_records=generation_pareto_source,
        )

    all_records = list(optimizer.cache.values())
    valid_records = [record for record in all_records if record["valid"]]
    pareto_source_records = population if resume_data is not None else all_records
    pareto_source_valid_records = [
        record for record in pareto_source_records if record["valid"]
    ]
    pareto = (
        non_dominated_sort(pareto_source_valid_records)[0]
        if pareto_source_valid_records
        else []
    )
    finished_at_unix = time.time()
    finished_at = current_timestamp()
    elapsed_seconds = finished_at_unix - started_at_unix
    summary = {
        "algorithm": "NGSA-IV",
        "generations": args.generations,
        "population_size": args.population_size,
        "started_at": started_at,
        "finished_at": finished_at,
        "started_at_unix": started_at_unix,
        "finished_at_unix": finished_at_unix,
        "elapsed_seconds": elapsed_seconds,
        "elapsed_time": format_elapsed(elapsed_seconds),
        "planned_simulations": planned_simulations,
        "planned_initial_simulations": planned_initial_simulations,
        "total_designs": total_designs,
        "valid_seed_designs": valid_seed_designs,
        "simulation_threads": args.sim_threads,
        "evaluations": len(all_records),
        "valid_evaluations": len(valid_records),
        "pareto_source": "population" if resume_data is not None else "all_evaluations",
        "pareto_source_evaluations": len(pareto_source_records),
        "pareto_source_valid_evaluations": len(pareto_source_valid_records),
        "pareto_size": len(pareto),
        "objectives": objectives,
        "hard_constraints": hard_constraints,
        "pareto_front": [compact_record(record) for record in pareto],
    }
    if resume_data is not None:
        summary["resume"] = configuration["resume"]
    write_json(Path(args.output_root) / "pareto_front.json", summary["pareto_front"])
    write_json(Path(args.output_root) / "optimization_summary.json", summary)
    print(
        "[optimize_circuits] complete: "
        f"{len(valid_records)}/{len(all_records)} valid evaluations, "
        f"{len(pareto)} Pareto candidates",
        flush=True,
    )
    print(f"[optimize_circuits] finished at: {finished_at}", flush=True)
    print(
        "[optimize_circuits] elapsed time: "
        f"{format_elapsed(elapsed_seconds)} ({elapsed_seconds:.3f} seconds)",
        flush=True,
    )
    return summary


def add_role_index_arguments(parser):
    for role in NETWORK_ROLES:
        for axis in RLC_AXES:
            parser.add_argument(
                f"--{role}-{axis}-indexes",
                dest=f"{role}_{axis}_indexes",
                default="all",
                help=(
                    f"Allowed {axis.upper()} indexes for {role}; use 'all', "
                    "comma-separated values, or inclusive ranges like 0,2:5."
                ),
            )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Optimize generated LNA netlists with an NGSA-IV-style multi-objective "
            "evolutionary loop."
        )
    )
    parser.add_argument("--output-root", default="optimized_circuits")
    parser.add_argument(
        "--network-database",
        default=str(DEFAULT_NETWORK_DATABASE_PATH),
        help="Passive-network database JSON.",
    )
    parser.add_argument(
        "--transistor-group",
        choices=sorted(TRANSISTOR_GROUP_ALIASES),
        default="all",
    )
    parser.add_argument("--vg-values", nargs="+", type=float)
    parser.add_argument("--vg-start", type=float, default=0.7)
    parser.add_argument("--vg-stop", type=float, default=1.3)
    parser.add_argument("--vg-step", type=float, default=0.1)
    parser.add_argument("--population-size", type=int, default=24)
    parser.add_argument("--offspring-size", type=int, default=24)
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--resume-from",
        help=(
            "Import optimization_history.jsonl and seed generation 0 from the "
            "latest generations/generation_*.json in this previous run. Use a "
            "different --output-root for the resumed run."
        ),
    )
    parser.add_argument(
        "--resume-in-place",
        action="store_true",
        help=(
            "Resume inside --output-root: preserve optimization_history.jsonl, "
            "append new evaluations, and continue generation numbering."
        ),
    )
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help=(
            "Allow starting a fresh run in an output directory that already "
            "contains optimization data. Without this, existing runs are protected."
        ),
    )
    parser.add_argument("--objectives", default=DEFAULT_OBJECTIVES)
    parser.add_argument(
        "--max-nf-db",
        type=float,
        help="Hard feasibility constraint: require NF_db <= this value.",
    )
    parser.add_argument(
        "--max-power-dbm",
        "--max-power",
        dest="max_power_dbm",
        type=float,
        help="Hard feasibility constraint: require power_dBm <= this value.",
    )
    parser.add_argument(
        "--min-s21-db",
        type=float,
        help="Hard feasibility constraint: require s21_db >= this value.",
    )
    parser.add_argument(
        "--min-f-bw",
        type=float,
        help="Hard feasibility constraint: require F_BW >= this value.",
    )
    parser.add_argument(
        "--max-s11-db",
        type=float,
        help="Hard feasibility constraint: require S11_db <= this value.",
    )
    parser.add_argument("--reference-partitions", type=int, default=4)
    parser.add_argument("--crossover-probability", type=float, default=0.9)
    parser.add_argument("--mutation-probability", type=float, default=0.2)
    parser.add_argument(
        "--include-default-networks",
        action="store_true",
        help="Include the generator's default gate/source/load inductors as choices.",
    )
    parser.add_argument("--no-source-none", action="store_true")
    parser.add_argument("--no-feedback-none", action="store_true")
    add_role_index_arguments(parser)
    parser.add_argument(
        "--sim-priority",
        choices=sorted(PRIORITY_NICE_VALUES),
        default=DEFAULT_SIMULATION_PRIORITY,
    )
    parser.add_argument(
        "--sim-threads",
        type=int,
        default=1,
        help="Number of circuit evaluations to simulate in parallel per generation.",
    )
    parser.add_argument(
        "--sim-timeout",
        type=float,
        help="Kill an ngspice simulation after this many seconds.",
    )
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--corner", default="tt")
    parser.add_argument("--pdk-root", default="$PDK_ROOT")
    parser.add_argument(
        "--process-lib-path",
        default="sky130A/libs.tech/ngspice/sky130.lib.spice",
    )
    parser.add_argument("--temperature-c", type=float, default=27)
    parser.add_argument("--f0", type=float, default=5e9)
    parser.add_argument("--vdd", type=float, default=1.8)
    parser.add_argument(
        "--ac-start",
        help="AC sweep start frequency. Defaults to one decade below --f0.",
    )
    parser.add_argument(
        "--ac-stop",
        help="AC sweep stop frequency. Defaults to one decade above --f0.",
    )
    args = parser.parse_args()

    if args.population_size < 1:
        raise ValueError("--population-size must be at least 1")
    if args.offspring_size < 1:
        raise ValueError("--offspring-size must be at least 1")
    if args.generations < 0:
        raise ValueError("--generations must be non-negative")
    if args.sim_threads < 1:
        raise ValueError("--sim-threads must be at least 1")
    if args.sim_timeout is not None and args.sim_timeout <= 0:
        raise ValueError("--sim-timeout must be positive")
    if not 0 <= args.crossover_probability <= 1:
        raise ValueError("--crossover-probability must be between 0 and 1")
    if not 0 <= args.mutation_probability <= 1:
        raise ValueError("--mutation-probability must be between 0 and 1")

    optimize(args)


if __name__ == "__main__":
    main()
