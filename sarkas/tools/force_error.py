import numpy as np
from numba import njit
import time as timer
from sarkas.potentials import force_pm, force_pp


@njit
def Gk(x, alpha, kappa):
    """
    Green's function of Coulomb/Yukawa potential.
    """
    return 4.0 * np.pi * np.exp(-(x ** 2 + kappa ** 2) / (2 * alpha) ** 2) / (kappa ** 2 + x ** 2)

@njit
def betamp(m, p, alpha, kappa):
    """
    Calculate :math:`\beta(m)` of eq.(37) in Dharuman et al. J Chem Phys 146 024112 (2017)
    """
    xa = np.linspace(0.0001, 500, 5000)
    return np.trapz(Gk(xa, alpha, kappa) * Gk(xa, alpha, kappa) * xa ** (2 * (m + p + 2)), x=xa)


def analytical_approx_pp(params):
    """
    Calculate PP force error.
    """

    kappa = 0.0 if params.potential.type == "Coulomb" else params.aws / params.lambda_TF

    r_min = params.potential.rc * 0.5
    r_max = params.potential.rc * 1.5

    rcuts = np.linspace(r_min, r_max, 101) / params.aws

    # Calculate the analytic PP error and the total force error
    DeltaF_PP = np.sqrt(2.0 * np.pi * kappa) * np.exp(- rcuts * kappa)
    DeltaF_PP *= np.sqrt(params.total_num_ptcls * params.aws ** 3 / params.box_volume)

    return DeltaF_PP, rcuts


def analytical_approx_pppm(params):
    """
    Calculate the total force error as given in Dharuman et al. J Chem Phys 146 024112 (2017).

    Parameters
    ----------
    params : object
        Simulation's parameters

    Returns
    -------
    Tot_DeltaF: ndarray
        Total force error approximation.

    DeltaF_PP: ndarray
        PP force error.

    DeltaF_PM: ndarray
        PM force error.

    rcuts: array
        Cut off values.

    alphas: array
        Ewald parameters.
    """

    kappa = 0.0 if params.potential.type == "Coulomb" else params.potential.matrix[1, 0, 0] * params.aws

    p = params.pppm.cao
    L = params.box_lengths[0] / params.aws
    h = L / params.pppm.MGrid[0]

    a_min = params.pppm.G_ew * 0.5
    a_max = params.pppm.G_ew * 1.5

    r_min = params.potential.rc * 0.5
    r_max = params.potential.rc * 1.5

    alphas = params.aws * np.linspace(a_min, a_max, 101)
    rcuts = np.linspace(r_min, r_max, 101) / params.aws

    DeltaF_PM = np.zeros(len(alphas))
    DeltaF_PP = np.zeros((len(alphas), len(rcuts)))
    Tot_DeltaF = np.zeros((len(alphas), len(rcuts)))

    # Coefficient from Deserno and Holm J Chem Phys 109 7694 (1998)
    if p == 1:
        Cmp = np.array([2 / 3])
    elif p == 2:
        Cmp = np.array([2 / 45, 8 / 189])
    elif p == 3:
        Cmp = np.array([4 / 495, 2 / 225, 8 / 1485])
    elif p == 4:
        Cmp = np.array([2 / 4725, 16 / 10395, 5528 / 3869775, 32 / 42525])
    elif p == 5:
        Cmp = np.array([4 / 93555, 2764 / 11609325, 8 / 25515, 7234 / 32531625, 350936 / 3206852775])
    elif p == 6:
        Cmp = np.array([2764 / 638512875, 16 / 467775, 7234 / 119282625, 1403744 / 25196700375,
                        1396888 / 40521009375, 2485856 / 152506344375])
    elif p == 7:
        Cmp = np.array([8 / 18243225, 7234 / 1550674125, 701872 / 65511420975, 2793776 / 225759909375,
                        1242928 / 132172165125, 1890912728 / 352985880121875, 21053792 / 8533724574375])

    for ia, alpha in enumerate(alphas):
        somma = 0.0
        for m in np.arange(p):
            expp = 2 * (m + p)
            somma += Cmp[m] * (2 / (1 + expp)) * betamp(m, p, alpha, kappa) * (h / 2.) ** expp
        # eq.(36) in Dharuman J Chem Phys 146 024112 (2017)
        DeltaF_PM[ia] = np.sqrt(3.0 * somma) / (2.0 * np.pi)
    # eq.(35)
    DeltaF_PM *= np.sqrt(params.total_num_ptcls * params.aws ** 3 / params.box_volume)

    # Calculate the analytic PP error and the total force error
    if params.potential.type == "QSP":
        for (ir, rc) in enumerate(rcuts):
            DeltaF_PP[:, ir] = np.sqrt(2.0 * np.pi * kappa) * np.exp(- rc * kappa)
            DeltaF_PP[:, ir] *= np.sqrt(params.total_num_ptcls * params.aws ** 3 / params.box_volume)
            for (ia, alfa) in enumerate(alphas):
                # eq.(42) from Dharuman J Chem Phys 146 024112 (2017)
                Tot_DeltaF[ia, ir] = np.sqrt(DeltaF_PM[ia] ** 2 + DeltaF_PP[ia, ir] ** 2)
    else:
        for (ir, rc) in enumerate(rcuts):
            for (ia, alfa) in enumerate(alphas):
                # eq.(30) from Dharuman J Chem Phys 146 024112 (2017)
                DeltaF_PP[ia, ir] = 2.0 * np.exp(-(0.5 * kappa / alfa) ** 2 - alfa ** 2 * rc ** 2) / np.sqrt(rc)
                DeltaF_PP[ia, ir] *= np.sqrt(params.total_num_ptcls * params.aws ** 3 / params.box_volume)
                # eq.(42) from Dharuman J Chem Phys 146 024112 (2017)
                Tot_DeltaF[ia, ir] = np.sqrt(DeltaF_PM[ia] ** 2 + DeltaF_PP[ia, ir] ** 2)

    return Tot_DeltaF, DeltaF_PP, DeltaF_PM, rcuts, alphas


