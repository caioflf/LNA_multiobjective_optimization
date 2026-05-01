from __future__ import annotations

import json


SCHEMA_VERSION = 1
NETWORK_ROLES = ("gate", "source", "load", "feedback")
IMPEDANCE_AXES = {
    "resistance": ("estimated_resistance_ohm", "resistance_ohm"),
    "inductance": ("estimated_inductance_h", "inductance_h"),
    "capacitance": ("estimated_capacitance_f", "capacitance_f"),
}
COORDINATE_AXES = (
    "transistor_length_index",
    "transistor_width_index",
    "transistor_m_index",
    "transistor_threshold_index",
    "transistor_model_index",
    "vg_index",
    "gate_r_index",
    "gate_l_index",
    "gate_c_index",
    "source_r_index",
    "source_l_index",
    "source_c_index",
    "load_r_index",
    "load_l_index",
    "load_c_index",
    "feedback_r_index",
    "feedback_l_index",
    "feedback_c_index",
)


def _as_float(value):
    if value is None:
        return 0.0
    return float(value)


def _field(item, name):
    if isinstance(item, dict):
        return item[name]
    return getattr(item, name)


def _unique_preserve_order(values):
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _unique_sorted(values):
    return sorted(_unique_preserve_order(values))


def _ordered_thresholds(values):
    threshold_order = {
        "standard": 0,
        "lvt": 1,
    }
    return sorted(
        _unique_preserve_order(values),
        key=lambda value: (threshold_order.get(value, 99), str(value)),
    )


def _indexed_values(values):
    return [
        {
            "index": index,
            "value": value,
        }
        for index, value in enumerate(values)
    ]


def _value_lookup(indexed_values):
    return {entry["value"]: entry["index"] for entry in indexed_values}


def _name_lookup(indexed_values):
    return {entry["name"]: entry["index"] for entry in indexed_values}


def _network_value(summary, impedance_axis):
    estimate_key, _ = IMPEDANCE_AXES[impedance_axis]
    if estimate_key in summary:
        return _as_float(summary.get(estimate_key))
    _, output_key = IMPEDANCE_AXES[impedance_axis]
    return _as_float(summary.get("estimated", {}).get(output_key))


def _network_passive_indexes(summary):
    indexes = summary.get("passive_indexes") or {}
    return {
        "r": int(indexes.get("r", 0)),
        "l": int(indexes.get("l", 0)),
        "c": int(indexes.get("c", 0)),
    }


def _network_lookup_key(summary):
    key_payload = {
        "mode": summary.get("mode"),
        "identifier": summary.get("identifier"),
        "topology": summary.get("topology"),
        "passive_indexes": _network_passive_indexes(summary),
        "resistance": _network_value(summary, "resistance"),
        "inductance": _network_value(summary, "inductance"),
        "capacitance": _network_value(summary, "capacitance"),
        "elements": [
            {
                "identifier": element.get("identifier"),
                "model_name": element.get("model_name"),
                "element_type": element.get("element_type"),
            }
            for element in summary.get("elements", [])
        ],
    }
    return json.dumps(key_payload, sort_keys=True)


def _network_entries(role, summaries, impedance_value_indexes):
    entries = []
    for index, summary in enumerate(_unique_network_summaries(summaries)):
        estimated = {
            output_key: _network_value(summary, axis)
            for axis, (_, output_key) in IMPEDANCE_AXES.items()
        }
        impedance_indexes = {
            f"{axis}_index": impedance_value_indexes[axis][estimated[output_key]]
            for axis, (_, output_key) in IMPEDANCE_AXES.items()
        }
        entries.append(
            {
                "index": index,
                "role": role,
                "identifier": summary.get("identifier"),
                "mode": summary.get("mode"),
                "topology": summary.get("topology"),
                "passive_indexes": _network_passive_indexes(summary),
                "estimated": estimated,
                "impedance_indexes": impedance_indexes,
                "elements": [
                    {
                        "identifier": element.get("identifier"),
                        "model_name": element.get("model_name"),
                        "element_type": element.get("element_type"),
                        "family": element.get("family"),
                    }
                    for element in summary.get("elements", [])
                ],
            }
        )
    return entries


