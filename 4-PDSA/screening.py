import pypowsybl as pp
import numpy as np
from math import pi
from common import *
from dataclasses import dataclass
if WITH_LXML:
    from lxml import etree
else:
    import xml.etree.ElementTree as etree
import scipy.sparse
import scipy.sparse.linalg
import scipy.linalg

@dataclass
class GeneratorData:
    M: float  # Inertia
    E: float  # Interval voltage magnitude
    Pm : float  # Mechanical power
    name: str
    delta_i: float  # Initial internal angle
    delta_f: float = 2*pi  # Final internal angle

@dataclass
class OMIBData:
    delta_i: float  # Initial internal angle
    delta_f: float  # Final internal angle
    Pc : float  # Constant electrical power
    Pmax : float  # Max electrical power
    Pm: float  # Mechanical power
    angle_shift: float

    def negate(self):
        self.delta_i = -self.delta_i
        self.delta_f = -self.delta_f
        self.Pc = -self.Pc
        self.Pmax = -self.Pmax
        self.Pm = -self.Pm
        self.angle_shift = -self.angle_shift

def get_generator_data(n: pp.network.Network, disconnected_elements = []) -> list[GeneratorData]:
    generator_data = []
    gens = n.get_generators()
    buses = n.get_buses()
    vl = n.get_voltage_levels()

    par_root = etree.parse('../3-DynData/{}.par'.format(NETWORK_NAME)).getroot()

    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue
        if gens.at[gen_id, 'energy_source'] in ['SOLAR', 'WIND']:
            continue
        if gen_id in disconnected_elements:
            continue

        par_set = par_root.find("{{{}}}set[@id='{}']".format(DYNAWO_NAMESPACE, gen_id))
        if par_set is None:
            raise ValueError(gen_id, 'parameters not found')
        Snom = float(par_set.find("{{{}}}par[@name='generator_SNom']".format(DYNAWO_NAMESPACE)).get('value'))
        M = float(par_set.find("{{{}}}par[@name='generator_H']".format(DYNAWO_NAMESPACE)).get('value')) * Snom / BASEMVA
        Xd = 1j * float(par_set.find("{{{}}}par[@name='generator_XpdPu']".format(DYNAWO_NAMESPACE)).get('value'))  / (Snom / BASEMVA)
        Snom_tfo = float(par_set.find("{{{}}}par[@name='generator_SnTfo']".format(DYNAWO_NAMESPACE)).get('value'))
        zTFO = (float(par_set.find("{{{}}}par[@name='generator_RTfPu']".format(DYNAWO_NAMESPACE)).get('value')) + 1j *
                float(par_set.find("{{{}}}par[@name='generator_XTfPu']".format(DYNAWO_NAMESPACE)).get('value'))) / (Snom_tfo / BASEMVA)
        z = Xd + zTFO
        Pm = -gens.at[gen_id, 'p'] / BASEMVA
        Q = -gens.at[gen_id, 'q'] / BASEMVA

        S = Pm + 1j * Q

        Ub = vl.at[gens.at[gen_id, 'voltage_level_id'], 'nominal_v']
        bus_id = gens.at[gen_id, 'bus_id']
        U = buses.at[bus_id, 'v_mag'] / Ub
        theta = buses.at[bus_id, 'v_angle'] * pi / 180
        V = U * np.exp(1j*theta)

        I = np.conj(S/V)
        E = V + z * I
        E, delta = np.absolute(E), np.angle(E)
        name = gen_id
        generator_data.append(GeneratorData(M, E, Pm, name, delta))
    return generator_data


