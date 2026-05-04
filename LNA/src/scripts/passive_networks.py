from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from itertools import combinations_with_replacement, product
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.database.capacitors import (
    MIM_CAPACITORS,
    VARACTORS,
    estimate_mim_capacitance_f,
    estimate_varactor_hvt_cmax_f,
    estimate_varactor_hvt_cmin_f,
    estimate_varactor_lvt_cmax_f,
    estimate_varactor_lvt_cmin_f,
)
from src.database.inductors import INDUCTORS
from src.database.resistors import GROUPS as RESISTOR_GROUPS

ALL_SIZED_POLY_RESISTORS = [
    model
    for model in RESISTOR_GROUPS["poly"]
    if model.nominal_resistance_ohm is not None
]
DEFAULT_POLY_RESISTORS = ALL_SIZED_POLY_RESISTORS[::2]
DEFAULT_REDUCED_POLY_RESISTORS = [
    model
    for index, model in enumerate(
        sorted(
            DEFAULT_POLY_RESISTORS,
            key=lambda model: model.nominal_resistance_ohm,
        ),
        start=1,
    )
    if index not in {2, 4}
]
DEFAULT_MIM_MODEL_NAMES = ("sky130_fd_pr__cap_mim_m3_2",)
DEFAULT_MIM_SIZE_TOKENS = ("2x2", "4x4", "6x6", "8x8", "10x10")
DEFAULT_MF_VALUES = (1,)


@dataclass(frozen=True)
class PassiveElementChoice:
    """Single layout-aware passive choice for building 2-terminal networks."""

    identifier: str
    model_name: str
    element_type: str
    family: str
    area_um2: float | None
    netlist_template: str
    nominal_resistance_ohm: float | None = None
    nominal_capacitance_f: float | None = None
    nominal_inductance_h: float | None = None
    tunable_capacitance_min_f: float | None = None
    tunable_capacitance_max_f: float | None = None

    def to_metadata(self) -> dict:
        return asdict(self)

    def instantiate(self, node_p: str, node_n: str, instance_suffix: str) -> str:
        return self.netlist_template.format(
            name="{name}_" + instance_suffix,
            p=node_p,
            n=node_n,
        )


@dataclass(frozen=True)
class PassiveNetworkChoice:
    """Network template ready to pass into `netlist_generator.write_netlist`."""

    identifier: str
    topology: str
    netlist: str
    estimated_area_um2: float | None
    elements: list[dict]
    passive_indexes: dict[str, int] | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        if payload["passive_indexes"] is None:
            del payload["passive_indexes"]
        return payload


def _build_inductor_choices() -> list[PassiveElementChoice]:
    choices = []
    for model in INDUCTORS:
        choices.append(
            PassiveElementChoice(
                identifier=model.name,
                model_name=model.name,
                element_type="inductor",
                family=model.family,
                area_um2=model.estimated_area_um2,
                netlist_template="X{name} {p} {n} {name}_ct 0 " + model.name,
                nominal_inductance_h=model.nominal_inductance_h,
            )
        )
    return choices


def _parse_size_token(size_token: str) -> tuple[int, int]:
    normalized = size_token.lower().strip()
    if "x" not in normalized:
        raise ValueError(f"Invalid MIM size '{size_token}'. Expected form WIDTHxLENGTH.")
    width_text, length_text = normalized.split("x", 1)
    return int(width_text), int(length_text)


def _resolve_poly_resistors(selection: str) -> list:
    if selection == "all":
        return list(ALL_SIZED_POLY_RESISTORS)
    if selection == "alternating5":
        return list(DEFAULT_POLY_RESISTORS)
    if selection == "alternating3":
        return list(DEFAULT_REDUCED_POLY_RESISTORS)
    raise ValueError(f"Unsupported poly resistor selection: {selection}")


def _build_mim_choices(
    mim_model_names,
    mim_size_tokens,
    mf_values,
) -> list[PassiveElementChoice]:
    models_by_name = {model.name: model for model in MIM_CAPACITORS}
    size_pairs = [_parse_size_token(size_token) for size_token in mim_size_tokens]
    choices = []
    for model_name in mim_model_names:
        model = models_by_name[model_name]
        for width_um, length_um in size_pairs:
            for mf in mf_values:
                identifier = f"{model.name}__w{width_um}_l{length_um}_mf{mf}"
                choices.append(
                    PassiveElementChoice(
                        identifier=identifier,
                        model_name=model.name,
                        element_type="capacitor",
                        family=model.family,
                        area_um2=width_um * length_um * mf,
                        netlist_template=(
                            "X{name} {p} {n} "
                            f"{model.name} w={width_um} l={length_um} mf={mf}"
                        ),
                        nominal_capacitance_f=estimate_mim_capacitance_f(
                            width_um, length_um, mf
                        ),
                    )
                )
    return choices