def _unique_network_summaries(summaries):
    seen = set()
    unique = []
    for summary in summaries:
        key = _network_lookup_key(summary)
        if key in seen:
            continue
        seen.add(key)
        unique.append(summary)
    return unique


def _transistor_as_dict(transistor):
    return {
        "name": _field(transistor, "name"),
        "device_type": _field(transistor, "device_type"),
        "threshold": _field(transistor, "threshold"),
        "fingers": _field(transistor, "fingers"),
        "width_um": _field(transistor, "width_um"),
        "length_um": _field(transistor, "length_um"),
    }


def _transistor_entries(transistors, value_indexes):
    entries = []
    for index, transistor in enumerate(transistors):
        transistor_data = _transistor_as_dict(transistor)
        entries.append(
            {
                "index": index,
                **transistor_data,
                "m": transistor_data["fingers"],
                "is_lvt": transistor_data["threshold"] == "lvt",
                "parameter_indexes": {
                    "length_index": value_indexes["length_um"][
                        transistor_data["length_um"]
                    ],
                    "width_index": value_indexes["width_um"][
                        transistor_data["width_um"]
                    ],
                    "fingers_index": value_indexes["fingers"][
                        transistor_data["fingers"]
                    ],
                    "m_index": value_indexes["fingers"][
                        transistor_data["fingers"]
                    ],
                    "threshold_index": value_indexes["threshold"][
                        transistor_data["threshold"]
                    ],
                },
            }
        )
    return entries


def build_optimization_index(transistors, network_summaries_by_role, vg_values):
    """
    Build reusable dictionaries that map physical design choices to compact indexes.

    `transistors` may contain TransistorModel objects or dictionaries. Network
    summaries are the same dictionaries stored under metadata["networks"][role].
    """
    unique_transistors = _unique_transistors(transistors)
    transistor_value_lists = {
        "length_um": _unique_sorted(
            _field(transistor, "length_um") for transistor in unique_transistors
        ),
        "width_um": _unique_sorted(
            _field(transistor, "width_um") for transistor in unique_transistors
        ),
        "fingers": _unique_sorted(
            _field(transistor, "fingers") for transistor in unique_transistors
        ),
        "threshold": _ordered_thresholds(
            _field(transistor, "threshold") for transistor in unique_transistors
        ),
    }
    transistor_value_indexes = {
        key: {value: index for index, value in enumerate(values)}
        for key, values in transistor_value_lists.items()
    }

    impedance_value_lists = {}
    for axis in IMPEDANCE_AXES:
        values = []
        for role in NETWORK_ROLES:
            values.extend(
                _network_value(summary, axis)
                for summary in network_summaries_by_role.get(role, [])
            )
        impedance_value_lists[axis] = _unique_sorted(values)
    impedance_value_indexes = {
        axis: {value: index for index, value in enumerate(values)}
        for axis, values in impedance_value_lists.items()
    }

    vg_list = _unique_sorted(vg_values)
    networks = {
        role: _network_entries(
            role,
            network_summaries_by_role.get(role, []),
            impedance_value_indexes,
        )
        for role in NETWORK_ROLES
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "coordinate_axes": list(COORDINATE_AXES),
        "transistor": {
            "length_um": _indexed_values(transistor_value_lists["length_um"]),
            "width_um": _indexed_values(transistor_value_lists["width_um"]),
            "fingers": _indexed_values(transistor_value_lists["fingers"]),
            "m": _indexed_values(transistor_value_lists["fingers"]),
            "threshold": [
                {
                    "index": index,
                    "value": value,
                    "is_lvt": value == "lvt",
                }
                for index, value in enumerate(transistor_value_lists["threshold"])
            ],
            "models": _transistor_entries(
                unique_transistors,
                transistor_value_indexes,
            ),
        },
        "bias": {
            "vg": _indexed_values(vg_list),
        },
        "impedance": {
            f"{output_key}": _indexed_values(impedance_value_lists[axis])
            for axis, (_, output_key) in IMPEDANCE_AXES.items()
        },
        "networks": networks,
    }


def _unique_transistors(transistors):
    seen = set()
    unique = []
    for transistor in transistors:
        name = _field(transistor, "name")
        if name in seen:
            continue
        seen.add(name)
        unique.append(transistor)
    return unique