def get_impedance_matrix(n: pp.network.Network, disconnected_elements = [], inverter_model='None', generator_model='None', with_loads=False, fault_location=None):
    return NotImplementedError('The code below works (only tested it for voltage screening), but it is actually faster to inverse the admittance matrix (np.linalg.inv(get_admittance_matrix(...)))')
    buses = n.get_buses()
    vl = n.get_voltage_levels()
    lines = n.get_lines()
    tfos = n.get_2_windings_transformers()
    gens = n.get_generators()
    loads = n.get_loads()
    bus_id_to_index = {bus_id: index for index, bus_id in enumerate(list(buses.index))}

    for disconnected_element in disconnected_elements:
        if (list(lines.index) + list(tfos.index) + list(gens.index)).count(disconnected_element) < 1:
            raise RuntimeError(disconnected_element, 'does not exist in network')
        elif (list(lines.index) + list(tfos.index) + list(gens.index)).count(disconnected_element) > 1:
            raise RuntimeError(disconnected_element, 'is ambiguous (multiple elements of different types with same name)')

    sync_gens = []
    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue
        if gens.at[gen_id, 'energy_source'] in ['SOLAR', 'WIND']:
            continue
        if gen_id in disconnected_elements:
            continue
        sync_gens.append(gen_id)

    N_buses = len(buses)
    N_gens = len(sync_gens)

    bus_shunt_admittances = np.zeros(N_buses + N_gens, complex)  # Create additonal buses to connect the generator Emf behind their transient reactances
    branch_admittances = {}

    for branch_type in ['line', 'tfo']:
        if branch_type == 'line':
            branches = lines
        else:
            branches = tfos

        for branch_id in branches.index:
            if not (branches.at[branch_id, 'connected1'] and branches.at[branch_id, 'connected2']):
                continue
            if branch_id in disconnected_elements:
                continue
            from_ = bus_id_to_index[branches.at[branch_id, 'bus1_id']]
            to = bus_id_to_index[branches.at[branch_id, 'bus2_id']]
            vl_id = branches.at[branch_id, 'voltage_level2_id']  # Transformer impedances given in secondary base (no impact for lines)
            Ub = vl.at[vl_id, 'nominal_v']
            Zb = Ub**2 / BASEMVA
            r = branches.at[branch_id, 'r'] / Zb
            x = branches.at[branch_id, 'x'] / Zb
            z = r + 1j*x

            if branch_type == 'line':
                b1 = 1j * branches.at[branch_id, 'b1'] * Zb
                b2 = 1j * branches.at[branch_id, 'b2'] * Zb
                bus_shunt_admittances[from_] += b1
                bus_shunt_admittances[to   ] += b2
            else:
                b = branches.at[branch_id, 'b'] * Zb
                tap = 1

                bus_shunt_admittances[from_] += b/2 * tap**2
                bus_shunt_admittances[to   ] += b/2

            branch_admittances[f"{from_}-{to}"] = branch_admittances.get(f"{from_}-{to}", 0) + 1/z  # TODO: more logic if tfo tap != 1


    for load_id in loads.index:
        if not with_loads:
            break

        if not loads.at[load_id, 'connected']:
            continue
        from_ = bus_id_to_index[loads.at[load_id, 'bus_id']]
        vl_id = loads.at[load_id, 'voltage_level_id']
        Ub = vl.at[vl_id, 'nominal_v']
        Zb = Ub**2 / BASEMVA
        S = loads.at[load_id, 'p0'] + 1j * loads.at[load_id, 'q0']
        if S == 0:
            continue
        U = buses.at[loads.at[load_id, 'bus_id'], 'v_mag']
        z = U**2 / np.conj(S) / Zb
        bus_shunt_admittances[from_] += 1/z

    if fault_location is not None:
        Ub_fault = vl.at[buses.at[fault_location, 'voltage_level_id'], 'nominal_v']
        Zb = Ub_fault**2 / BASEMVA
        from_ = bus_id_to_index[fault_location]
        bus_shunt_admittances[from_] += 1 / ((R_FAULT + 1j * X_FAULT) / Zb)


    # Inverter based generators
    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue
        if gen_id in disconnected_elements:
            continue
        if gens.at[gen_id, 'energy_source'] not in ['SOLAR', 'WIND']:
            continue  # Inverter based generators

        if inverter_model == 'None':
            break
        elif inverter_model == 'Load':
            from_ = bus_id_to_index[gens.at[gen_id, 'bus_id']]
            vl_id = gens.at[gen_id, 'voltage_level_id']
            Ub = vl.at[vl_id, 'nominal_v']
            Zb = Ub**2 / BASEMVA
            S = gens.at[gen_id, 'p'] + 1j * gens.at[gen_id, 'q']
            if S == 0:
                continue
            U = buses.at[gens.at[gen_id, 'bus_id'], 'v_mag']
            z = U**2 / np.conj(S) / Zb
            bus_shunt_admittances[from_] += 1/z
        else:
            raise NotImplementedError()


    # Synchronous generators
    par_root = etree.parse('../3-DynData/{}.par'.format(NETWORK_NAME)).getroot()
    for i, gen_id in enumerate(sync_gens):
        from_ = N_buses + i
        to = bus_id_to_index[gens.at[gen_id, 'bus_id']]

        par_set = par_root.find("{{{}}}set[@id='{}']".format(DYNAWO_NAMESPACE, gen_id))
        if par_set is None:
            raise ValueError(gen_id, 'parameters not found')
        Snom = float(par_set.find("{{{}}}par[@name='generator_SNom']".format(DYNAWO_NAMESPACE)).get('value'))
        Xd = 1j * float(par_set.find("{{{}}}par[@name='generator_XpdPu']".format(DYNAWO_NAMESPACE)).get('value')) / (Snom / BASEMVA)
        Snom_tfo = float(par_set.find("{{{}}}par[@name='generator_SnTfo']".format(DYNAWO_NAMESPACE)).get('value'))
        zTFO = (float(par_set.find("{{{}}}par[@name='generator_RTfPu']".format(DYNAWO_NAMESPACE)).get('value')) + 1j *
                float(par_set.find("{{{}}}par[@name='generator_XTfPu']".format(DYNAWO_NAMESPACE)).get('value'))) / (Snom_tfo / BASEMVA)
        z = Xd + zTFO

        branch_admittances[f"{from_}-{to}"] = branch_admittances.get(f"{from_}-{to}", 0) + 1/z

        if generator_model == 'None':
            continue
        elif generator_model == 'VoltageSource':
            bus_shunt_admittances[from_] += 1e9

    BIG_Z = 1e9
    bus_shunt_impedances = []
    for i in range(len(bus_shunt_admittances)):
        if bus_shunt_admittances[i] == 0:
            bus_shunt_impedances.append(BIG_Z)
        else:
            bus_shunt_impedances.append(1/bus_shunt_admittances[i])


    # Step 1 of Z construction: add all buses with shunt to ground (shunt set to BIG_Z if none) (rule #1 of https://home.engineering.iastate.edu/~jdm/ee457/Zbus.pdf)
    Z = np.diag(bus_shunt_impedances)

    # Step 2 of Z construction: add all branches between buses (rule #4 of https://home.engineering.iastate.edu/~jdm/ee457/Zbus.pdf)
    N = len(branch_admittances)
    i = 0
    for index in branch_admittances:
        from_, to = index.split('-')
        from_ = int(from_)
        to = int(to)
        z = 1/branch_admittances[index]

        gamma = 1 / (z + Z[from_][from_] - 2*Z[to][from_] + Z[to][to])
        b = Z[from_] - Z[to]

        Z -= gamma * np.outer(b, b)

        i += 1
        print(f'{i}/{N}', end='\r')

    return Z


