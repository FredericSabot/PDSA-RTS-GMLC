import glob
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
- Steam governor
- WECC models
"""

def unit_group_translation(unit_group):
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


# case = 'january'
# input_files = glob.glob('../2-SCOPF/d-Final-dispatch/' + case + '/*.iidm')

input_file = '../RTS-Data/RTS.iidm'
network = pp.network.load(input_file)

name = 'RTS'
XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
dyd_root = etree.parse('base.dyd', XMLparser).getroot()
par_root = etree.parse('base.par', XMLparser).getroot()
namespace = 'http://www.rte-france.com/dynawo'


loads = network.get_loads()
for loadID in loads.index:
    if loads.at[loadID, 'p'] == 0 and loads.at[loadID, 'q'] == 0:  # Dummy load
        load_attrib = {'id': 'Dummy_' +  loadID, 'lib': 'LoadAlphaBeta', 'parFile': name + '.par', 'parId': 'DummyLoad', 'staticId': loadID}
        loadID = 'Dummy_' + loadID
    else:
        load_attrib = {'id': loadID, 'lib': 'LoadAlphaBeta', 'parFile': name + '.par', 'parId': 'GenericLoadAlphaBeta', 'staticId': loadID}
    load = etree.SubElement(dyd_root, etree.QName(namespace, 'blackBoxModel'), load_attrib)

    etree.SubElement(load, etree.QName(namespace, 'macroStaticRef'), {'id': 'LOAD'})
    etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': loadID, 'id2': 'NETWORK', 'connector': 'LOAD-CONNECTOR'})


omega_attrib = {'id': 'OMEGA_REF', 'lib': 'DYNModelOmegaRef', 'parFile': name + '.par', 'parId': 'OmegaRef'}
etree.SubElement(dyd_root, etree.QName(namespace, 'blackBoxModel'), omega_attrib)
omega_par_set = etree.SubElement(par_root, etree.QName(namespace, 'set'), {'id' : 'OmegaRef'})


gens_csv = pd.read_csv('../RTS-Data/gen.csv').to_dict()
N_gens = len(gens_csv['GEN UID'])
omega_index = 0
gens = network.get_generators()
vl = network.get_voltage_levels()

for i in range(N_gens):
    unit_group = gens_csv['Unit Group'][i]
    unit_group = unit_group_translation(unit_group)
    genID = gens_csv['GEN UID'][i]
    
    if unit_group == 'PV' or unit_group == 'RTPV':
        lib = 'GenericIBG'
        synchronous = False
    elif unit_group == 'Wind':
        lib = 'WTG4BWeccCurrentSource'
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

    gen_attrib = {'id': genID, 'lib': lib, 'parFile': name + '.par', 'parId': genID, 'staticId': genID}
    gen = etree.SubElement(dyd_root, etree.QName(namespace, 'blackBoxModel'), gen_attrib)
    
    if synchronous:
        etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'OMEGA_REF', 'connector': 'MS_OMEGAREF_CONNECTOR', 'index2': str(omega_index)})
        etree.SubElement(gen, etree.QName(namespace, 'macroStaticRef'), {'id': 'GEN'})
        etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'NETWORK', 'connector': 'GEN-CONNECTOR'})
    else:
        if unit_group == 'Wind':
            etree.SubElement(dyd_root, etree.QName(namespace, 'connect'), {'id1': genID, 'var1': 'WTG4B_omegaRefPu', 'id2': 'OMEGA_REF', 'var2': 'omegaRef_grp_0_value'})
            etree.SubElement(gen, etree.QName(namespace, 'macroStaticRef'), {'id': 'Wind'})
            etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'NETWORK', 'connector': 'Wind-CONNECTOR'})
        elif unit_group == 'PV' or unit_group == 'RTPV':
            etree.SubElement(dyd_root, etree.QName(namespace, 'connect'), {'id1': genID, 'var1': 'ibg_omegaRefPu', 'id2': 'OMEGA_REF', 'var2': 'omegaRef_grp_0_value'})
            etree.SubElement(gen, etree.QName(namespace, 'macroStaticRef'), {'id': 'PV'})
            etree.SubElement(dyd_root, etree.QName(namespace, 'macroConnect'), {'id1': genID, 'id2': 'NETWORK', 'connector': 'PV-CONNECTOR'})
        else:
            raise NotImplemented(unit_group, 'is not considered')

    p_max = gens.at[genID, 'max_p']
    q_max = gens.at[genID, 'max_q']
    p_min = gens.at[genID, 'min_p']
    p_target = gens.at[genID, 'target_p']
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
                {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(p_max / pf)},
                {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(p_max / pf)},
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
                {'type': 'DOUBLE', 'name': 'governor_SNom', 'value': str(p_max / pf)},
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
            SNom = gens.at[genID, 'max_q']
            par_attribs += [  # Reference machine SC5 from Vijay Vittal book
                {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(SNom)},
                {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(SNom)},
                {'type': 'DOUBLE', 'name': 'generator_H', 'value': '2.5'},  # Use higher value than the SC5 reference machine (that only has H=1.1s)
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
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(p_max / pf)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(p_max / pf)},
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
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(p_max / pf)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(p_max / pf)},
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
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(p_max / pf)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(p_max / pf)},
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
            elif unit_group == 'Coal_155':  # Reference machine F8 from Vijay Vittal book
                pf = 0.85
                par_attribs +=[
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(p_max / pf)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(p_max / pf)},
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
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(p_max / pf)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(p_max / pf)},
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
                    {'type': 'DOUBLE', 'name': 'generator_SNom', 'value': str(p_max / pf)},
                    {'type': 'DOUBLE', 'name': 'generator_SnTfo', 'value': str(p_max / pf)},
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
        if unit_group == 'Wind':
            SNom = gens_csv['PMax MW'][i]
            par_attribs = [
                {'type': 'DOUBLE', 'name': 'WTG4B_RPu', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'WTG4B_XPu', 'value': '0.05'},
                {'type': 'DOUBLE', 'name': 'WTG4B_DDn', 'value': '20'},
                {'type': 'DOUBLE', 'name': 'WTG4B_DUp', 'value': '0.001'},
                {'type': 'BOOL', 'name': 'WTG4B_FreqFlag', 'value': 'true'},
                {'type': 'DOUBLE', 'name': 'WTG4B_IMaxPu', 'value': '1.2'},
                {'type': 'DOUBLE', 'name': 'WTG4B_IqFrzPu', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Iqh1Pu', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Iql1Pu', 'value': '-1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_IqrMaxPu', 'value': '20'},
                {'type': 'DOUBLE', 'name': 'WTG4B_IqrMinPu', 'value': '-20'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kc', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Ki', 'value': '1.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kig', 'value': '2.36'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kp', 'value': '0.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kpg', 'value': '0.05'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kqi', 'value': '0.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kqp', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kqv', 'value': '2'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kvi', 'value': '0.7'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Kvp', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_PMaxPu', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_PMinPu', 'value': '0'},
                {'type': 'BOOL', 'name': 'WTG4B_PPriority', 'value': 'false'},
                {'type': 'BOOL', 'name': 'WTG4B_PfFlag', 'value': 'false'},
                {'type': 'BOOL', 'name': 'WTG4B_QFlag', 'value': 'true'},
                {'type': 'DOUBLE', 'name': 'WTG4B_QMaxPu', 'value': '0.4'},
                {'type': 'DOUBLE', 'name': 'WTG4B_QMinPu', 'value': '-0.4'},
                {'type': 'BOOL', 'name': 'WTG4B_RateFlag', 'value': 'false'},
                {'type': 'BOOL', 'name': 'WTG4B_RefFlag', 'value': 'true'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tFilterPC', 'value': '0.04'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tFilterGC', 'value': '0.02'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tFt', 'value': '1e-5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tFv', 'value': '0.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tG', 'value': '0.02'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Tiq', 'value': '0.01'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tLag', 'value': '0.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tP', 'value': '0.05'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tPord', 'value': '0.01'},
                {'type': 'DOUBLE', 'name': 'WTG4B_tRv', 'value': '0.01'},
                {'type': 'DOUBLE', 'name': 'WTG4B_UMaxPu', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_UMinPu', 'value': '0.9'},
                {'type': 'BOOL', 'name': 'WTG4B_VFlag', 'value': 'true'},
                {'type': 'BOOL', 'name': 'WTG4B_VCompFlag', 'value': 'false'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VFrz', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VMaxPu', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VMinPu', 'value': '0.9'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VRef0Pu', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'WTG4B_DPMax', 'value': '2'},
                {'type': 'DOUBLE', 'name': 'WTG4B_DPMin', 'value': '-2'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Dbd', 'value': '0.01'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Dbd1', 'value': '-0.05'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Dbd2', 'value': '0.05'},
                {'type': 'DOUBLE', 'name': 'WTG4B_EMax', 'value': '0.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_EMin', 'value': '-0.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_FDbd1', 'value': '0.004'},
                {'type': 'DOUBLE', 'name': 'WTG4B_FDbd2', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_FEMax', 'value': '999'},
                {'type': 'DOUBLE', 'name': 'WTG4B_FEMin', 'value': '-999'},
                {'type': 'DOUBLE', 'name': 'WTG4B_Rrpwr', 'value': '10'},
                {'type': 'DOUBLE', 'name': 'WTG4B_KiPLL', 'value': '20'},
                {'type': 'DOUBLE', 'name': 'WTG4B_KpPLL', 'value': '3'},
                {'type': 'DOUBLE', 'name': 'WTG4B_OmegaMaxPu', 'value': '1.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_OmegaMinPu', 'value': '0.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_HoldIq', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'WTG4B_HoldIpMax', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VRef1Pu', 'value': '0'},
                {'type': 'BOOL', 'name': 'WTG4B_PFlag', 'value': 'true'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIp11', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIp12', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIp21', 'value': '1.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIp22', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIq11', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIq12', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIq21', 'value': '1.5'},
                {'type': 'DOUBLE', 'name': 'WTG4B_VDLIq22', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'WTG4B_SNom', 'value': str(SNom)},
            ]
            
            references = [
                {'name': 'WTG4B_P0Pu', 'origData': 'IIDM', 'origName': 'p_pu', 'type': 'DOUBLE'},
                # Use targetQ instead of Q because Powsybl sets the same Q for all generators of a bus irrespective of the generator sizes
                {'name': 'WTG4B_Q0Pu', 'origData': 'IIDM', 'origName': 'targetQ_pu', 'type': 'DOUBLE'},
                {'name': 'WTG4B_U0Pu', 'origData': 'IIDM', 'origName': 'v_pu', 'type': 'DOUBLE'},
                {'name': 'WTG4B_UPhase0', 'origData': 'IIDM', 'origName': 'angle_pu', 'type': 'DOUBLE'},
            ]

        elif unit_group == 'PV' or unit_group == 'RTPV':
            SNom = gens_csv['PMax MW'][i]
            par_attribs = [  # Typical parameters from Gilles Chaspierre's PhD thesis
                {'type': 'DOUBLE', 'name': 'ibg_IMaxPu', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'ibg_UQPrioPu', 'value': '0.1'},
                {'type': 'DOUBLE', 'name': 'ibg_US1', 'value': '0.9'},
                {'type': 'DOUBLE', 'name': 'ibg_US2', 'value': '1.1'},
                {'type': 'DOUBLE', 'name': 'ibg_kRCI', 'value': '2.5'},
                {'type': 'DOUBLE', 'name': 'ibg_kRCA', 'value': '2.5'},
                {'type': 'DOUBLE', 'name': 'ibg_m', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'ibg_n', 'value': '1'},
                {'type': 'DOUBLE', 'name': 'ibg_tG', 'value': '0.1'},
                {'type': 'DOUBLE', 'name': 'ibg_Tm', 'value': '0.1'},
                {'type': 'DOUBLE', 'name': 'ibg_IpSlewMaxPu', 'value': '0.5'},
                {'type': 'DOUBLE', 'name': 'ibg_tLVRTMin', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'ibg_tLVRTInt', 'value': '0.3'},
                {'type': 'DOUBLE', 'name': 'ibg_tLVRTMax', 'value': '1.5'},
                {'type': 'DOUBLE', 'name': 'ibg_ULVRTMinPu', 'value': '0'},
                {'type': 'DOUBLE', 'name': 'ibg_ULVRTIntPu', 'value': '0.5'},
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

with open(name + '.dyd', 'wb') as doc:
    doc.write(etree.tostring(dyd_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
with open(name + '.par', 'wb') as doc:
    doc.write(etree.tostring(par_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
