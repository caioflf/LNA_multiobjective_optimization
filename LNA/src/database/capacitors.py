from __future__ import annotations

from dataclasses import dataclass


MIM_DENSITY_F_PER_UM2 = 2.00e-15
MIM_EDGE_F_PER_UM = 0.19e-15


def estimate_mim_capacitance_f(width_um: float, length_um: float, mf: int = 1) -> float:
    unit_cap = (
        MIM_DENSITY_F_PER_UM2 * width_um * length_um
        + MIM_EDGE_F_PER_UM * 2 * (width_um + length_um)
    )
    return unit_cap * mf


def estimate_varactor_lvt_cmin_f(width_um: float, length_um: float, vm: float = 1.0) -> float:
    wd = width_um
    ld = length_um
    ldd = 0.018
    cm0 = 5.571e-16
    cm1 = 4.775e-16
    cm2 = 2.019e-16
    cm3 = 6.529e-16
    cx3 = 8.854e-14 * 3.9 / 41.6503
    return (cm0 + cm1 * ld + cm2 * wd + cm3 * wd * (ld - ldd) + cx3 * wd * ldd) * vm


def estimate_varactor_lvt_cmax_f(width_um: float, length_um: float, vm: float = 1.0) -> float:
    wd = width_um
    ld = length_um
    cx0 = 6.261e-16
    cx1 = 5.75e-16
    cx2 = 1.712e-16
    cx3 = 8.854e-14 * 3.9 / 41.6503
    return (cx0 + cx1 * ld + cx2 * wd + cx3 * wd * ld) * vm


def estimate_varactor_hvt_cmin_f(width_um: float, length_um: float, vm: float = 1.0) -> float:
    wd = width_um
    ld = length_um
    ldd = 0.015
    cm0 = 5.828e-16
    cm1 = 4.596e-16
    cm2 = 1.614e-16
    cm3 = 1.541e-15
    cx3 = 8.854e-14 * 3.9 / 41.7642
    return (cm0 + cm1 * ld + cm2 * wd + cm3 * wd * (ld - ldd) + cx3 * wd * ldd) * vm


def estimate_varactor_hvt_cmax_f(width_um: float, length_um: float, vm: float = 1.0) -> float:
    wd = width_um
    ld = length_um
    cx0 = 6.778e-16
    cx1 = 6.461e-16
    cx2 = 1.517e-16
    cx3 = 8.854e-14 * 3.9 / 41.7642
    return (cx0 + cx1 * ld + cx2 * wd + cx3 * wd * ld) * vm


@dataclass(frozen=True)
class CapacitorModel:
    """Metadata for a single capacitor model."""

    name: str
    family: str
    pin_order: tuple[str, ...]
    search_type: str
    use_case: str
    nominal_capacitance_f: float | None
    width_um: float | None
    length_um: float | None

    @property
    def is_fixed_cell(self) -> bool:
        return self.search_type == "categorical"

    @property
    def is_scalable(self) -> bool:
        return self.search_type == "grid"

    @property
    def is_tunable(self) -> bool:
        return self.family == "varactor"

    @property
    def estimated_area_um2(self) -> float | None:
        if self.width_um is None or self.length_um is None:
            return None
        return self.width_um * self.length_um


def _model(
    name: str,
    family: str,
    pin_order: tuple[str, ...],
    search_type: str,
    use_case: str,
    nominal_capacitance_f: float | None = None,
    width_um: float | None = None,
    length_um: float | None = None,
) -> CapacitorModel:
    return CapacitorModel(
        name=name,
        family=family,
        pin_order=pin_order,
        search_type=search_type,
        use_case=use_case,
        nominal_capacitance_f=nominal_capacitance_f,
        width_um=width_um,
        length_um=length_um,
    )


