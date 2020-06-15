"""
Module for calculating physical quantities from Sarkas checkpoints.
"""
import os
import numpy as np
import numba as nb
import pandas as pd
import matplotlib.pyplot as plt
import time as tme
from tqdm import tqdm

LW = 2
FSZ = 14
MSZ = 8


class Thermodynamics:
    """
    Thermodynamic functions.

    Attributes
    ----------
        a_ws : float
            Wigner-Seitz radius.

        box_volume: float
            Box Volume

        dataframe : pandas dataframe
            It contains all the thermodynamics functions.
            options: "Total Energy", "Potential Energy", "Kinetic Energy", "Temperature", "time", "Pressure",
                    "Pressure Tensor ACF", "Pressure Tensor", "Gamma", "{species name} Temperature",
                    "{species name} Kinetic Energy".

        dump_step : int
            Dump step frequency.

        filename_output: str
            Name of the energy output file.

        filename_csv : str
            Name of csv output file.

        fldr : str
            Folder containing dumps.

        eV2K : float
            Conversion factor from eV to Kelvin.

        no_dim : int
            Number of non-zero dimensions.

        no_dumps : int
            Number of dumps.

        no_species : int
            Number of species.

        species_np: array
            Array of integers with the number of particles for each species.

        species_names : list
            Names of particle species.

        species_masses : list
            Names of particle species.

        tot_no_ptcls : int
            Total number of particles.

        wp : float
            Plasma frequency.

        kB : float
            Boltzmann constant.

    """

    def __init__(self, params):
        self.fldr = params.Control.checkpoint_dir
        self.fname_app = params.Control.fname_app
        self.dump_step = params.Control.dump_step
        self.no_dumps = int(params.Control.Nsteps / params.Control.dump_step)
        self.no_dim = params.dimensions
        if params.load_method == "restart":
            self.restart_sim = True
        else:
            self.restart_sim = False
        self.box_lengths = params.Lv
        self.box_volume = params.box_volume
        self.tot_no_ptcls = params.total_num_ptcls

        self.no_species = len(params.species)
        self.species_np = np.zeros(self.no_species)
        self.species_names = []
        self.species_masses = np.zeros(self.no_species)
        self.species_dens = np.zeros(self.no_species)
        for i in range(self.no_species):
            self.species_np[i] = params.species[i].num
            self.species_names.append(params.species[i].name)
            self.species_masses[i] = params.species[i].mass
            self.species_dens[i] = params.species[i].num_density
        # Output file with Energy and Temperature
        self.filename_csv = os.path.join(self.fldr, "Thermodynamics_" + self.fname_app + '.csv')
        # Constants
        self.wp = params.wp
        self.kB = params.kB
        self.eV2K = params.eV2K
        self.a_ws = params.aws
        self.T = params.T_desired
        self.Gamma_eff = params.Potential.Gamma_eff

    def compute_pressure_quantities(self):
        """
        Calculate Pressure, Pressure Tensor, Pressure Tensor Auto Correlation Function.
        """
        pos = np.zeros((self.no_dim, self.tot_no_ptcls))
        vel = np.zeros((self.no_dim, self.tot_no_ptcls))
        acc = np.zeros((self.no_dim, self.tot_no_ptcls))

        pressure = np.zeros(self.no_dumps)
        pressure_tensor_temp = np.zeros((3, 3, self.no_dumps))

        # Collect particles' positions, velocities and accelerations
        for it in range(int(self.no_dumps)):
            dump = int(it * self.dump_step)

            data = load_from_restart(self.fldr, dump)
            pos[0, :] = data["pos"][:, 0]
            pos[1, :] = data["pos"][:, 1]
            pos[2, :] = data["pos"][:, 2]

            vel[0, :] = data["vel"][:, 0]
            vel[1, :] = data["vel"][:, 1]
            vel[2, :] = data["vel"][:, 2]

            acc[0, :] = data["acc"][:, 0]
            acc[1, :] = data["acc"][:, 1]
            acc[2, :] = data["acc"][:, 2]

            pressure[it], pressure_tensor_temp[:, :, it] = calc_pressure_tensor(pos, vel, acc, self.species_masses,
                                                                                self.species_np, self.box_volume)

        self.dataframe["Pressure"] = pressure

        if self.no_dim == 3:
            dim_lbl = ['X', 'Y', 'Z']

        # Calculate the acf of the pressure tensor
        for i in range(self.no_dim):
            for j in range(self.no_dim):
                self.dataframe["Pressure Tensor {}{}".format(dim_lbl[i], dim_lbl[j])] = pressure_tensor_temp[i, j, :]
                pressure_tensor_acf_temp = autocorrelationfunction_1D(pressure_tensor_temp[i, j, :])
                self.dataframe["Pressure Tensor ACF {}{}".format(dim_lbl[i], dim_lbl[j])] = pressure_tensor_acf_temp / \
                                                                                            pressure_tensor_acf_temp[0]

        # Save the pressure acf to file
        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

        return

    def compute_pressure_from_rdf(self, r, gr, potential, potential_matrix):
        """
        Calculate the Pressure using the radial distribution function

        Parameters
        ----------
        r : array
            Particles' distances.

        gr : array
            Pair distribution function.

        Returns
        -------
        pressure : float
            Pressure divided by :math:`k_BT`.
        """
        r *= self.a_ws
        r2 = r * r
        r3 = r2 * r

        if potential == "Coulomb":
            dv_dr = - 1.0 / r2
            # Check for finiteness of first element when r[0] = 0.0
            if not np.isfinite(dv_dr[0]):
                dv_dr[0] = dv_dr[1]
        elif potential == "Yukawa":
            pass
        elif potential == "QSP":
            pass
        else:
            raise ValueError('Unknown potential')

        # No. of independent g(r)
        T = np.mean(self.dataframe["Temperature"])
        pressure = self.kB * T - 2.0 / 3.0 * np.pi * self.species_dens[0] \
                   * potential_matrix[1, 0, 0] * np.trapz(dv_dr * r3 * gr, x=r)
        pressure *= self.species_dens[0]

        return pressure

    def plot(self, quantity="Total Energy", delta=True, show=False):
        """
        Plot `quantity` vs time and save the figure with appropriate name.

        Parameters
        ----------
        show
        quantity : str
            Quantity to plot. Default = Total Energy.

        delta : bool
            Flag for plotting relative difference of `quantity`. Default = True.

        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)

        if quantity[:8] == "Pressure":
            if not "Pressure" in self.dataframe.columns:
                print("Calculating Pressure quantities ...")
                self.compute_pressure_quantities()

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        ylbl = {}
        ylbl["Total Energy"] = r"$E_{tot}(t)$"
        ylbl["Kinetic Energy"] = r"$K_{tot}(t)$"
        ylbl["Potential Energy"] = r"$U_{tot}(t)$"
        ylbl["Temperature"] = r"$T(t)$"
        ylbl[
            "Pressure Tensor ACF"] = r'$P_{\alpha\beta} = \langle P_{\alpha\beta}(0)P_{\alpha\beta}(t)\rangle$'
        ylbl["Pressure Tensor"] = r"$P_{\alpha\beta}(t)$"
        ylbl["Gamma"] = r"$\Gamma(t)$"
        ylbl["Pressure"] = r"$P(t)$"
        dim_lbl = ['X', 'Y', 'Z']

        if quantity == "Pressure Tensor ACF":
            for i in range(self.no_dim):
                for j in range(self.no_dim):
                    ax.plot(self.dataframe["Time"] * self.wp,
                            self.dataframe["Pressure Tensor ACF {}{}".format(dim_lbl[i], dim_lbl[j])],
                            lw=LW, label=r'$P_{' + dim_lbl[i] + dim_lbl[j] + '} (t)$')
            ax.set_xscale('log')
            ax.legend(loc='best', ncol=3, fontsize=FSZ)
            ax.set_ylim(-1, 1.5)

        elif quantity == "Pressure Tensor":
            for i in range(self.no_dim):
                for j in range(self.no_dim):
                    ax.plot(self.dataframe["Time"] * self.wp,
                            self.dataframe["Pressure Tensor {}{}".format(dim_lbl[i], dim_lbl[j])],
                            lw=LW, label=r'$P_{' + dim_lbl[i] + dim_lbl[j] + '} (t)$')
            ax.set_xscale('log')
            ax.legend(loc='best', ncol=3, fontsize=FSZ)

        else:
            if delta:
                delta = (self.dataframe[quantity] - self.dataframe[quantity][0]) / self.dataframe[quantity][0]
                delta[0] = delta[1]
                ax.plot(self.dataframe["Time"] * self.wp, delta, lw=LW)
                ylbl[quantity] = r"$\Delta$" + ylbl[quantity] + '$/$' + ylbl[quantity][:-4] + "(0)$"
                ax.set_ylabel(ylbl[quantity], fontsize=FSZ)
            else:
                ax.plot(self.dataframe["Time"] * self.wp, self.dataframe[quantity], lw=LW)

        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=FSZ)
        ax.set_ylabel(ylbl[quantity], fontsize=FSZ)
        ax.set_xlabel(r'$\omega_p t$', fontsize=FSZ)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, quantity + '_' + self.fname_app + '.png'))
        if show:
            fig.show()

    def parse(self):
        """
        Parse Thermodynamics functions from saved csv file.
        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)


