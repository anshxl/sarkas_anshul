"""Module defining the three basic classes."""
import numpy as np
import os.path
import sys
import scipy.constants as const


class Parameters:
    """
    Class containing all the constants and physical constants of the simulation.

    Parameters
    ----------
    dic : dict, optional
        Dictionary to be copied.

    Attributes
    ----------
    a_ws : float
        Wigner-Seitz radius. Calculated from the ``total_num_density`` .

    boundary_conditions : str
        Type of boundary conditions.

    box_volume : float
        Volume of simulation box.

    dimensions : int
        Number of non-zero dimensions. Default = 3.

    fourpie0: float
        Electrostatic constant :math:`4\pi \epsilon_0`.

    num_species : int
        Number of species.

    kB : float
        Boltzmann constant obtained from ``scipy.constants``.

    hbar : float
        Reduced Planck's constant.

    hbar2 : float
        Square of reduced Planck's constant.

    a0 : float
        Bohr Radius.

    c0 : float
        Speed of light.

    qe : float
        Elementary charge.

    me : float
        Electron mass.

    eps0 : float
        Vacuum electrical permittivity.

    eV2K : float
        Conversion factor from eV to Kelvin obtained from ``scipy.constants``.

    J2erg : float
        Conversion factor from Joules to erg. Needed for cgs units.

    QFactor : float
        Charge Factor defined as :math:`\mathcal Q = \sum_{i}^{N} q_{i}^2` .

    Lx : float
        Box length in the :math:`x` direction.

    Ly : float
        Box length in the :math:`y` direction.

    Lz : float
        Box length in the :math:`z` direction.

    e1 : float
        Unit vector in the :math:`x` direction.

    e2 : float
        Unit vector in the :math:`y` direction.

    e3 : float
        Unit vector in the :math:`z` direction.

    input_file : str
        YAML Input file with all the simulation's parameters.

    T_desired : float
        Target temperature for the equilibration phase.

    species_num : numpy.ndarray
        Number of particles of each species. Shape = (``num_species``)

    species_concentrations : numpy.ndarray
        Concentration of each species. Shape = (``num_species``)

    species_temperatures : numpy.ndarray
        Initial temperature of each species. Shape = (``num_species``)

    species_masses : numpy.ndarray
        Mass of each species. Shape = (``num_species``)

    species_charges : numpy.ndarray
        Charge of each species. Shape = (``num_species``)

    species_names : list
        Name of each species. Len = (``num_species``)

    species_plasma_frequencies : numpy.ndarray
        Plasma Frequency of each species. Shape = (``num_species``)

    species_num_dens : numpy.ndarray
        Number density of each species. Shape = (``num_species``)

    total_ion_temperature : float
        Total initial ion temperature calculated as `` = species_concentration @ species_temperatures``.

    total_net_charge : float
        Total charge in the system.

    total_num_density : float
        Total number density. Calculated from the sum of ``Species.num_density``.

    total_num_ptcls : int
        Total number of particles. Calculated from the sum of ``Species.num``.

    measure : bool
        Flag for production phase.

    verbose : bool
        Flag for screen output.

    simulations_dir : str
        Name of directory where to store simulations.

    job_dir : str
        Directory name of the current job/run

    production_dir : str
        Directory name where to store simulation's files of the production phase. Default = 'Production'.

    equilibration_dir : str
        Directory name where to store simulation's file of the equilibration phase. Default = 'Equilibration'.

    preprocessing_dir : str
        Directory name where to store preprocessing files. Default = "PreProcessing".

    postprocessing_dir : str
        Directory name where to store postprocessing files. Default = "PostProcessing".

    prod_dump_dir : str
        Directory name where to store production phase's simulation's checkpoints. Default = 'dumps'.

    eq_dump_dir : str
        Directory name where to store equilibration phase's simulation's checkpoints. Default = 'dumps'.

    job_id : str
        Appendix of all simulation's files.

    log_file : str
        Filename of the simulation's log.

    np_per_side : numpy.ndarray
        Number of particles per simulation's box side.
        The product of its components should be equal to ``total_num_ptcls``.

    pre_run : bool
        Flag for preprocessing phase.

    """

    def __init__(self, dic: dict = None) -> None:

        self.input_file = None
        #
        self.Lx = 0.0
        self.Ly = 0.0
        self.Lz = 0.0
        self.box_lengths = np.zeros(3)
        self.box_volume = 0.0
        self.dimensions = 3
        self.J2erg = 1.0e+7  # erg/J
        self.eps0 = const.epsilon_0
        self.fourpie0 = 4.0 * np.pi * self.eps0
        self.mp = const.physical_constants["proton mass"][0]
        self.me = const.physical_constants["electron mass"][0]
        self.qe = const.physical_constants["elementary charge"][0]
        self.hbar = const.hbar
        self.hbar2 = self.hbar ** 2
        self.c0 = const.physical_constants["speed of light in vacuum"][0]
        self.eV2K = const.physical_constants["electron volt-kelvin relationship"][0]
        self.eV2J = const.physical_constants["electron volt-joule relationship"][0]
        self.a0 = const.physical_constants["Bohr radius"][0]
        self.kB = const.Boltzmann
        self.a_ws = 0.0

        # Control and Timing
        self.boundary_conditions = 'periodic'
        self.job_id = None
        self.job_dir = None
        self.log_file = None
        self.measure = False
        self.magnetized = False
        self.plot_style = None
        self.pre_run = False
        self.simulations_dir = "Simulations"
        self.production_dir = 'Production'
        self.magnetization_dir = 'Magnetization'
        self.equilibration_dir = 'Equilibration'
        self.preprocessing_dir = "PreProcessing"
        self.postprocessing_dir = "PostProcessing"
        self.prod_dump_dir = 'dumps'
        self.eq_dump_dir = 'dumps'
        self.mag_dump_dir = 'dumps'
        self.verbose = True

        self.np_per_side = None
        self.num_species = 1
        self.species_names = []
        self.species_num = None
        self.species_num_dens = None
        self.species_concentrations = None
        self.species_temperatures = None
        self.species_temperatures_eV = None
        self.species_masses = None
        self.species_charges = None
        self.species_plasma_frequencies = None
        self.species_cyclotron_frequencies = None
        self.species_couplings = None

        self.coupling_constant = 0.0
        self.total_num_density = 0.0
        self.total_num_ptcls = 0
        self.total_plasma_frequency = 0.0
        self.total_debye_length = 0.0
        self.total_mass_density = 0.0
        self.total_ion_temperature = 0.0
        self.T_desired = 0.0
        self.total_net_charge = 0.0
        self.QFactor = 0.0

        if dic:
            self.from_dict(dic)

    def __repr__(self):
        sortedDict = dict(sorted(self.__dict__.items(), key=lambda x: x[0].lower()))
        disp = 'Parameters( \n'
        for key, value in sortedDict.items():
            disp += "\t{} : {}\n".format(key, value)
        disp += ')'
        return disp

    def from_dict(self, input_dict: dict):
        """
        Update attributes from input dictionary.

        Parameters
        ----------
        input_dict: dict
            Dictionary to be copied.

        """
        self.__dict__.update(input_dict)

    def setup(self, species):
        """
        Setup simulations' parameters.

        Parameters
        ----------
        species : list
            List of ``sarkas.base.Species`` objects.

        """
        self.check_units()
        self.calc_parameters(species)
        self.calc_coupling_constant(species)

    def check_units(self) -> None:
        """Adjust default physical constants for cgs unit system and check for LJ potential."""
        # Physical constants
        if self.units == "cgs":
            self.kB *= self.J2erg
            self.c0 *= 1e2  # cm/s
            self.mp *= 1e3
            # Coulomb to statCoulomb conversion factor. See https://en.wikipedia.org/wiki/Statcoulomb
            C2statC = 1.0e-01 * self.c0
            self.hbar = self.J2erg * self.hbar
            self.hbar2 = self.hbar ** 2
            self.qe *= C2statC
            self.me *= 1.0e3
            self.eps0 = 1.0
            self.fourpie0 = 1.0
            self.a0 *= 1e2

        if self.potential_type == 'LJ':
            self.fourpie0 = 1.0
            self.species_lj_sigmas = np.zeros(self.num_species)

    def calc_parameters(self, species):
        """
        Assign the parsed parameters.

        Parameters
        ----------
        species : list
            List of ``sarkas.base.Species`` objects.

        """
        self.num_species = len(species)

        self.species_num = np.zeros(self.num_species, dtype=int)
        self.species_num_dens = np.zeros(self.num_species)
        self.species_concentrations = np.zeros(self.num_species)
        self.species_temperatures = np.zeros(self.num_species)
        self.species_temperatures_eV = np.zeros(self.num_species)
        self.species_masses = np.zeros(self.num_species)
        self.species_charges = np.zeros(self.num_species)
        self.species_plasma_frequencies = np.zeros(self.num_species)
        self.species_cyclotron_frequencies = np.zeros(self.num_species)
        self.species_couplings = np.zeros(self.num_species)

        # Loop over species and assign missing attributes
        # Collect species properties in single arrays
        wp_tot_sq = 0.0
        lambda_D = 0.0

        self.total_num_ptcls = 0
        self.total_num_density = 0.0

        for i, sp in enumerate(species):
            self.total_num_ptcls += sp.num

            # Calculate the mass of the species from the atomic weight if given
            if sp.atomic_weight:
                # Choose between atomic mass constant or proton mass
                # u = const.physical_constants["atomic mass constant"][0]
                sp.mass = self.mp * sp.atomic_weight

            # Calculate the mass of the species from the mass density if given
            if sp.mass_density:
                Av = const.physical_constants["Avogadro constant"][0]
                sp.number_density = sp.mass_density * Av / sp.atomic_weight
                self.total_num_density += sp.number_density

            assert sp.number_density, "{} number density not defined".format(sp.name)

            # Update arrays of species information
            self.total_num_density += sp.number_density
            self.species_names.append(sp.name)
            self.species_num[i] = sp.num
            self.species_masses[i] = sp.mass
            # Calculate the temperature in K if eV has been provided
            if sp.temperature_eV:
                sp.temperature = self.eV2K * sp.temperature_eV
                self.species_temperatures_eV[i] = sp.temperature_eV
            self.species_temperatures[i] = sp.temperature

            if sp.charge:
                self.species_charges[i] = sp.charge
                sp.Z = sp.charge / self.qe
            elif sp.Z:
                self.species_charges[i] = sp.Z * self.qe
                sp.charge = sp.Z * self.qe
            elif sp.epsilon:
                # LJ
                sp.charge = np.sqrt(sp.epsilon)
                sp.Z = 1.0
                self.species_charges[i] = np.sqrt(sp.epsilon)
            else:
                sp.charge = 0.0
                sp.Z = 0.0
                self.species_charges[i] = 0.0

            # Calculate the (total) plasma frequency
            if not self.potential_type == "LJ":
                # Q^2 factor see eq.(2.10) in Ballenegger et al. J Chem Phys 128 034109 (2008)
                sp.QFactor = sp.num * sp.charge ** 2
                self.QFactor += sp.QFactor / self.fourpie0

                sp.calc_plasma_frequency(self.fourpie0)
                wp_tot_sq += sp.wp ** 2
                sp.calc_debye_length(self.kB, self.fourpie0)
                lambda_D += sp.debye_length ** 2
            else:
                sp.QFactor = 0.0
                self.QFactor += sp.QFactor / self.fourpie0
                constant = 4.0 * np.pi * sp.number_density * sp.sigma ** 2
                sp.calc_plasma_frequency(constant)
                wp_tot_sq += sp.wp ** 2
                sp.calc_debye_length(self.kB, constant)
                lambda_D += sp.debye_length ** 2
                self.species_lj_sigmas[i] = sp.sigma

            if self.magnetized:

                if self.units == "cgs":
                    sp.calc_cyclotron_frequency( np.linalg.norm(self.magnetic_field) / self.c0)
                else:
                    sp.calc_cyclotron_frequency( np.linalg.norm(self.magnetic_field))

                sp.beta_c = sp.omega_c / sp.wp
                self.species_cyclotron_frequencies[i] = sp.omega_c

            self.species_plasma_frequencies[i] = sp.wp
            self.species_num_dens[i] = sp.number_density

        for i, sp in enumerate(species):
            sp.concentration = sp.num / self.total_num_ptcls
            self.species_concentrations[i] = float(sp.num / self.total_num_ptcls)

        self.total_net_charge = np.transpose(self.species_charges) @ self.species_num
        self.total_ion_temperature = np.transpose(self.species_concentrations) @ self.species_temperatures
        self.total_plasma_frequency = np.sqrt(wp_tot_sq)
        self.total_debye_length = np.sqrt(lambda_D)

        self.total_mass_density = self.species_masses.transpose() @ self.species_num_dens

        self.average_charge = np.transpose(self.species_charges) @ self.species_concentrations
        self.average_mass = np.transpose(self.species_masses) @ self.species_concentrations
        self.hydrodynamic_frequency = np.sqrt( 4.0* np.pi * self.average_charge**2 * self.total_num_density /
                                               (self.fourpie0 * self.average_mass))

        # Simulation Box Parameters
        # Wigner-Seitz radius calculated from the total number density
        self.a_ws = (3.0 / (4.0 * np.pi * self.total_num_density)) ** (1. / 3.)

        if self.np_per_side:
            msg = "Number of particles per dimension does not match total number of particles."
            assert int(np.prod(self.np_per_side)) == self.total_num_ptcls, msg

            self.Lx = self.a_ws * self.np_per_side[0] * (4.0 * np.pi / 3.0) ** (1.0 / 3.0)
            self.Ly = self.a_ws * self.np_per_side[1] * (4.0 * np.pi / 3.0) ** (1.0 / 3.0)
            self.Lz = self.a_ws * self.np_per_side[2] * (4.0 * np.pi / 3.0) ** (1.0 / 3.0)
        else:
            self.Lx = self.a_ws * (4.0 * np.pi * self.total_num_ptcls / 3.0) ** (1.0 / 3.0)
            self.Ly = self.a_ws * (4.0 * np.pi * self.total_num_ptcls / 3.0) ** (1.0 / 3.0)
            self.Lz = self.a_ws * (4.0 * np.pi * self.total_num_ptcls / 3.0) ** (1.0 / 3.0)

        self.box_lengths = np.array([self.Lx, self.Ly, self.Lz])  # box length vector

        # Dev Note: The following are useful for future geometries
        self.e1 = np.array([self.Lx, 0.0, 0.0])
        self.e2 = np.array([0.0, self.Ly, 0.0])
        self.e3 = np.array([0.0, 0.0, self.Lz])

        self.box_volume = abs(np.dot(np.cross(self.e1, self.e2), self.e3))

        self.dimensions = np.count_nonzero(self.box_lengths)  # no. of dimensions
        # Transform the list of species names into a np.array
        self.species_names = np.array(self.species_names)
        # Redundancy!!!
        self.T_desired = self.total_ion_temperature

    def calc_coupling_constant(self, species):
        """
        Calculate the coupling constant of each species and the total coupling constant.

        Parameters
        ----------
        species : list
            List of ``sarkas.base.Species`` objects.

        """
        z_avg = np.transpose(self.species_charges) @ self.species_concentrations

        for i, sp in enumerate(species):
            const = self.fourpie0 * self.kB
            sp.calc_coupling(self.a_ws, z_avg, const)
            self.species_couplings[i] = sp.coupling
            self.coupling_constant += sp.concentration * sp.coupling