def optimal_green_function_timer(params):
    """
    Calculate the Optimal Green Function.

    Parameters
    ----------
    params : object
        Simulation's parameters

    Returns
    -------
    green_function_time : float
        Calculation time.
    """
    # Dev notes. I am rewriting the functions here because I need to put a counter around it.
    # Optimized Green's Function

    kappa_Y = 1./params.lambda_TF if params.potential.type == "Yukawa" else 0.0
    constants = np.array([kappa_Y, params.pppm.G_ew, params.fourpie0])
    start = timer.time()
    params.pppm.G_k, params.pppm.kx_v, params.pppm.ky_v, params.pppm.kz_v, params.pppm.PM_err = force_pm.force_optimized_green_function(
        params.pppm.MGrid, params.pppm.aliases, params.box_lengths, params.pppm.cao, constants)

    params.pppm.PM_err *= np.sqrt(params.total_num_ptcls) * params.aws ** 2 * params.fourpie0 / params.box_volume ** (2. / 3.)

    green_time = timer.time() - start

    return green_time


def acceleration_timer(params, ptcls, loops):
    """
    Calculate the average time for force calculation.

    Parameters
    ----------
    params : object
        Simulation's parameters

    ptcls : object
        Particles data.

    loops : int
        Number of loops for averaging.

    Returns
    -------
    PP_force_time : array
        Times for the PP force calculation.

    PM_force_time : array
        Times for the PM force calculation.

    """
    # Dev notes. I am rewriting the functions here because I need to put a counter around it.

    PP_force_time = np.zeros(loops + 1)
    PM_force_time = np.zeros(loops + 1)

    for it in range(loops + 1):
        PP_force_time[it] = pp_acceleration_timer(params, ptcls)
        PM_force_time[it] = pm_acceleration_timer(params, ptcls)

    return PP_force_time, PM_force_time


