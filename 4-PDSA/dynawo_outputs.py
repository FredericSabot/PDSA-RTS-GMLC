from results import Results
from common import *
from dataclasses import dataclass
if WITH_LXML:
    from lxml import etree
else:
    import xml.etree.ElementTree as etree
import pypowsybl as pp
import os
import csv
import logger
from scipy.interpolate import interp1d
import scipy.integrate
import numpy as np
import pypowsybl as pp


def get_job_results(working_dir, fault_location):
    """
    Estimate the consequences and read the event timeline of a given scenario based on the simulation output files (located in working_dir)
    """
    excited_generator_failures = []
    network = pp.network.load(os.path.join(working_dir, NETWORK_NAME + '.iidm'))
    gens = network.get_generators()
    for gen_id in gens.index:
        if gens.at[gen_id, 'bus_id'] != fault_location:  # If generator connected to same bus as the fault (also account for if generator is connected at all)
            continue
            # TODO: compute some sort of electrical distance between fault and generator, not just faults on same bus as generator
        if (gens.at[gen_id, 'p']**2 + gens.at[gen_id, 'q']**2)**0.5 < GENERATOR_HIDDEN_FAILURE_MINIMUM_OUTPUT_MVA:
            continue
        if 'RTPV' in gen_id:  # Disconnection of DERs already modelled (not an "hidden" failure since it's common)
            continue
        excited_generator_failures.append(gen_id)

    log_file = os.path.join(working_dir, 'outputs', 'logs', 'dynawo.log')  # TODO: read file name from job instead of assuming it is outputs/dynawo.log
    # TODO: while at it, can check/force for <dyn:timeline exportMode="TXT" filter="true"/>

    # Search the end of the log file for | ERROR | to see if a convergence issue occured
    convergence_issue = False
    timeout = False
    max_line_number = 20
    line_number = 0
    t_end = 0
    if os.path.exists(log_file):  # Log file might not be created if it is empty (if log level set to error only)
        for line in reversed(list(open(log_file))):  # Read file from the end, from https://stackoverflow.com/a/2301792, note that it might read the whole file instead of just the end, but it should be ok
            if '| ERROR |' in line:
                if 'simulation interrupted by external signal' in line:
                    timeout = True  # Note: this can also occur when the whole job is stopped (e.g. SLURM time limit reached)
                convergence_issue = True
            line_split = line.split(' | ')
            if len(line_split) > 3:
                t_end = float(line_split[2])
                break
            line_number += 1
            if line_number > max_line_number:  # Don't search through the whole file (error is either at the very end of the file, or at the end before execution statistics)
                break

    if t_end == 0:
        logger.logger.warn(f"t_end could not be found (log file not found or incomplete) or simulation crashed at launch, {working_dir}")

    # Read timeline
    timeline_file = os.path.join(working_dir, 'outputs', 'timeLine', 'timeline.log')

    timeline = []
    trip_timeline = []
    generator_disconnection_timeline = []
    disconnected_models = []
    excited_hidden_failures = []
    if not os.path.exists(timeline_file):  # Might not be created if timeouts
        return Results(100.2, 0, trip_timeline, excited_hidden_failures, excited_generator_failures)

    with open(os.path.join(timeline_file), 'r') as f:
        events = f.readlines()
        for event in events:
            (time, model, event_description) = event.strip().split(' | ')
            event = TimeLineEvent(float(time), model, event_description)

            if 'hidden_failure' in event.model:
                if 'trip' in event.event_description:
                    if float(time) < T_INIT:  # Hidden failure activated in normal operation (before fault) --> skip
                        if 'Base' in working_dir:
                            # Only print warning for base contingency (since it will be identical for all contingencies, so avoid polluting the logs)
                            logger.logger.warning(f'{working_dir}: {model} tripped in normal operation (before fault), so skipped')
                        continue

                    if 'Distance' in event.event_description:  # Separate hidden failure depending on failure mode
                        if event.event_description.endswith('zone 1'):
                            excited_hidden_failures.append(model + '_Z1')
                        if event.event_description.endswith('zone 2'):
                            excited_hidden_failures.append(model + '_Z2')
                        if event.event_description.endswith('zone 3'):
                            excited_hidden_failures.append(model + '_Z3')
                    else:
                        excited_hidden_failures.append(model)
            else:
                if model in disconnected_models:
                    continue  # Disregard spurious events for models that are already disconnected

                timeline.append(event)

                if 'trip' in event.event_description:
                    trip_timeline.append(event)
                    disconnected_models.append(event.model)
                if 'UFLS step' in event.event_description and 'activated' in event.event_description:
                    trip_timeline.append(event)
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
            if 'Dummy' in timeline_event.model:
                continue
            disconnected_load += loads.at[timeline_event.model, 'p0']
        else:
            pass

    remaining_load = (total_load - disconnected_load) * UFLS_ratio

    load_shedding = (total_load - remaining_load) / total_load * 100

    if convergence_issue:
        if t_end >= T_END - 1:  # Disregard simplified solver failure at last time step
            pass
        elif t_end < T_BACKUP + 0.1:  # Disregard non-convergence issues during the fault, TODO: fix them
            pass
        else:
            load_shedding = 100.1  # Mark it as 100.1% load shedding to not affect averages, but still see there is a numerical issue
    if timeout:
        load_shedding = 100.2

    final_value_file = os.path.join(working_dir, 'outputs', 'finalStateValues', 'finalStateValues.csv')
    full_blackout = True
    with open(final_value_file, 'r') as file:
        reader = csv.reader(file, delimiter=';')
        next(reader)  # Skip header
        for row in reader:
            model = row[0]
            variable = row[1]
            value = float(row[2])
            if model == 'NETWORK' and 'Upu_value' in variable:
                if value > 0.5:
                    full_blackout = False
    if full_blackout:
        load_shedding = 100


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

    if len(generator_disconnection_timeline) == len(connected_machines):  # All machines are disconnected, i.e. full blackout
        load_shedding = 100
    elif len(generator_disconnection_timeline) > len(connected_machines):
        raise RuntimeError('Working_dir {}: missing generators in "connected_machines", or some generators were reconnected during the simulation'.format(working_dir))

    cost = load_shedding_to_cost(load_shedding, total_load)

    return Results(load_shedding, cost, trip_timeline, excited_hidden_failures, excited_generator_failures)