VPP_CAPACITORS = [
    _model(
        "sky130_fd_pr__cap_vpp_11p5x11p7_l1m1m2m3m4_shieldm5",
        "vpp",
        ("c0", "c1", "b", "m5"),
        "categorical",
        "fixed_matching_or_load",
        137.45e-15,
        11.5,
        11.7,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_11p5x11p7_l1m1m2m3m4_shieldpom5",
        "vpp",
        ("c0", "c1", "b", "m5"),
        "categorical",
        "fixed_matching_or_load",
        141.23e-15,
        11.5,
        11.7,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_11p5x11p7_m1m2m3m4_shieldl1m5",
        "vpp",
        ("c0", "c1", "b", "m5"),
        "categorical",
        "fixed_matching_or_load",
        116.75e-15,
        11.5,
        11.7,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_08p6x07p8_m1m2m3_shieldl1m5_floatm4",
        "vpp",
        ("c0", "c1", "b", "m5"),
        "categorical",
        "fixed_matching_or_load",
        42.11e-15,
        8.6,
        7.8,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_11p5x11p7_m1m2m3_shieldl1m5_floatm4",
        "vpp",
        ("c0", "c1", "b", "m5"),
        "categorical",
        "fixed_matching_or_load",
        97.328e-15,
        11.5,
        11.7,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_11p5x11p7_l1m1m2m3_shieldm4",
        "vpp",
        ("c0", "c1", "b", "m4"),
        "categorical",
        "fixed_matching_or_load",
        118.52e-15,
        11.5,
        11.7,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_06p8x06p1_l1m1m2m3_shieldpom4",
        "vpp",
        ("c0", "c1", "b", "m4"),
        "categorical",
        "fixed_matching_or_load",
        33.819e-15,
        6.8,
        6.1,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_06p8x06p1_m1m2m3_shieldl1m4",
        "vpp",
        ("c0", "c1", "b", "m4"),
        "categorical",
        "fixed_matching_or_load",
        26.560e-15,
        6.8,
        6.1,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_08p6x07p8_m1m2_noshield",
        "vpp",
        ("c0", "c1", "b"),
        "categorical",
        "fixed_matching_or_load",
        35.0e-15,
        8.6,
        7.8,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_02p4x04p6_m1m2_noshield",
        "vpp",
        ("c0", "c1", "b"),
        "categorical",
        "fixed_matching_or_load",
        4.37e-15,
        2.4,
        4.6,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_04p4x04p6_m1m2_noshield",
        "vpp",
        ("c0", "c1", "b"),
        "categorical",
        "fixed_matching_or_load",
        7.81e-15,
        4.4,
        4.6,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_11p5x11p7_m1m2_noshield",
        "vpp",
        ("c0", "c1", "b"),
        "categorical",
        "fixed_matching_or_load",
        74.6e-15,
        11.5,
        11.7,
    ),
    _model(
        "sky130_fd_pr__cap_vpp_01p8x01p8_m1m2_noshield",
        "vpp",
        ("c0", "c1", "b"),
        "categorical",
        "fixed_matching_or_load",
        0.7833e-15,
        1.8,
        1.8,
    ),
]

MIM_CAPACITORS = [
    _model(
        "sky130_fd_pr__cap_mim_m3_1",
        "mim",
        ("c0", "c1"),
        "grid",
        "coupling_bypass_matching",
        None,
    ),
    _model(
        "sky130_fd_pr__cap_mim_m3_2",
        "mim",
        ("c0", "c1"),
        "grid",
        "coupling_bypass_matching",
        None,
    ),
]

VARACTORS = [
    _model(
        "sky130_fd_pr__cap_var_lvt",
        "varactor",
        ("c0", "c1", "b"),
        "categorical",
        "tunable_matching_or_tank",
        None,
        5.0,
        0.5,
    ),
    _model(
        "sky130_fd_pr__cap_var_hvt",
        "varactor",
        ("c0", "c1", "b"),
        "categorical",
        "tunable_matching_or_tank",
        None,
        5.0,
        0.5,
    ),
]

CAPACITORS = VPP_CAPACITORS + MIM_CAPACITORS + VARACTORS
CAPACITOR_NAMES = tuple(capacitor.name for capacitor in CAPACITORS)

MIM_WIDTHS_UM = (2, 4, 6, 8, 10, 12)
MIM_LENGTHS_UM = (2, 4, 6, 8, 10, 12)
MIM_MULTIPLIERS = (1, 2, 4, 8)

GROUPS = {
    "vpp": VPP_CAPACITORS,
    "mim": MIM_CAPACITORS,
    "varactor": VARACTORS,
    "fixed": VPP_CAPACITORS,
    "tunable": VARACTORS,
    "all": CAPACITORS,
}

BY_NAME = {capacitor.name: capacitor for capacitor in CAPACITORS}
