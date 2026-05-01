from dataclasses import dataclass


@dataclass(frozen=True)
class TransistorModel:
    """Metadata for a single transistor model."""

    name: str
    device_type: str
    threshold: str
    fingers: int
    width_um: float
    length_um: float

    @property
    def is_nmos(self) -> bool:
        return self.device_type == "nmos"

    @property
    def is_pmos(self) -> bool:
        return self.device_type == "pmos"

    @property
    def is_lvt(self) -> bool:
        return self.threshold == "lvt"


def _model(
    device_type: str,
    fingers: int,
    width_um: float,
    length_um: float,
    threshold: str = "standard",
) -> TransistorModel:
    fet_name = "nfet" if device_type == "nmos" else "pfet"
    threshold_part = "_lvt" if threshold == "lvt" else ""
    encoded_width = f"{width_um:.2f}".replace(".", "p")
    encoded_length = f"{length_um:.2f}".replace(".", "p")
    name = (
        f"sky130_fd_pr__rf_{fet_name}_01v8{threshold_part}"
        f"_bM{fingers:02d}W{encoded_width}L{encoded_length}"
    )
    return TransistorModel(
        name=name,
        device_type=device_type,
        threshold=threshold,
        fingers=fingers,
        width_um=width_um,
        length_um=length_um,
    )


_WIDTHS_UM = (1.65, 3.00, 5.00)
_LENGTHS_UM = (0.15, 0.18, 0.25)
_FINGERS = (2, 4)

NMOS = [
    _model("nmos", fingers, width_um, length_um)
    for fingers in _FINGERS
    for width_um in _WIDTHS_UM
    for length_um in _LENGTHS_UM
]

NMOS_LVT = [
    _model("nmos", fingers, width_um, length_um, threshold="lvt")
    for fingers in _FINGERS
    for width_um in _WIDTHS_UM
    for length_um in _LENGTHS_UM
]

PMOS = [
    _model("pmos", fingers, width_um, length_um)
    for fingers in _FINGERS
    for width_um in _WIDTHS_UM
    for length_um in _LENGTHS_UM
]

LVT = NMOS_LVT

TRANSISTORS = NMOS + NMOS_LVT + PMOS
TRANSISTOR_NAMES = tuple(transistor.name for transistor in TRANSISTORS)

GROUPS = {
    "nmos": NMOS,
    "pmos": PMOS,
    "lvt": LVT,
    "nmos_lvt": NMOS_LVT,
    "all": TRANSISTORS,
}

BY_NAME = {transistor.name: transistor for transistor in TRANSISTORS}