def _build_varactor_choices() -> list[PassiveElementChoice]:
    choices = []
    for model in VARACTORS:
        width_um = model.width_um or 5.0
        length_um = model.length_um or 0.5
        if model.name.endswith("_lvt"):
            cmin_f = estimate_varactor_lvt_cmin_f(width_um, length_um)
            cmax_f = estimate_varactor_lvt_cmax_f(width_um, length_um)
        else:
            cmin_f = estimate_varactor_hvt_cmin_f(width_um, length_um)
            cmax_f = estimate_varactor_hvt_cmax_f(width_um, length_um)

        choices.append(
            PassiveElementChoice(
                identifier=f"{model.name}__w{width_um}_l{length_um}_vm1",
                model_name=model.name,
                element_type="capacitor",
                family=model.family,
                area_um2=width_um * length_um,
                netlist_template=(
                    "X{name} {p} {n} 0 "
                    f"{model.name} w={width_um} l={length_um} vm=1"
                ),
                tunable_capacitance_min_f=cmin_f,
                tunable_capacitance_max_f=cmax_f,
            )
        )
    return choices


def _build_layout_resistor_choices(poly_resistors) -> list[PassiveElementChoice]:
    choices = []
    for model in poly_resistors:
        choices.append(
            PassiveElementChoice(
                identifier=model.name,
                model_name=model.name,
                element_type="resistor",
                family=model.family,
                area_um2=model.estimated_area_um2,
                netlist_template="X{name} {p} {n} 0 " + model.name,
                nominal_resistance_ohm=model.nominal_resistance_ohm,
            )
        )
    return choices


def build_passive_element_choices(
    include_varactors: bool = True,
    mim_model_names=DEFAULT_MIM_MODEL_NAMES,
    mim_size_tokens=DEFAULT_MIM_SIZE_TOKENS,
    mf_values=DEFAULT_MF_VALUES,
    poly_resistor_selection="alternating5",
) -> list[PassiveElementChoice]:
    choices = []
    choices.extend(_build_inductor_choices())
    choices.extend(_build_mim_choices(mim_model_names, mim_size_tokens, mf_values))
    if include_varactors:
        choices.extend(_build_varactor_choices())
    choices.extend(
        _build_layout_resistor_choices(
            _resolve_poly_resistors(poly_resistor_selection)
        )
    )
    return choices


def _sum_area(elements: list[PassiveElementChoice]) -> float | None:
    if any(element.area_um2 is None for element in elements):
        return None
    return sum(element.area_um2 for element in elements if element.area_um2 is not None)


def _network_id(topology: str, elements: list[PassiveElementChoice]) -> str:
    names = "__".join(element.identifier for element in elements)
    return f"{topology}__{names}"


def _single_network(element: PassiveElementChoice) -> PassiveNetworkChoice:
    return PassiveNetworkChoice(
        identifier=_network_id("single", [element]),
        topology="single",
        netlist=element.instantiate("{p}", "{n}", "1"),
        estimated_area_um2=_sum_area([element]),
        elements=[element.to_metadata()],
    )


def _series_network(
    first: PassiveElementChoice,
    second: PassiveElementChoice,
) -> PassiveNetworkChoice:
    mid = "{name}_mid"
    netlist = "\n".join(
        [
            first.instantiate("{p}", mid, "1"),
            second.instantiate(mid, "{n}", "2"),
        ]
    )
    elements = [first, second]
    return PassiveNetworkChoice(
        identifier=_network_id("series", elements),
        topology="series",
        netlist=netlist,
        estimated_area_um2=_sum_area(elements),
        elements=[element.to_metadata() for element in elements],
    )


def _parallel_network(
    first: PassiveElementChoice,
    second: PassiveElementChoice,
) -> PassiveNetworkChoice:
    netlist = "\n".join(
        [
            first.instantiate("{p}", "{n}", "1"),
            second.instantiate("{p}", "{n}", "2"),
        ]
    )
    elements = [first, second]
    return PassiveNetworkChoice(
        identifier=_network_id("parallel", elements),
        topology="parallel",
        netlist=netlist,
        estimated_area_um2=_sum_area(elements),
        elements=[element.to_metadata() for element in elements],
    )


