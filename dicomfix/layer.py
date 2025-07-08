from typing import List
# import numpy as np
from dataclasses import dataclass, field
from dicomfix.spot import Spot


@dataclass
class Layer:
    """
    Handle layers in a plan.

    Attributes:
        spots: List of Spot objects representing scanned spots in this layer.
        energy_nominal: Nominal beam energy [MeV].
        energy_measured: Measured energy at nozzle [MeV].
        espread: Energy spread [MeV].
        cum_mu: Cumulative monitor units in this layer [MU].
        cum_particles: Cumulative number of particles in this layer.
        repaint: Number of repaintings (0 = no repainting).
        n_spots: Number of spots in this layer.
        mu_to_part_coef: Conversion coefficient from MU to number of particles.
        xmin/xmax/ymin/ymax: Spatial extent of spots in this layer [mm].
        is_empty: Whether the layer has non-zero MU.
    """

    spots: List[Spot] = field(default_factory=list)
    energy_nominal: float = 100.0
    energy_measured: float = 100.0
    espread: float = 0.0
    cum_mu: float = 0.0
    cum_particles: float = 0.0  # cumulative number of particles
    repaint: int = 0
    mu_to_part_coef: float = 0.0
    is_empty: bool = True  # marker if there are no MUs in this layer

    # Most cases, if not all, these do not change across layers for a single field, however
    # let us support it for completeness.
    # This may be used for e.g. arc-therapy.
    isocenter: tuple[float, float, float] = (0.0, 0.0, 0.0)
    gantry_angle: float = 0.0
    couch_angle: float = 0.0
    snout_position: float = 0.0  # position of snout in mm
    sad: tuple[float, float] = (0.0, 0.0)  # bending magnet to isocenter distance in mm (x, y)
    table_position: tuple[float, float, float] = (0.0, 0.0, 0.0)  # table position in mm (vertical, longitudinal, lateral)
    meterset_rate: float = 0.0  # meterset rate in MU/min (mostly used for IBA plans)

    @property
    def n_spots(self) -> int:
        """Number of spots in this layer."""
        return len(self.spots)

    @property
    def xmin(self) -> float:
        """Minimum X coordinate of spots in this layer."""
        return min(spot.x for spot in self.spots) if self.spots else 0.0

    @property
    def xmax(self) -> float:
        """Maximum X coordinate of spots in this layer."""
        return max(spot.x for spot in self.spots) if self.spots else 0.0

    @property
    def ymin(self) -> float:
        """Minimum Y coordinate of spots in this layer."""
        return min(spot.y for spot in self.spots) if self.spots else 0.0

    @property
    def ymax(self) -> float:
        """Maximum Y coordinate of spots in this layer."""
        return max(spot.y for spot in self.spots) if self.spots else 0.0

    def diagnose(self):
        """Print overview of layer."""
        print("------------------------------------------------")
        print(f"Energy nominal        : {self.energy_nominal:10.4f} MeV")
        print(f"Energy measured       : {self.energy_measured:10.4f} MeV")
        print(f"Energy spread         : {self.espread:10.4f} MeV")
        print(f"Cumulative MU         : {self.cum_mu:10.4f}")
        print(f"Cumulative particles  : {self.cum_particles:10.4e} (estimated)")
        print(f"Number of spots       : {self.n_spots:10d}")
        print("------------------------------------------------")
        print(f"Spot layer min/max X  : {self.xmin:+10.4f} {self.xmax:+10.4f} mm")
        print(f"Spot layer min/max Y  : {self.ymin:+10.4f} {self.ymax:+10.4f} mm")
        print("------------------------------------------------")
