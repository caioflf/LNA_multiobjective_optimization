from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.scripts.circuit_database import DEFAULT_CIRCUIT_DATABASE_PATH
from src.scripts.netlist_generator import (
    DEFAULT_NETWORK_DATABASE_PATH,
    load_network_database,
    resolve_ac_sweep_bounds,
)
from src.scripts.optimize_circuits import (
    DEFAULT_OBJECTIVES,
    NgsaIvOptimizer,
    add_role_index_arguments,
    available_index_values,
    build_float_sweep,
    build_hard_constraints,
    build_role_choices,
    build_role_filters,
    build_transistor_axes,
    compact_record,
    crowding_distances,
    current_timestamp,
    dominates,
    ensure_open_rlc_network,
    format_elapsed,
    load_network_payload,
    non_dominated_sort,
    parse_objectives,
    resolve_circuit_database_path,
    resolve_transistor_group,
    select_survivors_ngsa_iv,
    unique_records,
    write_generation,
    write_json,
)
from src.scripts.simulate_circuits import (
    DEFAULT_SIMULATION_PRIORITY,
    PRIORITY_NICE_VALUES,
)


def velocity_limits(space_sizes, velocity_clamp):
    return [
        0.0 if size <= 1 else max(0.0, (size - 1) * velocity_clamp)
        for size in space_sizes
    ]


def random_velocity(space_sizes, velocity_clamp, rng):
    limits = velocity_limits(space_sizes, velocity_clamp)
    return [
        0.0 if limit == 0.0 else rng.uniform(-limit, limit)
        for limit in limits
    ]


def clip(value, low, high):
    return min(max(value, low), high)


def genome_from_position(position, space_sizes):
    return tuple(
        int(round(clip(value, 0, size - 1)))
        for value, size in zip(position, space_sizes)
    )


def maybe_mutate_genome(genome, space_sizes, mutation_probability, rng):
    if mutation_probability <= 0:
        return genome
    mutated = list(genome)
    for index, size in enumerate(space_sizes):
        if size <= 1:
            continue
        if rng.random() <= mutation_probability:
            mutated[index] = rng.randrange(size)
    return tuple(mutated)


def random_unique_genomes(optimizer, count):
    genomes = []
    seen = set()
    max_attempts = max(1000, count * 100)
    attempts = 0
    while len(genomes) < count and attempts < max_attempts:
        attempts += 1
        genome = optimizer.random_genome()
        if genome in seen:
            continue
        seen.add(genome)
        genomes.append(genome)
    if len(genomes) < count:
        raise RuntimeError("Could not build a unique initial swarm")
    return genomes


def make_particle(particle_id, record, space_sizes, velocity_clamp, rng):
    position = [float(value) for value in record["genome"]]
    return {
        "particle_id": particle_id,
        "position": position,
        "velocity": random_velocity(space_sizes, velocity_clamp, rng),
        "record": record,
        "personal_best": record,
        "personal_best_position": list(position),
    }


def update_personal_best(particle, rng):
    current = particle["record"]
    best = particle["personal_best"]
    if dominates(current, best):
        particle["personal_best"] = current
        particle["personal_best_position"] = list(particle["position"])
        return
    if dominates(best, current):
        return
    if rng.random() < 0.5:
        particle["personal_best"] = current
        particle["personal_best_position"] = list(particle["position"])


def update_archive(records, archive_size, archive_partitions, rng):
    if not records:
        return []
    front = non_dominated_sort(unique_records(records))[0]
    if len(front) <= archive_size:
        return front
    return select_survivors_ngsa_iv(front, archive_size, archive_partitions, rng)


def archive_update_candidates(archive, swarm_records, particles=None):
    records = []
    records.extend(archive)
    records.extend(swarm_records)
    if particles is not None:
        records.extend(particle["personal_best"] for particle in particles)
    return records


def compact_record_ref(record):
    if record is None:
        return None
    return {
        "evaluation_id": record.get("evaluation_id"),
        "status": record.get("status"),
        "valid": record.get("valid"),
        "genome": record.get("genome"),
        "candidate": record.get("candidate"),
        "metrics": record.get("metrics") or {},
        "objectives": record.get("objectives"),
        "missing_metrics": record.get("missing_metrics") or [],
        "constraint_violations": record.get("constraint_violations") or [],
        "constraint_violation_score": record.get("constraint_violation_score"),
        "constraint_violation_count": record.get("constraint_violation_count"),
        "circuit_dir": record.get("circuit_dir"),
        "error": record.get("error"),
    }


