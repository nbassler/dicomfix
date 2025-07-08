from dataclasses import dataclass, field
from typing import List  # or Sequence, depending on usage
# from typing import Optional
# from typing import Optional


@dataclass
class Field:
    """A single field."""
    layers: List = field(default_factory=list)  # https://stackoverflow.com/questions/53632152/
    # n_layers is now a property that returns the number of layers

    dose: float = 0.0  # dose in [Gy]
    cum_mu: float = 0.0  # cumulative MU of all layers in this field
    # cum_particles: float = 0.0  # cumulative number of particles  NOT KNOWN BEFORE BEAM MODEL IS APPLIED
    pld_csetweight: float = 0.0  # IBA specific
    scaling: float = 1.0  # scaling applied to all particle numbers

    meterset_weight_final: float = 0.0
    meterset_per_weight: float = 0.0

    # moved to layer, since these are not field specific in dicom format.
    # snout_position: float = 0.0  # position of snout in mm
    # range_shifter_thickness: Optional[float] = None

    # isocenter_x: float = 0.0
    # isocenter_y: float = 0.0
    # isocenter_z: float = 0.0

    # gantry_angle: float = 0.0
    # couch_angle: float = 0.0

    lateral_spreading_device_distanceX: float = 0.0
    lateral_spreading_device_distanceY: float = 0.0

    sop_instance_uid: str = ""  # SOPInstanceUID for this field

    @property
    def n_layers(self) -> int:
        """Number of layers in this field."""
        return len(self.layers)

    @property
    def n_spots(self) -> int:
        """Total number of spots in this field."""
        return sum(layer.n_spots for layer in self.layers)

    @property
    def xmin(self) -> float:
        """Minimum X coordinate of spots in this field."""
        return min(layer.xmin for layer in self.layers) if self.layers else 0.0

    @property
    def xmax(self) -> float:
        """Maximum X coordinate of spots in this field."""
        return max(layer.xmax for layer in self.layers) if self.layers else 0.0

    @property
    def ymin(self) -> float:
        """Minimum Y coordinate of spots in this field."""
        return min(layer.ymin for layer in self.layers) if self.layers else 0.0

    @property
    def ymax(self) -> float:
        """Maximum Y coordinate of spots in this field."""
        return max(layer.ymax for layer in self.layers) if self.layers else 0.0

    def diagnose(self):
        """Print overview of field."""
        energy_list = [layer.energy_nominal for layer in self.layers]
        if energy_list:
            emin = min(energy_list)
            emax = max(energy_list)
        else:
            emin = 0.0
            emax = 0.0

        indent = "   "  # indent layer output, since this is a branch

        print(indent + "------------------------------------------------")
        print(indent + f"Energy layers          : {self.n_layers:10d}")
        print(indent + f"Total MUs              : {self.cum_mu:10.4f}")
        print(indent + "------------------------------------------------")
        for i, layer in enumerate(self.layers):
            print(indent + f"   Layer {i+1:3}: {layer.energy_nominal: 10.4f} MeV " + f"   {layer.n_spots:10d} spots")
        print(indent + f"Lowest energy          : {emin:10.4f} MeV")
        print(indent + f"Highest energy         : {emax:10.4f} MeV")
        print(indent + "------------------------------------------------")
        print(indent + f"Spot field min/max X   : {self.xmin:+10.4f} {self.xmax:+10.4f} mm")
        print(indent + f"Spot field min/max Y   : {self.ymin:+10.4f} {self.ymax:+10.4f} mm")
        print(indent + "------------------------------------------------")
        print("")
        print(indent + "------------------------------------------------")
        print(indent + f"Spot field min/max X   : {self.xmin:+10.4f} {self.xmax:+10.4f} mm")
        print(indent + f"Spot field min/max Y   : {self.ymin:+10.4f} {self.ymax:+10.4f} mm")
        print(indent + "------------------------------------------------")
        print("")
