from results import Results
from common import *
from dataclasses import dataclass

from lxml import etree
import pypowsybl as pp
import os

""" def isSameModel(model1, model2):
    ""
    Return true if model1 and model2 disconnect the same element
    ""
    if len(model1) >= 23 and len(model2) >= 23:  # e.g. 5.41972 _BUS___26-BUS___29-1_AC_side2_Distance
                                                 #      5.41972 _BUS___28-BUS___29-1_AC_side1_Distance
        if model1[:23] == model2[:23]:
            return True
    elif len(model1) >= 8 and len(model2) >= 8:  # e.g. 5.5 GEN___38_SM_UVA Under-voltage generator trip
                                                 #      5.59184 GEN___38_SM_Speed Speed protection trip
        if model1[:8] == model2[:8]:
            return True
    return False """

def get_job_results(working_dir):
    log_file = os.path.join(working_dir, 'outputs', 'logs', 'dynawo.log')  # TODO: read file name from job instead of assuming it is outputs/dynawo.log
    # TODO: while at it, can check/force for <dyn:timeline exportMode="TXT" filter="true"/>

    # Search the end of the log file for | ERROR | to see if a convergence issue occured
    convergence_issue = False
    max_line_number = 20
    line_number = 0
    for line in reversed(list(open(log_file))):  # from https://stackoverflow.com/a/2301792, note that it might read the whole file instead of just the end, but it should be ok
        if '| ERROR |' in line:
            convergence_issue = True
            break
        line_number += 1
        if line_number > max_line_number:  # Don't search through the whole file (error is either at the very end of the file, or at the end before execution statistics)
            break

    # Read timeline
    timeline_file = os.path.join(working_dir, 'outputs', 'timeLine', 'timeline.log')

    timeline = []
    trip_timeline = []
    distance_arming_timeline = []
    distance_disarming_timeline = []
    generator_disconnection_timeline = []
    disconnected_models = []
    with open(os.path.join(timeline_file), 'r') as f:
        events = f.readlines()
        for event in events:
            (time, model, event_description) = event.strip().split(' | ')
            event = TimeLineEvent(time, model, event_description)

            if model in disconnected_models:
                continue  # Disregard spurious events for models that are already disconnected

            timeline.append(event)

            if 'trip' in event.event_description:  # Does not include UFLS (might need update if other protections are added)
                trip_timeline.append(event)
                disconnected_models.append(event.model)

            if 'Distance protection zone' in event.event_description:
                if 'disarming' in event.event_description:
                    distance_disarming_timeline.append(event)  # TODO: now consider the fact that when a zone trips, the others disarm (still used?)
                elif 'arming' in event.event_description:  # elif -> does not include disarmings
                    distance_arming_timeline.append(event)

            if 'GENERATOR : disconnecting' in event.event_description:
                generator_disconnection_timeline.append(event)

    ###
    # Compute load shedding
    ###
    n = pp.network.load(os.path.join(working_dir, NETWORK_NAME + '.iidm'))
    loads = n.get_loads()
    for load_id in loads.index:
        if loads.at[load_id, 'p0'] == 0 and loads.at[load_id, 'q0'] == 0:  # Remove dummy loads
            loads = loads.drop(load_id)

    total_load = sum([loads.at[load, 'p0'] for load in loads.index])

    UFLS_ratio = 1
    disconnected_load = 0
    for timeline_event in timeline:
        if timeline_event.event_description == 'UFLS step 1 activated':
            UFLS_ratio += -0.1
        elif timeline_event.event_description == 'UFLS step 2 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 3 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 4 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 5 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 6 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 7 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 8 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 9 activated':
            UFLS_ratio += -0.05
        elif timeline_event.event_description == 'UFLS step 10 activated':
            UFLS_ratio += -0.05

        elif timeline_event.event_description == 'LOAD : disconnecting':
            if 'Dummy' in model:
                continue
            disconnected_load += loads.at[model, 'p0']
        else:
            pass

    remaining_load = (total_load - disconnected_load) * UFLS_ratio

    load_shedding = (total_load - remaining_load) / total_load * 100

    if convergence_issue:
        load_shedding = 100.1  # Mark it as 100.1% load shedding to not affect averages, but still see there is a numerical issue


    ###############################################
    # Identify cases with all synchronous machines
    # disconnected as full blackout instead of
    # convergence issues
    ###############################################
    connected_machines = []

    # Find machines with a connection to omega_grp via a connect
    dyd_root = etree.parse(os.path.join(working_dir, NETWORK_NAME + '.dyd')).getroot()
    for connection in dyd_root.iterfind("{{{}}}connect".format(DYNAWO_NAMESPACE)):
        if connection.get('id1') == 'OMEGA_REF' and 'omega_grp_' in connection.get('var1'):
            connected_machines.append(connection.get('id2'))
        elif connection.get('id2') == 'OMEGA_REF' and 'omega_grp_' in connection.get('var2'):
            connected_machines.append(connection.get('id1'))

    # Find machines with a connection to omega_grp via a macroConnect
    macro_connector_list = []
    for macro_connector in dyd_root.iterfind("{{{}}}macroConnector".format(DYNAWO_NAMESPACE)):
        for connection in macro_connector:
            if 'omega_grp_' in connection.get('var1') or 'omega_grp_' in connection.get('var2'):
                macro_connector_list.append(macro_connector.get('id'))
                break
    for macro_connection in dyd_root.iterfind("{{{}}}macroConnect".format(DYNAWO_NAMESPACE)):
        if macro_connection.get('connector') in macro_connector_list:
            if macro_connection.get('id1') == 'OMEGA_REF':
                connected_machines.append(macro_connection.get('id2'))
            elif macro_connection.get('id2') == 'OMEGA_REF':
                connected_machines.append(macro_connection.get('id1'))
            else:
                raise ValueError('OmegaRef model expected to be named "OMEGA_REF"')
    # Generator must be connected both in the dyd and iidm to count
    gens = n.get_generators()
    really_connected_machines = []
    for machine in connected_machines:
        if gens.at[machine, 'connected']:
            really_connected_machines.append(machine)

    if len(generator_disconnection_timeline) == len(really_connected_machines):  # All machines are disconnected, i.e. full blackout
        load_shedding = 100
    elif len(generator_disconnection_timeline) > len(really_connected_machines):
        raise RuntimeError('Missing generators in "really_connected_machines", or some generators were reconnected during the simulation')


    # TODO: check for low voltages using the new final values API (load_terminal_V_re, and _im -> compute abs)

    return Results(load_shedding)


@dataclass
class TimeLineEvent:
    time: float
    model: str
    event_description: str
