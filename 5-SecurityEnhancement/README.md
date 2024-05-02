Once the PDSA is performed, critical contingencies can be identified. In this step machine learning techniques are used to define security boundaries, i.e. identify which operating conditions are secure and which are unsecure against a given contingency. Those security boundaries can be injected in the operational rules (as demonstrated in 2-SCOPF/a-PSCDCOPF/PSCDCOPF_SVM.gms) to secure against critical contingencies to reduce the risk. The PDSA should be rerun from step 2 (SCOPF) to quantify how much this reduces the risk.

The 2-SCOPF/postprocessing/costs.py script can be used to estimate how much this impacts operating costs to perform a cost-benefit analysis.

# Requirements

```
pip install scikit-learn imblearn
```

# Usage

Select critical contingencies from the end of 4-PDSA/log0.log or from 4-PDSA/AnalysisOutput.xml and write them in the critical_contingency_list of security_enhancement.py (around line 30), then

```
python security_enhancement.py
```
