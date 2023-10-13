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

    @staticmethod
    def load_from_str(string: str):
        inputs = string.split(CSV_SEPARATOR)
        load_shedding = float(inputs.pop(0))
        trip_timeline = []
        while len(inputs) >= 3:
            time, model, event_description, *inputs = inputs
            trip_timeline.append(dynawo_outputs.TimeLineEvent(float(time), model, event_description))

        return Results(load_shedding, trip_timeline)
