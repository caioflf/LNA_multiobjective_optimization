from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.database.transistors import BY_NAME as TRANSISTOR_BY_NAME
from src.database.transistors import TRANSISTORS
from src.database.capacitors import estimate_mim_capacitance_f
from src.scripts.optimization_mapping import (
    build_circuit_optimization_mapping,
    build_optimization_index,
)

DEFAULT_RF_INCLUDE_PATH_TEMPLATE = [
    "sky130A/libs.tech/ngspice/sky130_fd_pr__model__inductors.model.spice",
]
DEFAULT_LG = 5e-9
DEFAULT_LS = 1e-9
DEFAULT_LD = 5e-9

DEFAULT_NETWORK_DATABASE_PATH = (
    REPO_ROOT / "src" / "database" / "passive_networks_mim_no_varactors.json"
)
OPEN_RLC_PARALLEL_IDENTIFIER = "rlc_parallel__r00__l00__c00"
FIXED_OUTPUT_COUPLING_CAP = {
    "identifier": "fixed_output_coupling_cap",
    "model_name": "sky130_fd_pr__cap_mim_m3_2",
    "family": "mim",
    "pin_order": ("c0", "c1"),
    "width_um": 10,
    "length_um": 10,
    "mf": 1,
    "area_um2": 10 * 10,
    "nominal_capacitance_f": estimate_mim_capacitance_f(10, 10, 1),
}
FIXED_INPUT_COUPLING_CAP = {
    **FIXED_OUTPUT_COUPLING_CAP,
    "identifier": "fixed_input_coupling_cap",
}


def _slugify(value, max_length=80):
    slug = "".join(
        character if character.isalnum() else "_"
        for character in str(value)
    )
    while "__" in slug:
        slug = slug.replace("__", "_")
    slug = slug.strip("_")
    if not slug:
        slug = "unnamed"
    return slug[:max_length]


def _transistor_short_label(transistor_model):
    device_type = getattr(transistor_model, "device_type", None)
    if device_type not in {"nmos", "pmos"}:
        model_name = getattr(transistor_model, "name", "")
        if "pfet" in model_name:
            device_type = "pmos"
        else:
            device_type = "nmos"

    threshold = getattr(transistor_model, "threshold", "standard")
    if threshold == "lvt" or "_lvt" in getattr(transistor_model, "name", ""):
        return f"{device_type}_lvt"
    return device_type


def build_circuit_netlist_stem(
    transistor_model,
    gate_network,
    source_network,
    load_network,
    feedback_network,
    *,
    circuit_index=None,
    vg=None,
):
    """Build a compact stem for generated `.cir` filenames."""
    parts = []
    if circuit_index is not None:
        parts.append(f"c{circuit_index:08d}")
    parts.extend(
        [
            _transistor_short_label(transistor_model),
            f"vg_{_slugify(vg, 16)}" if vg is not None else None,
        ]
    )
    return "__".join(part for part in parts if part is not None)


def _as_include_templates(include_templates):
    if include_templates is None:
        return []
    if isinstance(include_templates, str):
        return [include_templates]
    return list(include_templates)


def _format_include_path(pdk_root, include_template, corner):
    include_path = include_template.format(corner=corner)
    if include_path.startswith("$"):
        return include_path
    return f"{pdk_root}/{include_path}"


