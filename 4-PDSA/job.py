from dataclasses import dataclass
from contingencies import Contingency
from common import *
from itertools import count
import os
import subprocess
import time
import dynawo_inputs
from dynawo_outputs import get_job_results, get_job_results_special
from results import Results
import logger
import shutil
from pathlib import Path

class Job:
    _ids = count(0)
    def __init__(self, static_id, dynamic_seed, contingency: Contingency):
        self.id = next(Job._ids)
        self.static_id = static_id
        self.dynamic_seed = dynamic_seed
        self.contingency = contingency
        self.completed = False
        self.timed_out = False
        self.working_dir = os.path.join('./simulations', CASE, str(self.static_id), str(self.dynamic_seed), self.contingency.id)

    def complete(self, elapsed_time):
        self.elapsed_time = elapsed_time
        self.results = get_job_results(self.working_dir)
        self.completed = True
        shutil.rmtree(self.working_dir, ignore_errors=True)

    def timeout(self):
        self.timed_out = True
        self.elapsed_time = JOB_TIMEOUT_S
        self.results = Results(100.2, [])
        shutil.rmtree(self.working_dir, ignore_errors=True)

    def run(self):
        self.call_dynawo()

    def call_dynawo(self):
        t0 = time.time()

        dynawo_inputs.write_job_files(self)
        cmd = [DYNAWO_PATH, 'jobs', os.path.join(self.working_dir, NETWORK_NAME + '.jobs')]
        logger.logger.log(logger.logging.TRACE, 'Launching job %s' % self)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        timed_out = False
        try:
            _, stderr = proc.communicate(timeout=JOB_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            stderr = ''
            proc.kill()
            timed_out = True

        if 'Error' in str(stderr) or timed_out:  # Simulation failed, so retry with another solver
            # Delete output files of failed attempt
            output_dir = os.path.join(self.working_dir, 'outputs')
            shutil.rmtree(output_dir)
            # Retry with another solver
            cmd = [DYNAWO_PATH, 'jobs', os.path.join(self.working_dir, NETWORK_NAME + '_alt_solver.jobs')]
            logger.logger.log(logger.logging.TRACE, 'Launching job %s with alternative solver' % self)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            try:
                proc.communicate(timeout=JOB_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.timeout()
                return

        delta_t = time.time() - t0
        self.complete(delta_t)

    def __repr__(self) -> str:
        out = '\nJob {}\n'.format(self.id)
        out += 'Static id: {}\n'.format(self.static_id)
        out += 'Dynamic seed: {}\n'.format(self.dynamic_seed)
        out += 'Contingency: {}\n'.format(self.contingency)
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

    def timeout(self):
        self.variable_order, self.missing_events = False, False  # No timeline, so cannot check
        return super().timeout()


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
