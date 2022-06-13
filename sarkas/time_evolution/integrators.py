"""
Module of various types of time_evolution
"""

from copy import deepcopy
from IPython import get_ipython
from numba import float64, int64, jit, void
from numpy import arange, array, cos, cross, pi, sin, sqrt, zeros
from scipy.linalg import norm

if get_ipython().__class__.__name__ == "ZMQInteractiveShell":
    from tqdm import tqdm_notebook as tqdm
else:
    from tqdm import tqdm

from threading import Thread

# import fmm3dpy as fmm


class Integrator:
    """
    Class used to assign integrator type.

    Attributes
    ----------
    dt : float
        Timestep.

    equilibration_steps : int
        Total number of equilibration timesteps.

    eq_dump_step : int
        Equilibration dump interval.

    kB : float
        Boltzmann constant.

    magnetized : bool
        Magnetized simulation flag.

    production_steps : int
        Total number of production timesteps.

    prod_dump_step : int
        Production dump interval.

    species_num : numpy.ndarray
        Number of particles of each species.

    species_plasma_frequencies : numpy.ndarray
        Plasma frequency of each species.

    box_lengths : numpy.ndarray
        Length of each box side.

    pbox_lengths : numpy.ndarray
        Initial particle box sides' lengths.

    verbose : bool
        Verbose output flag.

    type : str
        Integrator type.

    update : func
        Integrator choice. 'verlet', 'verlet_langevin', 'magnetic_verlet' or 'magnetic_boris'.

    update_accelerations : func
        Link to the correct potential update function.

    thermostate : func
        Link to the correct thermostat function.

    enforce_bc : func
        Link to the function enforcing boundary conditions. 'periodic' or 'absorbing'.

    """

    type: str = None
    supported_integrators = [
        "verlet",
        "verlet_langevin",
        "magnetic_verlet",
        "magnetic_pos_verlet",
        "magnetic_boris",
        "cyclotronic",
    ]
    electrostatic_equilibration: bool = False

    dt: float = None
    kB: float = None

    eq_dump_step: int = None
    equilibration_steps: int = None
    prod_dump_step: int = None
    production_steps: int = None

    species_num = None
    species_plasma_frequencies = None

    # Magnetic attributes
    magnetized: bool = False
    mag_dump_steps: int = None
    magnetization_steps: int = None
    magnetic_field_uvector = None
    magnetic_field = None
    omega_c = None
    species_cyclotron_frequencies = None
    ccodt = None
    cdt = None
    ssodt = None
    sdt = None
    v_B = None
    v_F = None

    # Langevin attributes
    c1 = None
    c2 = None
    sigma = None
    box_lengths = None
    pbox_lengths = None

    boundary_conditions = None
    enforce_bc = None
    supported_boundary_conditions = ["periodic", "absorbing", "reflecting"]

    thermostate = None
    update = None
    update_accelerations = None
    verbose: bool = False

    threads_ls = []

    # def __repr__(self):
    #     sortedDict = dict(sorted(self.__dict__.items(), key=lambda x: x[0].lower()))
    #     disp = 'Integrator( \n'
    #     for key, value in sortedDict.items():
    #         disp += "\t{} : {}\n".format(key, value)
    #     disp += ')'
    #     return disp

    def __copy__(self):
        """Make a shallow copy of the object using copy by creating a new instance of the object and copying its __dict__."""
        # Create a new object
        _copy = type(self)()
        # copy the dictionary
        _copy.from_dict(input_dict=self.__dict__)
        return _copy

    def __deepcopy__(self, memodict={}):
        """Make a deepcopy of the object.

        Parameters
        ----------
        memodict: dict
            Dictionary of id's to copies

        Returns
        -------
        _copy: :class:`sarkas.time_evolution.integrators.Integrator`
            A new Integrator class.
        """
        id_self = id(self)  # memorization avoids unnecessary recursion
        _copy = memodict.get(id_self)
        if _copy is None:
            _copy = type(self)()
            # Make a deepcopy of the mutable arrays using numpy copy function
            for k, v in self.__dict__.items():
                if k != "thread_ls":
                    _copy.__dict__[k] = deepcopy(v, memodict)

        return _copy

    def from_dict(self, input_dict: dict):
        """
        Update attributes from input dictionary.

        Parameters
        ----------
        input_dict: dict
            Dictionary to be copied.

        """
        self.__dict__.update(input_dict)

    def setup(self, params, thermostat, potential):
        """
        Assign attributes from simulation's parameters and classes.

        Parameters
        ----------
        params : :class:`sarkas.core.Parameters`
            Parameters class.

        thermostat : :class:`sarkas.time_evolution.Thermostat`
            Thermostat class

        potential : :class:`sarkas.potentials.core.Potential`
            Potential class.

        """
        self.box_lengths = params.box_lengths
        self.pbox_lengths = params.pbox_lengths
        self.kB = params.kB
        self.species_num = params.species_num
        self.species_plasma_frequencies = params.species_plasma_frequencies
        self.verbose = params.verbose

        # Enforce consistency
        self.boundary_conditions = params.boundary_conditions.lower()
        self.type = self.type.lower()

        if self.dt is None:
            self.dt = params.dt

        if self.production_steps is None:
            self.production_steps = params.production_steps

        if self.equilibration_steps is None:
            self.equilibration_steps = params.equilibration_steps

        if self.prod_dump_step is None:
            if hasattr(params, "prod_dump_step"):
                self.prod_dump_step = params.prod_dump_step
            else:
                self.prod_dump_step = int(0.1 * self.production_steps)

        if self.eq_dump_step is None:
            if hasattr(params, "eq_dump_step"):
                self.eq_dump_step = params.eq_dump_step
            else:
                self.eq_dump_step = int(0.1 * self.equilibration_steps)

        if self.boundary_conditions not in self.supported_boundary_conditions:
            raise ValueError(
                "Unsupported boundary conditions. " "Please choose one of the supported boundary conditions \n",
                self.supported_boundary_conditions,
            )

        # Assign integrator.enforce_bc to the correct method
        if self.boundary_conditions == "periodic":
            self.enforce_bc = self.periodic
        elif self.boundary_conditions == "absorbing":
            self.enforce_bc = self.absorbing
        elif self.boundary_conditions == "reflective":
            self.enforce_bc = self.reflecting

        if params.magnetized or self.magnetized:
            self.magnetized = True
            self.species_cyclotron_frequencies = params.species_cyclotron_frequencies.copy()
            # Create the unit vector of the magnetic field
            self.magnetic_field_uvector = params.magnetic_field / norm(params.magnetic_field)
            self.omega_c = zeros((params.total_num_ptcls, params.dimensions))

            sp_start = 0
            sp_end = 0
            for ic, sp_np in enumerate(params.species_num):
                sp_end += sp_np
                self.omega_c[sp_start:sp_end, :] = params.species_cyclotron_frequencies[ic]
                sp_start += sp_np

            # array to temporary store velocities
            # Luciano: I have the vague doubt that allocating memory for these arrays is faster than calculating them
            # each time step
            self.v_B = zeros((params.total_num_ptcls, params.dimensions))

        if self.type not in self.supported_integrators:
            raise ValueError(
                "Integrator not supported. " "Please choose one of the supported integrators \n",
                self.supported_integrators,
            )

        # Assign integrator.update to the correct method
        if self.type == "verlet":
            self.update = self.verlet

        elif self.type == "verlet_langevin":

            self.sigma = sqrt(2.0 * self.langevin_gamma * params.kB * params.species_temperatures / params.species_masses)
            self.c1 = 1.0 - 0.5 * self.langevin_gamma * self.dt
            self.c2 = 1.0 / (1.0 + 0.5 * self.langevin_gamma * self.dt)
            self.update = self.verlet_langevin

        elif self.type == "magnetic_verlet":

            # Calculate functions for magnetic integrator
            # This could be used when the generalization to Forest-Ruth and MacLachlan algorithms will be implemented
            # In a magnetic Velocity-Verlet the coefficient is 1/2, see eq.~(78) in :cite:`Chin2008`
            self.magnetic_helpers(0.5)

            # array to temporary store velocities
            # Luciano: I have the vague doubt that allocating memory for these arrays is faster than calculating them
            # each time step
            self.v_F = zeros((params.total_num_ptcls, params.dimensions))

            if self.magnetic_field_uvector @ array([0.0, 0.0, 1.0]) == 1.0:  # dot product
                self.update = self.magnetic_verlet_zdir
            else:
                self.update = self.magnetic_verlet

        elif self.type == "magnetic_pos_verlet":
            # Calculate functions for magnetic integrator
            # This could be used when the generalization to Forest-Ruth and MacLachlan algorithms will be implemented
            # In a magnetic Velocity-Verlet the coefficient is 1/2, see eq.~(78) in :cite:`Chin2008`
            self.magnetic_helpers(1.0)

            # array to temporary store velocities
            # Luciano: I have the vague doubt that allocating memory for these arrays is faster than calculating them
            # each time step
            self.v_F = zeros((params.total_num_ptcls, params.dimensions))

            if self.magnetic_field_uvector @ array([0.0, 0.0, 1.0]) == 1.0:  # dot product
                self.update = self.magnetic_pos_verlet_zdir
            else:
                self.update = self.magnetic_pos_verlet

        elif self.type == "magnetic_boris":

            # In a leapfrog-type algorithm the coefficient is different for the acceleration and magnetic rotation
            # see eq.~(79) in :cite:`Chin2008`
            self.magnetic_helpers(1.0)

            if self.magnetic_field_uvector @ array([0.0, 0.0, 1.0]) == 1.0:  # dot product
                self.update = self.magnetic_boris_zdir
            else:
                self.update = self.magnetic_boris

            # array to temporary store velocities
            # Luciano: I have the vague doubt that allocating memory for these arrays is faster than calculating them
            # each time step
            self.v_F = zeros((params.total_num_ptcls, params.dimensions))

        elif self.type == "cyclotronic":
            # Calculate functions for magnetic integrator
            # This could be used when the generalization to Forest-Ruth and MacLachlan algorithms will be implemented
            # In a magnetic Velocity-Verlet the coefficient is 1/2, see eq.~(78) in :cite:`Chin2008`
            self.magnetic_helpers(0.5)

            if self.magnetic_field_uvector @ array([0.0, 0.0, 1.0]) == 1.0:  # dot product
                self.update = self.cyclotronic_zdir
            else:
                self.update = self.cyclotronic

        if self.magnetized and self.electrostatic_equilibration:
            params.electrostatic_equilibration = True
            self.magnetic_integrator = self.update
            self.update = self.verlet

            if self.magnetization_steps is None:
                self.magnetization_steps = params.magnetization_steps

            if self.prod_dump_step is None:
                if hasattr(params, "mag_dump_step"):
                    self.mag_dump_step = params.mag_dump_step
                else:
                    self.mag_dump_step = int(0.1 * self.production_steps)

        if potential.method != "fmm":
            if potential.pppm_on:
                self.update_accelerations = potential.update_pppm
            else:
                if potential.linked_list_on:
                    self.update_accelerations = potential.update_linked_list
                else:
                    self.update_accelerations = potential.update_brute
        else:
            self.update_accelerations = potential.update_fmm

        self.thermostate = thermostat.update

    def equilibrate(self, it_start, ptcls, checkpoint):
        """
        Loop over the equilibration steps.

        Parameters
        ----------
        it_start: int
            Initial step of equilibration.

        ptcls: :class:`sarkas.particles.Particles`
            Particles' class.

        checkpoint: :class:`sarkas.utilities.InputOutput`
            IO class for saving dumps.

        """
        for it in tqdm(range(it_start, self.equilibration_steps), disable=not self.verbose):
            # Calculate the Potential energy and update particles' data

            self.update(ptcls)

            if (it + 1) % self.eq_dump_step == 0:

                th = Thread(
                    target=checkpoint.dump,
                    name=f"Sarkas_Equilibration_Thread - {it+1}",
                    args=(
                        "equilibration",
                        ptcls.__deepcopy__(),
                        it + 1,
                    ),
                )

                self.threads_ls.append(th)

                th.start()

            self.thermostate(ptcls, it)
        ptcls.remove_drift()

    def magnetize(self, it_start, ptcls, checkpoint):
        """
        Loop over the magnetization steps.

        Parameters
        ----------
        it_start: int
            Initial step of magnetization.

        ptcls: :class:`sarkas.particles.Particles`
            Particles' class.

        checkpoint: :class:`sarkas.utilities.InputOutput`
            IO class for saving dumps.

        """
        self.update = self.magnetic_integrator
        for it in tqdm(range(it_start, self.magnetization_steps), disable=not self.verbose):
            # Calculate the Potential energy and update particles' data
            self.update(ptcls)
            if (it + 1) % self.mag_dump_step == 0:
                th = Thread(
                    target=checkpoint.dump,
                    name=f"Sarkas_Magnetization_Thread - {it+1}",
                    args=(
                        "magnetization",
                        ptcls.__deepcopy__(),
                        it + 1,
                    ),
                )
                self.threads_ls.append(th)
                th.start()
            self.thermostate(ptcls, it)

    def produce(self, it_start, ptcls, checkpoint):
        """
        Loop over the production steps.

        Parameters
        ----------
        it_start: int
            Initial step of production phase.

        ptcls: :class:`sarkas.particles.Particles`
            Particles' class.

        checkpoint: :class:`sarkas.utilities.InputOutput`
            IO class for saving dumps.

        """
        for it in tqdm(range(it_start, self.production_steps), disable=(not self.verbose)):

            # Move the particles and calculate the potential
            self.update(ptcls)
            if (it + 1) % self.prod_dump_step == 0:
                # Save particles' data for restart
                th = Thread(
                    target=checkpoint.dump,
                    name=f"Sarkas_Production_Thread - {it+1}",
                    args=(
                        "production",
                        ptcls.__deepcopy__(),
                        it + 1,
                    ),
                )
                self.threads_ls.append(th)
                th.start()

    def verlet_langevin(self, ptcls):
        """
        Update particles class using the velocity verlet algorithm and Langevin damping.

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.


        """
        beta = ptcls.gaussian(0.0, 1.0, ptcls.pos.shape[0])
        sp_start = 0  # start index for species loop
        sp_end = 0
        for ic, num in enumerate(self.species_num):
            sp_end += num
            ptcls.pos[sp_start:sp_end, :] += (
                self.c1 * self.dt * ptcls.vel[sp_start:sp_end, :]
                + 0.5 * self.dt**2 * ptcls.acc[sp_start:sp_end, :]
                + 0.5 * self.sigma[ic] * self.dt**1.5 * beta
            )
            sp_start += num

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        acc_old = ptcls.acc.copy()
        self.update_accelerations(ptcls)

        sp_start = 0
        sp_end = 0
        for ic, num in enumerate(self.species_num):
            sp_end += num

            ptcls.vel[sp_start:sp_end, :] = (
                self.c1 * self.c2 * ptcls.vel[sp_start:sp_end, :]
                + 0.5 * self.c2 * self.dt * (ptcls.acc[sp_start:sp_end, :] + acc_old[sp_start:sp_end, :])
                + self.c2 * self.sigma[ic] * sqrt(self.dt) * beta
            )
            sp_start += num

    def verlet(self, ptcls):
        """
        Update particles' class based on velocity verlet algorithm.
        More information can be found here: https://en.wikipedia.org/wiki/Verlet_integration
        or on the Sarkas website.

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        """
        # First half step velocity update
        ptcls.vel += 0.5 * ptcls.acc * self.dt
        # Full step position update
        ptcls.pos += ptcls.vel * self.dt
        # Enforce boundary condition
        self.enforce_bc(ptcls)
        # Compute total potential energy and acceleration for second half step velocity update
        self.update_accelerations(ptcls)
        # Second half step velocity update
        ptcls.vel += 0.5 * ptcls.acc * self.dt

    def magnetic_helpers(self, coefficient):
        """Calculate the trigonometric functions of the magnetic integrators.

        Parameters
        ----------
        coefficient: float
            Timestep coefficient.

        Notes
        -----
        This is useful for the Leapfrog magnetic algorithm and future Forest-Ruth and MacLachlan algorithms.

        """
        theta = self.omega_c * self.dt * coefficient
        self.sdt = sin(theta)
        self.cdt = cos(theta)
        self.ccodt = 1.0 - self.cdt
        self.ssodt = 1.0 - self.sdt / theta

    def magnetic_verlet_zdir(self, ptcls):
        """
        Update particles' class based on velocity verlet method in the case of a
        constant magnetic field along the :math:`z` axis. For more info see eq. (78) of Ref. :cite:`Chin2008`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        Notes
        -----
        This integrator is faster than `magnetic_verlet` but valid only for a magnetic field in the :math:`z`-direction.
        This is the preferred choice in this case.
        """

        # First half step of velocity update
        # # Magnetic rotation x - velocity
        # (B x v)_x  = -v_y, (B x B x v)_x = -v_x
        self.v_B[:, 0] = ptcls.vel[:, 1] * self.sdt[:, 0] + ptcls.vel[:, 0] * self.cdt[:, 0]
        # Magnetic rotation y - velocity
        # (B x v)_y  = v_x, (B x B x v)_y = -v_y
        self.v_B[:, 1] = -ptcls.vel[:, 0] * self.sdt[:, 0] + ptcls.vel[:, 1] * self.cdt[:, 1]

        # Magnetic + Const force field x - velocity
        # (B x a)_x  = -a_y, (B x B x a)_x = -a_x
        self.v_F[:, 0] = (
            self.ccodt[:, 1] / self.omega_c[:, 1] * ptcls.acc[:, 1]
            + self.sdt[:, 0] / self.omega_c[:, 0] * ptcls.acc[:, 0]
        )
        # Magnetic + Const force field y - velocity
        # (B x a)_y  = a_x, (B x B x a)_y = -a_y
        self.v_F[:, 1] = (
            -self.ccodt[:, 0] / self.omega_c[:, 0] * ptcls.acc[:, 0]
            + self.sdt[:, 1] / self.omega_c[:, 1] * ptcls.acc[:, 1]
        )

        ptcls.vel[:, 0] = self.v_B[:, 0] + self.v_F[:, 0]
        ptcls.vel[:, 1] = self.v_B[:, 1] + self.v_F[:, 1]
        ptcls.vel[:, 2] += 0.5 * self.dt * ptcls.acc[:, 2]

        # Position update
        ptcls.pos += ptcls.vel * self.dt

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        # Compute total potential energy and acceleration for second half step velocity update
        potential_energy = self.update_accelerations(ptcls)

        # # Magnetic rotation x - velocity
        # (B x v)_x  = -v_y, (B x B x v)_x = -v_x
        self.v_B[:, 0] = ptcls.vel[:, 1] * self.sdt[:, 0] + ptcls.vel[:, 0] * self.cdt[:, 0]
        # Magnetic rotation y - velocity
        # (B x v)_y  = v_x, (B x B x v)_y = -v_y
        self.v_B[:, 1] = -ptcls.vel[:, 0] * self.sdt[:, 0] + ptcls.vel[:, 1] * self.cdt[:, 1]

        # Magnetic + Const force field x - velocity
        # (B x a)_x  = -a_y, (B x B x a)_x = -a_x
        self.v_F[:, 0] = (
            self.ccodt[:, 1] / self.omega_c[:, 1] * ptcls.acc[:, 1]
            + self.sdt[:, 0] / self.omega_c[:, 0] * ptcls.acc[:, 0]
        )
        # Magnetic + Const force field y - velocity
        # (B x a)_y  = a_x, (B x B x a)_y = -a_y
        self.v_F[:, 1] = (
            -self.ccodt[:, 0] / self.omega_c[:, 0] * ptcls.acc[:, 0]
            + self.sdt[:, 1] / self.omega_c[:, 1] * ptcls.acc[:, 1]
        )

        ptcls.vel[:, 0] = self.v_B[:, 0] + self.v_F[:, 0]
        ptcls.vel[:, 1] = self.v_B[:, 1] + self.v_F[:, 1]
        ptcls.vel[:, 2] += 0.5 * self.dt * ptcls.acc[:, 2]

        return potential_energy

    def magnetic_verlet(self, ptcls):
        """
        Update particles' class based on velocity verlet method in the case of an arbitrary direction of the
        constant magnetic field. For more info see eq. (78) of Ref. :cite:`Chin2008`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        Notes
        -----
        :cite:`Chin2008` equations are written for a negative charge. This allows him to write
        :math:`\\dot{\\mathbf v} = \\omega_c \\hat{B} \\times \\mathbf v`. In the case of positive charges we will have
        :math:`\\dot{\\mathbf v} = - \\omega_c \\hat{B} \\times \\mathbf v`.
        Hence the reason of the different signs in the formulas below compared to Chin's.

        Warnings
        --------
        This integrator is valid for a magnetic field in an arbitrary direction. However, while the integrator works for
        an arbitrary direction, methods in :mod:`sarkas.tools.observables` work only for a magnetic field in the
        :math:`z` - direction. Hence, if you choose to use this integrator remember to change your physical observables.

        """
        # Calculate the cross products
        b_cross_v = cross(self.magnetic_field_uvector, ptcls.vel)
        b_cross_b_cross_v = cross(self.magnetic_field_uvector, b_cross_v)
        b_cross_a = cross(self.magnetic_field_uvector, ptcls.acc)
        b_cross_b_cross_a = cross(self.magnetic_field_uvector, b_cross_a)

        # First half step of velocity update
        ptcls.vel += -self.sdt * b_cross_v + self.ccodt * b_cross_b_cross_v

        ptcls.vel += (
            0.5 * ptcls.acc * self.dt
            - self.ccodt / self.omega_c * b_cross_a
            + 0.5 * self.dt * self.ssodt * b_cross_b_cross_a
        )

        # Position update
        ptcls.pos += ptcls.vel * self.dt

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        # Compute total potential energy and acceleration for second half step velocity update
        potential_energy = self.update_accelerations(ptcls)

        # Re-calculate the cross products
        b_cross_v = cross(self.magnetic_field_uvector, ptcls.vel)
        b_cross_b_cross_v = cross(self.magnetic_field_uvector, b_cross_v)
        b_cross_a = cross(self.magnetic_field_uvector, ptcls.acc)
        b_cross_b_cross_a = cross(self.magnetic_field_uvector, b_cross_a)

        # Second half step velocity update
        ptcls.vel += -self.sdt * b_cross_v + self.ccodt * b_cross_b_cross_v

        ptcls.vel += (
            0.5 * ptcls.acc * self.dt
            - self.ccodt / self.omega_c * b_cross_a
            + 0.5 * self.dt * self.ssodt * b_cross_b_cross_a
        )

        return potential_energy

    def magnetic_boris_zdir(self, ptcls):
        """
        Update particles' class using the Boris algorithm in the case of a
        constant magnetic field along the :math:`z` axis. For more info see eqs. (80) - (81) of Ref. :cite:`Chin2008`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        """
        # First half step of velocity update: Apply exp(dt * V_F / 2)
        ptcls.vel += 0.5 * ptcls.acc * self.dt

        # Rotate: Apply exp( dt * V)
        # B cross v
        self.v_B[:, 0] = -self.sdt[:, 1] * ptcls.vel[:, 1]
        self.v_B[:, 1] = self.sdt[:, 0] * ptcls.vel[:, 0]

        # B cross B cross v
        self.v_B[:, 0] -= self.ccodt[:, 0] * ptcls.vel[:, 0]
        self.v_B[:, 1] -= self.ccodt[:, 1] * ptcls.vel[:, 1]
        # Update velocities
        ptcls.vel[:, :2] += self.v_B[:, :2]

        # Second Acceleration half step: Apply exp(dt * V_F / 2)
        ptcls.vel += 0.5 * ptcls.acc * self.dt

        # Full step position update
        ptcls.pos += ptcls.vel * self.dt

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        # Compute total potential energy and acceleration for second half step velocity update
        potential_energy = self.update_accelerations(ptcls)

        return potential_energy

    def magnetic_boris(self, ptcls):
        """
        Update particles' class using the Boris algorithm in the case of a
        constant magnetic field along the :math:`z` axis. For more info see eqs. (80) - (81) of Ref. :cite:`Chin2008`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        """

        # First half step of velocity update: Apply exp(eV_F/2)
        ptcls.vel += 0.5 * ptcls.acc * self.dt

        # Rotate: Apply exp( dt * V)
        # B cross v
        b_cross_v = cross(self.magnetic_field_uvector, ptcls.vel)
        # B cross B cross v
        b_cross_b_cross_v = cross(self.magnetic_field_uvector, b_cross_v)
        ptcls.vel += self.sdt * b_cross_v + self.ccodt * b_cross_b_cross_v

        # Second Acceleration half step: Apply exp(dt * V_F / 2)
        ptcls.vel += 0.5 * ptcls.acc * self.dt

        # Full step position update
        ptcls.pos += ptcls.vel * self.dt

        # Periodic boundary condition
        enforce_pbc(ptcls.pos, ptcls.pbc_cntr, self.box_lengths)

        # Compute total potential energy and acceleration for second half step velocity update
        potential_energy = self.update_accelerations(ptcls)

        return potential_energy

    def magnetic_pos_verlet_zdir(self, ptcls):
        """
        Update particles' class based on position verlet method in the case of a
        constant magnetic field along the :math:`z` axis. For more info see eq. (79) of Ref. :cite:`Chin2008`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        Notes
        -----
        This integrator is faster than `magnetic_verlet` but valid only for a magnetic field in the :math:`z`-direction.
        This is the preferred choice in this case.
        """

        # Position update
        ptcls.pos += 0.5 * ptcls.vel * self.dt

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        # Compute total potential energy and acceleration for second half step velocity update
        potential_energy = self.update_accelerations(ptcls)

        # First half step of velocity update
        # # Magnetic rotation x - velocity
        # (B x v)_x  = -v_y, (B x B x v)_x = -v_x
        self.v_B[:, 0] = ptcls.vel[:, 1] * self.sdt[:, 0] + ptcls.vel[:, 0] * self.cdt[:, 0]
        # Magnetic rotation y - velocity
        # (B x v)_y  = v_x, (B x B x v)_y = -v_y
        self.v_B[:, 1] = -ptcls.vel[:, 0] * self.sdt[:, 0] + ptcls.vel[:, 1] * self.cdt[:, 1]

        # Magnetic + Const force field x - velocity
        # (B x a)_x  = -a_y, (B x B x a)_x = -a_x
        self.v_F[:, 0] = (
            self.ccodt[:, 1] / self.omega_c[:, 1] * ptcls.acc[:, 1]
            + self.sdt[:, 0] / self.omega_c[:, 0] * ptcls.acc[:, 0]
        )
        # Magnetic + Const force field y - velocity
        # (B x a)_y  = a_x, (B x B x a)_y = -a_y
        self.v_F[:, 1] = (
            -self.ccodt[:, 0] / self.omega_c[:, 0] * ptcls.acc[:, 0]
            + self.sdt[:, 1] / self.omega_c[:, 1] * ptcls.acc[:, 1]
        )

        ptcls.vel[:, 0] = self.v_B[:, 0] + self.v_F[:, 0]
        ptcls.vel[:, 1] = self.v_B[:, 1] + self.v_F[:, 1]
        ptcls.vel[:, 2] += self.dt * ptcls.acc[:, 2]

        # Position update
        ptcls.pos += 0.5 * ptcls.vel * self.dt

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        return potential_energy

    def magnetic_pos_verlet(self, ptcls):
        """
        Update particles' class based on position verlet method in the case of an arbitrary direction of the
        constant magnetic field. For more info see eq. (79) of Ref. :cite:`Chin2008`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        Notes
        -----
        :cite:`Chin2008` equations are written for a negative charge. This allows him to write
        :math:`\\dot{\\mathbf v} = \\omega_c \\hat{B} \\times \\mathbf v`. In the case of positive charges we will have
        :math:`\\dot{\\mathbf v} = - \\omega_c \\hat{B} \\times \\mathbf v`.
        Hence the reason of the different signs in the formulas below compared to Chin's.

        Warnings
        --------
        This integrator is valid for a magnetic field in an arbitrary direction. However, while the integrator works for
        an arbitrary direction, methods in :mod:`sarkas.tools.observables` work only for a magnetic field in the
        :math:`z` - direction. Hence, if you choose to use this integrator remember to change your physical observables.

        """
        # Half position update
        ptcls.pos += ptcls.vel * self.dt

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        # Compute total potential energy and acceleration for second half step velocity update
        potential_energy = self.update_accelerations(ptcls)

        # Calculate the cross products
        b_cross_v = cross(self.magnetic_field_uvector, ptcls.vel)
        b_cross_b_cross_v = cross(self.magnetic_field_uvector, b_cross_v)
        b_cross_a = cross(self.magnetic_field_uvector, ptcls.acc)
        b_cross_b_cross_a = cross(self.magnetic_field_uvector, b_cross_a)

        # First half step of velocity update
        ptcls.vel += -self.sdt * b_cross_v + self.ccodt * b_cross_b_cross_v

        ptcls.vel += (
            ptcls.acc * self.dt - self.ccodt / self.omega_c * b_cross_a + self.dt * self.ssodt * b_cross_b_cross_a
        )

        # Second half position update
        ptcls.pos += ptcls.vel * self.dt

        # Enforce boundary condition
        self.enforce_bc(ptcls)

        return potential_energy

    def cyclotronic_zdir(self, ptcls):
        """
        Update particles' class using the cyclotronic algorithm in the case of a
        constant magnetic field along the :math:`z` axis.
        For more info see eqs. (16) - (17) of Ref. :cite:`Patacchini2009`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        """
        # Drift half step
        # Rotate Positions
        ptcls.pos[:, 0] += (
            ptcls.vel[:, 0] * self.sdt[:, 0] / self.omega_c[:, 0]
            + ptcls.vel[:, 1] * self.ccodt[:, 1] / self.omega_c[:, 1]
        )
        ptcls.pos[:, 1] += (
            ptcls.vel[:, 1] * self.sdt[:, 1] / self.omega_c[:, 1]
            - ptcls.vel[:, 0] * self.ccodt[:, 0] / self.omega_c[:, 0]
        )
        ptcls.pos[:, 2] += 0.5 * ptcls.vel[:, 2] * self.dt
        # Enforce boundary condition
        self.enforce_bc(ptcls)
        # Create rotated velocities
        self.v_B[:, 0] = self.cdt[:, 0] * ptcls.vel[:, 0] + self.sdt[:, 1] * ptcls.vel[:, 1]
        self.v_B[:, 1] = self.cdt[:, 1] * ptcls.vel[:, 1] - self.sdt[:, 0] * ptcls.vel[:, 0]
        ptcls.vel[:, :2] = self.v_B[:, :2].copy()
        # Compute total potential energy and accelerations
        potential_energy = self.update_accelerations(ptcls)

        # Kick full step
        ptcls.vel += ptcls.acc * self.dt

        # Drift half step
        # Rotate Positions
        ptcls.pos[:, 0] += (
            ptcls.vel[:, 0] * self.sdt[:, 0] / self.omega_c[:, 0]
            + ptcls.vel[:, 1] * self.ccodt[:, 1] / self.omega_c[:, 1]
        )
        ptcls.pos[:, 1] += (
            ptcls.vel[:, 1] * self.sdt[:, 1] / self.omega_c[:, 1]
            - ptcls.vel[:, 0] * self.ccodt[:, 0] / self.omega_c[:, 0]
        )
        ptcls.pos[:, 2] += 0.5 * ptcls.vel[:, 2] * self.dt
        # Enforce boundary condition
        self.enforce_bc(ptcls)
        # Create rotated velocities
        self.v_B[:, 0] = self.cdt[:, 0] * ptcls.vel[:, 0] + self.sdt[:, 1] * ptcls.vel[:, 1]
        self.v_B[:, 1] = self.cdt[:, 1] * ptcls.vel[:, 1] - self.sdt[:, 0] * ptcls.vel[:, 0]
        # Update final velocities
        ptcls.vel[:, :2] = self.v_B[:, :2].copy()

        return potential_energy

    def cyclotronic(self, ptcls):
        """
        Update particles' class using the cyclotronic algorithm in the case of a
        constant magnetic field along the :math:`z` axis.
        For more info see eqs. (16) - (17) of Ref. :cite:`Patacchini2009`

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        Returns
        -------
        potential_energy : float
             Total potential energy.

        """
        # Drift half step

        # Calculate the cross products
        b_cross_v = cross(self.magnetic_field_uvector, ptcls.vel)
        b_cross_b_cross_v = cross(self.magnetic_field_uvector, b_cross_v)
        # Rotate Positions
        ptcls.pos += (
            0.5 * ptcls.vel * self.dt
            - self.ccodt * b_cross_v / self.omega_c
            + 0.5 * self.dt * self.ssodt * b_cross_b_cross_v
        )
        # Enforce boundary condition
        self.enforce_bc(ptcls)
        # First half step of velocity update
        ptcls.vel += -self.sdt * b_cross_v + self.ccodt * b_cross_b_cross_v
        # Compute total potential energy and accelerations
        potential_energy = self.update_accelerations(ptcls)

        # Kick full step
        ptcls.vel += ptcls.acc * self.dt

        # Drift half step
        # Calculate the cross products
        b_cross_v = cross(self.magnetic_field_uvector, ptcls.vel)
        b_cross_b_cross_v = cross(self.magnetic_field_uvector, b_cross_v)
        # Rotate Positions
        ptcls.pos += (
            0.5 * ptcls.vel * self.dt
            - self.ccodt * b_cross_v / self.omega_c
            + 0.5 * self.dt * self.ssodt * b_cross_b_cross_v
        )
        # Enforce boundary condition
        self.enforce_bc(ptcls)
        # Second half step of velocity update
        ptcls.vel += -self.sdt * b_cross_v + self.ccodt * b_cross_b_cross_v

        return potential_energy

    def periodic(self, ptcls):
        """
        Applies periodic boundary conditions by calling enforce_pbc

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        """

        enforce_pbc(ptcls.pos, ptcls.pbc_cntr, self.box_lengths)

    def absorbing(self, ptcls):
        """
        Applies absorbing boundary conditions by calling enforce_abc

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        """

        enforce_abc(ptcls.pos, ptcls.vel, ptcls.acc, ptcls.charges, self.box_lengths)

    def reflecting(self, ptcls):
        """
        Applies reflective boundary conditions by calling enforce_rbc

        Parameters
        ----------
        ptcls: :class:`sarkas.particles.Particles`
            Particles data.

        """

        enforce_rbc(ptcls.pos, ptcls.vel, self.box_lengths, self.dt)

    def pretty_print(self, potential_type: str, restart: str, restart_step: int):
        """Print integrator attributes in a user friendly way."""
        print("\nINTEGRATOR: ")
        if self.magnetized and self.electrostatic_equilibration:
            print("Type: {}".format(self.magnetic_integrator.__name__))
        else:
            print("Type: {}".format(self.type))

        if potential_type in ["yukawa", "egs", "coulomb", "moliere"]:
            wp_tot = norm(self.species_plasma_frequencies)
            wp_dt = wp_tot * self.dt
            print("Time step = {:.6e} [s]".format(self.dt))
            print("Total plasma frequency = {:.6e} [rad/s]".format(wp_tot))
            print("w_p dt = {:.4f} ~ 1/{}".format(wp_dt, int(1.0 / wp_dt)))
            if self.magnetized:
                high_wc_dt = abs(self.species_cyclotron_frequencies).max() * self.dt
                low_wc_dt = abs(self.species_cyclotron_frequencies).min() * self.dt

                if high_wc_dt > low_wc_dt:
                    print("Highest w_c dt = {:2.4f} = {:.4f} pi".format(high_wc_dt, high_wc_dt / pi))
                    print("Smallest w_c dt = {:2.4f} = {:.4f} pi".format(low_wc_dt, low_wc_dt / pi))
                else:
                    print("w_c dt = {:2.4f} = {:.4f} pi".format(high_wc_dt, high_wc_dt / pi))
        elif potential_type == "qsp":
            wp_tot = norm(self.species_plasma_frequencies)
            wp_ions = norm(self.species_plasma_frequencies[1:])
            wp_dt = wp_tot * self.dt
            print("Time step = {:.6e} [s]".format(self.dt))
            print("Total plasma frequency = {:.6e} [rad/s]".format(wp_tot))
            print("w_p dt = {:.4f} ~ 1/{}".format(wp_dt, int(1.0 / wp_dt)))

            print("e plasma frequency = {:.6e} [rad/s]".format(self.species_plasma_frequencies[0]))
            print("total ion plasma frequency = {:.6e} [rad/s]".format(wp_ions))
            print(
                "w_pe dt = {:2.4f} ~ 1/{}".format(
                    self.dt * self.species_plasma_frequencies[0],
                    int(1.0 / (self.dt * self.species_plasma_frequencies[0])),
                )
            )
            print("w_pi dt = {:2.4f} ~ 1/{}".format(self.dt * wp_ions, int(1.0 / (self.dt * wp_ions))))

            if self.magnetized:
                high_wc_dt = abs(self.species_cyclotron_frequencies[0]).max() * self.dt
                low_wc_dt = norm(self.species_cyclotron_frequencies[1:]) * self.dt
                print("e cyclotron frequency = {:.6e} [rad/s]".format(self.species_cyclotron_frequencies[0]))
                print(
                    "total ion cyclotron frequency = {:.6e} [rad/s]".format(norm(self.species_cyclotron_frequencies[1:]))
                )

                print("w_ce dt = {:2.4f} = {:.4f} pi".format(high_wc_dt, high_wc_dt / pi))
                print("w_ci dt = {:2.4f} = {:.4f} pi".format(low_wc_dt, low_wc_dt / pi))
        elif potential_type == "lj":
            wp_tot = norm(self.species_plasma_frequencies)
            wp_dt = wp_tot * self.dt
            print("Time step = {:.6e} [s]".format(self.dt))
            print("w_p = sqrt( epsilon / (sigma^2 * mass) )")
            print("Total equivalent plasma frequency = {:1.6e} [rad/s]".format(wp_tot))
            print("w_p dt = {:2.4f}".format(wp_dt))
            if self.magnetized:
                high_wc_dt = abs(self.species_cyclotron_frequencies).max() * self.dt
                low_wc_dt = abs(self.species_cyclotron_frequencies).min() * self.dt

                if high_wc_dt > low_wc_dt:
                    print("Highest w_c dt = {:2.4f} = {:.4f} pi".format(high_wc_dt, high_wc_dt / pi))
                    print("Smallest w_c dt = {:2.4f} = {:.4f} pi".format(low_wc_dt, low_wc_dt / pi))
                else:
                    print("w_c dt = {:2.4f} = {:.4f} pi".format(high_wc_dt, high_wc_dt / pi))
        elif potential_type == "hs_yukawa":
            wp_tot = norm(self.species_plasma_frequencies)
            wp_dt = wp_tot * self.dt
            print("Time step = {:.6e} [s]".format(self.dt))
            print("Total plasma frequency = {:1.6e} [rad/s]".format(wp_tot))
            print("w_p dt = {:.4f} ~ 1/{}".format(wp_dt, int(1.0 / wp_dt)))
            if self.magnetized:
                high_wc_dt = abs(self.species_cyclotron_frequencies).max() * self.dt
                low_wc_dt = abs(self.species_cyclotron_frequencies).min() * self.dt

                if high_wc_dt > low_wc_dt:
                    print("Highest w_c dt = {:2.4f} = {:.4f} pi".format(high_wc_dt, high_wc_dt / pi))
                    print("Smallest w_c dt = {:2.4f} = {:.4f} pi".format(low_wc_dt, low_wc_dt / pi))
                else:
                    print("w_c dt = {:2.4f} = {:.4f} pi".format(high_wc_dt, high_wc_dt / pi))

        # Print Time steps information
        # Check for restart simulations
        if restart in ["production_restart", "prod_restart"]:
            print("Restart step: {}".format(restart_step))
            print(
                "Total production steps = {} \n"
                "Total production time = {:.4e} [s] ~ {} w_p T_prod ".format(
                    self.production_steps, self.production_steps * self.dt, int(self.production_steps * wp_dt)
                )
            )
            print(
                "snapshot interval step = {} \n"
                "snapshot interval time = {:.4e} [s] = {:.4f} w_p T_snap".format(
                    self.prod_dump_step, self.prod_dump_step * self.dt, self.prod_dump_step * wp_dt
                )
            )
            print("Total number of snapshots = {} ".format(int(self.production_steps / self.prod_dump_step)))

        elif restart in ["equilibration_restart", "eq_restart"]:
            print("Restart step: {}".format(restart_step))
            print(
                "Total equilibration steps = {} \n"
                "Total equilibration time = {:.4e} [s] ~ {} w_p T_eq".format(
                    self.equilibration_steps, self.equilibration_steps * self.dt, int(self.eq_dump_step * wp_dt)
                )
            )
            print(
                "snapshot interval step = {} \n"
                "snapshot interval time = {:.4e} [s] = {:.4f} w_p T_snap".format(
                    self.eq_dump_step, self.eq_dump_step * self.dt, self.eq_dump_step * wp_dt
                )
            )
            print("Total number of snapshots = {} ".format(int(self.equilibration_steps / self.eq_dump_step)))

        elif restart in ["magnetization_restart", "mag_restart"]:
            print("Restart step: {}".format(restart_step))
            print(
                "Total magnetization steps = {} \n"
                "Total magnetization time = {:.4e} [s] ~ {} w_p T_mag".format(
                    self.magnetization_steps, self.magnetization_steps * self.dt, int(self.mag_dump_step * wp_dt)
                )
            )
            print(
                "snapshot interval step = {} \n"
                "snapshot interval time = {:.4e} [s] ~ {:.4f} w_p T_snap".format(
                    self.mag_dump_step, self.mag_dump_step * self.dt, self.mag_dump_step * wp_dt
                )
            )
            print("Total number of snapshots = {} ".format(int(self.magnetization_steps / self.mag_dump_step)))

        else:
            # Equilibration
            print(
                "\nEquilibration: \nNo. of equilibration steps = {} \n"
                "Total equilibration time = {:.4e} [s] ~ {} w_p T_eq ".format(
                    self.equilibration_steps, self.equilibration_steps * self.dt, int(self.equilibration_steps * wp_dt)
                )
            )
            print(
                "snapshot interval step = {} \n"
                "snapshot interval time = {:.4e} [s] = {:.4f} w_p T_snap".format(
                    self.eq_dump_step, self.eq_dump_step * self.dt, self.eq_dump_step * wp_dt
                )
            )
            print("Total number of snapshots = {} ".format(int(self.equilibration_steps / self.eq_dump_step)))

            # Magnetization
            if self.electrostatic_equilibration:
                print("Electrostatic Equilibration Type: {}".format(self.type))

                print(
                    "\nMagnetization: \nNo. of magnetization steps = {} \n"
                    "Total magnetization time = {:.4e} [s] ~ {} w_p T_mag ".format(
                        self.magnetization_steps,
                        self.magnetization_steps * self.dt,
                        int(self.magnetization_steps * wp_dt),
                    )
                )

                print(
                    "snapshot interval step = {} \n"
                    "snapshot interval time = {:.4e} [s] = {:.4f} w_p T_snap".format(
                        self.mag_dump_step, self.mag_dump_step * self.dt, self.mag_dump_step * wp_dt
                    )
                )
                print("Total number of snapshots = {} ".format(int(self.magnetization_steps / self.mag_dump_step)))
            # Production
            print(
                "\nProduction: \nNo. of production steps = {} \n"
                "Total production time = {:.4e} [s] ~ {} w_p T_prod ".format(
                    self.production_steps, self.production_steps * self.dt, int(self.production_steps * wp_dt)
                )
            )
            print(
                "snapshot interval step = {} \n"
                "snapshot interval time = {:.4e} [s] = {:.4f} w_p T_snap".format(
                    self.prod_dump_step, self.prod_dump_step * self.dt, self.prod_dump_step * wp_dt
                )
            )
            print("Total number of snapshots = {} ".format(int(self.production_steps / self.prod_dump_step)))