class ElectricCurrent:
    """
    Electric Current Auto-correlation function.

    Attributes
    ----------
        a_ws : float
            Wigner-Seitz radius.

        wp : float
            Total plasma frequency.

        dump_step : int
            Dump step frequency.

        dt : float
            Timestep magnitude.

        filename: str
            Name of output files.

        fldr : str
            Folder containing dumps.

        no_dumps : int
            Number of dumps.

        no_species : int
            Number of species.

        species_np: array
            Array of integers with the number of particles for each species.

        species_charge: array
            Array of with the charge of each species.

        species_names : list
            Names of particle species.

        tot_no_ptcls : int
            Total number of particles.
    """

    def __init__(self, params):
        self.fldr = params.Control.checkpoint_dir
        self.fname_app = params.Control.fname_app
        self.filename_csv = os.path.join(self.fldr, "ElectricCurrent_" + self.fname_app + '.csv')
        self.dump_step = params.Control.dump_step
        self.no_dumps = int(params.Control.Nsteps / params.Control.dump_step)
        self.no_species = len(params.species)
        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_names = []
        self.dt = params.Control.dt  # No of dump to skip
        self.species_charge = np.zeros(self.no_species)
        for i in range(self.no_species):
            self.species_np[i] = int(params.species[i].num)
            self.species_charge[i] = params.species[i].charge
            self.species_names.append(params.species[i].name)

        self.tot_no_ptcls = params.total_num_ptcls
        self.wp = params.wp
        self.a_ws = params.aws
        self.dt = params.Control.dt

    def parse(self):
        """
        Parse Electric functions from csv file if found otherwise compute them.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            data = {"Time": self.time}
            self.dataframe = pd.DataFrame(data)
            self.compute()

    def compute(self):
        """
        Compute the electric current and the corresponding auto-correlation functions.
        """

        # Parse the particles from the dump files
        vel = np.zeros((self.no_dumps, 3, self.tot_no_ptcls))
        #
        print("Parsing particles' velocities.")
        time = np.zeros(self.no_dumps)
        for it in tqdm(range(self.no_dumps)):
            dump = int(it * self.dump_step)
            time[it] = dump * self.dt
            datap = load_from_restart(self.fldr, dump)
            vel[it, 0, :] = datap["vel"][:, 0]
            vel[it, 1, :] = datap["vel"][:, 1]
            vel[it, 2, :] = datap["vel"][:, 2]
        #
        print("Calculating Electric current quantities.")
        species_current, total_current = calc_elec_current(vel, self.species_charge, self.species_np)
        data_dic = {"Time": time}
        self.dataframe = pd.DataFrame(data_dic)

        self.dataframe["Total Current X"] = total_current[0, :]
        self.dataframe["Total Current Y"] = total_current[1, :]
        self.dataframe["Total Current Z"] = total_current[2, :]

        cur_acf_xx = autocorrelationfunction_1D(total_current[0, :])
        cur_acf_yy = autocorrelationfunction_1D(total_current[1, :])
        cur_acf_zz = autocorrelationfunction_1D(total_current[2, :])

        tot_cur_acf = autocorrelationfunction(total_current)
        # Normalize and save
        self.dataframe["X Current ACF"] = cur_acf_xx / cur_acf_xx[0]
        self.dataframe["Y Current ACF"] = cur_acf_yy / cur_acf_yy[0]
        self.dataframe["Z Current ACF"] = cur_acf_zz / cur_acf_zz[0]
        self.dataframe["Total Current ACF"] = tot_cur_acf / tot_cur_acf[0]
        for sp in range(self.no_species):
            tot_acf = autocorrelationfunction(species_current[sp, :, :])
            acf_xx = autocorrelationfunction_1D(species_current[sp, 0, :])
            acf_yy = autocorrelationfunction_1D(species_current[sp, 1, :])
            acf_zz = autocorrelationfunction_1D(species_current[sp, 2, :])

            self.dataframe["{} Total Current".format(self.species_names[sp])] = np.sqrt(
                species_current[sp, 0, :] ** 2 + species_current[sp, 1, :] ** 2 + species_current[sp, 2, :] ** 2)
            self.dataframe["{} X Current".format(self.species_names[sp])] = species_current[sp, 0, :]
            self.dataframe["{} Y Current".format(self.species_names[sp])] = species_current[sp, 1, :]
            self.dataframe["{} Z Current".format(self.species_names[sp])] = species_current[sp, 2, :]

            self.dataframe["{} Total Current ACF".format(self.species_names[sp])] = tot_acf / tot_acf[0]
            self.dataframe["{} X Current ACF".format(self.species_names[sp])] = acf_xx / acf_xx[0]
            self.dataframe["{} Y Current ACF".format(self.species_names[sp])] = acf_yy / acf_yy[0]
            self.dataframe["{} Z Current ACF".format(self.species_names[sp])] = acf_zz / acf_zz[0]

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')
        return

    def plot(self, show=False):
        """
        Plot the electric current autocorrelation function and save the figure.
        """

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        ax.plot(self.dataframe["Time"] * self.wp, self.dataframe["Total Current ACF"], lw=LW,
                label=r'$J_{tot} (t)$')

        if self.no_species > 1:
            for i in range(self.no_species):
                ax.plot(self.dataframe["Time"] * self.wp,
                        self.dataframe["{} Total Current ACF".format(self.species_names[i])],
                        lw=LW, label=r'$J_{' + self.species_names[i] + '} (t)$')

        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize=FSZ)
        ax.tick_params(labelsize=FSZ)
        ax.set_ylabel(r'$J(t)$', fontsize=FSZ)
        ax.set_xlabel(r'$\omega_p t$', fontsize=FSZ)
        ax.set_xscale('log')
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'TotalCurrentACF_' + self.fname_app + '.png'))
        if show:
            fig.show()


class XYZFile:
    """
    Write the XYZ file for OVITO visualization.

    Attributes
    ----------
        a_ws : float
            Wigner-Seitz radius. Used for rescaling.

        dump_skip : int
            Dump step interval.

        dump_step : int
            Dump step frequency.

        filename: str
            Name of output files.

        fldr : str
            Folder containing dumps.

        no_dumps : int
            Number of dumps.

        tot_no_ptcls : int
            Total number of particles.

        wp : float
            Plasma frequency used for rescaling.
    """

    def __init__(self, params):
        self.fldr = params.Control.checkpoint_dir
        self.filename = os.path.join(self.fldr, "pva_" + params.Control.fname_app + '.xyz')
        self.dump_step = params.Control.dump_step
        self.no_dumps = int(params.Control.Nsteps / params.Control.dump_step)
        self.dump_skip = 1
        self.tot_no_ptcls = params.total_num_ptcls

        self.a_ws = params.aws
        self.wp = params.wp

    def save(self, dump_skip=1):
        """
        Save the XYZ file by reading Sarkas dumps.

        Parameters
        ----------
        dump_skip : int
            Interval of dumps to skip. Default = 1

        """

        self.dump_skip = dump_skip
        f_xyz = open(self.filename, "w+")

        # Rescale constants. This is needed since OVITO has a small number limit.
        pscale = 1.0 / self.aws
        vscale = 1.0 / (self.aws * self.wp)
        ascale = 1.0 / (self.aws * self.wp ** 2)

        for it in range(int(self.no_dumps / self.dump_skip)):
            dump = int(it * self.dump_step * self.dump_skip)

            data = load_from_restart(self.fldr, dump)

            f_xyz.writelines("{0:d}\n".format(self.tot_no_ptcls))
            f_xyz.writelines("name x y z vx vy vz ax ay az\n")
            np.savetxt(f_xyz,
                       np.c_[data["species_name"], data["pos"] * pscale, data["vel"] * vscale, data["acc"] * ascale],
                       fmt="%s %.6e %.6e %.6e %.6e %.6e %.6e %.6e %.6e %.6e")

        f_xyz.close()


class StaticStructureFactor:
    """ Static Structure Factors :math:`S_{ij}(k)`.

    Attributes
    ----------
        a_ws : float
            Wigner-Seitz radius.

        box_lengths : array
            Array with box length in each direction.

        dataframe : dict
            Pandas dataframe. It contains all the :math:`S_{ij}(k)` and :math:`ka_values`.

        dump_step : int
            Dump step frequency.

        filename_csv: str
            Name of output files.

        fname_app: str
            Appendix of filenames.

        fldr : str
            Folder containing dumps.

        ka_min : float
            Smallest possible (non-dimensional) wavenumber :math:`ka = 2\pi/L`.

        no_dumps : int
            Number of dumps.

        no_ka : int
            Number of integer multiples of minimum :math:`ka` value

        no_species : int
            Number of species.

        no_Sk : int
            Number of :math: `S_{ij}(k)` pairs.

        species_np: array
            Array of integers with the number of particles for each species.

        species_names : list
            Names of particle species.

        tot_no_ptcls : int
            Total number of particles.
        """

    def __init__(self, params):

        self.fldr = params.Control.checkpoint_dir
        self.fname_app = params.Control.fname_app
        self.ptcls_fldr = params.Control.dump_dir
        self.k_fldr = os.path.join(self.fldr, "k_space_data")
        self.k_file = os.path.join(self.k_fldr, "k_arrays.npz")
        self.nkt_file = os.path.join(self.k_fldr, "nkt.npy")

        self.filename_csv = os.path.join(self.fldr, "StaticStructureFunction_" + self.fname_app + ".csv")
        self.dump_step = params.Control.dump_step
        self.no_dumps = int(params.Control.Nsteps / params.Control.dump_step)
        self.no_species = len(params.species)
        self.tot_no_ptcls = params.total_num_ptcls

        if len(params.PostProcessing.ssf_no_ka_values) == 0:
            self.no_ka = np.array([params.PostProcessing.ssf_no_ka_values,
                                   params.PostProcessing.ssf_no_ka_values,
                                   params.PostProcessing.ssf_no_ka_values], dtype=int)
        else:
            self.no_ka = params.PostProcessing.ssf_no_ka_values  # number of ka values

        self.no_Sk = int(self.no_species * (self.no_species + 1) / 2)
        self.a_ws = params.aws
        self.box_lengths = np.array([params.Lx, params.Ly, params.Lz])
        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_names = []

        for i in range(self.no_species):
            self.species_np[i] = params.species[i].num
            self.species_names.append(params.species[i].name)

    def parse(self):
        """
        Read the Radial distribution function from the saved csv file.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            print("\nError: {} not found!".format(self.filename_csv))
        return

    def compute(self):
        """
        Calculate all :math:`S_{ij}(k)`, save them into a Pandas dataframe, and write them to a csv.

        Parameters
        ----------
        principal_axis : bool
            Flag to calculate :math:`S_{ij}(k)` only along the principal cartesian direction :math:`X, Y, Z`.

        """
        # Dev Note: The first index is the value of ka,
        # The second index indicates S_ij
        # The third index indicates S_ij(t)

        # Parse the particles from the dump files

        # Parse nkt otherwise calculate it
        try:
            nkt = np.load(self.nkt_file)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)
            print("n(k,t) Loaded")
        except FileNotFoundError:
            self.k_list, self.k_counts, k_unique = kspace_setup(self.no_ka, self.box_lengths)
            self.ka_values = 2.0 * np.pi * k_unique * self.a_ws
            self.no_ka_values = len(self.ka_values)

            if not (os.path.exists(self.k_fldr)):
                os.mkdir(self.k_fldr)

            np.savez(self.k_file,
                     k_list=self.k_list,
                     k_counts=self.k_counts,
                     ka_values=self.ka_values)

            nkt = calc_nkt(self.ptcls_fldr, self.no_dumps, self.dump_step, self.species_np, self.k_list)
            np.save(self.nkt_file, nkt)

        data = {"ka values": self.ka_values}
        self.dataframe = pd.DataFrame(data)

        start = tme.time()
        print("Calculating S(k) ...")
        Sk_all = calc_Sk_multi(nkt, self.k_list, self.k_counts, self.species_np, self.no_dumps)
        end = tme.time()
        print('Elapsed time = ', (end - start))
        Sk = np.mean(Sk_all, axis=-1)
        Sk_err = np.std(Sk_all, axis=-1)

        sp_indx = 0
        for sp_i in range(self.no_species):
            for sp_j in range(sp_i, self.no_species):
                column = "{}-{} SSF".format(self.species_names[sp_i], self.species_names[sp_j])
                err_column = "{}-{} SSF Errorbar".format(self.species_names[sp_i], self.species_names[sp_j])
                self.dataframe[column] = Sk[sp_indx, :]
                self.dataframe[err_column] = Sk_err[sp_indx, :]

                sp_indx += 1

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

        return

    def plot(self, errorbars=False, show=False):
        """
        Plot :math:`S_{ij}(k)` and save the figure.

        Parameters
        ----------
        show : bool
            Flag to prompt the figure to screen. Default=False.

        errorbars : bool
            Plot errorbars. Default = False.

        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        except FileNotFoundError:
            self.compute()

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        for i in range(self.no_species):
            for j in range(i, self.no_species):
                subscript = self.species_names[i] + self.species_names[j]
                if errorbars:
                    ax.errorbar(self.dataframe["ka values"],
                                self.dataframe["{}-{} SSF".format(self.species_names[i], self.species_names[j])],
                                yerr=self.dataframe[
                                    "{}-{} SSF Errorbar".format(self.species_names[i], self.species_names[j])],
                                lw=LW, ls='--', marker='o', ms=MSZ, label=r'$S_{ ' + subscript + '} (k)$')
                else:
                    ax.plot(self.dataframe["ka values"],
                            self.dataframe["{}-{} SSF".format(self.species_names[i], self.species_names[j])],
                            lw=LW, label=r'$S_{ ' + subscript + '} (k)$')

        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize=FSZ)
        ax.tick_params(labelsize=FSZ)
        ax.set_ylabel(r'$S(k)$', fontsize=FSZ)
        ax.set_xlabel(r'$ka$', fontsize=FSZ)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'StaticStructureFactor' + self.fname_app + '.png'))
        if show:
            fig.show()


class DynamicStructureFactor:
    """ Dynamic Structure factor.

    Attributes
    ----------
        a_ws : float
            Wigner-Seitz radius.

        dump_step : int
            Dump step frequency.

        filename: str
            Name of output files.

        fldr : str
            Folder containing dumps.

        ka_min : float
            Smallest possible (non-dimensional) wavenumber :math:`ka = 2\pi/L`.

        ka_max : float
            Largest possible (non-dimensional) wavenumber = ``no_ka * ka_min``

        no_dumps : int
            Number of dumps.

        no_ka : int
            Number of integer multiples of minimum :math:`ka` value

        no_species : int
            Number of species.

        species_np: array
            Array of integers with the number of particles for each species.

        dt : float
            Timestep's value normalized by the total plasma frequency.

        sp_names : list
            Names of particle species.

        tot_no_ptcls : int
            Total number of particles.

        """

    def __init__(self, params):

        self.fldr = params.Control.checkpoint_dir
        self.ptcls_fldr = params.Control.dump_dir
        self.k_fldr = os.path.join(self.fldr, "k_space_data")
        self.k_file = os.path.join(self.k_fldr, "k_arrays.npz")
        self.nkt_file = os.path.join(self.k_fldr, "nkt.npy")
        self.fname_app = params.Control.fname_app
        self.filename_csv = os.path.join(self.fldr, "DynamicStructureFactor_" + self.fname_app + '.csv')

        self.box_lengths = np.array([params.Lx, params.Ly, params.Lz])
        self.dump_step = params.Control.dump_step
        self.no_dumps = int(params.Control.Nsteps / params.Control.dump_step)
        self.no_species = len(params.species)
        self.tot_no_ptcls = params.total_num_ptcls

        self.species_np = np.zeros(self.no_species, dtype=int)
        self.species_names = []
        self.species_wp = np.zeros( self.no_species)
        for i in range(self.no_species):
            self.species_wp[i] = params.species[i].wp
            self.species_np[i] = int(params.species[i].num)
            self.species_names.append(params.species[i].name)

        self.Nsteps = params.Control.Nsteps
        self.dt = params.Control.dt
        self.no_Skw = int(self.no_species * (self.no_species + 1) / 2)
        self.a_ws = params.aws
        self.wp = params.wp

        # Create the lists of k vectors
        if len(params.PostProcessing.dsf_no_ka_values) == 0:
            self.no_ka = np.array([params.PostProcessing.dsf_no_ka_values,
                                   params.PostProcessing.dsf_no_ka_values,
                                   params.PostProcessing.dsf_no_ka_values], dtype=int)
        else:
            self.no_ka = params.PostProcessing.dsf_no_ka_values  # number of ka values

    def parse(self):
        """
        Read the Radial distribution function from the saved csv file.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]

        except FileNotFoundError:
            print("\nFile {} not found!".format(self.filename_csv))
            print("\nComputing DSF now")
            self.compute()
        return

    def compute(self):
        """
        Compute :math:`S_{ij}(k,\omega)' and the array of :math:`\omega/\omega_p` values.
        ``self.Skw``. Shape = (``no_ws``, ``no_Sij``)
        """

        data = {"Frequencies": 2.0 * np.pi * np.fft.fftfreq(self.no_dumps, self.dt * self.dump_step)}
        self.dataframe = pd.DataFrame(data)

        # Parse nkt otherwise calculate it
        try:
            nkt = np.load(self.nkt_file)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)
            print("Loaded")
            print(nkt.shape)
        except FileNotFoundError:
            self.k_list, self.k_counts, k_unique = kspace_setup(self.no_ka, self.box_lengths)
            self.ka_values = 2.0 * np.pi * k_unique * self.a_ws
            self.no_ka_values = len(self.ka_values)

            if not (os.path.exists(self.k_fldr)):
                os.mkdir(self.k_fldr)

            np.savez(self.k_file,
                     k_list=self.k_list,
                     k_counts=self.k_counts,
                     ka_values=self.ka_values)

            nkt = calc_nkt(self.ptcls_fldr, self.no_dumps, self.dump_step, self.species_np, self.k_list)
            np.save(self.nkt_file, nkt)

        # Calculate Skw
        Skw = calc_Skw(nkt, self.k_list, self.k_counts, self.species_np, self.no_dumps, self.dt, self.dump_step)
        print("Saving S(k,w)")
        sp_indx = 0
        for sp_i in range(self.no_species):
            for sp_j in range(sp_i, self.no_species):
                for ik in range(len(self.k_counts)):
                    if ik == 0:
                        column = "{}-{} DSF ka_min".format(self.species_names[sp_i], self.species_names[sp_j])
                    else:
                        column = "{}-{} DSF {} ka_min".format(self.species_names[sp_i],
                                                              self.species_names[sp_j], ik + 1)
                    self.dataframe[column] = Skw[sp_indx, ik, :]
                sp_indx += 1

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

        return

    def plot(self, show=False, dispersion=False):
        """
        Plot :math: `S(k,\omega)` and save the figure.
        """
        try:
            self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
            k_data = np.load(self.k_file)
            self.k_list = k_data["k_list"]
            self.k_counts = k_data["k_counts"]
            self.ka_values = k_data["ka_values"]
            self.no_ka_values = len(self.ka_values)
        except FileNotFoundError:
            print("Computing S(k,w)")
            self.compute()

        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        if self.no_species == 1:
            for sp_i in range(self.no_species):
                for sp_j in range(sp_i, self.no_species):
                    column = "{}-{} DSF ka_min".format(self.species_names[sp_i], self.species_names[sp_j])
                    ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.species_wp[0],
                            np.fft.fftshift(self.dataframe[column]), lw=LW,
                            label=r'$S_{' + self.species_names[sp_i] + self.species_names[sp_j] + '}(k,\omega)$')
        else:
            column = "{}-{} DSF ka_min".format(self.species_names[0], self.species_names[0])
            ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.species_wp[0],
                    np.fft.fftshift(self.dataframe[column]), lw=LW,
                    label=r'$ka = {:1.4f}$'.format(self.ka_values[0]))
            for i in range(1, 5):
                column = "{}-{} DSF {} ka_min".format(self.species_names[0], self.species_names[0], i + 1)
                ax.plot(np.fft.fftshift(self.dataframe["Frequencies"]) / self.wp,
                        np.fft.fftshift(self.dataframe[column]), lw=LW,
                        label=r'$ka = {:1.4f}$'.format(self.ka_values[i]))

        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', ncol=3, fontsize=FSZ)
        ax.tick_params(labelsize=FSZ)
        ax.set_yscale('log')
        ax.set_xlim(0, 3)
        ax.set_ylabel(r'$S(k,\omega)$', fontsize=FSZ)
        ax.set_xlabel(r'$\omega/\omega_p$', fontsize=FSZ)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'Skw_' + self.fname_app + '.png'))
        if show:
            fig.show()

        if dispersion:
            w_array = np.array(self.dataframe["Frequencies"]) / self.wp
            neg_indx = np.where(w_array < 0.0)[0][0]
            Skw = np.array(self.dataframe.iloc[:, 1:self.no_ka_values + 1])
            ka_vals, w = np.meshgrid(self.ka_values, w_array[: neg_indx])
            fig = plt.figure(figsize=(10, 7))
            plt.pcolor(ka_vals, w, Skw[: neg_indx, :], vmin=Skw[:, 1].min(), vmax=Skw[:, 1].max())
            cbar = plt.colorbar()
            cbar.set_ticks([])
            cbar.ax.tick_params(labelsize=FSZ - 2)
            plt.xlabel(r'$ka$', fontsize=FSZ)
            plt.ylabel(r'$\omega/\omega_p$', fontsize=FSZ)
            plt.ylim(0, 2)
            plt.tick_params(axis='both', which='major', labelsize=FSZ)
            plt.title("$S(k, \omega)$", fontsize=FSZ)
            fig.tight_layout()
            fig.savefig(os.path.join(self.fldr, 'Skw_Dispersion_' + self.fname_app + '.png'))
            if show:
                fig.show()