def get_admittance_matrix(n: pp.network.Network, disconnected_elements = [], inverter_model='None', generator_model='None', with_loads=False, fault_location=None):
    buses = n.get_buses()
    vl = n.get_voltage_levels()
    lines = n.get_lines()
    tfos = n.get_2_windings_transformers()
    gens = n.get_generators()
    loads = n.get_loads()
    bus_id_to_index = {bus_id: index for index, bus_id in enumerate(list(buses.index))}

    for disconnected_element in disconnected_elements:
        if (list(lines.index) + list(tfos.index) + list(gens.index)).count(disconnected_element) < 1:
            raise RuntimeError(disconnected_element, 'does not exist in network')
        elif (list(lines.index) + list(tfos.index) + list(gens.index)).count(disconnected_element) > 1:
            raise RuntimeError(disconnected_element, 'is ambiguous (multiple elements of different types with same name)')

    sync_gens = []
    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue
        if gens.at[gen_id, 'energy_source'] in ['SOLAR', 'WIND']:
            continue
        if gen_id in disconnected_elements:
            continue
        sync_gens.append(gen_id)

    N_buses = len(buses)
    N_gens = len(sync_gens)  # Create additonal buses to connect the generator Emf behind their transient reactances
    Y = np.zeros((N_buses + N_gens, N_buses + N_gens), complex)

    for line_id in lines.index:
        if not (lines.at[line_id, 'connected1'] and lines.at[line_id, 'connected2']):
            continue
        if line_id in disconnected_elements:
            continue
        from_ = bus_id_to_index[lines.at[line_id, 'bus1_id']]
        to = bus_id_to_index[lines.at[line_id, 'bus2_id']]
        vl_id = lines.at[line_id, 'voltage_level1_id']
        Ub = vl.at[vl_id, 'nominal_v']
        Zb = Ub**2 / BASEMVA
        r = lines.at[line_id, 'r'] / Zb
        x = lines.at[line_id, 'x'] / Zb
        z = r + 1j*x
        b1 = 1j * lines.at[line_id, 'b1'] * Zb
        b2 = 1j * lines.at[line_id, 'b2'] * Zb

        Y[from_, from_] += b1 + 1/z
        Y[from_, to] += -1/z
        Y[to, from_] += -1/z
        Y[to, to] += b2 + 1/z

    for tfo_id in tfos.index:
        if not (tfos.at[tfo_id, 'connected1'] and tfos.at[tfo_id, 'connected2']):
            continue
        if tfo_id in disconnected_elements:
            continue
        from_ = bus_id_to_index[tfos.at[tfo_id, 'bus1_id']]
        to = bus_id_to_index[tfos.at[tfo_id, 'bus2_id']]
        vl_id = tfos.at[tfo_id, 'voltage_level2_id']  # Impedances given in secondary base
        Ub = vl.at[vl_id, 'nominal_v']
        Zb = Ub**2 / BASEMVA
        r = tfos.at[tfo_id, 'r'] / Zb
        x = tfos.at[tfo_id, 'x'] / Zb
        z = r + 1j*x
        b = tfos.at[tfo_id, 'b'] * Zb

        tap = 1

        Y[from_, from_] += (b/2 + 1/z) * tap**2
        Y[from_, to] += -1/z * tap
        Y[to, from_] += -1/z * tap
        Y[to, to] += 1/z + b/2

    for load_id in loads.index:
        if not with_loads:
            break

        if not loads.at[load_id, 'connected']:
            continue
        from_ = bus_id_to_index[loads.at[load_id, 'bus_id']]
        vl_id = loads.at[load_id, 'voltage_level_id']
        Ub = vl.at[vl_id, 'nominal_v']
        Zb = Ub**2 / BASEMVA
        S = loads.at[load_id, 'p0'] + 1j * loads.at[load_id, 'q0']
        if S == 0:
            continue
        U = buses.at[loads.at[load_id, 'bus_id'], 'v_mag']
        z = U**2 / np.conj(S) / Zb
        Y[from_, from_] += 1/z

    if fault_location is not None:
        Ub_fault = vl.at[buses.at[fault_location, 'voltage_level_id'], 'nominal_v']
        Zb = Ub_fault**2 / BASEMVA
        from_ = bus_id_to_index[fault_location]
        Y[from_, from_] += 1 / ((R_FAULT + 1j * X_FAULT) / Zb)

    # Inverter based generators
    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue
        if gen_id in disconnected_elements:
            continue
        if gens.at[gen_id, 'energy_source'] not in ['SOLAR', 'WIND']:
            continue  # Inverter based generators

        if inverter_model == 'None':
            break
        elif inverter_model == 'Load':
            from_ = bus_id_to_index[gens.at[gen_id, 'bus_id']]
            vl_id = gens.at[gen_id, 'voltage_level_id']
            Ub = vl.at[vl_id, 'nominal_v']
            Zb = Ub**2 / BASEMVA
            S = gens.at[gen_id, 'p'] + 1j * gens.at[gen_id, 'q']
            if S == 0:
                continue
            U = buses.at[gens.at[gen_id, 'bus_id'], 'v_mag']
            z = U**2 / np.conj(S) / Zb
            Y[from_, from_] += 1/z
        else:
            raise NotImplementedError()


    # Synchronous generators
    par_root = etree.parse('../3-DynData/{}.par'.format(NETWORK_NAME)).getroot()
    for i, gen_id in enumerate(sync_gens):
        from_ = N_buses + i
        to = bus_id_to_index[gens.at[gen_id, 'bus_id']]

        par_set = par_root.find("{{{}}}set[@id='{}']".format(DYNAWO_NAMESPACE, gen_id))
        if par_set is None:
            raise ValueError(gen_id, 'parameters not found')
        Snom = float(par_set.find("{{{}}}par[@name='generator_SNom']".format(DYNAWO_NAMESPACE)).get('value'))
        Xd = 1j * float(par_set.find("{{{}}}par[@name='generator_XpdPu']".format(DYNAWO_NAMESPACE)).get('value')) / (Snom / BASEMVA)
        Snom_tfo = float(par_set.find("{{{}}}par[@name='generator_SnTfo']".format(DYNAWO_NAMESPACE)).get('value'))
        zTFO = (float(par_set.find("{{{}}}par[@name='generator_RTfPu']".format(DYNAWO_NAMESPACE)).get('value')) + 1j *
                float(par_set.find("{{{}}}par[@name='generator_XTfPu']".format(DYNAWO_NAMESPACE)).get('value'))) / (Snom_tfo / BASEMVA)
        z = Xd + zTFO

        Y[from_, from_] += 1/z
        Y[from_, to] += -1/z
        Y[to, from_] += -1/z
        Y[to, to] += 1/z

        if generator_model == 'None':
            continue
        elif generator_model == 'VoltageSource':
            Y[from_, from_] += 1e9

    return Y