def _write_insertion_network(
    fp,
    section_name,
    node_p,
    node_n,
    network_spec,
    default_line=None,
    allow_open=False,
    none_behavior="default",
):
    """
    Write a configurable 2-terminal insertion network.

    Supported `network_spec` values:
    - None: behavior depends on `none_behavior`
    - "open" or "": emit nothing when `allow_open=True`
    - "short": emit a near-short resistor
    - "default": emit `default_line`
    - raw netlist text: emitted as-is after `.format(...)`

    Raw netlist text may use these placeholders:
    - `{name}`: insertion section name
    - `{p}`: positive/first node
    - `{n}`: negative/second node
    """
    if network_spec is None:
        if none_behavior == "default":
            if default_line:
                fp.write(f"{default_line}\n")
            return
        if none_behavior == "short":
            fp.write(f"R{section_name}_SHORT {node_p} {node_n} 1e-9\n")
            return
        if none_behavior == "open":
            return
        if none_behavior == "error":
            raise ValueError(f"{section_name} requires an explicit network")
        raise ValueError(f"Unsupported none_behavior for {section_name}: {none_behavior}")
    if not isinstance(network_spec, str):
        raise TypeError(f"{section_name} network spec must be a string or None")

    normalized = network_spec.strip()
    if normalized.lower() == "default":
        if default_line:
            fp.write(f"{default_line}\n")
            return
        raise ValueError(f"{section_name} has no default element to restore")

    if not normalized or normalized.lower() == "open":
        if not allow_open:
            raise ValueError(f"{section_name} does not allow an open circuit insertion")
        return

    if normalized.lower() == "short":
        fp.write(f"R{section_name}_SHORT {node_p} {node_n} 1e-9\n")
        return

    rendered = normalized.format(name=section_name, p=node_p, n=node_n)
    if not rendered.endswith("\n"):
        rendered += "\n"
    fp.write(rendered)


