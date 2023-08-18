from dataclasses import dataclass
from contingencies import Contingency
from common import *
from itertools import count
import os
import subprocess
import time
import dynawo_inputs
from dynawo_outputs import get_job_results
from results import Results
import logger


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

    def complete(self, elapsed_time, results: Results):
        self.elapsed_time = elapsed_time
        self.results = results
        self.completed = True
        self.save_results()

    def timeout(self):
        self.timed_out = True
        self.elapsed_time = JOB_TIMEOUT_S

    def save_results(self):
        if not self.completed and not self.timed_out:
            raise RuntimeError('Job should be launched before saving its results')

        with open(os.path.join(self.working_dir, 'job.results'), 'w') as file:
            if self.completed:
                file.write(CSV_SEPARATOR.join([str(item) for item in [self.completed, self.elapsed_time, self.timed_out, self.results]]))
            else:
                file.write(CSV_SEPARATOR.join([str(item) for item in [self.completed, self.elapsed_time, self.timed_out]]))

    def load_results(self, save_file):
        with open(save_file, 'r') as file:
            save = file.readline().split(CSV_SEPARATOR)
            self.completed = save[0] == 'True'
            self.elapsed_time = float(save[1])
            self.timed_out = save[2] == 'True'
            if self.completed:
                self.results = Results.load_from_str(*save[3:])
        # TODO: add try/catch for incompatible saves from different versions, print warning and call_dynawo()

    def run(self):
        self.call_dynawo()

        save_file = os.path.join(self.working_dir, 'job.results')
        if REUSE_RESULTS and os.path.exists(save_file):
            self.load_results(save_file)
        else:
            self.call_dynawo()

    def call_dynawo(self):
        t0 = time.time()

        log_file = os.path.join(self.working_dir, 'outputs', 'logs', 'dynawo.log')
        timeline_file = os.path.join(self.working_dir, 'outputs', 'timeLine', 'timeline.log')  # TODO: read paths from .jobs instead of hardcoding them

        run_simulation = True
        if REUSE_RESULTS and os.path.exists(log_file) and os.path.exists(timeline_file):  # Don't rerun simulations if outputs exist
            run_simulation = False
            with open(timeline_file, 'r') as timeline:
                timeline = timeline.readlines()
                if len(timeline) > 0 and any('Simulation stopped : one interrupt signal was received' in
                                             timeline_string for timeline_string in timeline[-10:]):  # Rerun simulations if it was previously interupted by user (even if partial outputs exist)
                    run_simulation = True

        if run_simulation:
            dynawo_inputs.write_job_files(self)
            cmd = [DYNAWO_PATH, 'jobs', os.path.join(self.working_dir, NETWORK_NAME + '.jobs')]
            logger.logger.log(logger.logging.TRACE, 'Launching job %s' % self)
            proc = subprocess.Popen(cmd)

            try:
                proc.communicate(timeout=JOB_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                self.timeout()
                return

            delta_t = time.time() - t0
            self.complete(delta_t, get_job_results(self.working_dir))

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
