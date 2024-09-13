***************************************************************
*** SETS
***************************************************************

set i_thermal thermal generators;
set i_hydro hydro generators;
set i_pv utility scale pv generators;
set i_wind wind generators;
set i_rtpv rtpv generators;
set i_bus buses;
set i_branch branches;
set i_contingency contingencies;
alias(i_branch, j_branch);


***************************************************************
*** PARAMETERS
***************************************************************

parameter Mk;
Mk = 1e6;

parameter Mg;
Mg = 1e6;

*GENERATOR DATA

parameter thermal_map(i_thermal, i_bus) thermal generator map;
parameter hydro_map(i_hydro, i_bus) hydro generator map;
parameter pv_map(i_pv, i_bus) pv generator map;
parameter wind_map(i_wind, i_bus) wind generator map;
parameter rtpv_map(i_rtpv, i_bus) rtpv generator map;

parameter lincost_thermal(i_thermal) slope of each generator cost curve block;
parameter lincost_hydro(i_hydro) slope of each generator cost curve block;
parameter lincost_pv(i_pv) slope of each generator cost curve block;
parameter lincost_wind(i_wind) slope of each generator cost curve block;

parameter thermal_min(i_thermal) thermal generator minimum generation;
parameter thermal_max(i_thermal) thermal generator maximum generation;
parameter hydro_max(i_hydro) hydro generator available power;
parameter pv_max(i_pv) pv generator available power;
parameter wind_max(i_wind) wind generator available power;
parameter rtpv_max(i_rtpv) rtpv generator available power;

*BRANCH DATA

parameter branch_admittance(i_branch) admittance of branch connecting two nodes;

parameter branch_map(i_branch, i_bus) line map;

parameter branch_max_N(i_branch) line capacities;
parameter branch_max_E(i_branch) line capacities (emergency);

*parameter contingency_states(i_branch, i_contingency) line contingencies;
parameter LODFs(i_branch, i_contingency) line outage distribution factors;
parameter considered_contingencies_map(i_branch, i_contingency) contingency map;

*DEMAND DATA

parameter demand(i_bus) demand at each bus;


$gdxin PrePSCDCOPF
$load i_thermal i_hydro i_pv i_wind i_rtpv i_bus i_branch i_contingency thermal_map hydro_map pv_map wind_map rtpv_map lincost_thermal lincost_hydro lincost_pv lincost_wind thermal_min thermal_max hydro_max pv_max wind_max rtpv_max branch_admittance branch_map branch_max_N branch_max_E demand LODFs considered_contingencies_map
$gdxin

***************************************************************
*** VARIABLES
***************************************************************

variable total_cost objective function variable

* binary variable on(i_thermal) whether generator i in commited or not

positive variable P_thermal(i_thermal) thermal generator outputs
positive variable P_hydro(i_hydro) hydro generator outputs
positive variable P_pv(i_pv) pv generator outputs
positive variable P_wind(i_wind) wind generator outputs
positive variable P_rtpv(i_rtpv) rtpv generator outputs

variable pf0(i_branch) power flow through lines in initial state
variable pfcontingency(i_branch, i_contingency) power flow after a contingency

variable theta0(i_bus) bus voltage angles
variable power_balance(i_bus)

***************************************************************
*** EQUATION DECLARATION
***************************************************************

equations

cost objective function
thermal_minP(i_thermal) minimum thermal generator output
thermal_maxP(i_thermal) maximum thermal generator output
hydro_maxP(i_hydro) maximum hydro generator output
pv_maxP(i_pv) maximum pv generator output
wind_maxP(i_wind) maximum wind generator output
rtpv_maxP(i_rtpv) maximum rtpv generator output
power_balance_0(i_bus) power balance for each bus
line_flow_0(i_branch) defining power flow through lines
line_flow_contingency(i_branch, i_contingency) defining power flow through lines for contingency i
line_capacity_min_0(i_branch) line capacitiy negative limit
line_capacity_max_0(i_branch) line capacitiy positive limit
line_capacity_min_contingency(i_branch, i_contingency) line capacitiy negative limit for contingency i
line_capacity_max_contingency(i_branch, i_contingency) line capacitiy positive limit for contingency i
voltage_angles_min_0(i_bus) voltage angles negative limit
voltage_angles_max_0(i_bus) voltage angles positive limit
;