class RadialDistributionFunction:
    """
    Pair Distribution Function.

    Attributes
    ----------
        a_ws : float
            Wigner-Seitz radius.

        box_lengths : array
            Length of each side of the box.

        dataframe : dataframe
            Pandas dataframe containing the radial distribution functions.

        dump_step : int
            Dump step frequency.

        filename_csv: str
            Name of csv file containing the radial distribution functions.

        fname_app: str
            Appendix of file names.

        fldr : str
            Folder containing dumps.

        no_bins : int
            Number of bins.

        no_dumps : int
            Number of dumps.

        no_grs : int
            Number of :math: `g_{ij}(r)` pairs.

        no_species : int
            Number of species.

        species_np: array
            Array of integers with the number of particles for each species.

        species_names : list
            Names of particle species.

        tot_no_ptcls : int
            Total number of particles.

    """

    def __init__(self, params):
        self.no_bins = params.PostProcessing.rdf_nbins  # number of ka values
        self.fldr = params.Control.checkpoint_dir
        self.fname_app = params.Control.fname_app
        self.filename_csv = os.path.join(self.fldr, "RadialDistributionFunction_" + params.Control.fname_app + ".csv")
        self.dump_step = params.Control.dump_step
        self.no_dumps = int(params.Control.Nsteps / params.Control.dump_step)
        self.no_species = len(params.species)
        self.no_grs = int(params.num_species * (params.num_species + 1) / 2)
        self.tot_no_ptcls = params.total_num_ptcls

        self.no_steps = params.Control.Nsteps
        self.a_ws = params.aws
        self.dr_rdf = params.Potential.rc / self.no_bins / self.a_ws
        self.box_volume = params.box_volume / self.a_ws ** 3
        self.box_lengths = np.array([params.Lx / params.aws, params.Ly / params.aws, params.Lz / params.aws])
        self.species_np = np.zeros(self.no_species)  # Number of particles of each species
        self.species_names = []

        for i in range(self.no_species):
            self.species_np[i] = params.species[i].num
            self.species_names.append(params.species[i].name)

    def save(self, rdf_hist):
        """
        Parameters
        ----------
        rdf_hist : array
            Histogram of the radial distribution function.

        """
        # Initialize all the workhorse arrays
        ra_values = np.zeros(self.no_bins)
        bin_vol = np.zeros(self.no_bins)
        pair_density = np.zeros((self.no_species, self.no_species))
        gr = np.zeros((self.no_bins, self.no_grs))

        # No. of pairs per volume
        for i in range(self.no_species):
            pair_density[i, i] = self.species_np[i] * (self.species_np[i] - 1) / (2.0 * self.box_volume)
            for j in range(i + 1, self.no_species):
                pair_density[i, j] = self.species_np[i] * self.species_np[j] / self.box_volume
        # Calculate each bin's volume
        sphere_shell_const = 4.0 * np.pi / 3.0
        bin_vol[0] = sphere_shell_const * self.dr_rdf ** 3
        for ir in range(1, self.no_bins):
            r1 = ir * self.dr_rdf
            r2 = (ir + 1) * self.dr_rdf
            bin_vol[ir] = sphere_shell_const * (r2 ** 3 - r1 ** 3)
            ra_values[ir] = (ir + 0.5) * self.dr_rdf

        data = {"ra values": ra_values}
        self.dataframe = pd.DataFrame(data)

        gr_ij = 0
        for i in range(self.no_species):
            for j in range(i, self.no_species):
                if j == i:
                    pair_density[i, j] *= 2.0
                for ibin in range(self.no_bins):
                    gr[ibin, gr_ij] = (rdf_hist[ibin, i, j] + rdf_hist[ibin, j, i]) / (bin_vol[ibin]
                                                                                       * pair_density[i, j]
                                                                                       * self.no_steps)

                self.dataframe['{}-{} RDF'.format(self.species_names[i], self.species_names[j])] = gr[:, gr_ij]
                gr_ij += 1

        self.dataframe.to_csv(self.filename_csv, index=False, encoding='utf-8')

        return

    def parse(self):
        """
        Read the Radial distribution function from the saved csv file.
        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)
        return

    def plot(self, show=False):
        """
        Plot :math: `g_{ij}(r)` and save the figure.
        """
        self.dataframe = pd.read_csv(self.filename_csv, index_col=False)

        indx = 0
        fig, ax = plt.subplots(1, 1, figsize=(10, 7))
        for i in range(self.no_species):
            for j in range(i, self.no_species):
                subscript = self.species_names[i] + self.species_names[j]
                ax.plot(self.dataframe["ra values"],
                        self.dataframe["{}-{} RDF".format(self.species_names[i], self.species_names[j])],
                        lw=LW, label=r'$g_{' + subscript + '} (r)$')
                indx += 1
        ax.grid(True, alpha=0.3)
        if self.no_species > 2:
            ax.legend(loc='best', ncol=(self.no_species - 1), fontsize=FSZ)
        else:
            ax.legend(loc='best', fontsize=FSZ)

        ax.tick_params(labelsize=FSZ)
        ax.set_ylabel(r'$g(r)$', fontsize=FSZ)
        ax.set_xlabel(r'$r/a$', fontsize=FSZ)
        # ax.set_ylim(0, 5)
        fig.tight_layout()
        fig.savefig(os.path.join(self.fldr, 'RDF_' + self.fname_app + '.png'))
        if show:
            fig.show()
        return


class TransportCoefficients:
    """
    Transport Coefficients class

    Attributes
    ----------
    params : class
        Simulation parameters.
    """

    def __init__(self, params):
        self.params = params
        return

    def compute(self, quantity="Electrical Conductivity", tau=-1):
        """
        Calculate the desired transport coefficient

        Parameters
        ----------
        quantity: str
            Desired transport coefficient to calculate.

        tau: float
            Upper limit of time integration.

        Returns
        -------

        transport_coeff : float
            Desired transport coefficient value scaled by appropriate units

        """
        if quantity == "Electrical Conductivity":
            J = ElectricCurrent(self.params)
            J.plot(show=True)
            integrand = np.array(J.dataframe["Total Current ACF"])
            time = np.array(J.dataframe["Time"]) * self.params.wp
            if tau != -1:
                tau = np.where(time > tau)[0][0] - 1
            transport_coeff = np.trapz(integrand[:tau], x=time[:tau]) / (4.0 * np.pi)
            print("Electrical Conductivity = {:1.4e}/w_p".format(transport_coeff))
        return transport_coeff


def load_from_restart(fldr, it):
    """
    Load particles' data from checkpoints.

    Parameters
    ----------
    fldr : str
        Folder containing dumps.

    it : int
        Timestep.

    Returns
    -------
    data : dict
        Particles' data.
    """

    file_name = os.path.join(fldr, "S_checkpoint_" + str(it) + ".npz")
    data = np.load(file_name, allow_pickle=True)
    return data


def kspace_setup(no_ka, box_lengths):
    """
    Calculate all allowed :math:`k` vectors.

    Parameters
    ----------
    no_ka : array
        Number of harmonics in each direction.

    box_lengths : array
        Length of each box's side.

    Returns
    -------
    k_arr : list
        List of all possible :math:`k` vectors with their corresponding magnitudes and indexes.

    k_counts : array
        Number of occurrences of each :math:`k` magnitude.

    k_unique : array
        Magnitude of each allowed :math:`k` vector.
    """
    # Obtain all possible permutations of the wave number arrays
    k_arr = [np.array([i / box_lengths[0], j / box_lengths[1], k / box_lengths[2]]) for i in range(no_ka[0])
             for j in range(no_ka[1])
             for k in range(no_ka[2])]

    # Compute wave number magnitude - don't use |k| (skipping first entry in k_arr)
    k_mag = np.sqrt(np.sum(np.array(k_arr) ** 2, axis=1)[..., None])

    # Add magnitude to wave number array
    k_arr = np.concatenate((k_arr, k_mag), 1)

    # Sort from lowest to highest magnitude
    ind = np.argsort(k_arr[:, -1])
    k_arr = k_arr[ind]

    # Count how many times a |k| value appears
    k_unique, k_counts = np.unique(k_arr[1:, -1], return_counts=True)

    # Generate a 1D array containing index to be used in S array
    k_index = np.repeat(range(len(k_counts)), k_counts)[..., None]

    # Add index to k_array
    k_arr = np.concatenate((k_arr[1:, :], k_index), 1)
    return k_arr, k_counts, k_unique


@nb.njit
def calc_Sk_single(pos_data, ka_list, ka_counts, species_np, no_dumps):
    """
    Calculate :math:`S(k)`.

    Parameters
    ----------
    pos_data : ndarray
        Particles' position scaled by the box lengths. Shape = ( `no_dumps`, 3, `tot_no_ptcls')

    ka_list : list
        List of :math:`k` indices in each direction with corresponding magnitude and index of `ka_counts`.
        Shape=(`no_ka_values`, 5)

    ka_counts : array
        Number of times each :math:`k` magnitude appears.

    species_np : array
        Array with one element giving number of particles.

    no_dumps : int
        Number of dumps.

    Returns
    -------

    Sk : ndarray
        Array containing :math:`S(k)`. Shape=(`no_ka_values`, `no_dumps`)
    """
    num_ka_values = len(ka_counts)

    Sk = np.zeros((num_ka_values, no_dumps))

    # I don't know if this will cause problem with large numbers
    for it in range(no_dumps):
        for ik in range(ka_list.shape[0]):
            kr_i = (ka_list[ik][0] * pos_data[it, 0, :]
                    + ka_list[ik][1] * pos_data[it, 1, :]
                    + ka_list[ik][2] * pos_data[it, 2, :]) * 2.0 * np.pi

            nk_i = np.sum(np.exp(-1j * kr_i))
            indx = int(ka_list[ik][-1])

            Sk[indx, it] += np.abs(nk_i) ** 2 / (ka_counts[indx] * species_np[0])

    return Sk


@nb.njit
def calc_Sk_multi(nkt, ka_list, ka_counts, species_np, no_dumps):
    """
    Calculate all :math:`S_{ij}(k)`.

    Parameters
    ----------
    pos_data : ndarray
        Particles' position scaled by the box lengths. Shape = ( `no_dumps`, 3, `tot_no_ptcls')

    ka_list :
        List of :math:`k` indices in each direction with corresponding magnitude and index of `ka_counts`.
        Shape=(`no_ka_values`, 5)

    ka_counts : array
        Number of times each :math:`k` magnitude appears.

    species_np : array
        Array with number of particles of each species.

    no_dumps : int
        Number of dumps.

    Returns
    -------

    Sk_mat : ndarray
        Array containing :math:`S_{ij}(k)`. Shape=(`no_ka_values`, `no_sp`, `no_sp`, `no_dumps`)

    """

    no_sk = int(len(species_np) * (len(species_np) + 1) / 2)
    Sk_all = np.empty((no_sk, len(ka_counts), no_dumps))

    pair_indx = 0
    for ip, si in enumerate(species_np):
        for jp in range(ip, len(species_np)):
            sj = species_np[jp]
            for it in range(no_dumps):
                for ik, ka in enumerate(ka_list):
                    indx = int(ka[-1])
                    nk_i = nkt[ip, it, ik]
                    nk_j = nkt[jp, it, ik]
                Sk_all[pair_indx, indx, it] += np.real(np.conj(nk_i) * nk_j) / (ka_counts[indx] * np.sqrt(si * sj))
            pair_indx += 1

    return Sk_all


@nb.njit
def calc_Sk_single_pa(pos_data, ka_values, species_np, no_dumps):
    """
    Calculate :math: `S(k)` along principal axis only."

    Parameters
    ----------
    pos_data : array
        x - coordinate of all the particles.

    ka_values : array
        Array of :math: `ka` values.

    species_np : array
        Array with one element giving number of particles.

    no_dumps : int
        Number of saved checkpoints.

    Returns
    -------
    Sk : darray
        Static structure factor :math: `S_{ij}(k)`.
    """

    num_ka_values = len(ka_values)

    # Number of independent S_ij(k)  = no_sp*(no_sp + 1)/2

    # Dev Notes. I could not find a smart indexing way. So I went for the most fundamental one
    # Create a matrix of S_{ij}(k) and then add the off_diagonal together in the final Sk

    Sk = np.zeros((num_ka_values, no_dumps))

    for it in range(no_dumps):
        for (ik, ka) in enumerate(ka_values):
            krx_i = ka * pos_data[it, 0, :]
            kry_i = ka * pos_data[it, 1, :]
            krz_i = ka * pos_data[it, 2, :]

            nkx_i = np.sum(np.exp(-1j * krx_i))
            nky_i = np.sum(np.exp(-1j * kry_i))
            nkz_i = np.sum(np.exp(-1j * krz_i))

            Sk[ik, it] += (np.abs(nkx_i) ** 2 + np.abs(nky_i) ** 2 + np.abs(nkz_i) ** 2) / (3.0 * species_np[0])

    return Sk


@nb.njit
def calc_Sk_multi_pa(pos_data, ka_values, species_np, no_dumps):
    """
    Calculate all :math: `S_{ij}(k)` along the principal axis only."

    Parameters
    ----------
    pos_data : array
        x - coordinate of all the particles.

    ka_values : array
        Array of :math: `ka` values.

    species_np : array
        Array with only one element = number of particles for each species.

    no_dumps : int
        Number of saved checkpoints.

    Returns
    -------
    Sk : ndarray
        Static structure factors :math: `S_{ij}(k)`.
    """

    no_sp = len(species_np)
    num_ka_values = len(ka_values)

    # Dev Notes. I could not find a smart indexing way. So I went for the most fundamental one
    # Create a matrix of S_{ij}(k) and then add the off_diagonal together in the final Sk

    Sk_mat = np.zeros((num_ka_values, no_sp, no_sp, no_dumps))

    for it in range(no_dumps):
        for (ik, ka) in enumerate(ka_values):
            sp1_start = 0
            for i in range(no_sp):
                sp1_end = sp1_start + species_np[i]

                krx_i = ka * pos_data[it, 0, sp1_start:sp1_end]
                kry_i = ka * pos_data[it, 1, sp1_start:sp1_end]
                krz_i = ka * pos_data[it, 2, sp1_start:sp1_end]

                nkx_i = np.sum(np.exp(-1j * krx_i))
                nky_i = np.sum(np.exp(-1j * kry_i))
                nkz_i = np.sum(np.exp(-1j * krz_i))

                sp2_start = sp1_start
                for j in range(i, no_sp):
                    sp2_end = sp2_start + species_np[j]

                    krx_j = ka * pos_data[it, 0, sp2_start:sp2_end]
                    kry_j = ka * pos_data[it, 1, sp2_start:sp2_end]
                    krz_j = ka * pos_data[it, 2, sp2_start:sp2_end]

                    nkx_j = np.sum(np.exp(-1j * krx_j))
                    nky_j = np.sum(np.exp(-1j * kry_j))
                    nkz_j = np.sum(np.exp(-1j * krz_j))

                    Sk_mat[ik, i, j, it] += (np.real(nkx_i * nkx_j) + np.real(nky_i * nky_j) + np.real(nkz_i * nkz_j)
                                             ) / (3.0 * np.sqrt(species_np[i] * species_np[j]))

                    sp2_start = sp2_end

                sp1_start = sp1_end

    return Sk_mat


@nb.njit
def calc_elec_current(vel, sp_charge, sp_num):
    """
    Calcualte the total electric current and the electric current of each species.

    Parameters
    ----------
    vel: array
        Particles' velocities.

    sp_charge: array
        Charge of each species.

    sp_num: array
        Number of particles of each species.

    Returns
    -------
    Js : ndarray
        Electric current of each species.

    Jtot : ndarray
        Total electric current.
    """
    num_species = len(sp_num)
    no_dumps = vel.shape[0]

    Js = np.zeros((num_species, 3, no_dumps))
    Jtot = np.zeros((3, no_dumps))

    for it in range(no_dumps):
        sp_start = 0
        for s in range(num_species):
            sp_end = sp_start + sp_num[s]
            # Calculate the current of each species
            Js[s, :, it] = sp_charge[s] * np.sum(vel[it, :, sp_start:sp_end], axis=1)
            Jtot[:, it] += Js[s, :, it]

            sp_start = sp_end

    return Js, Jtot


@nb.njit
def autocorrelationfunction(At):
    """
    Calculate the autocorrelation function of the input.

    Parameters
    ----------
    At : array
        Observable to autocorrelate. Shape=(ndim, nsteps).

    Returns
    -------
    ACF : array
        Autocorrelation function of ``At``.
    """
    no_steps = At.shape[1]
    no_dim = At.shape[0]

    ACF = np.zeros(no_steps)
    Norm_counter = np.zeros(no_steps)

    for it in range(no_steps):
        for dim in range(no_dim):
            ACF[: no_steps - it] += At[dim, it] * At[dim, it:no_steps]
        Norm_counter[: no_steps - it] += 1.0

    return ACF / Norm_counter


@nb.njit
def autocorrelationfunction_1D(At):
    """
    Calculate the autocorrelation function of the input.

    Parameters
    ----------
    At : array
        Observable to autocorrelate. Shape=(nsteps).

    Returns
    -------
    ACF : array
        Autocorrelation function of ``At``.
    """
    no_steps = At.shape[0]
    ACF = np.zeros(no_steps)
    Norm_counter = np.zeros(no_steps)

    for it in range(no_steps):
        ACF[: no_steps - it] += At[it] * At[it:no_steps]
        Norm_counter[: no_steps - it] += 1.0

    return ACF / Norm_counter


@nb.njit
def calc_pressure_tensor(pos, vel, acc, species_mass, species_np, box_volume):
    no_dim = pos.shape[0]
    pressure_tensor = np.zeros((no_dim, no_dim))
    sp_start = 0
    sp_end = 0
    # Rescale vel and acc of each particle by their individual mass
    for sp in range(len(species_np)):
        sp_end = sp_start + species_np[sp]
        vel[:, sp_start: sp_end] *= np.sqrt(species_mass[sp])
        acc[:, sp_start: sp_end] *= species_mass[sp]  # force
        sp_start = sp_end

    pressure = 0.0
    for i in range(no_dim):
        for j in range(no_dim):
            pressure_tensor[i, j] = np.sum(vel[i, :] * vel[j, :] + pos[i, :] * acc[j, :]) / box_volume
        pressure += pressure_tensor[i, i] / 3.0

    return pressure, pressure_tensor


@nb.njit
def calc_nkt_single_pa(pos_data, ka_values, species_np, no_dumps):
    """
    Calculate :math: `n(k,t)' along the principal axis only."

    Parameters
    ----------
    pos_data : array
        x - coordinate of all the particles.

    ka_values : array
        Array of :math: `ka` values.

    species_np : array
        Number of particles.

    no_dumps : int
        Number of dumps from simulation.

    Returns
    -------
    nkt : ndarray
        Density :math: `n(k_x, k_y, k_z, t)/\sqrt(N)`.
        Shape=( `num_ka_values`, 3, `no_dumps`)
    """
    num_ka_values = len(ka_values)
    nkt = np.zeros((num_ka_values, 3, no_dumps), dtype=np.complex128)

    # Calculate nk(t)
    for it in range(no_dumps):
        for (ik, ka) in enumerate(ka_values):
            krx_i = ka * pos_data[it, 0, :]
            kry_i = ka * pos_data[it, 1, :]
            krz_i = ka * pos_data[it, 2, :]

            nkt[ik, 0, it] = np.sum(np.exp(-1j * krx_i)) / np.sqrt(species_np[0])
            nkt[ik, 1, it] = np.sum(np.exp(-1j * kry_i)) / np.sqrt(species_np[0])
            nkt[ik, 2, it] = np.sum(np.exp(-1j * krz_i)) / np.sqrt(species_np[0])

    return nkt


@nb.njit
def calc_nkt_multi_pa(pos_data, ka_min, num_ka_values, species_np, no_dumps):
    """
    Calculate all :math: `S_{ij}(k)` in case of multi-species simulation."

    Parameters
    ----------
    pos_data : array
        x - coordinate of all the particles.

    ka_min : float
        Smallest possible (non-dimensional) wavenumber :math:`ka = 2\pi/L`.

    num_ka_values : int
        Number of :math: `ka` values to compute.

    species_np : array
        Array of integers with the number of particles for each species.

    Returns
    -------
    ka_values : array
        Array of :math: `ka` values.

    Sk : ndarray
        Static structure factors :math: `S_{ij}(k)`.
    """

    no_sp = len(species_np)
    # Number of independent S_ij(k)  = no_sp*(no_sp + 1)/2
    no_Sk = int(no_sp * (no_sp + 1) / 2)

    Sk = np.zeros((num_ka_values, no_Sk, no_dumps))

    ka_values = np.zeros(num_ka_values)
    for ik in range(num_ka_values):
        ka_values[ik] = (ik + 1) * ka_min

    for it in range(no_dumps):
        for (ik, ka) in enumerate(ka_values):
            sp1_start = 0
            for i in range(no_sp):
                sp1_end = sp1_start + species_np[i]
                sp2_start = 0
                krx_i = ka * pos_data[it, 0, sp1_start:sp1_end]
                kry_i = ka * pos_data[it, 1, sp1_start:sp1_end]
                krz_i = ka * pos_data[it, 2, sp1_start:sp1_end]

                nkx_i = np.sum(np.exp(-1j * krx_i))
                nky_i = np.sum(np.exp(-1j * kry_i))
                nkz_i = np.sum(np.exp(-1j * krz_i))

                for j in range(no_sp):
                    sp2_end = sp2_start + species_np[j]
                    krx_j = ka * pos_data[it, 0, sp2_start:sp2_end]
                    kry_j = ka * pos_data[it, 1, sp2_start:sp2_end]
                    krz_j = ka * pos_data[it, 2, sp2_start:sp2_end]

                    nkx_j = np.sum(np.exp(1j * krx_j))
                    nky_j = np.sum(np.exp(1j * kry_j))
                    nkz_j = np.sum(np.exp(1j * krz_j))

                    indx = i * (no_sp - 1) + j
                    if i == j:
                        degeneracy = 1.0
                    else:
                        degeneracy = 2.0
                    Sk[ik, indx, it] += (np.real(nkx_i * nkx_j) +
                                         np.real(nky_i * nky_j) +
                                         np.real(nkz_i * nkz_j)
                                         ) / (3.0 * degeneracy * np.sqrt(species_np[i] * species_np[j]))

                    sp2_start = sp2_end

                sp1_start = sp1_end

    return ka_values, Sk


def calc_nkt(fldr, no_dumps, dump_step, species_np, k_list):
    """
    Calculate :math:`n(k)` for a single species.

    Parameters
    ----------
    fldr : str
        Name of folder containing particles data.

    no_dumps : int
        Number of saved timesteps.

    dump_step : int
        Timestep interval saving.

    species_np : array
        Number of particles of each species.

    k_list : list
        List of :math: `k` vectors.

    Return
    ------
    nkt : array, complex
        Density fluctations.
    """
    # Read particles' position for all times
    print("Calculating n(k,t).")
    nkt = np.zeros((len(species_np), no_dumps, len(k_list)), dtype=np.complex128)
    for it in tqdm(range(no_dumps)):
        dump = int(it * dump_step)
        data = load_from_restart(fldr, dump)
        pos = data["pos"]
        sp_start = 0
        for i, sp in enumerate(species_np):
            sp_end = sp_start + sp
            nkt[i, it, :] = calc_nk(pos[sp_start:sp_end, :], k_list)
            sp_start = sp_end

    return nkt


@nb.njit
def calc_nk(pos_data, k_list):
    """
    Calculate :math:`n(k)`.

    Parameters
    ----------
    pos_data : ndarray
        Particles' position scaled by the box lengths. Shape = ( `no_dumps`, 3, `tot_no_ptcls')

    k_list : list
        List of :math:`k` indices in each direction with corresponding magnitude and index of `ka_counts`.
        Shape=(`no_ka_values`, 5)

    Returns
    -------
    nk : array
        Array containing :math:`n(k)`.
    """

    nk = np.zeros(len(k_list), dtype=np.complex128)

    for ik, k_vec in enumerate(k_list):
        kr_i = 2.0 * np.pi * (k_vec[0] * pos_data[:, 0] + k_vec[1] * pos_data[:, 1] + k_vec[2] * pos_data[:, 2])
        nk[ik] = np.sum(np.exp(-1j * kr_i))

    return nk


def calc_Skw(nkt, ka_list, ka_counts, species_np, no_dumps, dt, dump_step):
    """
    Calculate :math:`S(k,w)` of all species.

    Parameters
    ----------
    nkt : nkarray, complex
        Particles' density fluctuations. Shape = ( `no_species`, `no_k_list`, `no_dumps`)

    ka_list : list
        List of :math:`k` indices in each direction with corresponding magnitude and index of `ka_counts`.
        Shape=(`no_ka_values`, 5)

    ka_counts : array
        Number of times each :math:`k` magnitude appears.

    species_np : array
        Array with one element giving number of particles.

    no_dumps : int
        Number of dumps.

    Returns
    -------
    Skw : ndarray
        DSF of each species and pair of species. Shape = (`no_skw`, `len(ka_counts)`, `len(w)`
    """

    norm = dt / np.sqrt(no_dumps * dt * dump_step)
    no_skw = int(len(species_np) * (len(species_np) + 1) / 2)
    Skw = np.empty((no_skw, len(ka_counts), no_dumps))

    pair_indx = 0
    for ip, si in enumerate(species_np):
        for jp in range(ip, len(species_np)):
            sj = species_np[jp]
            print("Calculating S(k,w) pair {}-{}".format(ip, jp))
            for ik, ka in tqdm(enumerate(ka_list)):
                indx = int(ka[-1])
                nkw_i = np.fft.fft(nkt[ip, :, ik]) * norm
                nkw_j = np.fft.fft(nkt[jp, :, ik]) * norm
                Skw[pair_indx, indx, :] += np.real(np.conj(nkw_i) * nkw_j) / (ka_counts[indx] * np.sqrt(si * sj))
            pair_indx += 1
    return Skw


def calc_Skw_single(pos_data, ka_list, ka_counts, species_np, no_dumps, dt, dump_step):
    """
    Calculate :math:`S(k,\omega)`.

    Parameters
    ----------
    pos_data : ndarray
        Particles' position scaled by the box lengths. Shape = ( `no_dumps`, 3, `tot_no_ptcls')

    ka_list : list
        List of :math:`k` indices in each direction with corresponding magnitude and index of `ka_counts`.
        Shape=(`no_ka_values`, 5)

    ka_counts : array
        Number of times each :math:`k` magnitude appears.

    species_np : array
        Array with one element giving number of particles.

    no_dumps : int
        Number of dumps.

    Returns
    -------

    Skw : ndarray
        Array containing :math:`S(k,\omega)`. Shape=(`no_ka_values`, `no_species`, `no_dumps`)
    """
    num_ka_values = len(ka_counts)
    num_species = len(species_np)
    Skw = np.zeros((num_ka_values, num_species, no_dumps))
    norm = dt / np.sqrt(no_dumps * dt * dump_step)
    for ik in tqdm(range(len(ka_list))):
        kr_i = 2.0 * np.pi * (ka_list[ik, 0] * pos_data[:, :, 0]
                              + ka_list[ik, 1] * pos_data[:, :, 1]
                              + ka_list[ik, 2] * pos_data[:, :, 2])

        nkt = np.sum(np.exp(-1j * kr_i), axis=1)
        nkw = np.fft.fft(nkt) * norm
        indx = int(ka_list[ik][-1])
        Skw[indx, 0, :] += np.real(np.conj(nkw) * nkw) / (ka_counts[indx] * species_np[0])

    return Skw
