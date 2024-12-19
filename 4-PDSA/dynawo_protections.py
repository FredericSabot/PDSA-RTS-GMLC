from common import *
if WITH_LXML:
    from lxml import etree
else:
    import xml.etree.ElementTree as etree
import pypowsybl as pp
from math import pi
import random
import pandas as pd


def add_protections(dyd_root, par_root, network: pp.network.Network, seed, protection_hidden_failures: list[str]):
    """
    Add all protection models to Dynawo input files
    """
    special = False
    if seed == 0:
        special = True

    CB_time = 0.08
    CB_max_error = 0.01  # +/- 10ms

    random.seed(seed)

    # Read iidm
    lines = network.get_lines()
    gens = network.get_generators()

    # Generator protections
    dyd_root.append(etree.Comment('Generator protections'))
    for gen_id in gens.index:
        if gens.at[gen_id, 'energy_source'] == 'SOLAR' or gens.at[gen_id, 'energy_source'] == 'WIND':
            continue  # Protection only for synchronous machines
        if not gens.at[gen_id, 'connected']:
            continue
        # Over-/under-speed protection
        add_gen_speed_protection(dyd_root, par_root, gen_id, CB_time, CB_max_error)
        # Under-voltage protection
        add_gen_UVA_protection(dyd_root, par_root, gen_id, CB_time, CB_max_error)
        # Out-of-step protection
        add_gen_OOS_protection(dyd_root, par_root, gen_id, CB_time, CB_max_error)

    # Under-frequency load shedding
    dyd_root.append(etree.Comment('Under-frequency load shedding'))
    add_UFLS(dyd_root, par_root, network)

    # Line/distance protection
    dyd_root.append(etree.Comment('Line protection'))
    bus2lines = get_buses_to_lines(network)
    lines_csv = pd.read_csv(f'../{NETWORK_NAME}-Data/branch.csv').to_dict()

    voltage_levels = network.get_voltage_levels()
    for i in range(len(lines_csv['UID'])):
        line_id = lines_csv['UID'][i]
        line_rating = lines_csv['Cont Rating'][i]
        if lines_csv['Tr Ratio'][i] != 0:
            continue  # Consider lines, not transformers

        if NETWORK_NAME == 'Texas':
            line_rating *= 1.5  # Necessary for OPF to converge during summer

        add_line_dist_protection(dyd_root, par_root, lines, voltage_levels, bus2lines, line_id, line_rating, CB_time, CB_max_error, special, protection_hidden_failures)
        add_line_overload_protection(dyd_root, par_root, lines, voltage_levels, line_id, line_rating)


def get_buses_to_lines(network):
    """
    Compute a dictionary where the keys are the bus ids of all buses in the network, and values are a list of all lines connected
    to said buses.
    """
    lines = network.get_lines()
    buses = network.get_buses()
    out = {}

    for bus_id in buses.index:
        out[bus_id] = []

    for line_id in lines.index:
        bus_1 = lines.at[line_id, 'bus1_id']
        bus_2 = lines.at[line_id, 'bus2_id']
        out[bus_1].append(line_id)
        out[bus_2].append(line_id)
    return out


def get_adjacent_lines(bus_to_lines, lines, line_id, side):
    """
    Get the list of lines that are connected to the side 'side' (1 or 2) or the line with ID 'line_id'. 'bus_to_lines' is the dict that
    maps buses to the lines that are connected to them (computed with function get_buses_to_lines(network))
    """
    common_bus = lines.at[line_id, 'bus{}_id'.format(side)]

    adj_lines = bus_to_lines[common_bus].copy()
    adj_lines.remove(line_id) # Remove the line itself from adjacent elements
    return adj_lines