def write_netlist(
    netlist_path,
    vg,
    lg,
    ls,
    ld,
    corner,
    transistor_model_name,
    circuit_title,
    pdk_root,
    process_lib_path,
    rf_include_path_template,
    temperature_c,
    f0,
    vdd,
    ac_start,
    ac_stop,
    print_useful_data=False,
    gate_network="default",
    source_network="default",
    load_network="default",
    feedback_network=None,
):
    """
    Generate an ngspice netlist.

    Optional insertion-network arguments replace the default passive element
    at each location:
    - `gate_network`: inserted between the fixed input coupling cap and `gate`
    - `source_network`: inserted between `source` and `0`
    - `load_network`: inserted between `vdd` and `drain`
    - `feedback_network`: inserted between `drain` and `gate`

    Each network may be:
    - "default": keep the default element (`gate/source/load`)
    - None: short for `source_network`, open for `feedback_network`
    - "" / "open": open circuit
    - "short": near-short resistor
    - raw netlist text with `{p}` and `{n}` placeholders

    When `print_useful_data=True`, the control block emits extra scalar data
    useful for post-processing without printing full vectors.
    """
    netlist_file = Path(netlist_path)
    include_paths = [
        _format_include_path(pdk_root, include_template, corner)
        for include_template in _as_include_templates(rf_include_path_template)
    ]

    with open(netlist_file, "w") as fp:
        fp.write(f"* {circuit_title}\n")
        fp.write(f'.lib "{pdk_root}/{process_lib_path}" {corner}\n\n')
        for include_path in include_paths:
            fp.write(f'.include "{include_path}"\n')
        if include_paths:
            fp.write("\n")

        fp.write(f".options temp={temperature_c}\n")
        fp.write(f".param F0={f0}\n")
        fp.write(f".csparam f0={f0}\n")
        fp.write(f".param VDD={vdd}\n")
        fp.write(f".param VG={vg}\n")
        fp.write(f".param LG={lg}\n")
        fp.write(f".param LS={ls}\n")
        fp.write(f".param LD={ld}\n\n")

        fp.write("VDD vdd 0 DC {VDD}\n")
        fp.write("VBIAS vbias 0 DC {VG}\n\n")

        fp.write("VIN       src 0 AC 1 DC 0\n")
        fp.write("Rsource   src in 50\n")
        fp.write(
            "XINCAP in gate_in "
            f"{FIXED_INPUT_COUPLING_CAP['model_name']} "
            f"w={FIXED_INPUT_COUPLING_CAP['width_um']} "
            f"l={FIXED_INPUT_COUPLING_CAP['length_um']} "
            f"mf={FIXED_INPUT_COUPLING_CAP['mf']}\n"
        )

        _write_insertion_network(
            fp,
            "LGATE",
            "gate_in",
            "gate",
            gate_network,
            default_line="LGATE gate_in gate {LG}",
            allow_open=True,
            none_behavior="error",
        )
        fp.write("RBIAS gate vbias 1MEG\n")

        _write_insertion_network(
            fp,
            "LSRC",
            "source",
            "0",
            source_network,
            default_line="LSRC source 0 {LS}",
            allow_open=True,
            none_behavior="short",
        )
        fp.write(f"xn1 drain gate source 0 {transistor_model_name}\n")

        _write_insertion_network(
            fp,
            "LLOAD",
            "vdd",
            "drain",
            load_network,
            default_line="LLOAD vdd drain {LD}",
            allow_open=True,
            none_behavior="error",
        )
        _write_insertion_network(
            fp,
            "FBBK",
            "drain",
            "gate",
            feedback_network,
            allow_open=True,
            none_behavior="open",
        )

        fp.write(
            "XOUTCAP drain out "
            f"{FIXED_OUTPUT_COUPLING_CAP['model_name']} "
            f"w={FIXED_OUTPUT_COUPLING_CAP['width_um']} "
            f"l={FIXED_OUTPUT_COUPLING_CAP['length_um']} "
            f"mf={FIXED_OUTPUT_COUPLING_CAP['mf']}\n"
        )
        fp.write("RLOAD out 0 50\n\n")

        fp.write(".control\n")
        fp.write("set sqrnoise\n")
        fp.write("op\n")
        fp.write("let idd = -i(VDD)\n")
        fp.write("let pdc = v(vdd) * idd\n")
        fp.write('echo idd = "$&idd"\n')
        fp.write('echo pdc = "$&pdc"\n')
        if print_useful_data:
            fp.write("show all\n")

        fp.write(f"ac dec 200 {ac_start} {ac_stop}\n\n")

        fp.write("setplot ac1\n")
        fp.write("let gain_db_vector = db(v(out)/v(in))\n")
        fp.write(f"meas ac gain_db       find    gain_db_vector                at={f0}\n")

        fp.write("let gain_3db = gain_db - 3\n")
        fp.write(f"let f_3db_low = {ac_start}\n")
        fp.write(f"let f_3db_high = {ac_stop}\n")
        fp.write("meas ac f_3db_low    when    gain_db_vector=gain_3db      rise=1\n")
        fp.write("meas ac f_3db_high   when    gain_db_vector=gain_3db      fall=1\n")
        fp.write(
            "noise v(out) VIN dec 200 $&f_3db_low $&f_3db_high\n\n"
        )

        fp.write("setplot ac1\n")

        fp.write("let vin_re_vector = real(v(in))\n")
        fp.write(f"meas ac vin_re       find    vin_re_vector                     at={f0}\n")

        fp.write("let vin_im_vector = imag(v(in))\n")
        fp.write(f"meas ac vin_im       find    vin_im_vector                     at={f0}\n")

        fp.write("let iin_re_vector = real(i(VIN))\n")
        fp.write(f"meas ac iin_re       find    iin_re_vector                  at={f0}\n")

        fp.write("let iin_im_vector = imag(i(VIN))\n")
        fp.write(f"meas ac iin_im       find    iin_im_vector                    at={f0}\n")

        fp.write("let vout_re_vector = real(v(out))\n")
        fp.write(f"meas ac vout_re      find    vout_re_vector                    at={f0}\n")

        fp.write("let vout_im_vector = imag(v(out))\n")
        fp.write(f"meas ac vout_im      find    vout_im_vector                    at={f0}\n")
        if print_useful_data:
            fp.write("let vin_mag_vector = mag(v(in))\n")
            fp.write(f"meas ac vin_mag      find    vin_mag_vector                    at={f0}\n")
            fp.write("let iin_mag_vector = mag(i(VIN))\n")
            fp.write(f"meas ac iin_mag      find    iin_mag_vector                    at={f0}\n")
            fp.write("let vout_mag_vector = mag(v(out))\n")
            fp.write(f"meas ac vout_mag     find    vout_mag_vector                   at={f0}\n")
            fp.write("let zin_re_vector = real(v(in)/(-i(VIN)))\n")
            fp.write(f"meas ac zin_re       find    zin_re_vector                     at={f0}\n")
            fp.write("let zin_im_vector = imag(v(in)/(-i(VIN)))\n")
            fp.write(f"meas ac zin_im       find    zin_im_vector                     at={f0}\n")

        fp.write("setplot noise2\n")
        fp.write("print inoise_total\n")
        fp.write("print onoise_total\n")

        fp.write(".endc\n")

        fp.write(".end\n")

    return netlist_file