class Particles:
    """
    Class handling particles' properties.

    Attributes
    ----------
    kB : float
        Boltzmann constant.

    pos : numpy.ndarray
        Particles' positions.

    vel : numpy.ndarray
        Particles' velocities.

    acc : numpy.ndarray
        Particles' accelerations.

    box_lengths : numpy.ndarray
        Box sides' lengths.

    masses : numpy.ndarray
        Mass of each particle. Shape = (``total_num_ptcls``).

    charges : numpy.ndarray
        Charge of each particle. Shape = (``total_num_ptcls``).

    id : numpy.ndarray,
        Species identifier. Shape = (``total_num_ptcls``).

    names : numpy.ndarray
        Species' names. Shape = (``total_num_ptcls``).

    rdf_nbins : int
        Number of bins for radial pair distribution.

    no_grs : int
        Number of independent :math:`g_{ij}(r)`.

    rdf_hist : numpy.ndarray
        Histogram array for the radial pair distribution function.

    prod_dump_dir : str
        Directory name where to store production phase's simulation's checkpoints. Default = 'dumps'.

    eq_dump_dir : str
        Directory name where to store equilibration phase's simulation's checkpoints. Default = 'dumps'.

    total_num_ptcls : int
        Total number of simulation's particles.

    num_species : int
        Number of species.

    species_num : numpy.ndarray
        Number of particles of each species. Shape = ``num_species``.

    dimensions : int
        Number of non-zero dimensions. Default = 3.

    potential_energy : float
        Instantaneous value of the potential energy.

    rnd_gen : numpy.random.Generator
        Random number generator.

    """

    def __init__(self):
        self.potential_energy = 0.0

    def __repr__(self):
        sortedDict = dict(sorted(self.__dict__.items(), key=lambda x: x[0].lower()))
        disp = 'Particles( \n'
        for key, value in sortedDict.items():
            disp += "\t{} : {}\n".format(key, value)
        disp += ')'
        return disp

    def setup(self, params, species):
        """
        Initialize class' attributes

        Parameters
        ----------
        params: sarkas.base.Parameters
            Simulation's parameters.

        species : list
            List of ``sarkas.base.Species`` objects.

        """

        self.kB = params.kB
        self.prod_dump_dir = params.prod_dump_dir
        self.eq_dump_dir = params.eq_dump_dir
        self.box_lengths = np.copy(params.box_lengths)
        self.total_num_ptcls = params.total_num_ptcls
        self.num_species = params.num_species
        self.species_num = np.copy(params.species_num)
        self.dimensions = params.dimensions

        if hasattr(params, "rand_seed"):
            self.rnd_gen = np.random.Generator(np.random.PCG64(params.rand_seed))
        else:
            self.rnd_gen = np.random.Generator(np.random.PCG64(123456789))

        self.pos = np.zeros((self.total_num_ptcls, params.dimensions))
        self.vel = np.zeros((self.total_num_ptcls, params.dimensions))
        self.acc = np.zeros((self.total_num_ptcls, params.dimensions))

        self.pbc_cntr = np.zeros((self.total_num_ptcls, params.dimensions))

        self.names = np.empty(self.total_num_ptcls, dtype=params.species_names.dtype)
        self.id = np.zeros(self.total_num_ptcls, dtype=int)

        self.species_init_vel = np.zeros((params.num_species, 3))
        self.species_thermal_velocity = np.zeros((params.num_species, 3))

        self.masses = np.zeros(self.total_num_ptcls)  # mass of each particle
        self.charges = np.zeros(self.total_num_ptcls)  # charge of each particle
        self.cyclotron_frequencies = np.zeros(self.total_num_ptcls)
        # No. of independent rdf
        self.no_grs = int(self.num_species * (self.num_species + 1) / 2)
        if hasattr(params, 'rdf_nbins'):
            self.rdf_nbins = params.rdf_nbins
        else:
            # nbins = 5% of the number of particles.
            self.rdf_nbins = int(0.05 * params.total_num_ptcls)
            params.rdf_nbins = self.rdf_nbins

        self.rdf_hist = np.zeros((self.rdf_nbins, self.num_species, self.num_species))

        self.update_attributes(species)

        self.load(params)

    def load(self, params):
        """
        Initialize particles' positions and velocities.
        Positions are initialized based on the load method while velocities are chosen
        from a Maxwell-Boltzmann distribution.

        Parameters
        ----------
        params: sarkas.base.Parameters
            Simulation's parameters.

        """
        # Particles Position Initialization
        if params.load_method in ['equilibration_restart', 'eq_restart',
                                  'magnetization_restart', 'mag_restart',
                                  'production_restart', 'prod_restart']:
            # checks
            assert hasattr(params, 'restart_step'), "Restart step not defined. Please define restart_step."
            assert type(params.restart_step) is int, "Only integers are allowed."

            if params.load_method[:2] == 'eq':
                self.load_from_restart('equilibration', params.restart_step)
            elif params.load_method[:2] == 'pr':
                self.load_from_restart('production', params.restart_step)
            elif params.load_method[:2] == 'ma':
                self.load_from_restart('magnetization', params.restart_step)

        elif params.load_method == 'file':
            msg = 'Input file not defined. Please define particle_input_file.'
            assert params.ptcls_input_file, msg
            self.load_from_file(params.ptcls_input_file)

        # position distribution.
        elif params.load_method == 'lattice':
            self.lattice(params.load_perturb)

        elif params.load_method == 'random_reject':
            assert params.load_rejection_radius, "Rejection radius not defined. Please define load_rejection_radius."
            self.random_reject(params.load_rejection_radius)

        elif params.load_method == 'halton_reject':
            assert params.load_rejection_radius, "Rejection radius not defined. Please define load_rejection_radius."
            self.halton_reject(params.load_halton_bases, params.load_rejection_radius)

        elif params.load_method in ['uniform', 'random_no_reject']:
            self.pos = self.uniform_no_reject([0.0, 0.0, 0.0], params.box_lengths)

        else:
            raise AttributeError('Incorrect particle placement scheme specified.')

    def gaussian(self, mean, sigma, num_ptcls):
        """
        Initialize particles' velocities according to a normalized Maxwell-Boltzmann (Normal) distribution.
        It calls ``numpy.random.Generator.normal``

        Parameters
        ----------
        num_ptcls : int
            Number of particles to initialize.

        mean : float
            Center of the normal distribution.

        sigma : float
            Scale of the normal distribution.

        Returns
        -------
         : numpy.ndarray
            Particles property distributed according to a Normal probability density function.

        """
        return self.rnd_gen.normal(mean, sigma, (num_ptcls, 3))

    def update_attributes(self, species):
        """
        Assign particles attributes.

        Parameters
        ----------
        species : list
            List of ``sarkas.base.Species`` objects.

        """
        species_end = 0
        for ic, sp in enumerate(species):
            species_start = species_end
            species_end += sp.num

            self.names[species_start:species_end] = sp.name
            self.masses[species_start:species_end] = sp.mass

            if hasattr(sp, 'charge'):
                self.charges[species_start:species_end] = sp.charge
            else:
                self.charges[species_start:species_end] = 1.0

            if hasattr(sp, 'omega_c'):
                self.cyclotron_frequencies[species_start:species_end] = sp.omega_c

            self.id[species_start:species_end] = ic

            if hasattr(sp, "init_vel"):
                self.species_init_vel[ic, :] = sp.init_vel

            if sp.initial_velocity_distribution == "boltzmann":
                if isinstance(sp.temperature, (int, float)):
                    sp_temperature = np.ones(self.dimensions) * sp.temperature

                self.species_thermal_velocity[ic] = np.sqrt(self.kB * sp_temperature / sp.mass)
                self.vel[species_start:species_end, :] = self.gaussian(sp.initial_velocity,
                                                                       self.species_thermal_velocity[ic], sp.num)

    def load_from_restart(self, phase, it):
        """
        Load particles' data from a checkpoint of a previous run

        Parameters
        ----------
        it : int
            Timestep.

        phase: str
            Restart phase.

        """
        if phase == 'equilibration':
            file_name = os.path.join(self.eq_dump_dir, "checkpoint_" + str(it) + ".npz")
            data = np.load(file_name, allow_pickle=True)
            self.id = data["id"]
            self.names = data["names"]
            self.pos = data["pos"]
            self.vel = data["vel"]
            self.acc = data["acc"]

        elif phase == 'production':
            file_name = os.path.join(self.prod_dump_dir, "checkpoint_" + str(it) + ".npz")
            data = np.load(file_name, allow_pickle=True)
            self.id = data["id"]
            self.names = data["names"]
            self.pos = data["pos"]
            self.vel = data["vel"]
            self.acc = data["acc"]
            self.pbc_cntr = data["cntr"]
            self.rdf_hist = data["rdf_hist"]

        elif phase == 'magnetization':
            file_name = os.path.join(self.mag_dump_dir, "checkpoint_" + str(it) + ".npz")
            data = np.load(file_name, allow_pickle=True)
            self.id = data["id"]
            self.names = data["names"]
            self.pos = data["pos"]
            self.vel = data["vel"]
            self.acc = data["acc"]
            self.pbc_cntr = data["cntr"]
            self.rdf_hist = data["rdf_hist"]

    def load_from_file(self, f_name):
        """
        Load particles' data from a specific file.

        Parameters
        ----------
        f_name : str
            Filename
        """
        pv_data = np.loadtxt(f_name)
        if not (pv_data.shape[0] == self.total_num_ptcls):
            print("Number of particles is not same between input file and initial p & v data file.")
            print("From the input file: N = ", self.total_num_ptcls)
            print("From the initial p & v data: N = ", pv_data.shape[0])
            sys.exit()
        self.pos[:, 0] = pv_data[:, 0]
        self.pos[:, 1] = pv_data[:, 1]
        self.pos[:, 2] = pv_data[:, 2]

        self.vel[:, 0] = pv_data[:, 3]
        self.vel[:, 1] = pv_data[:, 4]
        self.vel[:, 2] = pv_data[:, 5]

    def uniform_no_reject(self, mins, maxs):
        """
        Randomly distribute particles along each direction.

        Parameters
        ----------
        mins : float
            Minimum value of the range of a uniform distribution.

        maxs : float
            Maximum value of the range of a uniform distribution.

        Returns
        -------
         : numpy.ndarray
            Particles' property, e.g. pos, vel. Shape = (``total_num_ptcls``, 3).

        """

        return self.rnd_gen.uniform(mins, maxs, (self.total_num_ptcls, 3))

    def lattice(self, perturb):
        """
        Place particles in a simple cubic lattice with a slight perturbation ranging
        from 0 to 0.5 times the lattice spacing.

        Parameters
        ----------
        perturb : float
            Value of perturbation, p, such that 0 <= p <= 1.

        Notes
        -----
        Author: Luke Stanek
        Date Created: 5/6/19
        Date Updated: 6/2/19
        Updates: Added to S_init_schemes.py for Sarkas import
        """

        # Check if perturbation is below maximum allowed. If not, default to maximum perturbation.
        if perturb > 1:
            print('Warning: Random perturbation must not exceed 1. Setting perturb = 1.')
            perturb = 1  # Maximum perturbation

        print('Initializing particles with maximum random perturbation of {} times the lattice spacing.'.format(
            perturb * 0.5))

        # Determining number of particles per side of simple cubic lattice
        part_per_side = self.total_num_ptcls ** (1. / 3.)  # Number of particles per side of cubic lattice

        # Check if total number of particles is a perfect cube, if not, place more than the requested amount
        if round(part_per_side) ** 3 != self.total_num_ptcls:
            part_per_side = np.ceil(self.total_num_ptcls ** (1. / 3.))
            print('\nWARNING: Total number of particles requested is not a perfect cube.')
            print('Initializing with {} particles.'.format(int(part_per_side ** 3)))

        dx_lattice = self.box_lengths[0] / (self.total_num_ptcls ** (1. / 3.))  # Lattice spacing
        dz_lattice = self.box_lengths[1] / (self.total_num_ptcls ** (1. / 3.))  # Lattice spacing
        dy_lattice = self.box_lengths[2] / (self.total_num_ptcls ** (1. / 3.))  # Lattice spacing

        # Create x, y, and z position arrays
        x = np.arange(0, self.box_lengths[0], dx_lattice) + 0.5 * dx_lattice
        y = np.arange(0, self.box_lengths[1], dy_lattice) + 0.5 * dy_lattice
        z = np.arange(0, self.box_lengths[2], dz_lattice) + 0.5 * dz_lattice

        # Create a lattice with appropriate x, y, and z values based on arange
        X, Y, Z = np.meshgrid(x, y, z)

        # Perturb lattice
        X += self.rnd_gen.uniform(-0.5, 0.5, np.shape(X)) * perturb * dx_lattice
        Y += self.rnd_gen.uniform(-0.5, 0.5, np.shape(Y)) * perturb * dy_lattice
        Z += self.rnd_gen.uniform(-0.5, 0.5, np.shape(Z)) * perturb * dz_lattice

        # Flatten the meshgrid values for plotting and computation
        self.pos[:, 0] = X.ravel()
        self.pos[:, 1] = Y.ravel()
        self.pos[:, 2] = Z.ravel()

    def random_reject(self, r_reject):
        """
        Place particles by sampling a uniform distribution from 0 to L (the box length)
        and uses a rejection radius to avoid placing particles to close to each other.

        Parameters
        ----------
        r_reject : float
            Value of rejection radius.

        Notes
        -----
        Author: Luke Stanek
        Date Created: 5/6/19
        Date Updated: N/A
        Updates: N/A

        """

        # Initialize Arrays
        x = np.array([])
        y = np.array([])
        z = np.array([])

        # Set first x, y, and z positions
        x_new = self.rnd_gen.uniform(0, self.box_lengths[0])
        y_new = self.rnd_gen.uniform(0, self.box_lengths[1])
        z_new = self.rnd_gen.uniform(0, self.box_lengths[2])

        # Append to arrays
        x = np.append(x, x_new)
        y = np.append(y, y_new)
        z = np.append(z, z_new)

        # Particle counter
        i = 0

        cntr_reject = 0
        cntr_total = 0
        # Loop to place particles
        while i < self.total_num_ptcls - 1:

            # Set x, y, and z positions
            x_new = self.rnd_gen.uniform(0.0, self.box_lengths[0])
            y_new = self.rnd_gen.uniform(0.0, self.box_lengths[1])
            z_new = self.rnd_gen.uniform(0.0, self.box_lengths[2])

            # Check if particle was place too close relative to all other current particles
            for j in range(len(x)):

                # Flag for if particle is outside of cutoff radius (True -> not inside rejection radius)
                flag = 1

                # Compute distance b/t particles for initial placement
                x_diff = x_new - x[j]
                y_diff = y_new - y[j]
                z_diff = z_new - z[j]

                # periodic condition applied for minimum image
                if x_diff < - self.box_lengths[0] / 2:
                    x_diff += self.box_lengths[0]
                if x_diff > self.box_lengths[0] / 2:
                    x_diff -= self.box_lengths[0]

                if y_diff < - self.box_lengths[1] / 2:
                    y_diff += self.box_lengths[1]
                if y_diff > self.box_lengths[1] / 2:
                    y_diff -= self.box_lengths[1]

                if z_diff < -self.box_lengths[2] / 2:
                    z_diff += self.box_lengths[2]
                if z_diff > self.box_lengths[2] / 2:
                    z_diff -= self.box_lengths[2]

                # Compute distance
                r = np.sqrt(x_diff ** 2 + y_diff ** 2 + z_diff ** 2)

                # Check if new particle is below rejection radius. If not, break out and try again
                if r <= r_reject:
                    flag = 0  # new position not added (False -> no longer outside reject r)
                    cntr_reject += 1
                    cntr_total += 1
                    break

            # If flag true add new position
            if flag == 1:
                x = np.append(x, x_new)
                y = np.append(y, y_new)
                z = np.append(z, z_new)

                # Increment particle number
                i += 1
                cntr_total += 1

        self.pos[:, 0] = x
        self.pos[:, 1] = y
        self.pos[:, 2] = z

    def halton_reject(self, bases, r_reject):
        """
        Place particles according to a Halton sequence from 0 to L (the box length)
        and uses a rejection radius to avoid placing particles to close to each other.

        Parameters
        ----------
        bases : numpy.ndarray
            Array of 3 ints each of which is a base for the Halton sequence.
            Defualt: bases = np.array([2,3,5])

        r_reject : float
            Value of rejection radius.

        Notes
        -----
        Author: Luke Stanek
        Date Created: 5/6/19
        Date Updated: N/A
        Updates: N/A

        """

        # Get bases
        b1, b2, b3 = bases

        # Allocate space and store first value from Halton
        x = np.array([0])
        y = np.array([0])
        z = np.array([0])

        # Initialize particle counter and Halton counter
        i = 1
        k = 1

        # Loop over all particles
        while i < self.total_num_ptcls:

            # Increment particle counter
            n = k
            m = k
            p = k

            # Determine x coordinate
            f1 = 1
            r1 = 0
            while n > 0:
                f1 /= b1
                r1 += f1 * (n % int(b1))
                n = np.floor(n / b1)
            x_new = self.box_lengths[0] * r1  # new x value

            # Determine y coordinate
            f2 = 1
            r2 = 0
            while m > 0:
                f2 /= b2
                r2 += f2 * (m % int(b2))
                m = np.floor(m / b2)
            y_new = self.box_lengths[1] * r2  # new y value

            # Determine z coordinate
            f3 = 1
            r3 = 0
            while p > 0:
                f3 /= b3
                r3 += f3 * (p % int(b3))
                p = np.floor(p / b3)
            z_new = self.box_lengths[2] * r3  # new z value

            # Check if particle was place too close relative to all other current particles
            for j in range(len(x)):

                # Flag for if particle is outside of cutoff radius (1 -> not inside rejection radius)
                flag = 1

                # Compute distance b/t particles for initial placement
                x_diff = x_new - x[j]
                y_diff = y_new - y[j]
                z_diff = z_new - z[j]

                # Periodic condition applied for minimum image
                if x_diff < - self.box_lengths[0] / 2:
                    x_diff = x_diff + self.box_lengths[0]
                if x_diff > self.box_lengths[0] / 2:
                    x_diff = x_diff - self.box_lengths[0]

                if y_diff < -self.box_lengths[1] / 2:
                    y_diff = y_diff + self.box_lengths[1]
                if y_diff > self.box_lengths[1] / 2:
                    y_diff = y_diff - self.box_lengths[1]

                if z_diff < -self.box_lengths[2] / 2:
                    z_diff = z_diff + self.box_lengths[2]
                if z_diff > self.box_lengths[2] / 2:
                    z_diff = z_diff - self.box_lengths[2]

                # Compute distance
                r = np.sqrt(x_diff ** 2 + y_diff ** 2 + z_diff ** 2)

                # Check if new particle is below rejection radius. If not, break out and try again
                if r <= r_reject:
                    k += 1  # Increment Halton counter
                    flag = 0  # New position not added (0 -> no longer outside reject r)
                    break

            # If flag true add new positiion
            if flag == 1:
                # Add new positions to arrays
                x = np.append(x, x_new)
                y = np.append(y, y_new)
                z = np.append(z, z_new)

                k += 1  # Increment Halton counter
                i += 1  # Increment particle number

        self.pos[:, 0] = x
        self.pos[:, 1] = y
        self.pos[:, 2] = z

    def kinetic_temperature(self):
        """
        Calculate the kinetic energy and temperature of each species.

        Returns
        -------
        K : numpy.ndarray
            Kinetic energy of each species. Shape=(``num_species``).

        T : numpy.ndarray
            Temperature of each species. Shape=(``num_species``).

        """
        K = np.zeros(self.num_species)
        T = np.zeros(self.num_species)
        const = 2.0 / (self.kB * self.species_num * self.dimensions)
        kinetic = 0.5 * self.masses * (self.vel * self.vel).transpose()

        species_start = 0
        species_end = 0
        for i, num in enumerate(self.species_num):
            species_end += num
            K[i] = np.sum(kinetic[:, species_start:species_end])
            T[i] = const[i] * K[i]
            species_start = species_end

        return K, T

    def remove_drift(self):
        """
        Enforce conservation of total linear momentum. Updates particles velocities
        """
        species_start = 0
        species_end = 0
        momentum = self.masses * self.vel.transpose()
        for ic, nums in enumerate(self.species_num):
            species_end += nums
            P = np.sum(momentum[:, species_start:species_end], axis=1)
            self.vel[species_start:species_end, :] -= P / (nums * self.masses[species_end - 1])
            species_start = species_end