def voltage_screening(n: pp.network.Network, disconnected_elements = []):
    """
    Return False (insecure) if the short-circuit level at any bus is lower than 4 times the load at said bus.
    Also returns the minimum Shc to load ratio
    """
    if NETWORK_NAME == 'Texas':
        return False, 0  # Takes too much computation time for a screening indicator, so skipped

    buses = n.get_buses()
    loads = n.get_loads()
    bus_id_to_index = {bus_id: index for index, bus_id in enumerate(list(buses.index))}

    # Compute the impedance matrix as Z = 1/Y
    Y = get_admittance_matrix(n, disconnected_elements, inverter_model='None', generator_model='VoltageSource', with_loads=True)
    try:
        Y = scipy.sparse.csc_matrix(Y)
        lu = scipy.sparse.linalg.splu(Y)
        Z = lu.solve(np.eye(Y.shape[0]))  # Inverse matrix
    except scipy.linalg.LinAlgError:  # Matrix can be singular, typically if an isolated part of the grid has no load nor generators
        print('Warning: singular matrix')
        return False, 0

    # Could also build the impedance matrix directly instead of computing the inverse of Y, but for some reason, it takes even more time
    # Z = get_impedance_matrix(n, disconnected_elements, inverter_model='None', generator_model='VoltageSource', with_loads=True)

    min_shc_ratio = 1e9
    for load_id in loads.index:
        if not loads.at[load_id, 'connected']:
            continue
        S_load = (loads.at[load_id, 'p0']**2 + loads.at[load_id, 'q0']**2)**0.5 / BASEMVA
        if S_load == 0:
            continue
        from_ = bus_id_to_index[loads.at[load_id, 'bus_id']]
        S_shc = abs(-1 / Z[from_, from_])
        if S_shc / S_load < min_shc_ratio:
            min_shc_ratio = S_shc / S_load
    return min_shc_ratio > 4, min_shc_ratio