def add_gen_speed_protection(dyd_root, par_root, gen_id, CB_time, CB_max_error, omega_max_error=0.01):
    """
    Add generator speed protection model to Dynawo input files
    """
    protection_id = gen_id + '_Speed'
    speed_attrib = {'id': protection_id, 'lib': 'SpeedProtection', 'parFile': NETWORK_NAME + '.par', 'parId': protection_id}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), speed_attrib)

    connect_attribs = [
        {'id1': protection_id, 'var1': 'speedProtection_omegaMonitoredPu', 'id2': gen_id, 'var2': 'generator_omegaPu_value'},
        {'id1': protection_id, 'var1': 'speedProtection_switchOffSignal', 'id2': gen_id, 'var2': 'generator_switchOffSignal2'}
    ]
    for connect_attrib in connect_attribs:
        etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    if RANDOMISE_DYN_DATA:
        rand_omegaMax = random.uniform(-omega_max_error, omega_max_error)
        rand_omegaMin = random.uniform(-omega_max_error, omega_max_error)
        rand_CB = random.uniform(-CB_max_error, CB_max_error)
    else:
        rand_omegaMax = 0
        rand_omegaMin = 0
        rand_CB = 0

    speed_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : protection_id})
    par_attribs = [
        {'type':'DOUBLE', 'name':'speedProtection_OmegaMaxPu', 'value':str(1.05 + rand_omegaMax)},
        {'type':'DOUBLE', 'name':'speedProtection_OmegaMinPu', 'value':str(0.95 + rand_omegaMin)},
        {'type':'DOUBLE', 'name':'speedProtection_tLagAction', 'value':str(0.02 + CB_time + rand_CB)}
    ]
    for par_attrib in par_attribs:
        etree.SubElement(speed_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)


def add_gen_UVA_protection(dyd_root, par_root, gen_id, CB_time, CB_max_error):
    """
    Add generator under-voltage protection model to Dynawo input files
    """
    protection_id = gen_id + '_UVA'
    uva_attrib = {'id': protection_id, 'lib': 'UnderVoltageAutomaton', 'parFile': NETWORK_NAME + '.par', 'parId': protection_id}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), uva_attrib)

    connect_attribs = [
        {'id1': protection_id, 'var1': 'underVoltageAutomaton_UMonitoredPu', 'id2': 'NETWORK', 'var2': '@' + gen_id + '@@NODE@_Upu_value'},
        {'id1': protection_id, 'var1': 'underVoltageAutomaton_switchOffSignal', 'id2': gen_id, 'var2': 'generator_switchOffSignal2'}
    ]
    for connect_attrib in connect_attribs:
        etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    if RANDOMISE_DYN_DATA:
        rand_UMin = random.uniform(-0.05, 0)
        rand_CB = random.uniform(-CB_max_error, CB_max_error)
    else:
        rand_UMin = 0
        rand_CB = 0

    uva_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : protection_id})
    par_attribs = [
        {'type':'DOUBLE', 'name':'underVoltageAutomaton_UMinPu', 'value':str(0.85 + rand_UMin)},
        {'type':'DOUBLE', 'name':'underVoltageAutomaton_tLagAction', 'value':str(1.5 + CB_time + rand_CB)}
    ]
    for par_attrib in par_attribs:
        etree.SubElement(uva_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)


def add_gen_OOS_protection(dyd_root, par_root, gen_id, CB_time, CB_max_error, angle_max_error=10):
    """
    Add generator out-of-step protection model to Dynawo input files
    """
    protection_id = gen_id + '_InternalAngle'
    oos_attrib = {'id': protection_id, 'lib': 'LossOfSynchronismProtection', 'parFile': NETWORK_NAME + '.par', 'parId': protection_id}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), oos_attrib)

    connect_attribs = [
        {'id1': protection_id, 'var1': 'lossOfSynchronismProtection_thetaMonitored',  'id2': gen_id, 'var2': 'generator_thetaInternal_value'},
        {'id1': protection_id, 'var1': 'lossOfSynchronismProtection_switchOffSignal', 'id2': gen_id, 'var2': 'generator_switchOffSignal2'}
    ]
    for connect_attrib in connect_attribs:
        etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    if RANDOMISE_DYN_DATA:
        rand_thetaMin = random.uniform(-angle_max_error, angle_max_error) * pi/180
        rand_CB = random.uniform(-CB_max_error, CB_max_error)
    else:
        rand_thetaMin = 0
        rand_CB = 0

    oos_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : protection_id})
    par_attribs = [
        {'type':'DOUBLE', 'name':'lossOfSynchronismProtection_ThetaMax', 'value':str(7/8 * pi + rand_thetaMin)},
        {'type':'DOUBLE', 'name':'lossOfSynchronismProtection_tLagAction', 'value':str(0.02 + CB_time + rand_CB)}
    ]
    for par_attrib in par_attribs:
        etree.SubElement(oos_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)


