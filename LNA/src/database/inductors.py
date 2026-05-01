from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InductorModel:
    """Metadata for a single RF inductor model."""

    name: str
    family: str
    pin_order: tuple[str, ...]
    use_case: str
    nominal_inductance_h: float
    side_um: float
    nominal_series_resistance_ohm: float

    @property
    def is_center_tapped(self) -> bool:
        return "ct" in self.pin_order

    @property
    def estimated_area_um2(self) -> float:
        return self.side_um * self.side_um


def _model(
    name: str,
    nominal_inductance_h: float,
    side_um: float,
    nominal_series_resistance_ohm: float,
    use_case: str = "rf_matching",
) -> InductorModel:
    return InductorModel(
        name=name,
        family="spiral_inductor",
        pin_order=("a", "b", "ct", "sub"),
        use_case=use_case,
        nominal_inductance_h=nominal_inductance_h,
        side_um=side_um,
        nominal_series_resistance_ohm=nominal_series_resistance_ohm,
    )


RF_INDUCTORS = [
    _model("sky130_fd_pr__ind_03_90", 1.521e-9, 90.0, 2.038),
    _model("sky130_fd_pr__ind_05_125", 5.79e-9, 125.0, 3.529),
    _model("sky130_fd_pr__ind_05_220", 9.92e-9, 220.0, 4.118),
]

INDUCTORS = RF_INDUCTORS
INDUCTOR_NAMES = tuple(inductor.name for inductor in INDUCTORS)

GROUPS = {
    "rf": RF_INDUCTORS,
    "all": INDUCTORS,
}

BY_NAME = {inductor.name: inductor for inductor in INDUCTORS}