def build_optimization_index_from_metadata(metadata_items):
    transistors = []
    vg_values = []
    network_summaries_by_role = {role: [] for role in NETWORK_ROLES}

    for metadata in metadata_items:
        transistors.append(metadata["transistor"])
        generation_parameters = metadata.get("generation_parameters", {})
        if "vg" in generation_parameters:
            vg_values.append(generation_parameters["vg"])
        for role in NETWORK_ROLES:
            network_summaries_by_role[role].append(metadata["networks"][role])

    return build_optimization_index(
        transistors,
        network_summaries_by_role,
        vg_values,
    )


def build_circuit_optimization_mapping(metadata, optimization_index):
    transistor = metadata["transistor"]
    generation_parameters = metadata.get("generation_parameters", {})
    network_summaries = metadata["networks"]

    transistor_indexes = _transistor_index_maps(optimization_index)
    network_indexes = _network_index_maps(optimization_index)
    vg_lookup = _value_lookup(optimization_index["bias"]["vg"])

    transistor_mapping = {
        "length_index": transistor_indexes["length_um"][transistor["length_um"]],
        "width_index": transistor_indexes["width_um"][transistor["width_um"]],
        "fingers_index": transistor_indexes["fingers"][transistor["fingers"]],
        "m_index": transistor_indexes["fingers"][transistor["fingers"]],
        "threshold_index": transistor_indexes["threshold"][transistor["threshold"]],
        "model_index": transistor_indexes["models"][transistor["name"]],
        "is_lvt": transistor["threshold"] == "lvt",
    }

    vg = generation_parameters.get("vg")
    bias_mapping = {
        "vg": vg,
        "vg_index": vg_lookup.get(vg),
    }

    networks_mapping = {}
    for role in NETWORK_ROLES:
        summary = network_summaries[role]
        passive_indexes = _network_passive_indexes(summary)
        networks_mapping[role] = {
            "network_index": network_indexes[role][_network_lookup_key(summary)],
            "r_index": passive_indexes["r"],
            "l_index": passive_indexes["l"],
            "c_index": passive_indexes["c"],
        }

    coordinate_values = {
        "transistor_length_index": transistor_mapping["length_index"],
        "transistor_width_index": transistor_mapping["width_index"],
        "transistor_m_index": transistor_mapping["m_index"],
        "transistor_threshold_index": transistor_mapping["threshold_index"],
        "transistor_model_index": transistor_mapping["model_index"],
        "vg_index": bias_mapping["vg_index"],
    }
    for role in NETWORK_ROLES:
        role_mapping = networks_mapping[role]
        coordinate_values[f"{role}_r_index"] = role_mapping["r_index"]
        coordinate_values[f"{role}_l_index"] = role_mapping["l_index"]
        coordinate_values[f"{role}_c_index"] = role_mapping["c_index"]

    return {
        "schema_version": SCHEMA_VERSION,
        "coordinate_axes": list(COORDINATE_AXES),
        "coordinate": [coordinate_values[axis] for axis in COORDINATE_AXES],
        "transistor": transistor_mapping,
        "bias": bias_mapping,
        "networks": networks_mapping,
    }


def _transistor_index_maps(optimization_index):
    transistor_index = optimization_index["transistor"]
    return {
        "length_um": _value_lookup(transistor_index["length_um"]),
        "width_um": _value_lookup(transistor_index["width_um"]),
        "fingers": _value_lookup(transistor_index["fingers"]),
        "threshold": _value_lookup(transistor_index["threshold"]),
        "models": _name_lookup(transistor_index["models"]),
    }


def _network_index_maps(optimization_index):
    return {
        role: {
            _network_lookup_key(entry): entry["index"]
            for entry in optimization_index["networks"][role]
        }
        for role in NETWORK_ROLES
    }


def _impedance_index_maps(optimization_index):
    impedance_index = optimization_index["impedance"]
    return {
        "resistance_ohm": _value_lookup(impedance_index["resistance_ohm"]),
        "inductance_h": _value_lookup(impedance_index["inductance_h"]),
        "capacitance_f": _value_lookup(impedance_index["capacitance_f"]),
    }