def load_network_database(database_path=DEFAULT_NETWORK_DATABASE_PATH):
    """Load a passive-network JSON database."""
    database_file = Path(database_path)
    payload = json.loads(database_file.read_text())
    if isinstance(payload, dict):
        return payload["networks"]
    return payload


def index_network_database(network_database):
    """Index passive networks by identifier."""
    return {network["identifier"]: network for network in network_database}


def resolve_transistor_models(transistor_models=None):
    """
    Resolve transistor model references.

    Supported values:
    - None: all known transistor models
    - transistor model objects with a `.name` attribute
    - model-name strings
    """
    if transistor_models is None:
        return list(TRANSISTORS)

    resolved = []
    for model in transistor_models:
        if hasattr(model, "name"):
            resolved.append(model)
            continue
        resolved.append(TRANSISTOR_BY_NAME[model])
    return resolved


def build_float_sweep(start, stop, step, *, ndigits=12):
    """
    Build an inclusive floating-point sweep.

    Example:
      build_float_sweep(0.5, 1.5, 0.05)
    """
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


def _rlc_parallel_indexes(selection):
    indexes = selection.get("passive_indexes") or {}
    return {
        "r": int(indexes.get("r", 0)),
        "l": int(indexes.get("l", 0)),
        "c": int(indexes.get("c", 0)),
    }


def _is_open_rlc_parallel(selection):
    if not isinstance(selection, dict):
        return False
    if selection.get("topology") != "rlc_parallel":
        return False
    indexes = _rlc_parallel_indexes(selection)
    return indexes["r"] == 0 and indexes["l"] == 0 and indexes["c"] == 0


def _open_rlc_parallel_selection():
    return {
        "identifier": OPEN_RLC_PARALLEL_IDENTIFIER,
        "topology": "rlc_parallel",
        "netlist": "open",
        "estimated_area_um2": 0.0,
        "elements": [],
        "passive_indexes": {
            "r": 0,
            "l": 0,
            "c": 0,
        },
    }


def resolve_network_selections(
    network_refs,
    network_index,
    *,
    allow_none=False,
    allow_default=False,
):
    """
    Resolve passive-network references into metadata dictionaries or special values.

    Supported values:
    - network metadata dictionaries
    - identifier strings
    - None / "none" when `allow_none=True`
    - "default" when `allow_default=True`
    - "open" / "rlc_parallel__r00__l00__c00" for an open RLC network
    """
    resolved = []
    for ref in network_refs:
        if ref is None:
            if not allow_none:
                raise ValueError("This network slot does not allow None")
            resolved.append(None)
            continue

        if isinstance(ref, dict):
            resolved.append(ref)
            continue

        if not isinstance(ref, str):
            raise TypeError("Network references must be identifiers, dicts, or None")

        normalized = ref.strip().lower()
        if normalized == "none":
            if not allow_none:
                raise ValueError("This network slot does not allow None")
            resolved.append(None)
            continue
        if normalized == "default":
            if not allow_default:
                raise ValueError("This network slot does not allow 'default'")
            resolved.append("default")
            continue
        if normalized in {"open", OPEN_RLC_PARALLEL_IDENTIFIER}:
            resolved.append(_open_rlc_parallel_selection())
            continue

        resolved.append(network_index[ref])
    return resolved