def movement_record_ref(record):
    if record is None:
        return None
    return {
        "evaluation_id": record.get("evaluation_id"),
        "status": record.get("status"),
        "valid": record.get("valid"),
        "genome": record.get("genome"),
        "metrics": record.get("metrics") or {},
        "objectives": record.get("objectives"),
        "constraint_violation_score": record.get("constraint_violation_score"),
        "constraint_violation_count": record.get("constraint_violation_count"),
    }


def compact_particle_state(particle):
    return {
        "particle_id": particle["particle_id"],
        "position": particle["position"],
        "velocity": particle["velocity"],
        "record": compact_record_ref(particle["record"]),
        "personal_best_position": particle["personal_best_position"],
        "personal_best": compact_record_ref(particle["personal_best"]),
    }


def write_swarm_state(
    output_root,
    iteration,
    particles,
    archive,
    *,
    movements=None,
):
    payload = {
        "iteration": iteration,
        "swarm_size": len(particles),
        "archive_size": len(archive),
        "archive": [compact_record_ref(record) for record in archive],
        "particles": [compact_particle_state(particle) for particle in particles],
    }
    if movements is not None:
        payload["movements"] = movements
    write_json(
        Path(output_root) / "swarm" / f"iteration_{iteration:04d}.json",
        payload,
    )


def select_leader(archive, rng):
    if not archive:
        raise ValueError("Cannot select a MOPSO leader from an empty archive")
    if len(archive) == 1:
        return archive[0]

    distances = crowding_distances(archive)
    sample = rng.sample(archive, min(3, len(archive)))
    return max(
        sample,
        key=lambda record: distances.get(record["evaluation_id"], 0.0),
    )


def move_particle(
    particle,
    leader,
    space_sizes,
    inertia_weight,
    cognitive_weight,
    social_weight,
    velocity_clamp,
    mutation_probability,
    optimizer,
    rng,
):
    limits = velocity_limits(space_sizes, velocity_clamp)
    leader_position = [float(value) for value in leader["genome"]]
    next_position = []
    next_velocity = []

    for index, (position, velocity, limit) in enumerate(
        zip(particle["position"], particle["velocity"], limits)
    ):
        personal_term = (
            cognitive_weight
            * rng.random()
            * (particle["personal_best_position"][index] - position)
        )
        social_term = (
            social_weight
            * rng.random()
            * (leader_position[index] - position)
        )
        new_velocity = inertia_weight * velocity + personal_term + social_term
        if limit > 0.0:
            new_velocity = clip(new_velocity, -limit, limit)
        else:
            new_velocity = 0.0
        new_position = clip(position + new_velocity, 0, space_sizes[index] - 1)
        next_velocity.append(new_velocity)
        next_position.append(new_position)

    genome = genome_from_position(next_position, space_sizes)
    genome = optimizer.repair_genome(genome)
    genome = maybe_mutate_genome(
        genome,
        space_sizes,
        mutation_probability,
        rng,
    )
    genome = optimizer.repair_genome(genome)
    particle["velocity"] = next_velocity
    particle["position"] = [float(value) for value in genome]
    return genome


def prepare_optimizer_inputs(args):
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
    return {
        "objectives": objectives,
        "hard_constraints": hard_constraints,
        "available_indexes": available_indexes,
        "role_filters": role_filters,
        "role_filter_config": role_filter_config,
        "role_choices": role_choices,
        "vg_values": vg_values,
        "transistor_axes": transistor_axes,
        "transistor_axes_config": transistor_axes_config,
        "netlist_kwargs": netlist_kwargs,
        "search_space": search_space,
    }


