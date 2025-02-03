from dataclasses import dataclass, field


@dataclass
class Field:
    """A single field."""

    layers: list = field(default_factory=list)  # https://stackoverflow.com/questions/53632152/
    n_layers: int = 0  # number of layers in this field
    dose: float = 0.0  # dose in [Gy]
    cum_mu: float = 0.0  # cumulative MU of all layers in this field
    cum_particles: float = 0.0  # cumulative number of particles
    pld_csetweight: float = 0.0  # IBA specific
    # gantry: float = 0.0
    # couch: float = 0.0
    scaling: float = 1.0  # scaling applied to all particle numbers
    xmin: float = 0.0
    xmax: float = 0.0
    ymin: float = 0.0
    ymax: float = 0.0
    sop_instance_uid: str = ""  # SOPInstanceUID for this field

    def diagnose(self):
        """Print overview of field."""
        energy_list = [layer.energy_nominal for layer in self.layers]
        emin = min(energy_list)
        emax = max(energy_list)

        indent = "   "  # indent layer output, since this is a branch

        print(indent + "------------------------------------------------")
        print(indent + f"Energy layers          : {self.n_layers:10d}")
        print(indent + f"Total MUs              : {self.cum_mu:10.4f}")
        print(indent + f"Total particles        : {self.cum_particles:10.4e} (estimated)")
        print(indent + "------------------------------------------------")
        for i, layer in enumerate(self.layers):
            print(indent + f"   Layer {i+1: 3}: {layer.energy_nominal: 10.4f} MeV " + f"   {layer.n_spots:10d} spots")
        print(indent + "------------------------------------------------")
        print(indent + f"Lowest energy          : {emin:10.4f} MeV")
        print(indent + f"Highest energy         : {emax:10.4f} MeV")
        print(indent + "------------------------------------------------")
        print(indent + f"Spot field min/max X   : {self.xmin:+10.4f} {self.xmax:+10.4f} mm")
        print(indent + f"Spot field min/max Y   : {self.ymin:+10.4f} {self.ymax:+10.4f} mm")
        print(indent + "------------------------------------------------")
        print("")