def _zero_estimates():
    return {
        "estimated_area_um2": 0.0,
        "estimated_resistance_ohm": 0.0,
        "estimated_capacitance_f": 0.0,
        "estimated_inductance_h": 0.0,
        "tunable_capacitance_min_f": 0.0,
        "tunable_capacitance_max_f": 0.0,
    }


def _estimate_from_elements(elements):
    estimates = _zero_estimates()
    for element in elements:
        estimates["estimated_area_um2"] += element.get("area_um2") or 0.0
        estimates["estimated_resistance_ohm"] += (
            element.get("nominal_resistance_ohm") or 0.0
        )
        estimates["estimated_capacitance_f"] += (
            element.get("nominal_capacitance_f") or 0.0
        )
        estimates["estimated_inductance_h"] += (
            element.get("nominal_inductance_h") or 0.0
        )
        estimates["tunable_capacitance_min_f"] += (
            element.get("tunable_capacitance_min_f") or 0.0
        )
        estimates["tunable_capacitance_max_f"] += (
            element.get("tunable_capacitance_max_f") or 0.0
        )
    return estimates


def _merge_estimates(base, extra):
    merged = dict(base)
    for key, value in extra.items():
        merged[key] = merged.get(key, 0.0) + value
    return merged


def _selection_to_netlist_spec(selection):
    if selection is None:
        return None
    if selection == "default":
        return "default"
    if _is_open_rlc_parallel(selection):
        return "open"
    if isinstance(selection, dict):
        return selection["netlist"]
    return selection


def _describe_network_selection(role, selection, *, lg, ls, ld):
    if selection is None:
        if role == "source":
            summary = {
                "mode": "short",
                "identifier": None,
                "topology": "short",
                "netlist": None,
                "elements": [],
            }
            summary.update(
                {
                    "estimated_area_um2": 0.0,
                    "estimated_resistance_ohm": 1e-9,
                    "estimated_capacitance_f": 0.0,
                    "estimated_inductance_h": 0.0,
                    "tunable_capacitance_min_f": 0.0,
                    "tunable_capacitance_max_f": 0.0,
                }
            )
            return summary

        summary = {
            "mode": "open",
            "identifier": None,
            "topology": "open",
            "netlist": None,
            "elements": [],
        }
        summary.update(_zero_estimates())
        return summary

    if selection == "default":
        default_inductance_h = {
            "gate": lg,
            "source": ls,
            "load": ld,
        }[role]
        summary = {
            "mode": "default",
            "identifier": "default",
            "topology": "single",
            "netlist": "default",
            "elements": [],
        }
        summary.update(_zero_estimates())
        summary["estimated_inductance_h"] = default_inductance_h
        return summary

    if isinstance(selection, dict):
        if _is_open_rlc_parallel(selection):
            summary = {
                "mode": "open",
                "identifier": selection.get("identifier", OPEN_RLC_PARALLEL_IDENTIFIER),
                "topology": "rlc_parallel",
                "netlist": "open",
                "elements": [],
                "passive_indexes": {
                    "r": 0,
                    "l": 0,
                    "c": 0,
                },
            }
            summary.update(_zero_estimates())
            return summary
        summary = {
            "mode": "database",
            "identifier": selection["identifier"],
            "topology": selection["topology"],
            "netlist": selection["netlist"],
            "elements": selection["elements"],
        }
        if "passive_indexes" in selection:
            summary["passive_indexes"] = selection["passive_indexes"]
        summary.update(_estimate_from_elements(selection["elements"]))
        if selection.get("estimated_area_um2") is not None:
            summary["estimated_area_um2"] = selection["estimated_area_um2"]
        return summary

    raise TypeError(f"Unsupported network selection for {role}: {selection!r}")


