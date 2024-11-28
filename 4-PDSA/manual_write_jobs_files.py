from job import Job, SpecialJob
import sys
from contingencies import Contingency
import dynawo_inputs

def write_jobs_files(args):
    """
    Write job files for a given scenario. Meant to be used manually for local simulations. Run with
    python write_jobs_files static_id dynamic_seed contingency_id
    where static_id is the id of the operating condition sample and dynamic_seed is the seed to generate random protection parameters.
    """
    static_id = int(sys.argv[1])
    dynamic_seed = int(sys.argv[2])
    contingency_id = sys.argv[3]

    decomposition = contingency_id.split('~')
    contingency_id = decomposition[0]
    hidden_failures = decomposition[1:]

    contingencies = Contingency.create_base_contingency() + Contingency.create_N_1_contingencies() + Contingency.create_N_2_contingencies()

    for contingency in contingencies:
        if contingency.id == contingency_id:
            while len(hidden_failures) > 0:
                hidden_failure = hidden_failures.pop()
                if 'hidden_failure' in hidden_failure:
                    contingency = Contingency.from_parent_and_protection_failure(contingency, hidden_failure)
                else:
                    contingency = Contingency.from_parent_and_generator_failure(contingency, hidden_failure)

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
