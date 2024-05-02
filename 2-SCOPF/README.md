Main file: PSCACOPF.py

Comments:
- NLP problems are difficult to solve numerically, especially if they are not initialized in a good way
- The procedure followed here consists in initializing the final AC PSC-OPF through a succession of preliminary problems
  * A DC PSC-OPF (accounting for an estimation of the losses), to find an estimation of the active power dispatch
  * An AC OPF aiming at finding a feasible AC solution to the power flow equations the closest possible to the solution of the DC PSC-OPF and trying to set the reactive power of generators close to the middle of their capability. The aim is to avoid to push voltages to their upper bound to reduce the losses by generating the maximum of reactive power, at the expense of security (no margin).
  * An AC contingency analysis to find voltages and power flows for all the considered contingency cases
  * Finally, an AC PSCOPF initialized based on the outcome of the previous steps to optimize the convergence properties
    * Contingencies that are not secure in the current dispatch are iteratively added to the optimisation problem for performance reason
    * After a contingency, generators try to keep their terminal voltage equal to the pre-contingency value up to their reactive capabilities

The PSCACOPF.py scripts successively launches the PSC DC OPF, the ACOPF and PSC AC OPF python scripts respectively located in a-PSCDCOPF/, b-ACOPF, and c-PSCACOPF folders. These scripts themselves call GAMS scripts where the actual optimisation is performed.

The postprocessing/ folder contains small scripts for manual inspection of the results. They are not part of the main probabilistic security assessment workflow.