def extended_equal_area_criterion(n: pp.network.Network, fault_location, disconnected_elements = []):
    """
    Transient stability screening based on
    Bahmanyar et.al, Extended Equal Area Criterion Revisited: A Direct Method for Fast Transient Stability Analysis
    Bahmanyar et.al, Identification of the critical cluster of generators by during fault angle trajectory estimation for transient stability analysis
    """
    delta_max = 2*pi

    buses = n.get_buses()
    N_buses = len(buses)

    Y_pre = get_admittance_matrix(n, disconnected_elements=[], inverter_model='Load', generator_model='None', with_loads=True, fault_location=None)
    Y_dur = get_admittance_matrix(n, disconnected_elements=[], inverter_model='Load', generator_model='None', with_loads=True, fault_location=fault_location)
    Y_post = get_admittance_matrix(n, disconnected_elements=disconnected_elements, inverter_model='Load', generator_model='None', with_loads=True, fault_location=None)

    def fast_inverse(Y):
        Y = scipy.sparse.csc_matrix(Y)
        lu = scipy.sparse.linalg.splu(Y)
        return lu.solve(np.eye(Y.shape[0]))  # Inverse matrix

    b = list(range(N_buses))
    g = list(range(N_buses, Y_pre.shape[0]))
    # @ is numpy's matrix multiplication operator
    try:
        # TODO: replace np.linalg.inv(Y) by Z to reduce computation time, although tests for voltage screening show that inverting Y is actually faster
        Y_pre_red = Y_pre[g,:][:,g] - Y_pre[g,:][:,b] @ fast_inverse(Y_pre[b,:][:,b]) @ Y_pre[b,:][:,g]
        Y_dur_red = Y_dur[g,:][:,g] - Y_dur[g,:][:,b] @ fast_inverse(Y_dur[b,:][:,b]) @ Y_dur[b,:][:,g]
        g = list(range(N_buses, Y_post.shape[0]))
        Y_post_red = Y_post[g,:][:,g] - Y_post[g,:][:,b] @ fast_inverse(Y_post[b,:][:,b]) @ Y_post[b,:][:,g]
    except np.linalg.LinAlgError:
        return 0, [], [], 0, 0, 0

    S = get_generator_data(n, disconnected_elements=[])
    S_post = get_generator_data(n, disconnected_elements)
    delta_theta = angle_deviation_estimation(S, Y_dur_red)
    critical_groups = critical_group_identification(S, delta_theta)
    # print(critical_groups)

    CCTs = []
    CCs = []
    NCs = []
    delta_crits = []
    w_crits = []
    t_returns = []

    for critical_group in critical_groups:
        CC = []
        NC = []
        for i in range(len(S)):
            if S[i].name in critical_group:
                CC.append(i)
            else:
                NC.append(i)
        CCs.append(CC)
        NCs.append(NC)

        CC_post = []
        NC_post = []
        for i in range(len(S_post)):
            if S_post[i].name in critical_group:
                CC_post.append(i)
            else:
                NC_post.append(i)
        if len(CC_post) == 0 or len(NC_post) == 0:
            CCTs.append(999)
            delta_crits.append(0)
            w_crits.append(0)
            t_returns.append(999)
            continue


        OMIB_pre, _ = omib_equivalent(S, CC, NC, Y_pre_red)
        OMIB_dur, M_dur = omib_equivalent(S, CC, NC, Y_dur_red)
        OMIB_post, M_post = omib_equivalent(S_post, CC_post, NC_post, Y_post_red)

        delta_0 = np.arcsin((OMIB_pre.Pm - OMIB_pre.Pc) / OMIB_pre.Pmax) + OMIB_pre.angle_shift

        OMIB_dur.delta_f = delta_max
        OMIB_post.delta_f = delta_max
        OMIB_dur.delta_i = delta_0
        OMIB_post.delta_i = delta_0

        dflag, tflag, delta_crit, delta_return = critical_angle_OMIB(OMIB_dur, OMIB_post)
        if tflag == 'always_stable':
            t_crit = 999
            w_crit = 0
            t_return = 999
            w_return = 0
        elif tflag == 'always_unstable':
            t_crit = 0
            w_crit = 0
            t_return = 0
            w_return = 0
        else:
            t_crit, w_crit = angle_to_time(OMIB_dur, M_dur, delta_crit, delta_0, 0)
            t_return, w_return = angle_to_time(OMIB_post, M_post, delta_return, delta_crit, w_crit)
        CCTs.append(t_crit)
        delta_crits.append(delta_crit)
        w_crits.append(w_crit)
        t_returns.append(t_return)

    CCT = np.min(CCTs)
    index = CCTs.index(CCT)
    true_CC = CCs[index]
    true_NC = NCs[index]
    delta_crit = delta_crits[index]
    w_crit = w_crits[index]
    t_return = t_returns[index]
    t_obs = CCT + t_return

    return CCT, true_CC, true_NC, delta_crit, w_crit, t_obs


