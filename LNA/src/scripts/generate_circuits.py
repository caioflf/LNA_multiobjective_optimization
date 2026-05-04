from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.database.transistors import GROUPS as TRANSISTOR_GROUPS
from src.scripts.netlist_generator import (
    DEFAULT_NETWORK_DATABASE_PATH,
    generate_circuit_library,
    load_network_database,
)


TRANSISTOR_GROUP_ALIASES = {
    "nmos": "nmos",
    "nmos_lvt": "nmos_lvt",
    "lvt": "nmos_lvt",
    "nmos_and_lvt": "nmos_and_lvt",
    "all": "all",
}


def resolve_transistor_group(group_name):
    normalized = TRANSISTOR_GROUP_ALIASES[group_name]
    if normalized == "nmos_and_lvt":
        return TRANSISTOR_GROUPS["nmos"] + TRANSISTOR_GROUPS["nmos_lvt"]
    return TRANSISTOR_GROUPS[normalized]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate circuit folders from the passive-network database and the "
            "current circuit-role restrictions."
        )
    )
    parser.add_argument(
        "--output-root",
        default="generated_circuits",
        help="Directory where the circuits/ folder and manifest.json will be created.",
    )
    parser.add_argument(
        "--network-database",
        default=str(DEFAULT_NETWORK_DATABASE_PATH),
        help="Passive-network database JSON to use.",
    )
    parser.add_argument(
        "--transistor-group",
        choices=sorted(TRANSISTOR_GROUP_ALIASES),
        default="nmos",
        help="Transistor group to expand.",
    )
    parser.add_argument(
        "--vg-start",
        type=float,
        default=0.7,
        help="Bias sweep start voltage.",
    )
    parser.add_argument(
        "--vg-stop",
        type=float,
        default=1.3,
        help="Bias sweep stop voltage.",
    )
    parser.add_argument(
        "--vg-step",
        type=float,
        default=0.1,
        help="Bias sweep step voltage.",
    )
    parser.add_argument(
        "--max-circuits",
        type=int,
        help="Optional hard limit on generated circuit folders.",
    )
    parser.add_argument(
        "--print-useful-data",
        action="store_true",
        help="Emit extra scalar measurements in each generated netlist.",
    )
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Starting circuit index for folder numbering.",
    )
    args = parser.parse_args()

    network_database = load_network_database(args.network_database)
    network_ids = [network["identifier"] for network in network_database]
    transistor_models = resolve_transistor_group(args.transistor_group)

    manifest = generate_circuit_library(
        output_root=args.output_root,
        transistor_models=transistor_models,
        gate_networks=network_ids,
        source_networks=network_ids + [None],
        load_networks=network_ids,
        feedback_networks=network_ids + [None],
        network_database_path=args.network_database,
        vg_start=args.vg_start,
        vg_stop=args.vg_stop,
        vg_step=args.vg_step,
        start_index=args.start_index,
        max_circuits=args.max_circuits,
        print_useful_data=args.print_useful_data,
    )
    print(
        "Generated "
        f"{manifest['circuit_count']} circuits in {manifest['output_root']}"
    )


if __name__ == "__main__":
    main()
