
# PDSA-RTS-GMLC

This repo contains a collection of scripts to prepare a probabilistic dynamic security assessment (PDSA) and enhancement of the Reliability Test System - Grid Modernization Lab Consortium version (RTS-GMLC).

It consists in:

1. A market model/unit commitment model based on [Prescient](https://github.com/grid-parity-exchange/Prescient). Prescient iterates between day-ahead and hourly dispatch. A (DC) nodal market (considering N-1 limits) is used here.
2. A preventive security constrained AC optimal power flow (PSCACOPF) to refine individual hourly dispatches
3. Scripts to add dynamic data to the RTS in [dynawo](https://dynawo.github.io/) format. These data have been checked to lead to an N-1 secure system (considering all possible line faults occurring at either end of the line and being cleared in 100ms by opening the line) in all possible system dispatches.
4. Scripts to perform the PDSA. Results are written to AnalysisOutput.xml. Results can be visualised using software that shows XML files in grid view, such as Ximple ([http://www.ximple.cz/](http://www.ximple.cz/), Windows only) as shown below. Note: Ximple does not support files larger than 100Mb, a simplified version of AnalysisOutput.xml (e.g. without info regarding all individual jobs) could be written to alleviate this issue for larger systems.
5. A script to define machine-learning-based operating rules to secure some contingencies based on the results of the PDSA.

![AnalysisExample](AnalysisOutputExample.png)

Each step generates data needed by the next, and steps should thus be performed sequentially. Documentation is available in the README of folders 1 to 5 to explain how to perform those steps.

# Citation

If you find this code useful, please cite the following paper that also includes additional information on how to perform a PDSA:

```bibtex
@misc{sabot2025PDSA,
      title={Towards Probabilistic Dynamic Security Assessment and Enhancement of Large Power Systems},
      author={Frédéric Sabot and Pierre-Etienne Labeau and Pierre Henneaux},
      year={2025},
      eprint={2505.01147},
      archivePrefix={arXiv},
      primaryClass={eess.SY},
      url={https://arxiv.org/abs/2505.01147},
}
```