@jit(void(float64[:, :], float64[:, :], float64[:]), nopython=True)
def enforce_pbc(pos, cntr, box_vector) -> None:
    """
    Numba'd function to enforce periodic boundary conditions.

    Parameters
    ----------
    pos : numpy.ndarray
        Particles' positions.

    cntr : numpy.ndarray
        Counter for the number of times each particle get folded back into the main simulation box

    box_vector : numpy.ndarray
        Box Dimensions.

    """

    # Loop over all particles
    for p in arange(pos.shape[0]):
        for d in arange(pos.shape[1]):

            # If particle is outside of box in positive direction, wrap to negative side
            if pos[p, d] > box_vector[d]:
                pos[p, d] -= box_vector[d]
                cntr[p, d] += 1
            # If particle is outside of box in negative direction, wrap to positive side
            if pos[p, d] < 0.0:
                pos[p, d] += box_vector[d]
                cntr[p, d] -= 1


@jit(void(float64[:, :], float64[:, :], float64[:, :], float64[:], float64[:]), nopython=True)
def enforce_abc(pos, vel, acc, charges, box_vector) -> None:
    """
    Numba'd function to enforce absorbing boundary conditions.

    Parameters
    ----------
    pos: numpy.ndarray
        Particles' positions.

    vel : numpy.ndarray
        Particles' velocities.

    acc : numpy.ndarray
        Particles' accelerations.

    charges : numpy.ndarray
        Charge of each particle. Shape = (``total_num_ptcls``).

    box_vector: numpy.ndarray
        Box Dimensions.

    """

    # Loop over all particles
    for p in arange(pos.shape[0]):
        for d in arange(pos.shape[1]):

            # If particle is outside of box in positive direction, remove charge, velocity and acceleration
            if pos[p, d] >= box_vector[d]:
                pos[p, d] = box_vector[d]
                vel[p, :] = zeros(3)
                acc[p, :] = zeros(3)
                charges[p] = 0.0
            # If particle is outside of box in negative direction, remove charge, velocity and acceleration
            if pos[p, d] <= 0.0:
                pos[p, d] = 0.0
                vel[p, :] = zeros(3)
                acc[p, :] = zeros(3)
                charges[p] = 0.0