def angle_deviation_estimation(S: list[GeneratorData], Y_reduced):
    t_a = 0.200

    if len(S) != Y_reduced.shape[0]:
        raise

    w0 = 2 * pi * BASEFREQUENCY
    s = len(S)

    A = np.zeros(shape=(s,s))
    B = np.zeros(shape=(s,s))

    delta_der2 = np.zeros(shape=(s))
    delta_der4 = np.zeros(shape=(s))
    delta = np.zeros(shape=(s))

    for k in range(s):
        for j in range(s):
            A[k, j] = S[k].E * S[j].E * np.absolute(Y_reduced[k, j]) * np.cos(S[k].delta_i - S[j].delta_i - np.angle(Y_reduced[k, j]))
            B[k, j] = S[k].E * S[j].E * np.absolute(Y_reduced[k, j]) * np.sin(S[k].delta_i - S[j].delta_i - np.angle(Y_reduced[k, j]))
        delta_der2[k] = w0 / S[k].M * (S[k].Pm - sum(A[k, :]))

    for k in range(s):
        for j in range(s):
            delta_der4[k] += w0 / S[k].M * (B[k,j] * (delta_der2[k] - delta_der2[j]))
            delta[k] = 1/2 * delta_der2[k] * t_a**2 + 1/24 * delta_der4[k] * t_a**4

    return delta


def critical_group_identification(S: list[GeneratorData], delta_theta):
    # Sort S and delta_theta in decreasing order of delta_theta
    S, delta_theta = zip(*sorted(zip(S, delta_theta), key=lambda x: x[1], reverse=True))
    delta_theta_diff = np.array([delta_theta[i] - delta_theta[i+1] for i in range(len(delta_theta) - 1)])
    i = np.argmax(delta_theta_diff)
    return [[S[j].name for j in range(i+1)]]


