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
    xmin: float = 0.0
    xmax: float = 0.0
    ymin: float = 0.0
    ymax: float = 0.0
    repaint: int = 0
    mu_to_part_coef: float = 0.0
    is_empty: bool = True  # marker if there are no MUs in this layer

    @property
    def n_spots(self) -> int:
        """Number of spots in this layer."""
        return len(self.spots)
