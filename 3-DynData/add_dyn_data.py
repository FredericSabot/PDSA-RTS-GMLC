import pypowsybl as pp
import pandas as pd
from lxml import etree

"""
References
- Generator and exciter parameters:
    Vijay Vittal, James D. McCalley. Power System Control
    and Stability, third edition. Annex D "Typical System Data"
- Hydro governor: Y. Wang, W. Li and J. Lu, "Reliability Analysis of Wide-Area
    Measurement System," in IEEE Transactions on Power Delivery, vol. 25, no. 3,
    pp. 1483-1491, July 2010, doi: 10.1109/TPWRD.2010.2041797.
- Steam governor; default IEEEG1 parameters
- Generic inverter-based generation models: Gilles Chaspierre's PhD thesis
"""

def unit_group_translation(network_name, unit_group, P_max):
    if network_name == 'RTS':
        match unit_group:
            case 'PV':
                return 'PV'
            case 'RTPV':
                return 'RTPV'
            case 'WIND':
                return 'Wind'
            case 'Sync_Cond':
                return 'Syncon'
            case 'U12':
                return 'Oil_12'
            case 'U20':
                return 'Oil_20'
            case 'U50':
                return 'Hydro_50'
            case 'U55':
                return 'CT_55'
            case 'U76':
                return 'Coal_76'
            case 'U155':
                return 'Coal_155'
            case 'U350':
                return 'Coal_350'
            case 'U355':
                return 'CC_355'
            case 'U400':
                return 'Nuclear_400'
            case _:
                raise NotImplementedError(unit_group, 'is not considered')

    elif network_name == 'Texas':
        match unit_group:
            case 'PV':
                return 'PV'
            case 'Wind':
                return 'Wind'
            case 'Oil':
                if P_max < 15:
                    return 'Oil_12'
                else:
                    return 'Oil_20'
            case 'Hydro':
                return 'Hydro_50'
            case 'Coal':
                if P_max < 100:
                    return 'Coal_76'
                elif P_max < 250:
                    return 'Coal_155'
                else:
                    return 'Coal_350'
            case 'NG':
                if P_max < 100:
                    return 'CT_55'
                elif P_max < 200:
                    return 'CC_150'
                else:
                    return 'CC_355'
            case 'Nuclear':
                return 'Nuclear_400'
            case _:
                raise NotImplementedError(unit_group, 'is not considered')
    else:
        raise NotImplementedError(network_name, 'is not considered')


def select_gfm_generators(network_name, buses_csv, gens_csv, gens, min_gfm_share_per_area = 0.4):
    """
    Select a minimum number of inverter-based generators to be set to grid-forming mode such that the share of grid-forming units (considering
    both GFM inverters and synchronous machines) is higher than min_gfm_share_per_area
    """
    gfm_generators = []
    if network_name == 'RTS':
        return []
    elif network_name == 'Texas':
        pass
    else:
        raise NotImplementedError()

    buses_to_area = {}
    area_list = []
    for i in range(len(buses_csv['Bus ID'])):
        bus_id = buses_csv['Bus ID'][i]
        area = buses_csv['Area'][i]

        if network_name == 'Texas':
            if area == 2:
                longitude = buses_csv['lng'][i]
                if longitude > -98:
                    area = 5  # Area 2 is too spread out for the purpose of guaranteeing minimum level of inertia per zone, makes more sense to merge its east side with area 5 (that is closer electrically/geographically)

            # Manually fixes buses with obviously incorrect area
            if bus_id in [23, 174, 175, 176]:
                area = 8
            if bus_id in [32, 207, 208, 209, 210]:
                area = 4
            if bus_id in [67, 340, 341, 342]:
                area = 7

        buses_to_area[bus_id] = area
        if area not in area_list:
            area_list.append(area)

    generators_per_area = {area: [] for area in area_list}
    generators_per_area_synchronous = {area: [] for area in area_list}
    generators_per_area_inverter = {area: [] for area in area_list}

    N_gens = len(gens_csv['GEN UID'])
    for i in range(N_gens):
        unit_group = gens_csv['Unit Group'][i]
        unit_group = unit_group_translation(network_name, unit_group, gens_csv['PMax MW'][i])
        gen_id = gens_csv['GEN UID'][i]

        if not gens.at[gen_id, 'connected']:
            continue

        bus_id = gens_csv['Bus ID'][i]
        area = buses_to_area[bus_id]

        generators_per_area[area].append(gen_id)
        if unit_group == 'PV' or unit_group == 'RTPV' or unit_group == 'Wind':
            generators_per_area_inverter[area].append(gen_id)
        else:
            generators_per_area_synchronous[area].append(gen_id)

    for area in area_list:
        total_capacity = 0
        total_gfm_capacity = 0

        for gen_id in generators_per_area_synchronous[area]:
            s = gens.at[gen_id, 'rated_s']
            total_capacity += s
            total_gfm_capacity += s
        for gen_id in generators_per_area_inverter[area]:
            s = gens.at[gen_id, 'rated_s']
            total_capacity += s

        gfm_capacity_to_add = total_capacity * min_gfm_share_per_area - total_gfm_capacity

        for gen_id in sorted(generators_per_area_inverter[area], key=lambda id: gens.at[id, 'rated_s'] , reverse=True):
            if gfm_capacity_to_add < 0:
                break
            if gen_id in ['186_PV_2', '134_WIND_1', '135_WIND_2', '245_WIND_1', '246_WIND_2', '247_WIND_3', '248_WIND_4']:  # These generators tend to cause issues when operated as GFM
                continue
            s = gens.at[gen_id, 'rated_s']
            gfm_capacity_to_add -= s
            gfm_generators.append(gen_id)

    return gfm_generators