def _build_circuit_metadata(
    circuit_index,
    transistor_model,
    gate_selection,
    source_selection,
    load_selection,
    feedback_selection,
    *,
    lg,
    ls,
    ld,
    netlist_filename,
    circuit_title,
    generation_parameters,
):
    gate_summary = _describe_network_selection("gate", gate_selection, lg=lg, ls=ls, ld=ld)
    source_summary = _describe_network_selection(
        "source", source_selection, lg=lg, ls=ls, ld=ld
    )
    load_summary = _describe_network_selection("load", load_selection, lg=lg, ls=ls, ld=ld)
    feedback_summary = _describe_network_selection(
        "feedback", feedback_selection, lg=lg, ls=ls, ld=ld
    )

    total_estimates = _zero_estimates()
    for summary in (gate_summary, source_summary, load_summary, feedback_summary):
        total_estimates = _merge_estimates(
            total_estimates,
            {
                key: summary[key]
                for key in total_estimates
            },
        )

    fixed_totals = _zero_estimates()
    for fixed_cap in (FIXED_INPUT_COUPLING_CAP, FIXED_OUTPUT_COUPLING_CAP):
        fixed_totals["estimated_area_um2"] += fixed_cap["area_um2"]
        fixed_totals["estimated_capacitance_f"] += fixed_cap["nominal_capacitance_f"]
    circuit_totals = _merge_estimates(total_estimates, fixed_totals)

    return {
        "circuit_index": circuit_index,
        "circuit_title": circuit_title,
        "transistor": {
            "name": transistor_model.name,
            "device_type": transistor_model.device_type,
            "threshold": transistor_model.threshold,
            "fingers": transistor_model.fingers,
            "width_um": transistor_model.width_um,
            "length_um": transistor_model.length_um,
        },
        "networks": {
            "gate": gate_summary,
            "source": source_summary,
            "load": load_summary,
            "feedback": feedback_summary,
        },
        "estimated_passive_totals": total_estimates,
        "estimated_fixed_totals": fixed_totals,
        "estimated_circuit_totals": circuit_totals,
        "fixed_passives": {
            "input_coupling_cap": FIXED_INPUT_COUPLING_CAP,
            "output_coupling_cap": FIXED_OUTPUT_COUPLING_CAP,
        },
        "generation_parameters": generation_parameters,
        "files": {
            "netlist": netlist_filename,
            "metadata": "metadata.json",
        },
    }


def create_circuit_bundle(
    output_root,
    circuit_index,
    transistor_model,
    gate_network,
    source_network,
    load_network,
    feedback_network,
    *,
    vg=0.7,
    lg=DEFAULT_LG,
    ls=DEFAULT_LS,
    ld=DEFAULT_LD,
    corner="tt",
    circuit_title="RF LNA - Common Source with Inductive Degeneration",
    pdk_root="$PDK_ROOT",
    process_lib_path="sky130A/libs.tech/ngspice/sky130.lib.spice",
    rf_include_path_template=None,
    temperature_c=27,
    f0=5e9,
    vdd=1.8,
    ac_start="100MEG",
    ac_stop="10G",
    print_useful_data=True,
    netlist_stem=None,
    optimization_index=None,
):
    """
    Create one circuit folder containing the generated netlist and metadata.
    """
    output_root = Path(output_root)
    circuit_dir = output_root / "circuits" / f"circuit_{circuit_index:08d}"
    circuit_dir.mkdir(parents=True, exist_ok=True)

    if netlist_stem is None:
        netlist_stem = build_circuit_netlist_stem(
            transistor_model,
            gate_network,
            source_network,
            load_network,
            feedback_network,
            circuit_index=circuit_index,
            vg=vg,
        )

    netlist_path = circuit_dir / f"{netlist_stem}.cir"
    write_netlist(
        netlist_path=netlist_path,
        vg=vg,
        lg=lg,
        ls=ls,
        ld=ld,
        corner=corner,
        transistor_model_name=transistor_model.name,
        circuit_title=circuit_title,
        pdk_root=pdk_root,
        process_lib_path=process_lib_path,
        rf_include_path_template=(
            DEFAULT_RF_INCLUDE_PATH_TEMPLATE
            if rf_include_path_template is None
            else rf_include_path_template
        ),
        temperature_c=temperature_c,
        f0=f0,
        vdd=vdd,
        ac_start=ac_start,
        ac_stop=ac_stop,
        print_useful_data=print_useful_data,
        gate_network=_selection_to_netlist_spec(gate_network),
        source_network=_selection_to_netlist_spec(source_network),
        load_network=_selection_to_netlist_spec(load_network),
        feedback_network=_selection_to_netlist_spec(feedback_network),
    )

    metadata = _build_circuit_metadata(
        circuit_index,
        transistor_model,
        gate_network,
        source_network,
        load_network,
        feedback_network,
        lg=lg,
        ls=ls,
        ld=ld,
        netlist_filename=netlist_path.name,
        circuit_title=circuit_title,
        generation_parameters={
            "vg": vg,
            "lg": lg,
            "ls": ls,
            "ld": ld,
            "corner": corner,
            "pdk_root": pdk_root,
            "process_lib_path": process_lib_path,
            "temperature_c": temperature_c,
            "f0": f0,
            "vdd": vdd,
            "ac_start": ac_start,
            "ac_stop": ac_stop,
            "print_useful_data": print_useful_data,
        },
    )
    if optimization_index is not None:
        metadata["optimization"] = build_circuit_optimization_mapping(
            metadata,
            optimization_index,
        )
    metadata_path = circuit_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return circuit_dir


