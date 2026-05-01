from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
import re
import subprocess
import threading
from pathlib import Path


DEFAULT_MEASURE_FILENAME = "measures.json"
DEFAULT_ANALYSIS_FILENAME = "analysis.json"
DEFAULT_LOG_FILENAME = "ngspice.log.txt"
ZO = 50.0
TEMPERATURE_C = 27.0
TEMPERATURE_K = TEMPERATURE_C + 273.15
K_BOLTZMANN = 1.380649e-23
DEFAULT_F0 = 2.4e9
DEFAULT_SIMULATION_THREADS = 8
DEFAULT_SIMULATION_PRIORITY = "high"
DEFAULT_PROGRESS_EVERY = 1
PRIORITY_NICE_VALUES = {
    "high": -10,
    "normal": 0,
    "low": 10,
}
_PROGRESS_LOCK = threading.Lock()


def _print_progress(message):
    with _PROGRESS_LOCK:
        print(f"[simulate_circuits] {message}", flush=True)


def _should_report_progress(index, total, progress_every):
    if progress_every <= 1:
        return True
    return index == 1 or index == total or index % progress_every == 0


def _simulate_one_with_progress(
    index,
    total,
    circuit_dir,
    *,
    show_progress,
    progress_every,
    measure_filename,
    log_filename,
    priority,
):
    display_index = index + 1
    report = show_progress and _should_report_progress(
        display_index,
        total,
        progress_every,
    )
    if report:
        _print_progress(f"running {display_index}/{total}: {Path(circuit_dir).name}")
    return run_circuit_simulation(
        circuit_dir,
        measure_filename=measure_filename,
        log_filename=log_filename,
        priority=priority,
    )


def parse_measures_from_stdout(stdout_text):
    """Parse scalar ngspice measurements already emitted to stdout."""
    measures = {}
    pattern = re.compile(
        r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"
        r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)",
        re.MULTILINE,
    )
    for match in pattern.finditer(stdout_text):
        measures[match.group(1).strip().lower()] = float(match.group(2))
    measures.update(parse_mos_operating_point_from_show_all(stdout_text))
    return measures


def parse_mos_operating_point_from_show_all(stdout_text):
    """Extract the active MOS operating point from the ngspice `show all` table."""
    row_values = {
        "gm": [],
        "gmbs": [],
        "gds": [],
    }
    number_pattern = re.compile(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    )

    for line in stdout_text.splitlines():
        parts = line.split()
        if not parts:
            continue
        row_name = parts[0].lower()
        if row_name not in row_values:
            continue
        values = [float(value) for value in number_pattern.findall(line)]
        row_values[row_name].extend(values)

    if not row_values["gm"]:
        return {}

    active_index = max(
        range(len(row_values["gm"])),
        key=lambda index: abs(row_values["gm"][index]),
    )
    extracted = {
        "gm_dc": row_values["gm"][active_index],
    }
    if active_index < len(row_values["gmbs"]):
        extracted["gmb_dc"] = row_values["gmbs"][active_index]
    if active_index < len(row_values["gds"]):
        gds = row_values["gds"][active_index]
        extracted["gds_dc"] = gds
        if gds != 0:
            extracted["ro_dc"] = 1 / gds
    return extracted


def _read_metadata(circuit_dir):
    metadata_path = Path(circuit_dir) / "metadata.json"
    if not metadata_path.exists():
        return {}
    return json.loads(metadata_path.read_text())


def _resolve_netlist_path(circuit_dir, netlist_filename=None):
    circuit_dir = Path(circuit_dir)
    if netlist_filename is not None:
        netlist_path = circuit_dir / netlist_filename
        if not netlist_path.exists():
            raise FileNotFoundError(f"Netlist not found: {netlist_path}")
        return netlist_path

    metadata = _read_metadata(circuit_dir)
    netlist_name = metadata.get("files", {}).get("netlist")
    if netlist_name:
        netlist_path = circuit_dir / netlist_name
        if netlist_path.exists():
            return netlist_path

    netlists = sorted(circuit_dir.glob("*.cir"))
    if len(netlists) != 1:
        raise ValueError(
            f"Expected exactly one .cir file in {circuit_dir}, found {len(netlists)}"
        )
    return netlists[0]


