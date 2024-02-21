from __future__ import annotations
from common import *
from dataclasses import dataclass
import dynawo_outputs

@dataclass
class Results:
    load_shedding: float
    trip_timeline: list[dynawo_outputs.TimeLineEvent]

    def __repr__(self) -> str:
        return CSV_SEPARATOR.join([str(self.load_shedding)] + [str(timeline_event) for timeline_event in self.trip_timeline])
