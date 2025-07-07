from dataclasses import dataclass


@dataclass
class Spot:
    x: float
    y: float
    mu: float
    # wt: float = 0.0  # relative weight, for now not used.
    size_x: float = 0.0
    size_y: float = 0.0