class Species:
    """
    Class used to store all the information of a single species.

    Parameters
    ----------
    input_dict : dict, optional
        Dictionary to be copied.


    Attributes
    ----------
    name : str
        Species' name.

    number_density : float
        Species number density in appropriate units.

    num : int
        Number of particles of Species.

    mass : float
        Species' mass.

    charge : float
        Species' charge.

    Z : float
        Species charge number.

    ai : float
        Species Wigner - Seitz radius.

    coupling : float
        Species coupling constant

    wp : float
        Species' plasma frequency.

    debye_length : float
        Species' Debye Length.

    omega_c : float
        Species' cyclotron frequency.

    initial_velocity : numpy.ndarray
        Initial velocity in x,y,z directions.

    temperature : float
        Initial temperature of the species.

    temperature_eV : float
        Initial temperature of the species in eV.

    initial_velocity_distribution : str
        Type of distribution. Default = 'boltzmann'.

    initial_spatial_distribution : str
        Type of distribution. Default = 'uniform'.

    atomic_weight : float
        (Optional) Species mass in atomic units.

    concentration : float
        Species' concentration.

    mass_density : float
        (Optional) Species' mass density.

    """

    def __init__(self, input_dict: dict = None):
        self.name = None
        self.number_density = None
        self.charge = None
        self.mass = None
        self.num = None
        self.concentration = None
        self.mass_density = None
        self.atomic_weight = None
        self.initial_velocity_distribution = 'boltzmann'
        self.initial_spatial_distribution = 'random_no_reject'
        self.Z = None
        self.initial_velocity = np.zeros(3)
        self.temperature = None
        self.temperature_eV = None

        if input_dict:
            self.from_dict(input_dict)

    def __repr__(self):
        sortedDict = dict(sorted(self.__dict__.items(), key=lambda x: x[0].lower()))
        disp = 'Species( \n'
        for key, value in sortedDict.items():
            disp += "\t{} : {}\n".format(key, value)
        disp += ')'
        return disp

    def from_dict(self, input_dict: dict):
        """
        Update attributes from input dictionary.

        Parameters
        ----------
        input_dict: dict
            Dictionary to be copied.

        """
        self.__dict__.update(input_dict)
        if not isinstance(self.initial_velocity, np.ndarray):
            self.initial_velocity = np.array(self.initial_velocity)

    def calc_plasma_frequency(self, constant: float):
        """
        Calculate the plasma frequency.

        Parameters
        ----------
        constant : float
            Charged systems: Electrostatic constant  :math: `4\pi \epsilon_0` [mks]
            Neutral systems: :math: `1/n\sigma^2`

        """
        self.wp = np.sqrt(4.0 * np.pi * self.charge ** 2 * self.number_density / (self.mass * constant))

    def calc_debye_length(self, kB: float, constant: float):
        """
        Calculate the Debye Length.

        Parameters
        ----------
        kB : float
            Boltzmann constant.

        constant : float
            Charged systems: Electrostatic constant  :math: `4 \pi \epsilon_0` [mks]
            Neutral systems: :math: `1/n\sigma^2`


        """
        self.debye_length = np.sqrt((self.temperature * kB * constant)
                                    / (4.0 * np.pi * self.charge ** 2 * self.number_density))

    def calc_cyclotron_frequency(self, magnetic_field_strength):
        """
        Calculate the cyclotron frequency.
        See https://en.wikipedia.org/wiki/Lorentz_force

        Parameters
        ----------

        magnetic_field_strength : float
            Magnetic field strength.

        """
        self.omega_c = self.charge * magnetic_field_strength / self.mass

    def calc_coupling(self, a_ws, z_avg, const):
        """
        Calculate the coupling constant between particles.

        Parameters
        ----------
        a_ws : float
            Total Wigner-Seitz radius.

        z_avg : float
            Species charge.

        const : float
            Electrostatic * Thermal constants.

        """
        # self.ai = (self.charge / z_avg) ** (1. / 3.) * a_ws
        self.ai = (3.0 / (4.0 * np.pi * self.number_density)) ** (1. / 3.)
        self.coupling = self.charge ** 2 / (self.ai * const * self.temperature)