def omib_equivalent(S: list[GeneratorData], CC, NC, Y_reduced):
    """
    Algo 1 from Bahmanyar et. al., 'Extended Equal Area Criterion Revisited: A Direct Method for Fast Transient Stability Analysis'
    ZOOMIB only
    """
    s = len(S)
    G = np.real(Y_reduced)
    B = np.imag(Y_reduced)

    b = np.empty((s,s))
    g = np.empty((s,s))
    for j in range(s):
        for k in range(s):
            b[k,j] = S[k].E * S[j].E * B[k,j]
            g[k,j] = S[k].E * S[j].E * G[k,j]

    M_cc = sum([S[j].M for j in CC])
    M_nc = sum([S[j].M for j in NC])
    M_T = M_cc + M_nc
    M = M_cc * M_nc / M_T

    delta_i_cc = 1/M_cc * sum([S[j].M * S[j].delta_i for j in CC])
    delta_f_cc = 1/M_cc * sum([S[j].M * S[j].delta_f for j in CC])
    delta_i_nc = 1/M_nc * sum([S[j].M * S[j].delta_i for j in NC])
    delta_f_nc = 1/M_nc * sum([S[j].M * S[j].delta_f for j in NC])
    delta_i = delta_i_cc - delta_i_nc
    delta_f = delta_f_cc - delta_f_nc
    delta_f = 2*pi  # Formula above gives 0 (delta_f_nc should be -2*pi instead of 2*pi?)

    Pm = 1/M_T * (M_nc * sum([S[j].Pm for j in CC]) - M_cc * sum([S[j].Pm for j in NC]))

    C = D = 0
    for k in CC:
        for j in NC:
            C += (M_nc - M_cc) / M_T * g[k,j]
            D += b[k,j]

    Pc = 0
    for k in CC:
        for j in CC:
            Pc += M_nc/M_T * g[k,j]
    for k in NC:
        for j in NC:
            Pc -= M_cc/M_T * g[k,j]

    Pmax = (C**2 + D**2)**0.5
    angle_shift = -np.arctan2(C, D)

    return OMIBData(delta_i, delta_f, Pc, Pmax, Pm, angle_shift), M

def critical_angle_OMIB(OMIB_dur: OMIBData, OMIB_post: OMIBData):
    delta_step = 0.5 * pi/180
    delta_max = 2*pi
    dflag = 'first_swing'
    tflag = 'potentially_stable'
    direction = 1
    delta_0 = OMIB_dur.delta_i
    Pe, Pm = OMIB_power(OMIB_dur, delta_0)

    if Pm < Pe:
        dflag = 'backward-swing'
        direction = -1
        OMIB_dur.negate()
        OMIB_post.negate()

    delta = delta_0
    delta_return = delta_0
    delta_m = delta + delta_step

    if delta >= delta_max:
        return 1, 'always_unstable', delta_0, delta_max

    while delta < delta_max:
        A_dur = OMIB_area(OMIB_dur, delta_0, delta)
        while delta_m <= delta_max:
            A_post = OMIB_area(OMIB_post, delta, delta_m)
            if A_dur + A_post <= 0:
                delta_crit = direction * delta
                delta_return = delta_m
                break
            delta_m += delta_step

        if delta_m > delta_max:
            if delta == delta_0:
                tflag = 'always_unstable'
                delta_crit = delta_0
                delta_return = direction * delta_0
                break
            Pe, Pm = OMIB_power(OMIB_post, delta_return)
            if Pm <= Pe:
                tflag = 'potentially_stable'
                delta_crit = direction * delta
                delta_return = direction * delta_return
                break

        delta += delta_step
        delta_m = delta + delta_step

    if delta >= delta_max:
        tflag = 'always_stable'
        delta_crit = direction * delta_max
        delta_return = direction * delta_max

    return dflag, tflag, delta_crit, delta_return


def OMIB_power(OMIB: OMIBData, delta):
    Pe = OMIB.Pc + OMIB.Pmax * np.sin(delta - OMIB.angle_shift)
    Pm = OMIB.Pm
    return Pe, Pm


def OMIB_area(OMIB: OMIBData, delta_a, delta_b):
    return (OMIB.Pm - OMIB.Pc) * (delta_b - delta_a) + OMIB.Pmax * (np.cos(delta_b - OMIB.angle_shift) - np.cos(delta_a - OMIB.angle_shift))


