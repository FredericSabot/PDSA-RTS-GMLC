from job import Job, SpecialJob
import sys
from contingencies import Contingency
import dynawo_inputs

def write_jobs_files(args):
    static_id = int(sys.argv[1])
    dynamic_seed = int(sys.argv[2])
    contingency_id = sys.argv[3]

    contingencies = Contingency.create_base_contingency() + Contingency.create_N_1_contingencies() + Contingency.create_N_2_contingencies()

    for contingency in contingencies:
        if contingency.id == contingency_id:
            if dynamic_seed == 0:
                job = SpecialJob(static_id, dynamic_seed, contingency)
            else:
                job = Job(static_id, dynamic_seed, contingency)
            dynawo_inputs.write_job_files(job)
            return
    for contingency in contingencies:
        print(contingency.id)
    raise ValueError("Contingency {} not found".format(contingency_id))

if __name__ == "__main__":
    write_jobs_files(sys.argv)