def _set_process_priority(process, priority):
    """Best-effort process priority adjustment for the spawned ngspice process."""
    if priority == "normal":
        return {
            "requested": priority,
            "applied": True,
            "message": "using inherited process priority",
        }
    if not hasattr(os, "setpriority") or not hasattr(os, "PRIO_PROCESS"):
        return {
            "requested": priority,
            "applied": False,
            "message": "process priority is not supported on this platform",
        }

    nice_value = PRIORITY_NICE_VALUES[priority]
    try:
        os.setpriority(os.PRIO_PROCESS, process.pid, nice_value)
    except OSError as exc:
        return {
            "requested": priority,
            "applied": False,
            "message": (
                f"could not set process priority to {priority} "
                f"(nice {nice_value}): {exc}"
            ),
        }

    return {
        "requested": priority,
        "applied": True,
        "nice": nice_value,
        "message": f"set process priority to {priority} (nice {nice_value})",
    }


def run_circuit_simulation(
    circuit_dir,
    *,
    netlist_filename=None,
    measure_filename=DEFAULT_MEASURE_FILENAME,
    log_filename=DEFAULT_LOG_FILENAME,
    priority=DEFAULT_SIMULATION_PRIORITY,
):
    """
    Run `ngspice -b` for one generated circuit folder and save parsed measures.
    """
    circuit_dir = Path(circuit_dir)
    netlist_path = _resolve_netlist_path(circuit_dir, netlist_filename=netlist_filename)

    process = subprocess.Popen(
        ["ngspice", "-b", netlist_path.name],
        cwd=circuit_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    priority_status = _set_process_priority(process, priority)
    stdout, stderr = process.communicate()

    result = subprocess.CompletedProcess(
        process.args,
        process.returncode,
        stdout,
        stderr,
    )
    log_text = result.stdout
    if result.stderr:
        if log_text and not log_text.endswith("\n"):
            log_text += "\n"
        log_text += result.stderr
    if not priority_status["applied"]:
        if log_text and not log_text.endswith("\n"):
            log_text += "\n"
        log_text += f"[simulate_circuits] {priority_status['message']}\n"
    (circuit_dir / log_filename).write_text(log_text)
    measures = parse_measures_from_stdout(result.stdout)

    payload = {
        "netlist": netlist_path.name,
        "returncode": result.returncode,
        "log": log_filename,
        "priority": priority_status,
        "measures": measures,
    }
    (circuit_dir / measure_filename).write_text(json.dumps(payload, indent=2) + "\n")

    if result.returncode != 0:
        raise RuntimeError(f"ngspice failed for {netlist_path.name} in {circuit_dir}")

    return payload


def derive_metrics(measures, *, f0=DEFAULT_F0, zo=ZO, temperature_k=TEMPERATURE_K):
    """Derive useful LNA metrics from the saved scalar measures."""
    gain_db = measures.get("gain_db")
    f_3db_low = measures.get("f_3db_low")
    f_3db_high = measures.get("f_3db_high")
    vin_re = measures.get("vin_re")
    vin_im = measures.get("vin_im")
    iin_re = measures.get("iin_re")
    iin_im = measures.get("iin_im")
    inoise_total = measures.get("inoise_total")

    derived = {}

    if gain_db is not None:
        derived["gain_db"] = gain_db

    if f_3db_low is not None and f_3db_high is not None and f0:
        bandwidth_hz = f_3db_high - f_3db_low
        derived["bandwidth_hz"] = bandwidth_hz
        derived["fractional_bandwidth_percent"] = 100.0 * bandwidth_hz / f0

    if None not in (vin_re, vin_im, iin_re, iin_im):
        vin = complex(vin_re, vin_im)
        iin = -complex(iin_re, iin_im)
        if abs(iin) > 0:
            zin = vin / iin
            gamma = (zin - zo) / (zin + zo)
            derived["zin_re"] = zin.real
            derived["zin_im"] = zin.imag
            derived["s11_mag"] = abs(gamma)
            if abs(gamma) > 0:
                derived["s11_db"] = 20.0 * math.log10(abs(gamma))

    if (
        inoise_total is not None
        and f_3db_low is not None
        and f_3db_high is not None
        and f_3db_high > f_3db_low
    ):
        bandwidth_hz = f_3db_high - f_3db_low
        nf = inoise_total / (4 * K_BOLTZMANN * temperature_k * zo * bandwidth_hz)
        if nf > 0:
            derived["noise_figure"] = nf
            derived["noise_figure_db"] = 10.0 * math.log10(nf)

    return derived


def analyze_circuit_measures(
    circuit_dir,
    *,
    measure_filename=DEFAULT_MEASURE_FILENAME,
    analysis_filename=DEFAULT_ANALYSIS_FILENAME,
):
    """
    Read an existing `measures.json`, derive metrics, and save `analysis.json`.
    """
    circuit_dir = Path(circuit_dir)
    measure_path = circuit_dir / measure_filename
    payload = json.loads(measure_path.read_text())
    metadata = _read_metadata(circuit_dir)
    f0 = metadata.get("generation_parameters", {}).get("f0", DEFAULT_F0)
    derived = derive_metrics(payload.get("measures", {}), f0=f0)
    analysis = {
        "netlist": payload.get("netlist"),
        "derived_metrics": derived,
    }
    (circuit_dir / analysis_filename).write_text(json.dumps(analysis, indent=2) + "\n")
    return analysis


def _select_circuit_dirs(output_root, subset=None, max_circuits=None):
    circuit_dirs = sorted((Path(output_root) / "circuits").glob("circuit_*"))
    if subset:
        subset_set = set(subset)
        circuit_dirs = [path for path in circuit_dirs if path.name in subset_set]
    if max_circuits is not None:
        circuit_dirs = circuit_dirs[:max_circuits]
    return circuit_dirs


def simulate_circuit_library(
    output_root,
    *,
    subset=None,
    max_circuits=None,
    threads=DEFAULT_SIMULATION_THREADS,
    priority=DEFAULT_SIMULATION_PRIORITY,
    measure_filename=DEFAULT_MEASURE_FILENAME,
    log_filename=DEFAULT_LOG_FILENAME,
    show_progress=True,
    progress_every=DEFAULT_PROGRESS_EVERY,
):
    """Run ngspice on all or a chosen subset of generated circuit folders."""
    if threads < 1:
        raise ValueError("threads must be at least 1")
    if progress_every < 1:
        raise ValueError("progress_every must be at least 1")

    circuits_root = Path(output_root) / "circuits"
    if show_progress:
        _print_progress(f"selecting circuits from {circuits_root}")
    circuit_dirs = _select_circuit_dirs(
        output_root,
        subset=subset,
        max_circuits=max_circuits,
    )
    total = len(circuit_dirs)
    if show_progress:
        _print_progress(f"selected {total} circuit(s) from {circuits_root}")
        if total:
            _print_progress(
                f"simulating with {threads} thread(s), priority={priority}"
            )
    if threads == 1:
        results = []
        for index, circuit_dir in enumerate(circuit_dirs):
            try:
                results.append(
                    _simulate_one_with_progress(
                        index,
                        total,
                        circuit_dir,
                        show_progress=show_progress,
                        progress_every=progress_every,
                        measure_filename=measure_filename,
                        log_filename=log_filename,
                        priority=priority,
                    )
                )
            except Exception as exc:
                if show_progress:
                    _print_progress(
                        f"failed {index + 1}/{total}: {circuit_dir.name}: {exc}"
                    )
                raise
            if show_progress and _should_report_progress(
                index + 1,
                total,
                progress_every,
            ):
                _print_progress(f"finished {index + 1}/{total}: {circuit_dir.name}")
        if show_progress:
            _print_progress(f"simulation complete: {len(results)}/{total} finished")
        return results

    results = [None] * total
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {
            executor.submit(
                _simulate_one_with_progress,
                index,
                total,
                circuit_dir,
                show_progress=show_progress,
                progress_every=progress_every,
                measure_filename=measure_filename,
                log_filename=log_filename,
                priority=priority,
            ): index
            for index, circuit_dir in enumerate(circuit_dirs)
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            index = futures[future]
            circuit_dir = circuit_dirs[index]
            try:
                results[index] = future.result()
            except Exception as exc:
                if show_progress:
                    _print_progress(
                        f"failed {completed}/{total}: {circuit_dir.name}: {exc}"
                    )
                raise
            if show_progress and _should_report_progress(
                completed,
                total,
                progress_every,
            ):
                _print_progress(f"finished {completed}/{total}: {circuit_dir.name}")
    if show_progress:
        _print_progress(f"simulation complete: {total}/{total} finished")
    return results


def analyze_circuit_library(
    output_root,
    *,
    subset=None,
    max_circuits=None,
    measure_filename=DEFAULT_MEASURE_FILENAME,
    analysis_filename=DEFAULT_ANALYSIS_FILENAME,
    show_progress=True,
    progress_every=DEFAULT_PROGRESS_EVERY,
):
    """Analyze existing measure files for all or a chosen subset of circuits."""
    if progress_every < 1:
        raise ValueError("progress_every must be at least 1")

    circuits_root = Path(output_root) / "circuits"
    if show_progress:
        _print_progress(f"selecting circuits from {circuits_root}")
    circuit_dirs = _select_circuit_dirs(
        output_root,
        subset=subset,
        max_circuits=max_circuits,
    )
    total = len(circuit_dirs)
    if show_progress:
        _print_progress(f"analyzing {total} circuit(s)")
    analyses = []
    for index, circuit_dir in enumerate(circuit_dirs, start=1):
        if show_progress and _should_report_progress(index, total, progress_every):
            _print_progress(f"analyzing {index}/{total}: {circuit_dir.name}")
        analyses.append(
            analyze_circuit_measures(
                circuit_dir,
                measure_filename=measure_filename,
                analysis_filename=analysis_filename,
            )
        )
    if show_progress:
        _print_progress(f"analysis complete: {len(analyses)}/{total} finished")
    return analyses


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run ngspice on already generated circuit folders and/or analyze the "
            "saved scalar measures."
        )
    )
    parser.add_argument("output_root", help="Library root containing the circuits/ folder.")
    parser.add_argument(
        "--subset",
        nargs="+",
        help="Optional list of circuit folder names, e.g. circuit_00000001 circuit_00000042",
    )
    parser.add_argument(
        "--max-circuits",
        type=int,
        help="Limit processing to the first N selected circuit folders.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_SIMULATION_THREADS,
        help=(
            "Number of ngspice simulations to run concurrently "
            f"(default: {DEFAULT_SIMULATION_THREADS})."
        ),
    )
    parser.add_argument(
        "--priority",
        choices=sorted(PRIORITY_NICE_VALUES),
        default=DEFAULT_SIMULATION_PRIORITY,
        help=(
            "Best-effort process priority for spawned ngspice processes "
            f"(default: {DEFAULT_SIMULATION_PRIORITY})."
        ),
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Skip ngspice runs and only analyze existing measures.json files.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable terminal progress messages.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=DEFAULT_PROGRESS_EVERY,
        help=(
            "Print per-circuit progress every N circuits "
            f"(default: {DEFAULT_PROGRESS_EVERY})."
        ),
    )
    args = parser.parse_args()
    show_progress = not args.no_progress

    if not args.analyze_only:
        simulate_circuit_library(
            args.output_root,
            subset=args.subset,
            max_circuits=args.max_circuits,
            threads=args.threads,
            priority=args.priority,
            show_progress=show_progress,
            progress_every=args.progress_every,
        )
    analyze_circuit_library(
        args.output_root,
        subset=args.subset,
        max_circuits=args.max_circuits,
        show_progress=show_progress,
        progress_every=args.progress_every,
    )


if __name__ == "__main__":
    main()
