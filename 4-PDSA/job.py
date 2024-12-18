from __future__ import annotations
from dataclasses import dataclass
from contingencies import Contingency
import contingencies
from common import *
from itertools import count
import os
import subprocess
import signal
import time
import dynawo_inputs
from dynawo_outputs import get_job_results, get_job_results_special
from results import Results
import logger
import shutil
import screening
import pypowsybl as pp

class Job:
    _ids = count(0)
    def __init__(self, static_id, dynamic_seed, contingency: Contingency):
        self.id = next(Job._ids)
        self.static_id = static_id
        self.dynamic_seed = dynamic_seed
        self.contingency = contingency
        self.completed = False
        self.timed_out = False
        self.working_dir = os.path.join('./simulations', f'{CASE}_{NETWORK_NAME}', str(self.static_id), str(self.dynamic_seed), self.contingency.id)

    @classmethod
    def from_parent_and_protection_failure(cls, parent: Job, protection_hidden_failure):
        contingency = Contingency.from_parent_and_protection_failure(parent.contingency, protection_hidden_failure)
        return cls(parent.static_id, parent.dynamic_seed, contingency)

    @classmethod
    def from_parent_and_generator_failure(cls, parent: Job, generator_failure):
        contingency = Contingency.from_parent_and_generator_failure(parent.contingency, generator_failure)
        return cls(parent.static_id, parent.dynamic_seed, contingency)

    def complete(self, elapsed_time):
        self.elapsed_time = elapsed_time
        self.results = get_job_results(self.working_dir, self.contingency.fault_location)
        self.completed = True
        shutil.rmtree(self.working_dir, ignore_errors=True)
        if NEGLECT_NORMAL_FAULT_RISK:
            if self.contingency.order < 2 and ('DELAYED' not in self.contingency.id and '~' not in self.contingency.id):
                self.results.load_shedding = 0
                self.results.cost = 0

    def skip(self):
        self.elapsed_time = 1
        self.results = Results(0, 0, [], [], [])
        self.completed = True

    def run(self):
        logger.logger.log(logger.logging.TRACE, 'Launching job %s' % self)

        self.stability_screening()

        if not self.voltage_stable or not self.transient_stable or not self.frequency_stable or BYPASS_SCREENING:
            self.call_dynawo()
        else:
            self.skip()

    def call_dynawo(self):
        t0 = time.time()

        dynawo_inputs.write_job_files(self)

        # Launch cmd and interrupt it if last longer than JOB_TIMEOUT_S
        cmd = [DYNAWO_PATH, 'jobs', os.path.join(self.working_dir, NETWORK_NAME + '.jobs')]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        try:
            _, stderr = proc.communicate(timeout=JOB_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            stderr = ''
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)  # Send ctrl+c signal to Dynawo (https://stackoverflow.com/a/4791612, but setsid replaced by start_new_session according to https://docs.python.org/3/library/subprocess.html)
            time.sleep(10)  # Let some time for Dynawo to gracefully interrupt and write output files
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # Kill if needed
            self.timed_out = True

        if ('Error' in str(stderr) or self.timed_out) and NETWORK_NAME != 'Texas':  # Simulation failed, so retry with another solver (not for Texas case because IDA not performant enough on large networks)
            # Delete output files of failed attempt
            output_dir = os.path.join(self.working_dir, 'outputs')
            shutil.rmtree(output_dir, ignore_errors=True)
            # Retry with another solver
            cmd = [DYNAWO_PATH, 'jobs', os.path.join(self.working_dir, NETWORK_NAME + '_alt_solver.jobs')]
            logger.logger.log(logger.logging.TRACE, 'Launching job %s with alternative solver' % self)
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

            try:
                proc.communicate(timeout=JOB_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                time.sleep(10)  # Let some time for Dynawo to gracefully interrupt and write output files
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)

        delta_t = time.time() - t0
        self.complete(delta_t)

    def stability_screening(self):
        network_path = os.path.join('../2-SCOPF/d-Final-dispatch', f'{CASE}_{NETWORK_NAME}', str(self.static_id) + '.iidm')
        network = pp.network.load(network_path)
        disconnected_elements = [event.element for event in self.contingency.init_events if not isinstance(event, contingencies.InitFault)]
        lines = network.get_lines()
        disconnected_lines = [disconnected_element for disconnected_element in disconnected_elements if disconnected_element in lines.index]
        self.voltage_stable, self.shc_ratio = screening.voltage_screening(network, disconnected_elements)
        self.transient_stable, self.cct = screening.transient_screening(network, self.contingency.clearing_time, self.contingency.fault_location, disconnected_elements)

        sensitive_buses = []
        for disconnected_line in disconnected_lines:
            sensitive_buses += [lines.at[disconnected_line, 'bus1_id'], lines.at[disconnected_line, 'bus2_id']]

        if self.contingency.clearing_time > 0:
            # Generators near the fault are likely to trip, so also perform screening assuming they trip
            gens = network.get_generators()
            for gen_id in gens.index:
                if not gens.at[gen_id, 'connected']:
                    continue
                if gen_id in disconnected_elements:
                    continue

                if gens.at[gen_id, 'energy_source'] in ['SOLAR', 'WIND']:
                    if gens.at[gen_id, 'bus_id'] == self.contingency.fault_location or gens.at[gen_id, 'bus_id'] in sensitive_buses:
                        disconnected_elements.append(gen_id)
                else:
                    if gens.at[gen_id, 'bus_id'] == self.contingency.fault_location and self.contingency.clearing_time > 0.15:
                        disconnected_elements.append(gen_id)

            voltage_stable, shc_ratio = screening.voltage_screening(network, disconnected_elements)
            transient_stable, cct = screening.transient_screening(network, self.contingency.clearing_time, self.contingency.fault_location, disconnected_elements)

            self.voltage_stable = self.voltage_stable and voltage_stable
            self.transient_stable = self.transient_stable and transient_stable
            self.shc_ratio = min(self.shc_ratio, shc_ratio)
            self.cct = min(self.cct, cct)

        self.frequency_stable, self.RoCoF, self.power_loss_over_reserve = screening.frequency_screening(network, disconnected_elements)


    def __repr__(self) -> str:
        out = '\nJob {}\n'.format(self.id)
        out += 'Static id: {}\n'.format(self.static_id)
        out += 'Dynamic seed: {}\n'.format(self.dynamic_seed)
        out += 'Contingency: {}\n'.format(self.contingency.id)
        if self.timed_out:
            out += 'Job timeout\n'
        elif not self.completed:
            out += 'Not yet completed\n'
        else:
            out += 'Completed in {}s\n'.format(self.elapsed_time)
            out += 'Results: {}\n'.format(self.results)
        return out


class SpecialJob(Job):
    def __init__(self, static_id, dynamic_seed, contingency: Contingency):
        if dynamic_seed != 0:
            raise ValueError("Special jobs should have a dynamic seed of 0")
        super().__init__(static_id, dynamic_seed, contingency)

    def __repr__(self) -> str:
        out = super().__repr__()
        if self.completed:
            out += 'Variable order: {}, missing events: {}\n'.format(self.variable_order, self.missing_events)
        return out

    def complete(self, elapsed_time):
        self.variable_order, self.missing_events = get_job_results_special(self.working_dir)
        super().complete(elapsed_time)

    def skip(self):
        self.variable_order, self.missing_events = False, False
        super().skip()


@dataclass
class InitEvent:
    time_start: float
    category: str
    element: str

    def __repr__(self) -> str:
        return self.category + '_' + self.element

@dataclass
class InitFault(InitEvent):
    fault_id: str
    r: float
    x: float
    time_end: float

    def __repr__(self) -> str:
        return self.fault_id + '_' + self.element
