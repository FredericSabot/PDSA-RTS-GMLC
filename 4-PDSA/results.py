from __future__ import annotations
from common import *
from dataclasses import dataclass
import dynawo_outputs

@dataclass
class Results:
    load_shedding: float
    cost: float
    trip_timeline: list[dynawo_outputs.TimeLineEvent]
    excited_hidden_failures: list[str]
    excited_generator_failures: list[str]

    def __repr__(self) -> str:
        return CSV_SEPARATOR.join([str(self.load_shedding), str(self.cost)] + [str(timeline_event) for timeline_event in self.trip_timeline])

    def get_sanitised_tripped_models(self):
        """
        Return tripped models from trip_timeline but disregard 'fake trips' of distance protection, duplicates, and merge succesive RTPV trips
        """
        trip_timeline = [timeline_event for timeline_event in self.trip_timeline if 'tripped zone 1' not in timeline_event.event_description or 'tripped zone 4' not in timeline_event.event_description]

        tripped_models_no_duplicates = []
        for trip_event in trip_timeline:
            if trip_event.model not in tripped_models_no_duplicates:
                tripped_models_no_duplicates.append(trip_event.model)

        tripped_models_merged_rtpv = []
        for tripped_model in tripped_models_no_duplicates:
            if len(tripped_models_merged_rtpv) == 0:
                tripped_models_merged_rtpv.append(tripped_model)
            else:
                # Merge successive RTPV trips in timeline
                if 'RTPV' in tripped_models_merged_rtpv[-1] and 'RTPV' in tripped_model:
                    tripped_models_merged_rtpv[-1] += ', ' + tripped_model
                else:
                    tripped_models_merged_rtpv.append(tripped_model)

        return tripped_models_merged_rtpv