def load_shedding_to_cost(load_shedding, total_load):
    """
    Compute Value of Lost Load (VoLL)
    Derived from Pierre Henneaux and  Daniel S. Kirschen, "Probabilistic Security
    Analysis of Optimal Transmission Switching"
    """
    time = [1/60, 20/60, 1, 4, 8, 24]
    cost = [571, 61, 39, 30, 27, 13]
    for i in range(len(cost)):
        cost[i] *= 1000 # from kWh to MWh

    def interpolVoLL(t):
        if t >= time[0]:
            return interp1d(time, cost)(t)
        else:
            return interp1d(time, cost)(time[0])

    H = 0.1419 * load_shedding + 0.6482
    load_shedding_MW = load_shedding / 100 * total_load

    k = 3
    return scipy.integrate.quad(lambda t: k/H*np.exp(-k*t/H) * t * interpolVoLL(t), 0, H, epsabs=1e-4, epsrel=1e-4)[0] * load_shedding_MW / 1e6  # To Millions of euros/dollars


def get_job_results_special(working_dir):
    """
    Same as get_job_results() but also check if protection-related uncertainties can affect the cascading path (for special jobs only)
    """
    timeline_file = os.path.join(working_dir, 'outputs', 'timeLine', 'timeline.log')

    trip_timeline: list[TimeLineEvent]
    trip_timeline = []
    disconnected_models = []
    if not os.path.exists(timeline_file):  # Might not be created if timeouts
        return False, False

    with open(os.path.join(timeline_file), 'r') as f:
        events = f.readlines()
        for event in events:
            try:
                (time, model, event_description) = event.strip().split(' | ')
            except ValueError as e:
                print(working_dir)
                print(event)
                raise e
            event = TimeLineEvent(float(time), model, event_description)

            if model in disconnected_models:
                continue  # Disregard spurious events for protections that already tripped

            if 'hidden_failure' in event.model:
                continue  # Disregard fake trips from hidden failure models

            if 'trip' in event.event_description:
                trip_timeline.append(event)

    slow_trip_timeline = [timeline_event for timeline_event in trip_timeline if 'tripped zone 2' in timeline_event.event_description or 'tripped zone 3' in timeline_event.event_description]
    fast_trip_timeline = [timeline_event for timeline_event in trip_timeline if 'tripped zone 1' in timeline_event.event_description or 'tripped zone 4' in timeline_event.event_description]

    for timeline_event in fast_trip_timeline:
        if timeline_event.event_description == 'Distance protection tripped zone 1':  # Translate fast timeline events into slow equivalents for easier matching
            timeline_event.event_description = 'Distance protection tripped zone 2'
        if timeline_event.event_description == 'Distance protection tripped zone 4':
            timeline_event.event_description = 'Distance protection tripped zone 3'

    same_order = True
    index = 0
    for slow_timeline_event in slow_trip_timeline:
        time = float(slow_timeline_event.time)
        for following_timeline_event in slow_trip_timeline[index+1:]:
            for fast_timeline_event in fast_trip_timeline:
                if timeline_events_match(fast_timeline_event, following_timeline_event):
                    fast_time = float(fast_timeline_event.time)
                    if fast_time + 0.07 < time:  # check if they can occur before the considered event (with more than min CB time difference)
                        same_order = False
                    break
        index += 1

    missing_events = False
    for fast_timeline_event in fast_trip_timeline:
        found = False
        for slow_timeline_event in slow_trip_timeline:
            if timeline_events_match(fast_timeline_event, slow_timeline_event):
                found = True
                break
        if not found:
            missing_events = True
            break
    # Search event in slow that is not in fast (not possible if both are derived from a single simulation, and probably rare even if computed from two separate simulations)
    for slow_timeline_event in slow_trip_timeline:
        found = False
        for fast_timeline_event in fast_trip_timeline:
            if timeline_events_match(fast_timeline_event, slow_timeline_event):
                found = True
                break
        if not found:
            missing_events = True
            break

    return not same_order, missing_events

@dataclass
class TimeLineEvent:
    time: float
    model: str
    event_description: str

    def __repr__(self) -> str:
        return CSV_SEPARATOR.join([str(self.time), self.model, self.event_description])

def timeline_events_match(timeline_event_1: TimeLineEvent, timeline_event_2: TimeLineEvent) -> bool:
    if timeline_event_1.model == timeline_event_2.model and timeline_event_1.event_description == timeline_event_2.event_description:
        return True
    else:
        return False
