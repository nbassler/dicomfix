import numpy as np
from dataclasses import dataclass, field


@dataclass
class Layer:
    """
    Handle layers in a plan.

    spots : np.array([[x_i, y_i, mu_i, n], [...], ...) for i spots.
            x,y : are spot positions at isocenter in [mm].
            mu  : are monitor units (meterset) for the individual spots [MU] (not relative meterset weights).
    spotsize: np.array() FWHM width of spot in along x and y axis, respectively [mm]
    enorm : nominal energy in [MeV]
    emeas : measured energy in [MeV] at exit nozzle
    cum_mu : cumulative monitor units for this layers [MU]
    repaint : number of repainting, 0 for no repaints TODO: check what is convention here.
    n_spots : number of spots in total
    mu_to_part_coef : conversion coefficient from MU to number of particles (depends on energy)
    """

    spots: np.array = field(default_factory=np.array)
    spotsize: np.array = field(default_factory=np.array)
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
    n_spots: int = 1
    mu_to_part_coef: float = 1.0
    is_empty: bool = True  # marker if there are no MUs in this layer
