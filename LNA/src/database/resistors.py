from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResistorModel:
    """Metadata for a single resistor model."""

    name: str
    family: str
    pin_order: tuple[str, ...]
    use_case: str
    nominal_resistance_ohm: float | None
    width_um: float | None
    length_um: float | None

    @property
    def is_poly(self) -> bool:
        return self.family in {"high_po", "xhigh_po"}

    @property
    def estimated_area_um2(self) -> float | None:
        if self.width_um is None or self.length_um is None:
            return None
        return self.width_um * self.length_um


def estimate_high_po_resistance_ohm(width_um: float, length_um: float = 5.0) -> float:
    return 254.77 + length_um * 230.05


def estimate_xhigh_po_resistance_ohm(width_um: float, length_um: float = 5.0) -> float:
    end_resistance = -46.62 / (width_um * width_um) + 331.73 / width_um + 20.576
    body_resistance = length_um * 2000.0 / width_um
    return end_resistance + body_resistance


def estimate_iso_pw_resistance_ohm(length_um: float, width_um: float = 2.65) -> float:
    return 3816.0 * ((length_um + 0.52) / width_um)


def _model(
    name: str,
    family: str,
    use_case: str,
    pin_order: tuple[str, ...] = ("r0", "r1", "b"),
    nominal_resistance_ohm: float | None = None,
    width_um: float | None = None,
    length_um: float | None = None,
) -> ResistorModel:
    return ResistorModel(
        name=name,
        family=family,
        pin_order=pin_order,
        use_case=use_case,
        nominal_resistance_ohm=nominal_resistance_ohm,
        width_um=width_um,
        length_um=length_um,
    )


HIGH_POLY_RESISTORS = [
    _model("sky130_fd_pr__res_high_po", "high_po", "bias_feedback_damping"),
    _model("sky130_fd_pr__res_high_po_0p35", "high_po", "bias_feedback_damping", nominal_resistance_ohm=1405.02, width_um=0.35, length_um=5.0),
    _model("sky130_fd_pr__res_high_po_0p69", "high_po", "bias_feedback_damping", nominal_resistance_ohm=1405.02, width_um=0.69, length_um=5.0),
    _model("sky130_fd_pr__res_high_po_1p41", "high_po", "bias_feedback_damping", nominal_resistance_ohm=1405.02, width_um=1.41, length_um=5.0),
    _model("sky130_fd_pr__res_high_po_2p85", "high_po", "bias_feedback_damping", nominal_resistance_ohm=1405.02, width_um=2.85, length_um=5.0),
    _model("sky130_fd_pr__res_high_po_5p73", "high_po", "bias_feedback_damping", nominal_resistance_ohm=1405.02, width_um=5.73, length_um=5.0),
]

XHIGH_POLY_RESISTORS = [
    _model("sky130_fd_pr__res_xhigh_po", "xhigh_po", "bias_feedback_damping"),
    _model("sky130_fd_pr__res_xhigh_po_0p35", "xhigh_po", "bias_feedback_damping", nominal_resistance_ohm=29159.233142857145, width_um=0.35, length_um=5.0),
    _model("sky130_fd_pr__res_xhigh_po_0p69", "xhigh_po", "bias_feedback_damping", nominal_resistance_ohm=14896.177134215503, width_um=0.69, length_um=5.0),
    _model("sky130_fd_pr__res_xhigh_po_1p41", "xhigh_po", "bias_feedback_damping", nominal_resistance_ohm=7324.594560434586, width_um=1.41, length_um=5.0),
    _model("sky130_fd_pr__res_xhigh_po_2p85", "xhigh_po", "bias_feedback_damping", nominal_resistance_ohm=3640.0048088642657, width_um=2.85, length_um=5.0),
    _model("sky130_fd_pr__res_xhigh_po_5p73", "xhigh_po", "bias_feedback_damping", nominal_resistance_ohm=1822.2503236205148, width_um=5.73, length_um=5.0),
]

DIFFUSION_WELL_RESISTORS = [
    _model("sky130_fd_pr__res_iso_pw", "iso_pw", "isolation", ("r0", "r1", "b"), width_um=2.65),
    _model(
        "sky130_fd_pr__res_generic_nd",
        "generic_nd",
        "damping_or_special_layout",
        ("t1", "t2", "b"),
    ),
    _model(
        "sky130_fd_pr__res_generic_pd",
        "generic_pd",
        "damping_or_special_layout",
        ("t1", "t2", "b"),
    ),
]

RESISTORS = HIGH_POLY_RESISTORS + XHIGH_POLY_RESISTORS + DIFFUSION_WELL_RESISTORS
RESISTOR_NAMES = tuple(resistor.name for resistor in RESISTORS)

GROUPS = {
    "high_po": HIGH_POLY_RESISTORS,
    "xhigh_po": XHIGH_POLY_RESISTORS,
    "diffusion_well": DIFFUSION_WELL_RESISTORS,
    "poly": HIGH_POLY_RESISTORS + XHIGH_POLY_RESISTORS,
    "all": RESISTORS,
}

BY_NAME = {resistor.name: resistor for resistor in RESISTORS}