def _indexed_element_metadata(
    element: PassiveElementChoice,
    axis: str,
    index: int,
) -> dict:
    metadata = element.to_metadata()
    metadata["passive_axis"] = axis
    metadata["passive_index"] = index
    return metadata


def _passive_index_entry(index: int, element: PassiveElementChoice | None) -> dict:
    if element is None:
        return {
            "index": index,
            "identifier": None,
            "element_type": None,
            "description": "not instantiated",
        }

    entry = element.to_metadata()
    entry["index"] = index
    return entry


def _rlc_parallel_network(
    r_index: int,
    resistor: PassiveElementChoice | None,
    l_index: int,
    inductor: PassiveElementChoice | None,
    c_index: int,
    capacitor: PassiveElementChoice | None,
) -> PassiveNetworkChoice:
    selected = [
        ("r", r_index, resistor),
        ("l", l_index, inductor),
        ("c", c_index, capacitor),
    ]
    instantiated = [
        (axis, index, element)
        for axis, index, element in selected
        if element is not None
    ]
    if not instantiated:
        return PassiveNetworkChoice(
            identifier="rlc_parallel__r00__l00__c00",
            topology="rlc_parallel",
            netlist="open",
            estimated_area_um2=0.0,
            elements=[],
            passive_indexes={
                "r": r_index,
                "l": l_index,
                "c": c_index,
            },
        )

    netlist = "\n".join(
        element.instantiate("{p}", "{n}", axis)
        for axis, _, element in instantiated
    )
    elements = [element for _, _, element in instantiated]
    return PassiveNetworkChoice(
        identifier=f"rlc_parallel__r{r_index:02d}__l{l_index:02d}__c{c_index:02d}",
        topology="rlc_parallel",
        netlist=netlist,
        estimated_area_um2=_sum_area(elements),
        elements=[
            _indexed_element_metadata(element, axis, index)
            for axis, index, element in instantiated
        ],
        passive_indexes={
            "r": r_index,
            "l": l_index,
            "c": c_index,
        },
    )


def _resistor_count(elements: list[PassiveElementChoice]) -> int:
    return sum(1 for element in elements if element.element_type == "resistor")


def generate_rlc_parallel_network_library(
    include_varactors: bool = True,
    mim_model_names=DEFAULT_MIM_MODEL_NAMES,
    mim_size_tokens=DEFAULT_MIM_SIZE_TOKENS,
    mf_values=DEFAULT_MF_VALUES,
    poly_resistor_selection="alternating5",
) -> tuple[list[PassiveNetworkChoice], dict]:
    """Generate all parallel R/L/C networks; index 0 means absent, all-zero is open."""
    elements = build_passive_element_choices(
        include_varactors=include_varactors,
        mim_model_names=mim_model_names,
        mim_size_tokens=mim_size_tokens,
        mf_values=mf_values,
        poly_resistor_selection=poly_resistor_selection,
    )
    resistor_choices = sorted(
        (element for element in elements if element.element_type == "resistor"),
        key=lambda element: (
            element.nominal_resistance_ohm is None,
            element.nominal_resistance_ohm or 0.0,
            element.identifier,
        ),
    )
    inductor_choices = sorted(
        (element for element in elements if element.element_type == "inductor"),
        key=lambda element: (
            element.nominal_inductance_h is None,
            element.nominal_inductance_h or 0.0,
            element.identifier,
        ),
    )
    capacitor_choices = sorted(
        (element for element in elements if element.element_type == "capacitor"),
        key=lambda element: (
            element.nominal_capacitance_f is None,
            element.nominal_capacitance_f or 0.0,
            element.identifier,
        ),
    )

    indexed_resistors = list(enumerate([None] + resistor_choices))
    indexed_inductors = list(enumerate([None] + inductor_choices))
    indexed_capacitors = list(enumerate([None] + capacitor_choices))

    networks = []
    for (
        (r_index, resistor),
        (l_index, inductor),
        (c_index, capacitor),
    ) in product(indexed_resistors, indexed_inductors, indexed_capacitors):
        networks.append(
            _rlc_parallel_network(
                r_index,
                resistor,
                l_index,
                inductor,
                c_index,
                capacitor,
            )
        )

    index_definitions = {
        "r": [
            _passive_index_entry(index, element)
            for index, element in indexed_resistors
        ],
        "l": [
            _passive_index_entry(index, element)
            for index, element in indexed_inductors
        ],
        "c": [
            _passive_index_entry(index, element)
            for index, element in indexed_capacitors
        ],
    }
    return networks, index_definitions