***************************************************************
*** SETTINGS
***************************************************************

*setting the reference bus
theta0.fx ('1') = 0;


***************************************************************
*** EQUATIONS
***************************************************************

cost..
total_cost =e=
sum(i_thermal, P_thermal(i_thermal) * lincost_thermal(i_thermal)) +
sum(i_hydro, P_hydro(i_hydro) * lincost_hydro(i_hydro)) +
sum(i_pv, P_pv(i_pv) * lincost_pv(i_pv)) +
sum(i_wind, P_wind(i_wind) * lincost_wind(i_wind));

thermal_minP(i_thermal)..   P_thermal(i_thermal) =g= 0 * thermal_min(i_thermal);

thermal_maxP(i_thermal)..   P_thermal(i_thermal) =l= 1 * thermal_max(i_thermal);

hydro_maxP(i_hydro)..       P_hydro(i_hydro) =l= hydro_max(i_hydro);

pv_maxP(i_pv)..       P_pv(i_pv) =l= pv_max(i_pv);

wind_maxP(i_wind)..       P_wind(i_wind) =l= wind_max(i_wind);

rtpv_maxP(i_rtpv)..         P_rtpv(i_rtpv) =e= rtpv_max(i_rtpv);

power_balance_0(i_bus)..    sum(i_thermal$(thermal_map(i_thermal, i_bus)), P_thermal(i_thermal)) + sum(i_hydro$(hydro_map(i_hydro, i_bus)), P_hydro(i_hydro)) + sum(i_pv$(pv_map(i_pv, i_bus)), P_pv(i_pv)) + sum(i_wind$(wind_map(i_wind, i_bus)), P_wind(i_wind)) + sum(i_rtpv$(rtpv_map(i_rtpv, i_bus)), P_rtpv(i_rtpv)) - sum(i_branch, pf0(i_branch)*branch_map(i_branch, i_bus))
                            =e= demand(i_bus);

line_flow_0(i_branch)..         pf0(i_branch) =e= -branch_admittance(i_branch)*sum(i_bus, theta0(i_bus)*branch_map(i_branch, i_bus));

line_flow_contingency(i_branch, i_contingency)..   pfcontingency(i_branch, i_contingency) =e= pf0(i_branch) + LODFs(i_branch, i_contingency) * sum(j_branch$(considered_contingencies_map(j_branch, i_contingency)), pf0(j_branch));

line_capacity_min_0(i_branch)..   pf0(i_branch) =g= -0.95 * branch_max_N(i_branch);

line_capacity_max_0(i_branch)..   pf0(i_branch) =l= 0.95 * branch_max_N(i_branch);

line_capacity_min_contingency(i_branch, i_contingency)..   pfcontingency(i_branch, i_contingency) =g= -0.95 * branch_max_E(i_branch);

line_capacity_max_contingency(i_branch, i_contingency)..   pfcontingency(i_branch, i_contingency) =l= 0.95 * branch_max_E(i_branch);

voltage_angles_min_0(i_bus)..  theta0(i_bus) =g= -pi;

voltage_angles_max_0(i_bus)..  theta0(i_bus) =l= pi;

***************************************************************
*** SOLVE
***************************************************************

model test /all/;

option reslim = 1800;
*option Savepoint=1;
option optcr=1e-3;

option qcp = cplex;
option mip = cplex;
option lp = cplex;
test.optfile=1;

solve test using lp minimizing total_cost;

scalar sol;
sol = test.modelstat;

execute_unload 'PostPSCDCOPF' total_cost, P_thermal, P_hydro, P_pv, P_wind, pf0, theta0, sol;