def add_UFLS(dyd_root, par_root, network):
    """
    Add under-frequency load shedding model to Dynawo input files
    """
    protection_id = 'UFLS'
    ufls_attrib = {'id': protection_id, 'lib': 'UFLS10Steps', 'parFile': NETWORK_NAME + '.par', 'parId': protection_id}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), ufls_attrib)

    connect_attribs = [
        {'id1': protection_id, 'var1': 'ufls_omegaMonitoredPu',  'id2': 'OMEGA_REF', 'var2': 'omegaRef_0_value'}
    ]
    loads = network.get_loads()
    for load_id in loads.index:
        if loads.at[load_id, 'p0'] != 0 or loads.at[load_id, 'q0'] != 0:  # Skip dummy loads
            connect_attribs += [
                {'id1': protection_id, 'var1': 'ufls_deltaPQfiltered', 'id2': load_id, 'var2': 'load_deltaP'},
                {'id1': protection_id, 'var1': 'ufls_deltaPQfiltered', 'id2': load_id, 'var2': 'load_deltaQ'}
            ]
    for connect_attrib in connect_attribs:
        etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    # UFLS parameters
    ufls_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : protection_id})
    par_attribs = [
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_0_', 'value':'0.1'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_1_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_2_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_3_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_4_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_5_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_6_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_7_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_8_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_UFLSStep_9_', 'value':'0.05'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_0_', 'value':'0.98'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_1_', 'value':'0.978'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_2_', 'value':'0.976'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_3_', 'value':'0.974'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_4_', 'value':'0.972'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_5_', 'value':'0.97'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_6_', 'value':'0.968'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_7_', 'value':'0.966'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_8_', 'value':'0.964'},
        {'type':'DOUBLE', 'name':'ufls_omegaThresholdPu_9_', 'value':'0.962'},
        {'type':'DOUBLE', 'name':'ufls_tLagAction', 'value':'0.1'}
    ]
    for par_attrib in par_attribs:
        etree.SubElement(ufls_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)


