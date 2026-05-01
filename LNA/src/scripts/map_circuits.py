from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.scripts.optimization_mapping import (
    NETWORK_ROLES,
    build_circuit_optimization_mapping,
    build_optimization_index,
)


DEFAULT_MAP_FILENAME = "circuit_map.json"


def _print_progress(message):
    print(f"[map_circuits] {message}", flush=True)


def _should_report(index, total, progress_every):
    if progress_every <= 1:
        return True
    return index == 1 or index == total or index % progress_every == 0


def _read_manifest(output_root):
    manifest_path = Path(output_root) / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text())


def _metadata_path_for_index(circuits_root, circuit_index):
    return circuits_root / f"circuit_{circuit_index:08d}" / "metadata.json"


def _select_metadata_paths(output_root, *, subset=None, max_circuits=None):
    output_root = Path(output_root)
    circuits_root = output_root / "circuits"

    if subset:
        paths = [circuits_root / name / "metadata.json" for name in subset]
        return paths[:max_circuits] if max_circuits is not None else paths

    manifest = _read_manifest(output_root)
    start_index = manifest.get("start_index")
    last_index = manifest.get("last_index")
    if max_circuits is not None and start_index is not None and last_index is not None:
        stop_index = min(last_index, start_index + max_circuits - 1)
        return [
            path
            for path in (
                _metadata_path_for_index(circuits_root, circuit_index)
                for circuit_index in range(start_index, stop_index + 1)
            )
            if path.exists()
        ]

    paths = sorted(circuits_root.glob("circuit_*/metadata.json"))
    return paths[:max_circuits] if max_circuits is not None else paths


def _collect_optimization_inputs(
    metadata_paths,
    *,
    show_progress=True,
    progress_every=1000,
):
    total = len(metadata_paths)
    transistors = []
    transistor_names = set()
    vg_values = []
    seen_vg_values = set()
    network_summaries_by_role = {role: [] for role in NETWORK_ROLES}
    seen_networks_by_role = {role: set() for role in NETWORK_ROLES}

    for index, metadata_path in enumerate(metadata_paths, start=1):
        if show_progress and _should_report(index, total, progress_every):
            _print_progress(f"indexing {index}/{total}: {metadata_path.parent.name}")
        metadata = json.loads(metadata_path.read_text())
        transistor = metadata["transistor"]
        transistor_name = transistor["name"]
        if transistor_name not in transistor_names:
            transistor_names.add(transistor_name)
            transistors.append(transistor)

        generation_parameters = metadata.get("generation_parameters", {})
        if "vg" in generation_parameters:
            vg = generation_parameters["vg"]
            if vg not in seen_vg_values:
                seen_vg_values.add(vg)
                vg_values.append(vg)

        for role in NETWORK_ROLES:
            network_summary = metadata["networks"][role]
            network_key = json.dumps(network_summary, sort_keys=True)
            if network_key in seen_networks_by_role[role]:
                continue
            seen_networks_by_role[role].add(network_key)
            network_summaries_by_role[role].append(network_summary)

    return transistors, network_summaries_by_role, vg_values


def build_circuit_map(
    output_root,
    *,
    subset=None,
    max_circuits=None,
    update_metadata=False,
    show_progress=True,
    progress_every=1000,
):
    if progress_every < 1:
        raise ValueError("progress_every must be at least 1")

    output_root = Path(output_root)
    if show_progress:
        _print_progress(f"selecting metadata from {output_root / 'circuits'}")
    metadata_paths = _select_metadata_paths(
        output_root,
        subset=subset,
        max_circuits=max_circuits,
    )
    if show_progress:
        _print_progress(f"selected {len(metadata_paths)} circuit metadata file(s)")

    transistors, network_summaries_by_role, vg_values = _collect_optimization_inputs(
        metadata_paths,
        show_progress=show_progress,
        progress_every=progress_every,
    )
    optimization_index = build_optimization_index(
        transistors,
        network_summaries_by_role,
        vg_values,
    )

    circuit_entries = []
    total = len(metadata_paths)
    for index, metadata_path in enumerate(metadata_paths, start=1):
        metadata = json.loads(metadata_path.read_text())
        mapping = build_circuit_optimization_mapping(metadata, optimization_index)
        if update_metadata:
            metadata["optimization"] = mapping
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

        if show_progress and _should_report(index, total, progress_every):
            _print_progress(f"mapped {index}/{total}: {metadata_path.parent.name}")

        circuit_entries.append(
            {
                "circuit_index": metadata.get("circuit_index"),
                "circuit_dir": metadata_path.parent.name,
                "metadata": str(metadata_path.relative_to(output_root)),
                "netlist": metadata.get("files", {}).get("netlist"),
                "coordinate": mapping["coordinate"],
            }
        )

    return {
        "schema_version": optimization_index["schema_version"],
        "output_root": str(output_root),
        "circuit_count": len(circuit_entries),
        "coordinate_axes": optimization_index["coordinate_axes"],
        "optimization_index": optimization_index,
        "circuits": circuit_entries,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build a compact optimization map for generated circuit metadata."
        )
    )
    parser.add_argument(
        "output_root",
        nargs="?",
        default="generated_circuits",
        help="Library root containing manifest.json and circuits/.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Output JSON path. Defaults to circuit_map.json under output_root."
        ),
    )
    parser.add_argument(
        "--subset",
        nargs="+",
        help="Optional list of circuit folder names, e.g. circuit_00000001.",
    )
    parser.add_argument(
        "--max-circuits",
        type=int,
        help="Limit mapping to the first N selected circuits.",
    )
    parser.add_argument(
        "--update-metadata",
        action="store_true",
        help="Also write each circuit coordinate back into metadata.json.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable terminal progress messages.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=1000,
        help="Print per-circuit progress every N circuits (default: 1000).",
    )
    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_path = (
        Path(args.output)
        if args.output
        else output_root / DEFAULT_MAP_FILENAME
    )
    circuit_map = build_circuit_map(
        output_root,
        subset=args.subset,
        max_circuits=args.max_circuits,
        update_metadata=args.update_metadata,
        show_progress=not args.no_progress,
        progress_every=args.progress_every,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(circuit_map, indent=2) + "\n")
    if not args.no_progress:
        _print_progress(f"wrote {output_path}")


if __name__ == "__main__":
    main()
