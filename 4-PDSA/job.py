from dataclasses import dataclass
from contingencies import Contingency
from common import *
from itertools import count

@dataclass
class Results:
    load_shedding: float


class Job:
    _ids = count(0)
    def __init__(self, static_id, dynamic_seed, contingency: Contingency):
        self.id = next(Job._ids)
        self.static_id = static_id
        self.dynamic_seed = dynamic_seed
        self.contingency = contingency
        self.completed = False
        self.timeout = False

    def complete(self, elapsed_time, results: Results):
        self.elapsed_time = elapsed_time
        self.results = results
        self.completed = True

    def timeout(self):
        self.timeout = True
        self.elapsed_time = JOB_TIMEOUT_S

    def __repr__(self) -> str:
        out = '\nJ {}ob\n'.format(self.id)
        out += 'Static id: {}\n'.format(self.static_id)
        out += 'Dynamic seed: {}\n'.format(self.dynamic_seed)
        out += 'Contingency: {}\n'.format(self.contingency)
        if self.timeout:
            out += 'Job timeout\n'
        elif not self.completed:
            out += 'Not yet completed\n'
        else:
            out += 'Completed\n'
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