def add_line_dist_protection(dyd_root, par_root, lines, voltage_levels, bus2lines, line_id, line_rating, CB_time, CB_max_error, special,
                             protection_hidden_failures: list[str], measurement_max_error = 0.1):
    """
    Add line distance protection model to Dynawo input files
    """
    voltage_level = lines.at[line_id, 'voltage_level1_id']
    Ub = float(voltage_levels.at[voltage_level, 'nominal_v']) * 1000
    Sb = 100e6  # 100MW is the default base in Dynawo
    Zb = Ub**2/Sb

    if Ub < DISTANCE_PROTECTION_MINIMUM_VOLTAGE_LEVEL:
        return

    for side in [1,2]:
        opposite_side = 3-side  # 2 if side == 1, 1 if side == 2
        protection_id = line_id + '_side{}'.format(side) + '_Distance'
        lib = 'DistanceProtectionLineFourZonesWithBlinder'
        dist_attrib = {'id': protection_id, 'lib': lib, 'parFile': NETWORK_NAME + '.par', 'parId': protection_id}
        etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), dist_attrib)

        connect_attribs = [
            {'id1': protection_id, 'var1': 'distance_UMonitoredPu', 'id2': 'NETWORK', 'var2': line_id + '_U{}_value'.format(side)},
            {'id1': protection_id, 'var1': 'distance_PMonitoredPu', 'id2': 'NETWORK', 'var2': line_id + '_P{}_value'.format(side)},
            {'id1': protection_id, 'var1': 'distance_QMonitoredPu', 'id2': 'NETWORK', 'var2': line_id + '_Q{}_value'.format(side)},
            {'id1': protection_id, 'var1': 'distance_lineState', 'id2': 'NETWORK', 'var2': line_id + '_state'}
        ]
        for connect_attrib in connect_attribs:
            etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

        # Parameters
        dist_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : protection_id})

        X = lines.at[line_id, 'x'] / Zb
        # R = lines.at[line_id, 'r'] / Zb

        X1 = 0.8 * X
        R1 = X1

        adj_lines = get_adjacent_lines(bus2lines, lines, line_id, opposite_side)  # Only the adjacent lines that can be "seen" from a forward looking distance relay
        adj_lines_X = [lines.at[adj_line, 'x'] for adj_line in adj_lines]
        if not adj_lines_X: # is empty
            adj_lines_X = [0]
        max_adj_X = max(adj_lines_X) / Zb
        min_adj_X = min(adj_lines_X) / Zb

        X2 = max(0.9*(X + 0.85*min_adj_X), 1.15*X)
        R2 = X2

        X3 = (X + 1.15 * max_adj_X)
        R3 = X3

        X4 = X3 * 1.2  # X4 is only used to signal when apparent impedance is close to entering zone 3, not used for actual tripping
        R4 = R3 * 1.2

        # Load blinder taken as 1.5 times the nominal current at 0.85pu voltage with power factor of 30 degrees following NERC recommandations
        I_max = line_rating / 100
        blinder_reach = 0.85 / (1.5 * I_max)
        blinder_angle = 45 * (pi/180)  # 45 instead of 30 due to high reactive flows in some lines (mainly interconnections I believe)

        if adj_lines_X == [0]: # No adjacent lines
            X3 = 0  # Zone 2 and zone 3 would be identical -> remove zone 3
            R3 = 0
            X4 = 0
            R4 = 0

        if RANDOMISE_DYN_DATA:
            rand_measurement_ratio = 1 + random.uniform(-measurement_max_error, measurement_max_error)
            rand_CB = random.uniform(-CB_max_error, CB_max_error)
        else:
            rand_measurement_ratio = 1
            rand_CB = 0

        if special:
            par_attribs = [
                {'type':'INT', 'name':'distance_LineSide', 'value':str(side)},
                {'type':'DOUBLE', 'name':'distance_tZone_0_', 'value':str(0.3)},
                {'type':'DOUBLE', 'name':'distance_tZone_1_', 'value':str(0.3)},
                {'type':'DOUBLE', 'name':'distance_tZone_2_', 'value':str(0.6)},
                {'type':'DOUBLE', 'name':'distance_tZone_3_', 'value':str(0.6)},
                {'type':'DOUBLE', 'name':'distance_RPu_0_', 'value': str(R2 * (1 + measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_XPu_0_', 'value': str(X2 * (1 + measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_RPu_1_', 'value': str(R2 * (1 - measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_XPu_1_', 'value': str(X2 * (1 - measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_RPu_2_', 'value': str(R3 * (1 - measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_XPu_2_', 'value': str(X3 * (1 - measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_RPu_3_', 'value': str(R3 * (1 + measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_XPu_3_', 'value': str(X3 * (1 + measurement_max_error))},
                {'type':'DOUBLE', 'name':'distance_BlinderAnglePu', 'value': str(blinder_angle)},
                {'type':'DOUBLE', 'name':'distance_BlinderReachPu', 'value': str(blinder_reach)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_0_', 'value': str(CB_time - CB_max_error)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_1_', 'value': str(CB_time + CB_max_error)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_2_', 'value': str(CB_time + CB_max_error)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_3_', 'value': str(CB_time - CB_max_error)},
                {'type':'BOOL', 'name':'distance_TrippingZone_0_', 'value': 'false'},
                {'type':'BOOL', 'name':'distance_TrippingZone_1_', 'value': 'true'},
                {'type':'BOOL', 'name':'distance_TrippingZone_2_', 'value': 'true'},
                {'type':'BOOL', 'name':'distance_TrippingZone_3_', 'value': 'false'},
            ]
        else:
            par_attribs = [
                {'type':'INT', 'name':'distance_LineSide', 'value':str(side)},
                {'type':'DOUBLE', 'name':'distance_tZone_0_', 'value':'999999'},
                {'type':'DOUBLE', 'name':'distance_tZone_1_', 'value':str(0.3)},
                {'type':'DOUBLE', 'name':'distance_tZone_2_', 'value':str(0.6)},
                {'type':'DOUBLE', 'name':'distance_tZone_3_', 'value':'999999'},
                {'type':'DOUBLE', 'name':'distance_RPu_0_', 'value': str(R1 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_XPu_0_', 'value': str(X1 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_RPu_1_', 'value': str(R2 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_XPu_1_', 'value': str(X2 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_RPu_2_', 'value': str(R3 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_XPu_2_', 'value': str(X3 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_RPu_3_', 'value': str(R4 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_XPu_3_', 'value': str(X4 * rand_measurement_ratio)},
                {'type':'DOUBLE', 'name':'distance_BlinderAnglePu', 'value': str(blinder_angle)},
                {'type':'DOUBLE', 'name':'distance_BlinderReachPu', 'value': str(blinder_reach)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_0_', 'value': str(CB_time + rand_CB)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_1_', 'value': str(CB_time + rand_CB)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_2_', 'value': str(CB_time + rand_CB)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_3_', 'value': str(CB_time + rand_CB)},
                {'type':'BOOL', 'name':'distance_TrippingZone_0_', 'value': 'false'},
                {'type':'BOOL', 'name':'distance_TrippingZone_1_', 'value': 'true'},
                {'type':'BOOL', 'name':'distance_TrippingZone_2_', 'value': 'true'},
                {'type':'BOOL', 'name':'distance_TrippingZone_3_', 'value': 'false'},
            ]
        for par_attrib in par_attribs:
            etree.SubElement(dist_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)


        if WITH_HIDDEN_FAILURES:
            hidden_failure_id = protection_id + '_hidden_failure'
            for hidden_failure in protection_hidden_failures:
                if hidden_failure.startswith(protection_id):
                    hidden_failure_id += '_activated'

            dist_attrib = {'id': hidden_failure_id, 'lib': lib, 'parFile': NETWORK_NAME + '.par', 'parId': hidden_failure_id}
            etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), dist_attrib)

            connect_attribs = [
                {'id1': hidden_failure_id, 'var1': 'distance_UMonitoredPu', 'id2': 'NETWORK', 'var2': line_id + '_U{}_value'.format(side)},
                {'id1': hidden_failure_id, 'var1': 'distance_PMonitoredPu', 'id2': 'NETWORK', 'var2': line_id + '_P{}_value'.format(side)},
                {'id1': hidden_failure_id, 'var1': 'distance_QMonitoredPu', 'id2': 'NETWORK', 'var2': line_id + '_Q{}_value'.format(side)},
                {'id1': hidden_failure_id, 'var1': 'distance_lineState', 'id2': 'NETWORK', 'var2': line_id + '_state'}
            ]
            for connect_attrib in connect_attribs:
                etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

            # Parameters
            dist_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : hidden_failure_id})

            par_attribs = [
                {'type':'INT', 'name':'distance_LineSide', 'value':str(side)},
                {'type':'DOUBLE', 'name':'distance_tZone_0_', 'value':str(0.02)},
                {'type':'DOUBLE', 'name':'distance_tZone_1_', 'value':str(0.3)},
                {'type':'DOUBLE', 'name':'distance_tZone_2_', 'value':str(0.6)},
                {'type':'DOUBLE', 'name':'distance_tZone_3_', 'value':'999999'},
                {'type':'DOUBLE', 'name':'distance_RPu_0_', 'value': '0'}, # str(X1 * 3)},  # Z1 trips a bit too often
                {'type':'DOUBLE', 'name':'distance_XPu_0_', 'value': '0'}, # str(X1 * 3)},  # Z1 trips a bit too often
                {'type':'DOUBLE', 'name':'distance_RPu_1_', 'value': str(X2 * 3)},  # 10x the range because of wrong setting, but blinder should avoid tripping in normal operation
                {'type':'DOUBLE', 'name':'distance_XPu_1_', 'value': str(X2 * 3)},
                {'type':'DOUBLE', 'name':'distance_RPu_2_', 'value': str(R3 * 3)},
                {'type':'DOUBLE', 'name':'distance_XPu_2_', 'value': str(X3 * 3)},
                {'type':'DOUBLE', 'name':'distance_RPu_3_', 'value': '0'},
                {'type':'DOUBLE', 'name':'distance_XPu_3_', 'value': '0'},
                {'type':'DOUBLE', 'name':'distance_BlinderAnglePu', 'value': str(blinder_angle)},
                {'type':'DOUBLE', 'name':'distance_BlinderReachPu', 'value': str(blinder_reach)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_0_', 'value': str(CB_time)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_1_', 'value': str(CB_time)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_2_', 'value': str(CB_time)},
                {'type':'DOUBLE', 'name':'distance_CircuitBreakerTime_3_', 'value': str(CB_time)},
                {'type':'BOOL', 'name':'distance_TrippingZone_0_', 'value': 'false'},  # Do not actually trip
                {'type':'BOOL', 'name':'distance_TrippingZone_1_', 'value': 'false'},
                {'type':'BOOL', 'name':'distance_TrippingZone_2_', 'value': 'false'},
                {'type':'BOOL', 'name':'distance_TrippingZone_3_', 'value': 'false'},
            ]

            for hidden_failure in protection_hidden_failures:
                if hidden_failure.startswith(protection_id):
                    if hidden_failure.endswith('_Z1'):
                        par_attribs[-4] = {'type':'BOOL', 'name':'distance_TrippingZone_0_', 'value': 'true'}  # Activate hidden failure
                    elif hidden_failure.endswith('_Z2'):
                        par_attribs[-3] = {'type':'BOOL', 'name':'distance_TrippingZone_1_', 'value': 'true'}
                    elif hidden_failure.endswith('_Z3'):
                        par_attribs[-2] = {'type':'BOOL', 'name':'distance_TrippingZone_2_', 'value': 'true'}

            for par_attrib in par_attribs:
                etree.SubElement(dist_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)


def add_line_overload_protection(dyd_root, par_root, lines, voltage_levels, line_id, line_rating):
    """
    Add line distance protection model to Dynawo input files
    """
    voltage_level = lines.at[line_id, 'voltage_level1_id']
    Ub = float(voltage_levels.at[voltage_level, 'nominal_v']) * 1000

    if Ub >= DISTANCE_PROTECTION_MINIMUM_VOLTAGE_LEVEL:  # Use distance protection instead
        return

    protection_id = line_id + '_Overload'
    lib = 'CurrentLimitAutomaton'
    dist_attrib = {'id': protection_id, 'lib': lib, 'parFile': NETWORK_NAME + '.par', 'parId': protection_id}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), dist_attrib)

    connect_attribs = [
        {'id1': protection_id, 'var1': 'currentLimitAutomaton_IMonitored', 'id2': 'NETWORK', 'var2': line_id + '_iSide1'},
        {'id1': protection_id, 'var1': 'currentLimitAutomaton_order', 'id2': 'NETWORK', 'var2': line_id + '_state'},
        {'id1': protection_id, 'var1': 'currentLimitAutomaton_AutomatonExists', 'id2': 'NETWORK', 'var2': line_id + '_desactivate_currentLimits'}
    ]
    for connect_attrib in connect_attribs:
        etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    # Parameters
    dist_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : protection_id})
    P_max = 1.5 * line_rating
    I_max = (P_max * 1e6) / (Ub * 3**0.5)

    par_attribs = [

        {'type':'INT', 'name':'currentLimitAutomaton_OrderToEmit', 'value':'1'},
        {'type':'BOOL', 'name':'currentLimitAutomaton_Running', 'value':'true'},
        {'type':'DOUBLE', 'name':'currentLimitAutomaton_IMax', 'value':str(I_max)},
        {'type':'DOUBLE', 'name':'currentLimitAutomaton_tLagBeforeActing', 'value':'1'},
    ]

    for par_attrib in par_attribs:
        etree.SubElement(dist_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)