def pp_acceleration_timer(params, ptcls):
    """
    Calculate the average time for force calculation.

    Parameters
    ----------
    params : object
        Simulation's parameters

    ptcls : object
        Particles data.

    Returns
    -------
    PP_force_time : array
        Times for the PP force calculation.
    """
    # Dev notes. I am rewriting the functions here because I need to put a counter around it.
    if params.potential.LL_on:
        start = timer.time()
        U_short, acc_s_r = force_pp.update(ptcls.pos, ptcls.species_id, ptcls.mass, params.box_lengths,
                                           params.potential.rc, params.potential.matrix, params.force,
                                           params.measure, ptcls.rdf_hist)
        PP_force_time = timer.time() - start
    else:
        start = timer.time()
        U_short, acc_s_r = force_pp.update_0D(ptcls.pos, ptcls.species_id, ptcls.mass, params.box_lengths,
                                              params.potential.rc, params.potential.matrix, params.force,
                                              params.measure, ptcls.rdf_hist)
        PP_force_time = timer.time() - start
    return PP_force_time


def pm_acceleration_timer(params, ptcls):
    """
    Calculate the average time for force calculation.

    Parameters
    ----------
    params : object
        Simulation's parameters

    ptcls : object
        Particles data.

    Returns
    -------
    PM_force_time : array
        Times for the PP force calculation.
    """
    start = timer.time()
    U_long, acc_l_r = force_pm.update(ptcls.pos, ptcls.charges, ptcls.mass,
                                      params.pppm.MGrid, params.box_lengths, params.pppm.G_k, params.pppm.kx_v,
                                      params.pppm.ky_v,
                                      params.pppm.kz_v, params.pppm.cao)
    PM_force_time = timer.time() - start
    return PM_force_time


def print_time_report(str_id, t, loops):
    """
    Print times estimates of simulation.
    """
    if str_id == "GF":
        print("Optimal Green's Function Time = {:1.3f} sec \n".format(t))
    elif str_id == "PP":
        print('Average time of PP acceleration calculation over {} loops: {:1.3f} msec \n'.format(loops, t * 1e3))
    elif str_id == "PM":
        print('Average time of PM acceleration calculation over {} loops: {:1.3f} msec \n'.format(loops, t * 1e3))


@njit
def analytical_approx_pppm_single(kappa, rc, p, h, alpha):
    """
    Calculate the total force error for a given value of ``rc`` and ``alpha``. See similar function above.
    """
    # Coefficient from Deserno and Holm J Chem Phys 109 7694 (1998)
    if p == 1:
        Cmp = np.array([2 / 3])
    elif p == 2:
        Cmp = np.array([2 / 45, 8 / 189])
    elif p == 3:
        Cmp = np.array([4 / 495, 2 / 225, 8 / 1485])
    elif p == 4:
        Cmp = np.array([2 / 4725, 16 / 10395, 5528 / 3869775, 32 / 42525])
    elif p == 5:
        Cmp = np.array([4 / 93555, 2764 / 11609325, 8 / 25515, 7234 / 32531625, 350936 / 3206852775])
    elif p == 6:
        Cmp = np.array([2764 / 638512875, 16 / 467775, 7234 / 119282625, 1403744 / 25196700375,
                        1396888 / 40521009375, 2485856 / 152506344375])
    elif p == 7:
        Cmp = np.array([8 / 18243225, 7234 / 1550674125, 701872 / 65511420975, 2793776 / 225759909375,
                        1242928 / 132172165125, 1890912728 / 352985880121875, 21053792 / 8533724574375])

    somma = 0.0
    for m in np.arange(p):
        expp = 2 * (m + p)
        somma += Cmp[m] * (2 / (1 + expp)) * betamp(m, p, alpha, kappa) * (h / 2.) ** expp
    # eq.(36) in Dharuman J Chem Phys 146 024112 (2017)
    DeltaF_PM = np.sqrt(3.0 * somma) / (2.0 * np.pi)

    # eq.(30) from Dharuman J Chem Phys 146 024112 (2017)
    DeltaF_PP = 2.0 * np.exp(-(0.5 * kappa / alpha) ** 2 - alpha ** 2 * rc ** 2) / np.sqrt(rc)
    # eq.(42) from Dharuman J Chem Phys 146 024112 (2017)
    Tot_DeltaF = np.sqrt(DeltaF_PM ** 2 + DeltaF_PP ** 2)

    return Tot_DeltaF, DeltaF_PP, DeltaF_PM