def add_dyn_data(network_name, network: pp.network.Network, dyd_root, par_root, namespace, motor_share = 0.3, contingency_minimum_voltage_level = 0):
    # Loads
    loads = network.get_loads()
    voltage_levels = network.get_voltage_levels()
    for loadID in loads.index:
        if abs(loads.at[loadID, 'p']) <= 1e-3 and abs(loads.at[loadID, 'q']) <= 1e-3:  # Dummy load
            voltage_level = loads.at[loadID, 'voltage_level_id']
            Ub = float(voltage_levels.at[voltage_level, 'nominal_v'])
            if Ub < contingency_minimum_voltage_level:  # Dummy loads are only useful to make the bus they are connected to "connectable" such that Dynawo can apply faults on them. They do not need to be added if no faults will be performed on their bus (reduces number of variables in dynamic simulation)
                continue

            load_attrib = {'id': 'Dummy_' +  loadID, 'lib': 'LoadAlphaBeta', 'parFile': network_name + '.par', 'parId': 'DummyLoad', 'staticId': loadID}
            loadID = 'Dummy_' + loadID
        else:
            if motor_share != 0:
                load_attrib = {'id': loadID, 'lib': 'LoadAlphaBetaMotorSimplified', 'parFile': network_name + '.par', 'parId': 'GenericLoadAlphaBetaMotor', 'staticId': loadID}
            else:
                load_attrib = {'id': loadID, 'lib': 'LoadAlphaBeta', 'parFile': network_name + '.par', 'parId': 'GenericLoadAlphaBetaMotor', 'staticId': loadID}
        load = etree.SubElement(dyd_root, etree.QName(namespace, 'blackBoxModel'), load_attrib)

        etree.SubElement(load, etree.QName(namespace, 'macroStaticRef'), {'id': 'LOAD'})
        etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': loadID, 'id2': 'NETWORK', 'connector': 'LOAD-CONNECTOR'})

        if 'Motor' in  load_attrib['lib']:
            etree.SubElement(dyd_root, etree.QName(namespace, 'connect'), {'id1': loadID, 'var1': 'load_omegaRefPu', 'id2': 'OMEGA_REF', 'var2': 'omegaRef_0'})

    motor_par_set = etree.SubElement(par_root, etree.QName(namespace, 'set'), {'id' : 'GenericLoadAlphaBetaMotor'})
    par_attribs = [
        {'type': 'DOUBLE', 'name': 'load_alpha', 'value': '2'},
        {'type': 'DOUBLE', 'name': 'load_beta', 'value': '2'},
        {'type': 'DOUBLE', 'name': 'load_Alpha', 'value': '2.0'},
        {'type': 'DOUBLE', 'name': 'load_Beta', 'value': '2.0'},
        {'type': 'DOUBLE', 'name': 'load_ActiveMotorShare_0_', 'value': str(motor_share)},
        {'type': 'DOUBLE', 'name': 'load_RrPu_0_', 'value': '0.02'},
        {'type': 'DOUBLE', 'name': 'load_RsPu_0_', 'value': '0.02'},
        {'type': 'DOUBLE', 'name': 'load_XmPu_0_', 'value': '4.0'},
        {'type': 'DOUBLE', 'name': 'load_XrPu_0_', 'value': '0.1'},
        {'type': 'DOUBLE', 'name': 'load_XsPu_0_', 'value': '0.1'},
        {'type': 'DOUBLE', 'name': 'load_H_0_', 'value': '1.5'},
        {'type': 'DOUBLE', 'name': 'load_torqueExponent_0_', 'value': '0'},
    ]
    for par_attrib in par_attribs:
        etree.SubElement(motor_par_set, etree.QName(namespace, 'par'), par_attrib)

    references = [
        {'name': 'load_P0Pu', 'origData': 'IIDM', 'origName': 'p_pu', 'type': 'DOUBLE'},
        {'name': 'load_Q0Pu', 'origData': 'IIDM', 'origName': 'q_pu', 'type': 'DOUBLE'},
        {'name': 'load_U0Pu', 'origData': 'IIDM', 'origName': 'v_pu', 'type': 'DOUBLE'},
        {'name': 'load_UPhase0', 'origData': 'IIDM', 'origName': 'angle_pu', 'type': 'DOUBLE'},
    ]
    for ref in references:
        etree.SubElement(motor_par_set, etree.QName(namespace, 'reference'), ref)


    # Omegaref
    omega_attrib = {'id': 'OMEGA_REF', 'lib': 'DYNModelOmegaRef', 'parFile': network_name + '.par', 'parId': 'OmegaRef'}
    etree.SubElement(dyd_root, etree.QName(namespace, 'blackBoxModel'), omega_attrib)
    omega_par_set = etree.SubElement(par_root, etree.QName(namespace, 'set'), {'id' : 'OmegaRef'})


    gens_csv = pd.read_csv(f'../{network_name}-Data/gen.csv').to_dict()
    buses_csv = pd.read_csv(f'../{network_name}-Data/bus.csv').to_dict()
    N_gens = len(gens_csv['GEN UID'])
    omega_index = 0
    gens = network.get_generators()
    vl = network.get_voltage_levels()
    gfm_generators = select_gfm_generators(network_name, buses_csv, gens_csv, gens, min_gfm_share_per_area=0.4)

    for i in range(N_gens):
        unit_group = gens_csv['Unit Group'][i]
        unit_group = unit_group_translation(network_name, unit_group, gens_csv['PMax MW'][i])
        genID = gens_csv['GEN UID'][i]

        if not gens.at[genID, 'connected']:
            continue

        if (unit_group == 'PV' or unit_group == 'RTPV') and gens.at[genID, 'max_p'] == 0:  # Turn of PV at night (and dawn and morning)
            continue

        if unit_group == 'PV' or unit_group == 'RTPV':
            lib = 'GenericIBG'
            synchronous = False
        elif unit_group == 'Wind':
            lib = 'GenericIBG'
            synchronous = False
        elif unit_group == 'Syncon':
            lib = 'GeneratorSynchronousThreeWindingsRtsSyncon'
            synchronous = True
        elif unit_group == 'Hydro_50':
            lib = 'GeneratorSynchronousThreeWindingsRtsHydro'
            synchronous = True
        else:
            lib = 'GeneratorSynchronousFourWindingsRtsThermal'
            synchronous = True

        GFM = False
        if network_name == 'Texas':
            if genID in gfm_generators:
                GFM = True
                lib = 'GridFormingConverterDroopControl'  # Note: P is only limited by the converter rating (through virtual impedance), so it can be higher than available power (pv or wind source) after a transient. This assumes an energy buffer sufficient for the simulated period.

        gen_attrib = {'id': genID, 'lib': lib, 'parFile': network_name + '.par', 'parId': genID, 'staticId': genID}
        gen = etree.SubElement(dyd_root, etree.QName(namespace, 'blackBoxModel'), gen_attrib)

        if synchronous:
            etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'OMEGA_REF', 'connector': 'MS_OMEGAREF_CONNECTOR', 'index2': str(omega_index)})
            etree.SubElement(gen, etree.QName(namespace, 'macroStaticRef'), {'id': 'GEN'})
            etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'NETWORK', 'connector': 'GEN-CONNECTOR'})
        else:
            if GFM:
                etree.SubElement(gen, etree.QName(namespace, 'macroStaticRef'), {'id': 'GFM'})
                etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'NETWORK', 'connector': 'GFM-CONNECTOR'})
                etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'OMEGA_REF', 'connector': 'OmegaRefToGFM', 'index2': str(omega_index)})
                etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': 'OMEGA_REF', 'id2': 'NETWORK', 'connector': 'OmegaRefToNumCCMachine', 'index1': str(omega_index), 'name2': genID})
            elif unit_group == 'PV' or unit_group == 'RTPV' or unit_group == 'Wind':
                etree.SubElement(dyd_root, etree.QName(namespace, 'connect'), {'id1': genID, 'var1': 'ibg_omegaRefPu', 'id2': 'OMEGA_REF', 'var2': 'omegaRef_0_value'})
                etree.SubElement(gen, etree.QName(namespace, 'macroStaticRef'), {'id': 'PV'})
                etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'NETWORK', 'connector': 'PV-CONNECTOR'})
            else:
                raise NotImplemented(unit_group, 'is not considered')

        p_max = gens.at[genID, 'max_p']
        q_max = gens.at[genID, 'max_q']
        SNom = gens.at[genID, 'rated_s']
        p_min = gens.at[genID, 'min_p']
        u_nom = vl['nominal_v'][gens['voltage_level_id'][genID]]

        gen_par_set = etree.SubElement(par_root, etree.QName(namespace, 'set'), {'id' : genID})

        if synchronous:
            par_attribs = [
                {'type': 'BOOL', 'name': 'generator_UseApproximation', 'value': 'false'},
                {'type': 'INT', 'name': 'generator_ExcitationPu', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'generator_md', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'generator_mq', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'generator_nd', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'generator_nq', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'generator_MdPuEfd', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'generator_DPu', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'generator_UNom', 'value': str(u_nom)},
                {'type': 'DOUBLE', 'name': 'generator_PNomTurb', 'value': str(max(p_max, 1))},  # Avoid div by 0 for syncons
                {'type': 'DOUBLE', 'name': 'generator_PNomAlt', 'value': str(max(p_max, 1))},
                {'type': 'DOUBLE', 'name': 'generator_UNomHV', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'generator_UNomLV', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'generator_UBaseHV', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'generator_UBaseLV', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'generator_RTfPu', 'value': '0.0'},
                {'type': 'DOUBLE', 'name': 'generator_XTfPu', 'value': '0.0'},
            ]
            if unit_group == 'Hydro_50':
                pf = 0.9
                par_attribs += [  # Reference machine H6 from Vijay Vittal book
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'generator_H', 'value': str(168/54)},
                    {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.340'},
                    {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.380'},
                    {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.130'},
                    {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.340'},
                    {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '0.680'},
                    {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.0049'},
                    {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.210'},
                    {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.041'},
                    {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '8.5'},
                    {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.06'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.001'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '25'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.2'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '1'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '-1'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '-0.057'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '0.646'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 3.480)},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '3.480'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.0885'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.3480'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0.103'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '1.00'},
                ]
                par_attribs += [
                    {'type': 'DOUBLE', 'name': 'governor_PNomTurb', 'value': str(p_max)},
                    {'type': 'DOUBLE', 'name': 'governor_SNom', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'governor_At', 'value': '1.1'},
                    {'type': 'DOUBLE', 'name': 'governor_DTurb', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'governor_FlowNoLoad', 'value': '0.08'},
                    {'type': 'DOUBLE', 'name': 'governor_KDroopPerm', 'value': '0.05'},
                    {'type': 'DOUBLE', 'name': 'governor_KDroopTemp', 'value': '0.3'},
                    {'type': 'DOUBLE', 'name': 'governor_OpeningGateMax', 'value': '1'},
                    {'type': 'DOUBLE', 'name': 'governor_OpeningGateMin', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'governor_VelMax', 'value': '0.2'},
                    {'type': 'DOUBLE', 'name': 'governor_tF', 'value': '0.05'},
                    {'type': 'DOUBLE', 'name': 'governor_tG', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'governor_tR', 'value': '5.2'},
                    {'type': 'DOUBLE', 'name': 'governor_tW', 'value': '1.3'},
                ]
            elif unit_group == 'Syncon':
                par_attribs += [  # Reference machine SC5 from Vijay Vittal book
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'generator_H', 'value': '4.5'},  # Use higher value than the SC5 reference machine (that only has H=1.1s)
                    {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.170'},
                    {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.320'},
                    {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.560'},
                    {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.200'},
                    {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '1.00'},
                    {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.0017'},
                    {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.0987'},
                    {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.039'},
                    {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '16.00'},
                    {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.235'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.001'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '18'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.2'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '1'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '-1'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '-0.0138'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '0.0669'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 7.270)},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '7.270'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.0634'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.1512'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0.0153'},
                    {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '1.00'},
                ]
            else:  # Thermal unit
                par_attribs += [  # Default parameters of IEEEG1
                    {'type': 'DOUBLE', 'name': 'governor_DerPMaxPu', 'value': '1'},
                    {'type': 'DOUBLE', 'name': 'governor_DerPMinPu', 'value': '-10'},
                    {'type': 'DOUBLE', 'name': 'governor_K', 'value': '25'},
                    {'type': 'DOUBLE', 'name': 'governor_K1', 'value': '0.2'},
                    {'type': 'DOUBLE', 'name': 'governor_K2', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'governor_K3', 'value': '0.3'},
                    {'type': 'DOUBLE', 'name': 'governor_K4', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'governor_K5', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'governor_K6', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'governor_K7', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'governor_K8', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'governor_PMinPu', 'value': str(p_min / p_max)},
                    {'type': 'DOUBLE', 'name': 'governor_PMaxPu', 'value': '1'},
                    {'type': 'DOUBLE', 'name': 'governor_PNomTurb', 'value': '1'},  # Base, might be removed from the model
                    {'type': 'DOUBLE', 'name': 'governor_SNom', 'value': '1'},  # Base, might be removed from the model
                    {'type': 'DOUBLE', 'name': 'governor_t1', 'value': '0.001'},
                    {'type': 'DOUBLE', 'name': 'governor_t2', 'value': '0.001'},
                    {'type': 'DOUBLE', 'name': 'governor_t3', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'governor_t4', 'value': '0.3'},
                    {'type': 'DOUBLE', 'name': 'governor_t5', 'value': '5'},
                    {'type': 'DOUBLE', 'name': 'governor_t6', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'governor_t7', 'value': '0.001'},
                ]
                if unit_group == 'Oil_12' or unit_group == 'Oil_20':  # Reference machine F1 from Vijay Vittal book
                    pf = 0.8
                    par_attribs +=[
                        {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_H', 'value': str(125.4/25)},
                        {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.120'},
                        {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.232'},
                        {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.250'},
                        {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.120'},
                        {'type': 'DOUBLE', 'name': 'generator_XpqPu', 'value': '0.715'},
                        {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '1.220'},
                        {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.0014'},
                        {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.134'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.059'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '4.750'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.21'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpq0', 'value': '1.500'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.001'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '20'},  # Note Ka and tA are swapped in book
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.050'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '6.812'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '0'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '1'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '0.700'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 3.567)},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '3.567'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.414'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.908'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '1.00'},
                    ]
                elif unit_group == 'CT_55':  # Reference machine CT2 from Vijay Vittal book
                    pf = 0.85
                    par_attribs +=[
                        {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_H', 'value': str(713.5/62.5)},
                        {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.102'},
                        {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.159'},
                        {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.640'},
                        {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.100'},
                        {'type': 'DOUBLE', 'name': 'generator_XpqPu', 'value': '0.306'},
                        {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '1.575'},
                        {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.034'},
                        {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.113'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.054'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '7.50'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.1'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpq0', 'value': '1.500'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.001'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '400'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.020'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '7.300'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '-7.300'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '1'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '0.253'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 7.300)},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '7.300'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.500'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.860'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0.03'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '1.00'},
                    ]
                elif unit_group == 'Coal_76':  # Reference machine F4 from Vijay Vittal book
                    pf = 0.8
                    par_attribs +=[
                        {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_H', 'value': str(464/75)},
                        {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.130'},
                        {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.185'},
                        {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.050'},
                        {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.130'},
                        {'type': 'DOUBLE', 'name': 'generator_XpqPu', 'value': '0.360'},
                        {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '0.980'},
                        {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.0031'},
                        {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.070'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.038'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '6.10'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.099'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpq0', 'value': '0.30'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.001'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '20'},  # Note Ka and tA inversed in book
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.050'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '4.380'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '0'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '1'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '1.980'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 3.180)},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '3.180'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.0967'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.3774'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '1.00'},
                    ]
                elif unit_group == 'Coal_155' or 'CC_150':  # Reference machine F8 from Vijay Vittal book (no data on combined cycle gas turbines)
                    pf = 0.85
                    par_attribs +=[
                        {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_H', 'value': str(634/160)},
                        {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.185'},
                        {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.245'},
                        {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.700'},
                        {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.185'},
                        {'type': 'DOUBLE', 'name': 'generator_XpqPu', 'value': '0.380'},
                        {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '1.640'},
                        {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.0031'},
                        {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.110'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.033'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '5.900'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.076'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpq0', 'value': '0.540'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.060'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '25'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.2'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '1'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '-1'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '-0.0497'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '0.560'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 4.02)},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '4.02'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.0765'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.2985'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0.0896'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '0.35'},
                    ]
                elif unit_group == 'Coal_350' or unit_group == 'CC_355':  # Reference machine F13 from Vijay Vittal book (no data on combined cycle gas turbines)
                    pf = 0.85
                    par_attribs +=[
                        {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_H', 'value': str(1006.5/384)},
                        {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.260'},
                        {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.324'},
                        {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.798'},
                        {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.255'},
                        {'type': 'DOUBLE', 'name': 'generator_XpqPu', 'value': '1.051'},
                        {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '1.778'},
                        {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.0014'},
                        {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.1930'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.042'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '5.210'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.042'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpq0', 'value': '1.50'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.001'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '400'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.2'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '8.130'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '-8.130'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '1'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '0.812'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 4.91)},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '4.91'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.459'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.656'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0.060'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '1'},
                    ]
                elif unit_group == 'Nuclear_400':  # Reference machine N3 from Vijay Vittal book
                    pf = 0.90
                    par_attribs +=[
                        {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                        {'type': 'DOUBLE', 'name': 'generator_H', 'value': str(1990/500)},
                        {'type': 'DOUBLE', 'name': 'generator_XppdPu', 'value': '0.283'},
                        {'type': 'DOUBLE', 'name': 'generator_XpdPu', 'value': '0.444'},
                        {'type': 'DOUBLE', 'name': 'generator_XdPu', 'value': '1.782'},
                        {'type': 'DOUBLE', 'name': 'generator_XppqPu', 'value': '0.277'},
                        {'type': 'DOUBLE', 'name': 'generator_XpqPu', 'value': '1.201'},
                        {'type': 'DOUBLE', 'name': 'generator_XqPu', 'value': '1.739'},
                        {'type': 'DOUBLE', 'name': 'generator_RaPu', 'value': '0.0041'},
                        {'type': 'DOUBLE', 'name': 'generator_XlPu', 'value': '0.275'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppd0', 'value': '0.055'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpd0', 'value': '6.070'},
                        {'type': 'DOUBLE', 'name': 'generator_Tppq0', 'value': '0.152'},
                        {'type': 'DOUBLE', 'name': 'generator_Tpq0', 'value': '1.50'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tR', 'value': '0.001'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ka', 'value': '256'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tA', 'value': '0.05'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMaxPu', 'value': '2.858'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdRawMinPu', 'value': '-2.858'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Ke', 'value': '-0.170'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tE', 'value': '2.150'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdLowPu', 'value': str(0.75 * 3.665)},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdHighPu', 'value': '3.665'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatLowPu', 'value': '0.22'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_EfdSatHighPu', 'value': '0.95'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_Kf', 'value': '0.040'},
                        {'type': 'DOUBLE', 'name': 'voltageRegulator_tF', 'value': '1'},
                    ]
                else:
                    raise NotImplementedError(unit_group, 'not considered')


            for par_attrib in par_attribs:
                etree.SubElement(gen_par_set, etree.QName(namespace, 'par'), par_attrib)

            references = [
                {'name': 'generator_P0Pu', 'origData': 'IIDM', 'origName': 'p_pu', 'type': 'DOUBLE'},
                # Use targetQ instead of Q because Powsybl sets the same Q for all generators of a bus irrespective of the generator sizes
                {'name': 'generator_Q0Pu', 'origData': 'IIDM', 'origName': 'targetQ_pu', 'type': 'DOUBLE'},
                {'name': 'generator_U0Pu', 'origData': 'IIDM', 'origName': 'v_pu', 'type': 'DOUBLE'},
                {'name': 'generator_UPhase0', 'origData': 'IIDM', 'origName': 'angle_pu', 'type': 'DOUBLE'},
            ]
            for ref in references:
                etree.SubElement(gen_par_set, etree.QName(namespace, 'reference'), ref)

            etree.SubElement(omega_par_set, etree.QName(namespace, 'par'), {'type': 'DOUBLE', 'name': 'weight_gen_' + str(omega_index), 'value': str(max(p_max, q_max))})  # Use q_max instead of p_max for syncons
            omega_index += 1

        else:  # Not synchronous (PV, wind, RTPV)
            if GFM:
                etree.SubElement(omega_par_set, etree.QName(namespace, 'par'), {'type': 'DOUBLE', 'name': 'weight_gen_' + str(omega_index), 'value': str(max(p_max, q_max))})  # Use q_max instead of p_max for syncons/statcoms
                omega_index += 1

                par_attribs = [  # Parameters from Dynawo grid forming example
                    {'type': 'DOUBLE', 'name': 'converter_SNom', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'converter_Cdc', 'value': '0.01'},
                    {'type': 'DOUBLE', 'name': 'converter_RFilter', 'value': '0.005'},
                    {'type': 'DOUBLE', 'name': 'converter_LFilter', 'value': '0.1'},  # Reduced to not limit transfer capacity
                    {'type': 'DOUBLE', 'name': 'converter_CFilter', 'value': '0.066'},
                    {'type': 'DOUBLE', 'name': 'converter_RTransformer', 'value': '0.01'},
                    {'type': 'DOUBLE', 'name': 'converter_LTransformer', 'value': '0.1'},  # Transformer already modelled in the static data, so reduced to not limit transfer capacity too much (still non-zero because the transformer inductance is modelled in a dynamic way (U = L der(i)) in the dynamic model but not in the static data (U = Z I))
                    {'type': 'DOUBLE', 'name': 'control_KpVI', 'value': '0.67'},
                    {'type': 'DOUBLE', 'name': 'control_XRratio', 'value': '5'},
                    {'type': 'DOUBLE', 'name': 'control_Kpc', 'value': '0.7388'},
                    {'type': 'DOUBLE', 'name': 'control_Kic', 'value': '1.19'},
                    {'type': 'DOUBLE', 'name': 'control_Kpv', 'value': '0.52'},
                    {'type': 'DOUBLE', 'name': 'control_Kiv', 'value': '1.161022'},
                    {'type': 'DOUBLE', 'name': 'control_Mq', 'value': '0.000'},
                    {'type': 'DOUBLE', 'name': 'control_Wf', 'value': '60'},
                    {'type': 'DOUBLE', 'name': 'control_Mp', 'value': '0.02'},
                    {'type': 'DOUBLE', 'name': 'control_Wff', 'value': '16.66'},
                    {'type': 'DOUBLE', 'name': 'control_Kff', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'control_RFilter', 'value': '0.005'},
                    {'type': 'DOUBLE', 'name': 'control_LFilter', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'control_CFilter', 'value': '0.066'},
                    {'type': 'DOUBLE', 'name': 'control_Kpdc', 'value': '50'},
                    {'type': 'DOUBLE', 'name': 'control_IMaxVI', 'value': '1.5'}
                ]

                references = [
                    {'name': 'converter_P0Pu', 'origData': 'IIDM', 'origName': 'p_pu', 'type': 'DOUBLE'},
                    # Use targetQ instead of Q because Powsybl sets the same Q for all generators of a bus irrespective of the generator sizes
                    {'name': 'converter_Q0Pu', 'origData': 'IIDM', 'origName': 'targetQ_pu', 'type': 'DOUBLE'},
                    {'name': 'converter_U0Pu', 'origData': 'IIDM', 'origName': 'v_pu', 'type': 'DOUBLE'},
                    {'name': 'converter_UPhase0', 'origData': 'IIDM', 'origName': 'angle_pu', 'type': 'DOUBLE'},
                ]

            elif unit_group == 'Wind':
                par_attribs = [  # Typical parameters from Gilles Chaspierre's PhD thesis
                    {'type': 'DOUBLE', 'name': 'ibg_IMaxPu', 'value': '1.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_UQPrioPu', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_US1', 'value': '0.94'},
                    {'type': 'DOUBLE', 'name': 'ibg_US2', 'value': '1.06'},
                    {'type': 'DOUBLE', 'name': 'ibg_kRCI', 'value': '2.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_kRCA', 'value': '-2.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_m', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_n', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_tG', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_Tm', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_IpSlewMaxPu', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_IqSlewMaxPu', 'value': '5'},
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTMin', 'value': '0.14'},  # LVRT from ENA EREC G99
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTInt', 'value': '0.14'},
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTMax', 'value': '2.2'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTMinPu', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTIntPu', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTArmingPu', 'value': '0.85'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaMaxPu', 'value': '1.05'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaDeadBandPu', 'value': '1.01'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaMinPu', 'value': '0.95'},
                    {'type': 'DOUBLE', 'name': 'ibg_tFilterOmega', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_tFilterU', 'value': '0.01'},
                    {'type': 'DOUBLE', 'name': 'ibg_UMaxPu', 'value': '1.4'},  # Original: 1.2, increased because of overvoltages caused by plant itself, requires better modelling
                    {'type': 'DOUBLE', 'name': 'ibg_UPLLFreezePu', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_Ki', 'value': '20'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_Kp', 'value': '3'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_', 'value': '3'},
                    {'type': 'DOUBLE', 'name': 'ibg_SNom', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'ibg_tf', 'value': '0.1'},
                ]

                if network_name == 'RTS':
                    par_attribs += [{'type': 'DOUBLE', 'name': 'ibg_Kf', 'value': '0.5'}]
                else:
                    par_attribs += [{'type': 'DOUBLE', 'name': 'ibg_Kf', 'value': '0'}]


                references = [
                    {'name': 'ibg_P0Pu', 'origData': 'IIDM', 'origName': 'p_pu', 'type': 'DOUBLE'},
                    # Use targetQ instead of Q because Powsybl sets the same Q for all generators of a bus irrespective of the generator sizes
                    {'name': 'ibg_Q0Pu', 'origData': 'IIDM', 'origName': 'targetQ_pu', 'type': 'DOUBLE'},
                    {'name': 'ibg_U0Pu', 'origData': 'IIDM', 'origName': 'v_pu', 'type': 'DOUBLE'},
                    {'name': 'ibg_UPhase0', 'origData': 'IIDM', 'origName': 'angle_pu', 'type': 'DOUBLE'},
                ]

            elif unit_group == 'PV':
                par_attribs = [  # Typical parameters from Gilles Chaspierre's PhD thesis
                    {'type': 'DOUBLE', 'name': 'ibg_IMaxPu', 'value': '1.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_UQPrioPu', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_US1', 'value': '0.9'},
                    {'type': 'DOUBLE', 'name': 'ibg_US2', 'value': '1.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_kRCI', 'value': '2.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_kRCA', 'value': '-2.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_m', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_n', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_tG', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_Tm', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_IpSlewMaxPu', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_IqSlewMaxPu', 'value': '5'},
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTMin', 'value': '0.15'},  # LVRT from ENA EREC G99
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTInt', 'value': '0.15'},
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTMax', 'value': '2.2'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTMinPu', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTIntPu', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTArmingPu', 'value': '0.85'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaMaxPu', 'value': '1.05'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaDeadBandPu', 'value': '1.01'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaMinPu', 'value': '0.95'},
                    {'type': 'DOUBLE', 'name': 'ibg_tFilterOmega', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_tFilterU', 'value': '0.01'},
                    {'type': 'DOUBLE', 'name': 'ibg_UMaxPu', 'value': '1.2'},
                    {'type': 'DOUBLE', 'name': 'ibg_UPLLFreezePu', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_Ki', 'value': '20'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_Kp', 'value': '3'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_', 'value': '3'},
                    {'type': 'DOUBLE', 'name': 'ibg_SNom', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'ibg_Kf', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_tf', 'value': '1'},
                ]

                references = [
                    {'name': 'ibg_P0Pu', 'origData': 'IIDM', 'origName': 'p_pu', 'type': 'DOUBLE'},
                    # Use targetQ instead of Q because Powsybl sets the same Q for all generators of a bus irrespective of the generator sizes
                    {'name': 'ibg_Q0Pu', 'origData': 'IIDM', 'origName': 'targetQ_pu', 'type': 'DOUBLE'},
                    {'name': 'ibg_U0Pu', 'origData': 'IIDM', 'origName': 'v_pu', 'type': 'DOUBLE'},
                    {'name': 'ibg_UPhase0', 'origData': 'IIDM', 'origName': 'angle_pu', 'type': 'DOUBLE'},
                ]

            elif unit_group == 'RTPV':
                par_attribs = [  # Typical parameters from Gilles Chaspierre's PhD thesis, no voltage/frequency support from rooftop solar (LV connected)
                    {'type': 'DOUBLE', 'name': 'ibg_IMaxPu', 'value': '1.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_UQPrioPu', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_US1', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_US2', 'value': '10'},
                    {'type': 'DOUBLE', 'name': 'ibg_kRCI', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_kRCA', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_m', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_n', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_tG', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_Tm', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_IpSlewMaxPu', 'value': '0.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_IqSlewMaxPu', 'value': '5'},
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTMin', 'value': '0.15'},
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTInt', 'value': '0.3'},
                    {'type': 'DOUBLE', 'name': 'ibg_tLVRTMax', 'value': '1.5'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTMinPu', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTIntPu', 'value': '0.25'},  # Original: 0.5, made more strict to help frequency stable screening (TODO: better estimate of the amount of RTPV disconnection instead)
                    {'type': 'DOUBLE', 'name': 'ibg_ULVRTArmingPu', 'value': '0.85'},  # Original: 0.9
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaMaxPu', 'value': '1.05'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaDeadBandPu', 'value': '1.05'},
                    {'type': 'DOUBLE', 'name': 'ibg_OmegaMinPu', 'value': '0.95'},
                    {'type': 'DOUBLE', 'name': 'ibg_tFilterOmega', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_tFilterU', 'value': '0.01'},
                    {'type': 'DOUBLE', 'name': 'ibg_UMaxPu', 'value': '1.2'},
                    {'type': 'DOUBLE', 'name': 'ibg_UPLLFreezePu', 'value': '0.1'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_Ki', 'value': '20'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_Kp', 'value': '3'},
                    {'type': 'DOUBLE', 'name': 'ibg_PLLFreeze_', 'value': '3'},
                    {'type': 'DOUBLE', 'name': 'ibg_SNom', 'value': str(SNom)},
                    {'type': 'DOUBLE', 'name': 'ibg_Kf', 'value': '0'},
                    {'type': 'DOUBLE', 'name': 'ibg_tf', 'value': '1'},
                ]

                references = [
                    {'name': 'ibg_P0Pu', 'origData': 'IIDM', 'origName': 'p_pu', 'type': 'DOUBLE'},
                    # Use targetQ instead of Q because Powsybl sets the same Q for all generators of a bus irrespective of the generator sizes
                    {'name': 'ibg_Q0Pu', 'origData': 'IIDM', 'origName': 'targetQ_pu', 'type': 'DOUBLE'},
                    {'name': 'ibg_U0Pu', 'origData': 'IIDM', 'origName': 'v_pu', 'type': 'DOUBLE'},
                    {'name': 'ibg_UPhase0', 'origData': 'IIDM', 'origName': 'angle_pu', 'type': 'DOUBLE'},
                ]

            else:
                raise NotImplemented(unit_group, 'is not considered')

            for par_attrib in par_attribs:
                etree.SubElement(gen_par_set, etree.QName(namespace, 'par'), par_attrib)
            for ref in references:
                etree.SubElement(gen_par_set, etree.QName(namespace, 'reference'), ref)
    etree.SubElement(omega_par_set, etree.QName(namespace, 'par'), {'type': 'INT', 'name': 'nbGen', 'value': str(omega_index)})

    # return dyd_root, par_root  # Unecessary since they are mutable

if __name__ == '__main__':
    for network_name in ['RTS', 'Texas']:
        input_file = f'../{network_name}-Data/{network_name}.iidm'
        network = pp.network.load(input_file)

        XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
        dyd_root = etree.parse('base.dyd', XMLparser).getroot()
        par_root = etree.parse('base.par', XMLparser).getroot()
        namespace = 'http://www.rte-france.com/dynawo'

        if network_name == 'RTS':
            add_dyn_data(network_name, network, dyd_root, par_root, namespace, motor_share=0.3)
        else:
            add_dyn_data(network_name, network, dyd_root, par_root, namespace, motor_share=0)

        with open(network_name + '.dyd', 'wb') as doc:
            doc.write(etree.tostring(dyd_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
        with open(network_name + '.par', 'wb') as doc:
            doc.write(etree.tostring(par_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