def optimize(args):
    started_at_unix = time.time()
    started_at = current_timestamp()
    rng = random.Random(args.seed)
    prepared = prepare_optimizer_inputs(args)

    search_space = prepared["search_space"]
    total_designs = math.prod(search_space.values())
    valid_seed_designs = (
        len(prepared["transistor_axes"]["valid_model_keys"])
        * len(prepared["vg_values"])
        * len(prepared["role_choices"]["gate"])
        * len(prepared["role_choices"]["source"])
        * len(prepared["role_choices"]["load"])
        * len(prepared["role_choices"]["feedback"])
    )
    if args.swarm_size > valid_seed_designs:
        raise ValueError(
            f"Swarm size {args.swarm_size} exceeds valid initial search "
            f"space size {valid_seed_designs}"
        )

    output_root = Path(args.output_root)
    existing_run_markers = [
        output_root / "optimization_history.jsonl",
        output_root / "optimization_config.json",
        output_root / "generations",
    ]
    if not args.overwrite_output:
        existing = [path for path in existing_run_markers if path.exists()]
        if existing:
            raise ValueError(
                f"Output root already contains optimization data: {output_root}. "
                "Choose a new --output-root or pass --overwrite-output to "
                "intentionally start over there."
            )

    circuit_database_path = resolve_circuit_database_path(
        args.circuit_database,
        args.no_circuit_database,
    )
    optimizer = NgsaIvOptimizer(
        output_root=args.output_root,
        transistor_axes=prepared["transistor_axes"],
        vg_values=prepared["vg_values"],
        role_choices=prepared["role_choices"],
        objectives=prepared["objectives"],
        hard_constraints=prepared["hard_constraints"],
        netlist_kwargs=prepared["netlist_kwargs"],
        simulation_priority=args.sim_priority,
        simulation_timeout_seconds=args.sim_timeout,
        fail_fast=args.fail_fast,
        rng=rng,
        circuit_database_path=circuit_database_path,
    )

    planned_simulations = args.swarm_size + args.swarm_size * args.iterations
    configuration = {
        "algorithm": "MOPSO",
        "swarm_size": args.swarm_size,
        "population_size": args.swarm_size,
        "archive_size": args.archive_size,
        "iterations": args.iterations,
        "generations": args.iterations,
        "seed": args.seed,
        "started_at": started_at,
        "started_at_unix": started_at_unix,
        "objectives": prepared["objectives"],
        "hard_constraints": prepared["hard_constraints"],
        "search_space": search_space,
        "total_designs": total_designs,
        "planned_evaluations": planned_simulations,
        "planned_simulations": planned_simulations,
        "planned_initial_simulations": args.swarm_size,
        "valid_seed_designs": valid_seed_designs,
        "available_transistor_models": len(prepared["transistor_axes"]["models"]),
        "transistor_axes": prepared["transistor_axes_config"],
        "available_passive_indexes": prepared["available_indexes"],
        "role_filters": prepared["role_filter_config"],
        "network_database": str(args.network_database),
        "netlist_parameters": prepared["netlist_kwargs"],
        "simulation_threads": args.sim_threads,
        "simulation_timeout_seconds": args.sim_timeout,
        "circuit_database": {
            "requested_path": None if args.no_circuit_database else args.circuit_database,
            "enabled": circuit_database_path is not None,
            "path": None if circuit_database_path is None else str(circuit_database_path),
        },
        "swarm_trace": {
            "enabled": True,
            "path_pattern": "swarm/iteration_XXXX.json",
        },
        "mopso_parameters": {
            "inertia_weight": args.inertia_weight,
            "cognitive_weight": args.cognitive_weight,
            "social_weight": args.social_weight,
            "velocity_clamp": args.velocity_clamp,
            "mutation_probability": args.mutation_probability,
            "archive_partitions": args.archive_partitions,
        },
    }
    write_json(Path(args.output_root) / "optimization_config.json", configuration)

    print(f"[optimize_circuits_mopso] started at: {started_at}", flush=True)
    print(
        "[optimize_circuits_mopso] search space sizes: "
        + ", ".join(f"{key}={value}" for key, value in search_space.items()),
        flush=True,
    )
    print(
        "[optimize_circuits_mopso] search space total: "
        f"{total_designs:,} index combinations "
        f"({valid_seed_designs:,} valid initial transistor/network/bias combinations)",
        flush=True,
    )
    print(
        "[optimize_circuits_mopso] planned new evaluations: "
        f"{planned_simulations:,} = initial swarm {args.swarm_size:,} + "
        f"swarm {args.swarm_size:,} * iterations {args.iterations:,}",
        flush=True,
    )
    if prepared["hard_constraints"]:
        print(
            "[optimize_circuits_mopso] hard constraints: "
            + ", ".join(
                f"{item['name']} {item['operator']} {item['limit']}"
                for item in prepared["hard_constraints"]
            ),
            flush=True,
        )
    if args.sim_timeout is not None:
        print(
            f"[optimize_circuits_mopso] simulation timeout: {args.sim_timeout:g} second(s)",
            flush=True,
        )
    print(
        f"[optimize_circuits_mopso] simulation workers: {args.sim_threads}",
        flush=True,
    )
    if circuit_database_path is not None:
        print(
            "[optimize_circuits_mopso] circuit database reuse: "
            f"{circuit_database_path}",
            flush=True,
        )
    elif not args.no_circuit_database:
        print(
            "[optimize_circuits_mopso] circuit database reuse: disabled "
            f"(not found: {args.circuit_database})",
            flush=True,
        )
    print(
        f"[optimize_circuits_mopso] config written to: {Path(args.output_root) / 'optimization_config.json'}",
        flush=True,
    )

    initial_genomes = random_unique_genomes(optimizer, args.swarm_size)
    swarm_records = optimizer.evaluate_many(initial_genomes, args.sim_threads)
    particles = [
        make_particle(index, record, optimizer.space_sizes, args.velocity_clamp, rng)
        for index, record in enumerate(swarm_records)
    ]
    archive = update_archive(
        archive_update_candidates([], swarm_records, particles),
        args.archive_size,
        args.archive_partitions,
        rng,
    )
    write_generation(
        args.output_root,
        0,
        swarm_records,
        list(optimizer.cache.values()),
        pareto_source_records=archive,
    )
    write_swarm_state(args.output_root, 0, particles, archive)

    for iteration in range(1, args.iterations + 1):
        print(
            f"[optimize_circuits_mopso] iteration {iteration}/{args.iterations}",
            flush=True,
        )
        next_genomes = []
        movements = []
        for particle in particles:
            leader = select_leader(archive, rng)
            before_position = list(particle["position"])
            before_velocity = list(particle["velocity"])
            genome = move_particle(
                particle,
                leader,
                optimizer.space_sizes,
                args.inertia_weight,
                args.cognitive_weight,
                args.social_weight,
                args.velocity_clamp,
                args.mutation_probability,
                optimizer,
                rng,
            )
            next_genomes.append(genome)
            movements.append(
                {
                    "particle_id": particle["particle_id"],
                    "leader": movement_record_ref(leader),
                    "before_position": before_position,
                    "before_velocity": before_velocity,
                    "personal_best_before": movement_record_ref(
                        particle["personal_best"]
                    ),
                    "personal_best_position_before": list(
                        particle["personal_best_position"]
                    ),
                    "after_position": list(particle["position"]),
                    "after_velocity": list(particle["velocity"]),
                    "moved_genome": list(genome),
                }
            )

        swarm_records = optimizer.evaluate_many(next_genomes, args.sim_threads)
        for particle, record, movement in zip(particles, swarm_records, movements):
            particle["record"] = record
            particle["position"] = [float(value) for value in record["genome"]]
            update_personal_best(particle, rng)
            movement["evaluated_record"] = movement_record_ref(record)
            movement["personal_best_after"] = movement_record_ref(
                particle["personal_best"]
            )
            movement["personal_best_position_after"] = list(
                particle["personal_best_position"]
            )

        archive = update_archive(
            archive_update_candidates(archive, swarm_records, particles),
            args.archive_size,
            args.archive_partitions,
            rng,
        )
        write_generation(
            args.output_root,
            iteration,
            swarm_records,
            list(optimizer.cache.values()),
            pareto_source_records=archive,
        )
        write_swarm_state(
            args.output_root,
            iteration,
            particles,
            archive,
            movements=movements,
        )

    all_records = list(optimizer.cache.values())
    valid_records = [record for record in all_records if record["valid"]]
    pareto = non_dominated_sort(valid_records)[0] if valid_records else []
    finished_at_unix = time.time()
    finished_at = current_timestamp()
    elapsed_seconds = finished_at_unix - started_at_unix
    summary = {
        "algorithm": "MOPSO",
        "iterations": args.iterations,
        "generations": args.iterations,
        "swarm_size": args.swarm_size,
        "population_size": args.swarm_size,
        "archive_size": args.archive_size,
        "started_at": started_at,
        "finished_at": finished_at,
        "started_at_unix": started_at_unix,
        "finished_at_unix": finished_at_unix,
        "elapsed_seconds": elapsed_seconds,
        "elapsed_time": format_elapsed(elapsed_seconds),
        "planned_evaluations": planned_simulations,
        "planned_simulations": planned_simulations,
        "planned_initial_simulations": args.swarm_size,
        "total_designs": total_designs,
        "valid_seed_designs": valid_seed_designs,
        "simulation_threads": args.sim_threads,
        "database_hits": optimizer.database_hits,
        "simulation_runs": optimizer.simulation_runs,
        "evaluations": len(all_records),
        "valid_evaluations": len(valid_records),
        "pareto_source": "all_evaluations",
        "pareto_source_evaluations": len(all_records),
        "pareto_source_valid_evaluations": len(valid_records),
        "pareto_size": len(pareto),
        "objectives": prepared["objectives"],
        "hard_constraints": prepared["hard_constraints"],
        "mopso_parameters": configuration["mopso_parameters"],
        "pareto_front": [compact_record(record) for record in pareto],
    }
    write_json(Path(args.output_root) / "pareto_front.json", summary["pareto_front"])
    write_json(Path(args.output_root) / "optimization_summary.json", summary)
    print(
        "[optimize_circuits_mopso] complete: "
        f"{len(valid_records)}/{len(all_records)} valid evaluations, "
        f"{len(pareto)} Pareto candidates",
        flush=True,
    )
    print(
        "[optimize_circuits_mopso] evaluation sources: "
        f"{optimizer.database_hits:,} database hit(s), "
        f"{optimizer.simulation_runs:,} ngspice simulation(s)",
        flush=True,
    )
    print(f"[optimize_circuits_mopso] finished at: {finished_at}", flush=True)
    print(
        "[optimize_circuits_mopso] elapsed time: "
        f"{format_elapsed(elapsed_seconds)} ({elapsed_seconds:.3f} seconds)",
        flush=True,
    )
    optimizer.close()
    return summary


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Optimize generated LNA netlists with a discrete MOPSO "
            "multi-objective loop."
        )
    )
    parser.add_argument("--output-root", default="optimized_circuits_mopso")
    parser.add_argument(
        "--network-database",
        default=str(DEFAULT_NETWORK_DATABASE_PATH),
        help="Passive-network database JSON.",
    )
    parser.add_argument(
        "--transistor-group",
        choices=("all", "lvt", "nmos", "nmos_and_lvt", "nmos_lvt"),
        default="all",
    )
    parser.add_argument("--vg-values", nargs="+", type=float)
    parser.add_argument("--vg-start", type=float, default=0.7)
    parser.add_argument("--vg-stop", type=float, default=1.3)
    parser.add_argument("--vg-step", type=float, default=0.1)
    parser.add_argument("--swarm-size", type=int, default=24)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--archive-size", type=int, default=100)
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help=(
            "Allow starting a fresh MOPSO run in an output directory that "
            "already contains optimization data."
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
    parser.add_argument("--inertia-weight", type=float, default=0.6)
    parser.add_argument("--cognitive-weight", type=float, default=1.5)
    parser.add_argument("--social-weight", type=float, default=1.5)
    parser.add_argument("--velocity-clamp", type=float, default=0.5)
    parser.add_argument("--mutation-probability", type=float, default=0.05)
    parser.add_argument(
        "--archive-partitions",
        "--reference-partitions",
        dest="archive_partitions",
        type=int,
        default=4,
        help="Reference-direction partitions used when capping the leader archive.",
    )
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
        help="Number of circuit evaluations to simulate in parallel per iteration.",
    )
    parser.add_argument(
        "--sim-timeout",
        type=float,
        help="Kill an ngspice simulation after this many seconds.",
    )
    parser.add_argument(
        "--circuit-database",
        default=str(DEFAULT_CIRCUIT_DATABASE_PATH),
        help=(
            "SQLite simulated-circuit database to reuse before running "
            "ngspice. If the path does not exist, simulations run normally."
        ),
    )
    parser.add_argument(
        "--no-circuit-database",
        action="store_true",
        help="Disable simulated-circuit database reuse.",
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

    if args.swarm_size < 1:
        raise ValueError("--swarm-size must be at least 1")
    if args.iterations < 0:
        raise ValueError("--iterations must be non-negative")
    if args.archive_size < 1:
        raise ValueError("--archive-size must be at least 1")
    if args.sim_threads < 1:
        raise ValueError("--sim-threads must be at least 1")
    if args.sim_timeout is not None and args.sim_timeout <= 0:
        raise ValueError("--sim-timeout must be positive")
    if args.velocity_clamp < 0:
        raise ValueError("--velocity-clamp must be non-negative")
    if not 0 <= args.mutation_probability <= 1:
        raise ValueError("--mutation-probability must be between 0 and 1")
    if args.archive_partitions < 0:
        raise ValueError("--archive-partitions must be non-negative")

    optimize(args)


if __name__ == "__main__":
    main()