def generate_circuit_library(
    output_root,
    *,
    transistor_models,
    gate_networks,
    source_networks,
    load_networks,
    feedback_networks,
    vg_values=None,
    vg_start=None,
    vg_stop=None,
    vg_step=None,
    network_database_path=DEFAULT_NETWORK_DATABASE_PATH,
    start_index=1,
    max_circuits=None,
    **netlist_kwargs,
):
    """
    Generate circuit folders for every passed combination.

    This function does not implicitly generate the full design space; it only
    expands the transistor and network selections passed in by the caller.
    """
    network_database = load_network_database(network_database_path)
    network_index = index_network_database(network_database)
    resolved_transistors = resolve_transistor_models(transistor_models)
    resolved_gate_networks = resolve_network_selections(
        gate_networks, network_index, allow_default=True
    )
    resolved_source_networks = resolve_network_selections(
        source_networks, network_index, allow_none=True, allow_default=True
    )
    resolved_load_networks = resolve_network_selections(
        load_networks, network_index, allow_default=True
    )
    resolved_feedback_networks = resolve_network_selections(
        feedback_networks, network_index, allow_none=True
    )

    if vg_values is not None and any(
        value is not None for value in (vg_start, vg_stop, vg_step)
    ):
        raise ValueError(
            "Pass either vg_values or vg_start/vg_stop/vg_step, not both"
        )

    if vg_values is not None:
        resolved_vg_values = list(vg_values)
    elif any(value is not None for value in (vg_start, vg_stop, vg_step)):
        if None in (vg_start, vg_stop, vg_step):
            raise ValueError(
                "vg_start, vg_stop, and vg_step must all be provided for a sweep"
            )
        resolved_vg_values = build_float_sweep(vg_start, vg_stop, vg_step)
    else:
        resolved_vg_values = [netlist_kwargs.get("vg", 0.7)]

    if not resolved_gate_networks:
        raise ValueError("No gate networks were provided")
    if not resolved_source_networks:
        raise ValueError("No source networks were provided")
    if not resolved_load_networks:
        raise ValueError("No load networks were provided")
    if not resolved_feedback_networks:
        raise ValueError("No feedback networks were provided")
    if not resolved_vg_values:
        raise ValueError("No vg_values were provided")

    lg = netlist_kwargs.get("lg", DEFAULT_LG)
    ls = netlist_kwargs.get("ls", DEFAULT_LS)
    ld = netlist_kwargs.get("ld", DEFAULT_LD)
    optimization_index = build_optimization_index(
        resolved_transistors,
        {
            "gate": [
                _describe_network_selection("gate", selection, lg=lg, ls=ls, ld=ld)
                for selection in resolved_gate_networks
            ],
            "source": [
                _describe_network_selection("source", selection, lg=lg, ls=ls, ld=ld)
                for selection in resolved_source_networks
            ],
            "load": [
                _describe_network_selection("load", selection, lg=lg, ls=ls, ld=ld)
                for selection in resolved_load_networks
            ],
            "feedback": [
                _describe_network_selection(
                    "feedback",
                    selection,
                    lg=lg,
                    ls=ls,
                    ld=ld,
                )
                for selection in resolved_feedback_networks
            ],
        },
        resolved_vg_values,
    )

    output_root = Path(output_root)
    circuits_root = output_root / "circuits"
    circuits_root.mkdir(parents=True, exist_ok=True)

    circuit_count = 0
    next_index = start_index
    for combination in product(
        resolved_transistors,
        resolved_gate_networks,
        resolved_source_networks,
        resolved_load_networks,
        resolved_feedback_networks,
        resolved_vg_values,
    ):
        if max_circuits is not None and circuit_count >= max_circuits:
            break

        (
            transistor_model,
            gate_network,
            source_network,
            load_network,
            feedback_network,
            vg,
        ) = combination

        circuit_netlist_kwargs = dict(netlist_kwargs)
        circuit_netlist_kwargs["vg"] = vg
        create_circuit_bundle(
            output_root=output_root,
            circuit_index=next_index,
            transistor_model=transistor_model,
            gate_network=gate_network,
            source_network=source_network,
            load_network=load_network,
            feedback_network=feedback_network,
            optimization_index=optimization_index,
            **circuit_netlist_kwargs,
        )
        next_index += 1
        circuit_count += 1

    manifest = {
        "output_root": str(output_root),
        "network_database_path": str(network_database_path),
        "circuit_count": circuit_count,
        "start_index": start_index,
        "last_index": next_index - 1 if circuit_count else None,
        "selection_sizes": {
            "transistor_models": len(resolved_transistors),
            "gate_networks": len(resolved_gate_networks),
            "source_networks": len(resolved_source_networks),
            "load_networks": len(resolved_load_networks),
            "feedback_networks": len(resolved_feedback_networks),
            "vg_values": len(resolved_vg_values),
        },
        "selected_vg_values": resolved_vg_values,
        "selected_transistor_models": [model.name for model in resolved_transistors],
        "selected_gate_networks": [
            "default" if selection == "default" else selection["identifier"]
            for selection in resolved_gate_networks
        ],
        "selected_source_networks": [
            None
            if selection is None
            else "default" if selection == "default" else selection["identifier"]
            for selection in resolved_source_networks
        ],
        "selected_load_networks": [
            "default" if selection == "default" else selection["identifier"]
            for selection in resolved_load_networks
        ],
        "selected_feedback_networks": [
            None if selection is None else selection["identifier"]
            for selection in resolved_feedback_networks
        ],
        "optimization_index": optimization_index,
        "netlist_parameters": netlist_kwargs,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    written_file = write_netlist(
        netlist_path="rf_lna.cir",
        vg=0.7,
        lg=5e-9,
        ls=1e-9,
        ld=5e-9,
        corner="tt",
        transistor_model_name="sky130_fd_pr__rf_nfet_01v8_bM02W1p65L0p15",
        circuit_title="RF LNA - Common Source with Inductive Degeneration",
        pdk_root="$PDK_ROOT",
        process_lib_path="sky130A/libs.tech/ngspice/sky130.lib.spice",
        rf_include_path_template=DEFAULT_RF_INCLUDE_PATH_TEMPLATE,
        temperature_c=27,
        f0=5e9,
        vdd=1.8,
        ac_start="100MEG",
        ac_stop="10G",
    )
    print(f"Wrote {written_file}")