def generate_network_library(
    include_varactors: bool = True,
    max_resistors_per_network: int | None = None,
    mim_model_names=DEFAULT_MIM_MODEL_NAMES,
    mim_size_tokens=DEFAULT_MIM_SIZE_TOKENS,
    mf_values=DEFAULT_MF_VALUES,
    poly_resistor_selection="alternating5",
) -> list[PassiveNetworkChoice]:
    """Generate all single, 2-series, and 2-parallel passive networks."""
    elements = build_passive_element_choices(
        include_varactors=include_varactors,
        mim_model_names=mim_model_names,
        mim_size_tokens=mim_size_tokens,
        mf_values=mf_values,
        poly_resistor_selection=poly_resistor_selection,
    )
    networks = []
    for element in elements:
        if (
            max_resistors_per_network is not None
            and _resistor_count([element]) > max_resistors_per_network
        ):
            continue
        networks.append(_single_network(element))

    for first, second in combinations_with_replacement(elements, 2):
        combo = [first, second]
        if (
            max_resistors_per_network is not None
            and _resistor_count(combo) > max_resistors_per_network
        ):
            continue
        networks.append(_series_network(first, second))
        networks.append(_parallel_network(first, second))

    return networks


def _write_output(
    networks: list[PassiveNetworkChoice],
    output_path: str | None,
    *,
    network_topology: str,
    index_definitions: dict | None = None,
) -> None:
    network_payload = [network.to_dict() for network in networks]
    if index_definitions is None:
        payload = network_payload
    else:
        payload = {
            "schema_version": 2,
            "network_topology": network_topology,
            "index_semantics": {
                "r": "0 means no resistor branch; positive indexes select a resistor",
                "l": "0 means no inductor branch; positive indexes select an inductor",
                "c": "0 means no capacitor branch; positive indexes select a capacitor",
            },
            "index_definitions": index_definitions,
            "networks": network_payload,
        }
    if output_path is None:
        print(json.dumps(payload, indent=2))
        return

    destination = Path(output_path)
    destination.write_text(json.dumps(payload, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate insertion-ready passive network templates with at most "
            "two passive elements in series or parallel."
        )
    )
    parser.add_argument(
        "--output",
        help="Write the generated library to this JSON file instead of stdout.",
    )
    parser.add_argument(
        "--no-varactors",
        action="store_true",
        help="Exclude tunable varactor options from the generated library.",
    )
    parser.add_argument(
        "--mim-models",
        nargs="+",
        default=list(DEFAULT_MIM_MODEL_NAMES),
        help="MIM model names to include.",
    )
    parser.add_argument(
        "--mim-sizes",
        nargs="+",
        default=list(DEFAULT_MIM_SIZE_TOKENS),
        help="Discrete MIM capacitor sizes in WIDTHxLENGTH form, for example 4x4 8x8.",
    )
    parser.add_argument(
        "--mf-values",
        nargs="+",
        type=int,
        default=list(DEFAULT_MF_VALUES),
        help="Discrete MIM multiplier values to include.",
    )
    parser.add_argument(
        "--poly-resistor-selection",
        choices=("alternating3", "alternating5", "all"),
        default="alternating5",
        help="Which sized poly resistor subset to include.",
    )
    parser.add_argument(
        "--max-resistors-per-network",
        type=int,
        default=None,
        help="Maximum number of resistors allowed in each generated network.",
    )
    parser.add_argument(
        "--network-topology",
        choices=("rlc-parallel", "legacy"),
        default="rlc-parallel",
        help=(
            "Network family to generate. rlc-parallel emits one optional R, L, "
            "and C branch in parallel with index 0 meaning absent."
        ),
    )
    args = parser.parse_args()

    if args.network_topology == "rlc-parallel":
        networks, index_definitions = generate_rlc_parallel_network_library(
            include_varactors=not args.no_varactors,
            mim_model_names=args.mim_models,
            mim_size_tokens=args.mim_sizes,
            mf_values=args.mf_values,
            poly_resistor_selection=args.poly_resistor_selection,
        )
    else:
        networks = generate_network_library(
            include_varactors=not args.no_varactors,
            max_resistors_per_network=args.max_resistors_per_network,
            mim_model_names=args.mim_models,
            mim_size_tokens=args.mim_sizes,
            mf_values=args.mf_values,
            poly_resistor_selection=args.poly_resistor_selection,
        )
        index_definitions = None
    _write_output(
        networks,
        args.output,
        network_topology=args.network_topology,
        index_definitions=index_definitions,
    )


if __name__ == "__main__":
    main()
