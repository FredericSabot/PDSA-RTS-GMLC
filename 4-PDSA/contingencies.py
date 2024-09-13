from dataclasses import dataclass
import pypowsybl as pp
from common import *
from dynawo_protections import get_buses_to_lines, get_adjacent_lines
import pandas as pd

@dataclass
class InitEvent:
    time_start: float
    category: INIT_EVENT_CATEGORIES
    element: str

    def __repr__(self) -> str:
        return self.category.name + '_' + self.element


@dataclass
class InitFault(InitEvent):
    fault_id: str
    r: float
    x: float
    time_end: float

    def __repr__(self) -> str:
        return self.fault_id + '_' + self.element


@dataclass
class Contingency:
    id: str
    frequency: float
    init_events: list[InitEvent]
    clearing_time: float
    fault_location: str = None

    """
    To limit the number of contingencies, double(/triple/...) lines are only counted once, but the associated contingencies
    have their frequency doubled(/tripled/...). This is done by doubling(/tripling/...) their lengths since the frequency is taken
    as OUTAGE_RATE_PER_KM * length. If substation configurations were considered, this should be updated, i.e. a topology computation
    should be done to identify which contingencies are equivalent
    """
    line_lengths = pd.read_csv(f'../{NETWORK_NAME}-Data/branch.csv', index_col=0).Length
    n = pp.network.load(f'../{NETWORK_NAME}-Data/{NETWORK_NAME}.iidm')
    lines = n.get_lines()
    unique_lines = []
    for line_id in lines.index:
        found = False
        for unique_line_id in unique_lines:
            if (lines.loc[line_id] == lines.loc[unique_line_id]).all():
                found = True
                break
        if found:
            line_lengths.loc[unique_line_id] += line_lengths.loc[line_id]
        else:
            unique_lines.append(line_id)


    """ def __eq__(self, other) -> bool:
        return set(self.events) == set(other.events) """

    @staticmethod
    def create_base_contingency():
        return [Contingency('Base', OUTAGE_RATE_PER_KM, [], 0)]  # Contingency with no events, use a low frequency to avoid running it too often

    @staticmethod
    def create_N_1_contingencies(with_lines = True, with_generators = False, with_normal_clearing = True, with_delayed_clearing = True):
        contingencies = []
        # Read network
        n = pp.network.load(f'../{NETWORK_NAME}-Data/{NETWORK_NAME}.iidm')
        lines = n.get_lines()
        vl = n.get_voltage_levels()

        # Fault on each end of the line + disconnection of the line
        if with_lines:
            for line_id in Contingency.unique_lines:
                voltage_level = lines.at[line_id, 'voltage_level1_id']
                Vb = float(vl.at[voltage_level, 'nominal_v']) * 1e3
                if Vb < CONTINGENCY_MINIMUM_VOLTAGE_LEVEL:
                    continue
                frequency = OUTAGE_RATE_PER_KM * Contingency.line_lengths.at[line_id]
                bus_ids = ['@' + line_id + '@@NODE1@', '@' + line_id + '@@NODE2@']
                ends = [1, 2]
                for bus_id, end in zip(bus_ids, ends):
                    contingency_id = line_id + '_end{}'.format(end)
                    fault_id = 'FAULT_' + bus_id

                    if with_normal_clearing:
                        init_events = []
                        init_events.append(InitFault(time_start=T_INIT, time_end=T_CLEARING, category=INIT_EVENT_CATEGORIES.BUS_FAULT, element=bus_id,
                                                fault_id=fault_id, r=R_FAULT, x=X_FAULT))
                        init_events.append(InitEvent(time_start=T_CLEARING, category=INIT_EVENT_CATEGORIES.LINE_DISC, element=line_id))

                        fault_location = lines.at[line_id, 'bus{}_id'.format(end)]
                        contingencies.append(Contingency(contingency_id, frequency, init_events, T_CLEARING - T_INIT, fault_location))

                    if with_delayed_clearing:
                        init_events = []
                        init_events.append(InitFault(time_start=T_INIT, time_end=T_BACKUP, category=INIT_EVENT_CATEGORIES.BUS_FAULT, element=bus_id,
                                                fault_id=fault_id, r=R_FAULT, x=X_FAULT))
                        init_events.append(InitEvent(time_start=T_BACKUP, category=INIT_EVENT_CATEGORIES.LINE_DISC, element=line_id))

                        fault_location = lines.at[line_id, 'bus{}_id'.format(end)]
                        contingencies.append(Contingency(contingency_id + '_DELAYED', frequency * DELAYED_CLEARING_RATE, init_events, T_BACKUP - T_INIT, fault_location))

        if with_generators:
            raise NotImplementedError('The code below most likely works, but automatic merging of generator contingencies has not been implemented (and identical generators might not always be connected at the same time)')
            for gen_id in gens.index:
                contingency_id = gen_id
                bus_id = '@' + gen_id + '@@NODE@'
                fault_id = 'FAULT_' + bus_id
                init_events = []
                init_events.append(InitFault(time_start=T_INIT, time_end=T_CLEARING, category=INIT_EVENT_CATEGORIES.BUS_FAULT, element=bus_id,
                                            fault_id=fault_id, r=R_FAULT, x=X_FAULT))
                init_events.append(InitEvent(time_start=T_CLEARING, category=INIT_EVENT_CATEGORIES.GEN_DISC, element=line_id))

                contingencies.append(Contingency(contingency_id, init_events))

        contingencies = Contingency.merge_identical_contingencies(contingencies)
        return contingencies

    @staticmethod
    def create_N_2_contingencies():
        """
        Generate a list of possible N-2 contingencies. For now, only line contingencies are considered.
        The considered contingencies consist of a line fault (on either side of the line) leading to the
        line disconnection, but with a circuit breaker (CB) failure to open (on either side of the line).

        It is assumed that CB failure protection schemes are deployed in every substation, and that it
        disconnect exactly one adjacent line (a contingency is created for every adjacent line). In a
        more realistic framework, this would depend on the substation configurations and on wether a
        CB failure protection scheme is actually in place.

        Implementation details:
        In Dynawo, it is only possible to create bus faults, not line faults. So, to model a fault on
        end1 of a line with stuck CB on end2:
            - Create a 100ms fault on the bus connected to end1 of the faulted line
            - Open the line and clear fault after 100ms (T_CLEARING)
            - Create a new fault at _end2 with resistance = line resistance + line impedance (incl. capa if possible) after 100ms
            - Clear the new fault + adjacent line after 200ms (T_BACKUP)

        Fault on line_end1 with stuck CB on same end is more straighforward:
            - open line at 100ms
            - disconnect the other element at 200ms
            - remove the fault at 200ms
        Note: buses are considered to always be connected to at least 2 lines (this is true for our modified
        Reliability Test System). Otherwise, some contingencies will be skipped

        TODO: consider node-breaker model and generators
        """
        contingencies = []
        # Read network
        n = pp.network.load(f'../{NETWORK_NAME}-Data/{NETWORK_NAME}.iidm')
        lines = n.get_lines()
        vl = n.get_voltage_levels()

        bus2lines = get_buses_to_lines(n)

        for line_id in Contingency.unique_lines:
            voltage_level = lines.at[line_id, 'voltage_level1_id']
            Vb = float(vl.at[voltage_level, 'nominal_v']) * 1e3
            if Vb < CONTINGENCY_MINIMUM_VOLTAGE_LEVEL:
                continue
            Sb = 100e6  # 100MW is default base in Dynawo
            Zb = Vb**2/Sb
            r_line = lines.at[line_id, 'r'] / Zb
            x_line = lines.at[line_id, 'x'] / Zb

            r_replacement_fault = R_FAULT + r_line
            x_replacement_fault = X_FAULT + x_line

            frequency = OUTAGE_RATE_PER_KM * Contingency.line_lengths.at[line_id] * CB_FAILURE_RATE

            for fault_side in [1, 2]:
                for CB_fail_side in [1, 2]:
                    for adj_line_id in get_adjacent_lines(bus2lines, n, line_id, CB_fail_side):
                        contingency_id = line_id + '_end{}-BREAKER_end{}-'.format(fault_side, CB_fail_side) + adj_line_id

                        # Initial fault
                        bus_id = '@' + line_id + '@@NODE{}@'.format(fault_side)
                        if fault_side == CB_fail_side:
                            T_INIT_fault_cleared = T_BACKUP  # Fault cleared in backup up time
                        else:
                            T_INIT_fault_cleared = T_CLEARING  # Fault "cleared" in normal time (but replaced by another one later on)

                        init_events = []
                        init_fault_id = 'FAULT_' + line_id + '_end' + str(fault_side)
                        init_events.append(InitFault(time_start=T_INIT, time_end=T_INIT_fault_cleared,
                                                     category=INIT_EVENT_CATEGORIES.BUS_FAULT,
                                                     element=bus_id, fault_id=init_fault_id, r=R_FAULT, x=X_FAULT))

                        # Line disconnection
                        init_events.append(InitEvent(time_start=T_CLEARING, category=INIT_EVENT_CATEGORIES.LINE_DISC, element=line_id))
                        # Adjacent line disconnection
                        init_events.append(InitEvent(time_start=T_BACKUP, category=INIT_EVENT_CATEGORIES.LINE_DISC, element=adj_line_id))

                        if fault_side != CB_fail_side:
                            # Replacement fault
                            replacement_fault_id = 'Replacement fault_' + line_id
                            bus_id = '@' + line_id + '@@NODE{}@'.format(CB_fail_side)

                            init_events.append(InitFault(time_start=T_CLEARING, time_end=T_BACKUP,
                                                     category=INIT_EVENT_CATEGORIES.BUS_FAULT,
                                                     element=bus_id, fault_id=replacement_fault_id,
                                                     r=r_replacement_fault, x=x_replacement_fault))

                        fault_location = lines.at[line_id, 'bus{}_id'.format(fault_side)]
                        contingencies.append(Contingency(contingency_id, frequency, init_events, T_BACKUP - T_INIT, fault_location))

        contingencies = Contingency.merge_identical_contingencies(contingencies)
        return contingencies

    @staticmethod
    def create_N_2_contingencies_from_node_breaker():
        raise NotImplementedError()

    @staticmethod
    def merge_identical_contingencies(contingencies):
        return contingencies
        unique_contingencies = []
        for contingency in contingencies:
            if contingency not in unique_contingencies:
                unique_contingencies.append(contingency)
            else:
                index = unique_contingencies.index(contingency)
                unique_contingencies[index].frequency += contingency.frequency
        return unique_contingencies