@jit(void(float64[:, :], float64[:, :], float64[:], float64), nopython=True)
def enforce_rbc(pos, vel, box_vector, dt) -> None:
    """
    Numba'd function to enforce reflecting boundary conditions.

    Parameters
    ----------
    pos: numpy.ndarray
        Particles' positions.

    vel : numpy.ndarray
        Particles' velocities.

    box_vector: numpy.ndarray
        Box Dimensions.

    dt : float
        Timestep.

    """

    # Loop over all particles
    for p in arange(pos.shape[0]):
        for d in arange(pos.shape[1]):

            # If particle is outside of box in positive direction, wrap to negative side
            if pos[p, d] > box_vector[d] or pos[p, d] < 0.0:
                # Revert velocity
                vel[p, d] *= -1.0
                # Restore previous position assuming verlet algorithm
                pos[p, d] += vel[p, d] * dt


@jit(void(float64[:, :], int64[:], float64[:]), nopython=True)
def remove_drift(vel, nums, masses) -> None:
    """
    Numba'd function to enforce conservation of total linear momentum.
    It updates :attr:`sarkas.particles.Particles.vel`.

    Parameters
    ----------
    vel: numpy.ndarray
        Particles' velocities.

    nums: numpy.ndarray
        Number of particles of each species.

    masses: numpy.ndarray
        Mass of each species.

    """

    P = zeros((len(nums), vel.shape[1]))
    species_start = 0
    for ic in range(len(nums)):
        species_end = species_start + nums[ic]
        P[ic, :] = vel[species_start:species_end, :].sum(axis=0) * masses[ic]
        species_start = species_end

    if P.sum(axis=0).any() > 1e-40:
        # Remove tot momentum
        species_start = 0
        for ic in range(len(nums)):
            species_end = species_start + nums[ic]
            vel[species_start:species_end, :] -= P[ic, :] / (float(nums[ic]) * masses[ic])
            species_start = species_end
