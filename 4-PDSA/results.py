from common import *
from dataclasses import dataclass

@dataclass
class Results:
    load_shedding: float

    def __repr__(self) -> str:
        return CSV_SEPARATOR.join([str(self.load_shedding)])

    @staticmethod
    def load_from_str(load_shedding: str):
        return Results(float(load_shedding))