def angle_to_time(OMIB: OMIBData, M, delta_f, delta_i, w_i):
    w0 = 2 * pi * BASEFREQUENCY
    Pe = OMIB.Pc + OMIB.Pmax * np.sin(delta_i - OMIB.angle_shift)
    gamma_der = w0/M * OMIB.Pmax * np.cos(delta_i - OMIB.angle_shift)  # Sign error in paper?
    gamma_der2 = - w0/M * OMIB.Pmax * np.sin(delta_i - OMIB.angle_shift)  # Sign error in paper?
    gamma_der3 = - gamma_der
    delta_der = w0 * w_i
    delta_der2 = w0/M * (OMIB.Pm - Pe)
    delta_der3 = gamma_der * delta_der
    delta_der4 = gamma_der2 * delta_der**2 + gamma_der * delta_der2
    delta_der5 = gamma_der3 * delta_der**3 + gamma_der * delta_der3 + 3 * gamma_der2 * delta_der2 * delta_der

    roots = np.roots([1/24 * delta_der4, 1/6 * delta_der3, 1/2 * delta_der2, delta_der, delta_i - delta_f])
    positive_real_roots = []
    for root in roots:
        if np.isreal(root) and np.real(root) > 0:
            positive_real_roots.append(np.real(root))

    if len(positive_real_roots) == 0:
        positive_real_roots.append(0)

    t_f = min(positive_real_roots)
    w_f = w_i + 1/w0 * (delta_der2 * t_f + 1/2 * delta_der3 * t_f**2 + 1/6 * delta_der4 * t_f**3 + 1/24 * delta_der5 * t_f**4)
    return t_f, w_f


def transient_screening(n: pp.network.Network, clearing_time, fault_location, disconnected_elements = []):
    """
    Return true if estimated CCT is smaller than 0.8 * the clearing time. Assumes all disconnected elements are disconnected at the clearing time
    """
    if NETWORK_NAME == 'Texas':
        return False, 0  # Takes too much computation time for a screening indicator, so skipped

    if fault_location is None:
        return True, 999

    CCT = extended_equal_area_criterion(n, fault_location, disconnected_elements)[0]
    return clearing_time < CCT - 0.05, CCT


def frequency_screening(n: pp.network.Network, disconnected_elements):
    """
    Returns False (insecure) if the power loss caused by the "disconnected elements" causes a RoCoF > 0.4Hz.s or loss higher than 70% of primary reserve.
    Also, returns said RoCoF
    """
    gens = n.get_generators()
    par_root = etree.parse('../3-DynData/{}.par'.format(NETWORK_NAME)).getroot()
    power_loss = 0
    total_inertia = 0
    reserves = 0

    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue

        if gen_id in disconnected_elements:
            power_loss += -gens.at[gen_id, 'p']
        else:
            p = -gens.at[gen_id, 'p']
            p_max = gens.at[gen_id, 'max_p']
            reserves += (p_max - p)

    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            continue
        if gens.at[gen_id, 'energy_source'] in ['SOLAR', 'WIND']:
            continue
        if gen_id in disconnected_elements:
            continue

        par_set = par_root.find("{{{}}}set[@id='{}']".format(DYNAWO_NAMESPACE, gen_id))
        if par_set is None:
            raise ValueError(gen_id, 'parameters not found')
        Snom = float(par_set.find("{{{}}}par[@name='generator_SNom']".format(DYNAWO_NAMESPACE)).get('value'))
        inertia = float(par_set.find("{{{}}}par[@name='generator_H']".format(DYNAWO_NAMESPACE)).get('value')) * Snom / BASEMVA
        total_inertia += Snom * inertia

    RoCoF = power_loss / (2 * total_inertia / BASEFREQUENCY)

    return RoCoF < 0.4 and power_loss < 0.7 * reserves, RoCoF, power_loss / reserves


if __name__ == '__main__':
    n = pp.network.load('/home/fsabot/Desktop/PDSA-RTS-GMLC/4-PDSA/simulations/year_Texas/8000/0/110126-111216_1_end1_DELAYED/Texas.iidm')
    # n = pp.network.load('/home/fsabot/Desktop/PDSA-RTS-GMLC/4-PDSA/simulations/year_RTS/2000/0/Base/RTS.iidm')
    print(voltage_screening(n, []))
    print(transient_screening(n, 0.15, 'V-240195_0', ['240195_NG_4']))
    # print(transient_screening(n, 0.15, 'V-121_0', ['121_NUCLEAR_1']))
    print(frequency_screening(n, ['240195_NG_4']))

    # TODO: could precompute some stuff. No, Z matrix takes 800Mo and need to save 8000 cases
    # TODO: compute Z_post first and modify it to get Z_pre and Z_dur (Z_dur with additional rule from course)
