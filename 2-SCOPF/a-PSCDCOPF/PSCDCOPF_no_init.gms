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

parameter contingency_states(i_branch, i_contingency) line contingencies;

*DEMAND DATA

parameter demand(i_bus) demand at each bus;


$gdxin PrePSCDCOPF
$load i_thermal i_hydro i_pv i_wind i_rtpv i_bus i_branch i_contingency thermal_map hydro_map pv_map wind_map rtpv_map lincost_thermal lincost_hydro lincost_pv lincost_wind thermal_min thermal_max hydro_max pv_max wind_max rtpv_max branch_admittance branch_map branch_max_N branch_max_E demand contingency_states
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

positive variable P_thermal_contingency(i_thermal, i_contingency) thermal generator output for contingency i
positive variable P_hydro_contingency(i_hydro, i_contingency) hydro generator output for contingency i
positive variable P_pv_contingency(i_pv, i_contingency) pv generator output for contingency i
positive variable P_wind_contingency(i_wind, i_contingency) wind generator output for contingency i
positive variable P_rtpv_contingency(i_rtpv, i_contingency) rtpv generator output generators for contingency i

variable pf0(i_branch) power flow through lines in initial state
variable pfcontingency(i_branch, i_contingency) power flow through lines in contingency i

variable theta0(i_bus) bus voltage angles
variable thetacontingency(i_bus, i_contingency) bus voltage angles in contingency i

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
power_balance_contingency(i_bus, i_contingency) power balance for each bus for contingency i
P_thermal_cont(i_thermal, i_contingency) thermal outputs for contingency i
P_hydro_cont(i_hydro, i_contingency) hydro outputs for contingency i
P_pv_cont(i_pv, i_contingency) pv outputs for contingency i
P_wind_cont(i_wind, i_contingency) wind outputs for contingency i
P_rtpv_cont(i_rtpv, i_contingency) rtpv outputs for contingency i
line_flow_0(i_branch) defining power flow through lines
line_flow_contingency(i_branch, i_contingency) defining power flow through lines for contingency i
line_capacity_min_0(i_branch) line capacitiy negative limit
line_capacity_max_0(i_branch) line capacitiy positive limit
line_capacity_min_contingency(i_branch, i_contingency) line capacitiy negative limit for contingency i
line_capacity_max_contingency(i_branch, i_contingency) line capacitiy positive limit for contingency i
voltage_angles_min_0(i_bus) voltage angles negative limit
voltage_angles_max_0(i_bus) voltage angles positive limit
voltage_angles_min_ck(i_bus, i_contingency) voltage angles negative limit for contingency i_states
voltage_angles_max_ck(i_bus, i_contingency) voltage angles positive limit for contingency i_states
;


***************************************************************
*** SETTINGS
***************************************************************

*setting the reference bus
theta0.fx ('1') = 0;
thetacontingency.fx('1', i_contingency)= 0;


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

power_balance_contingency(i_bus, i_contingency)..
sum(i_thermal$(thermal_map(i_thermal, i_bus)), P_thermal_contingency(i_thermal, i_contingency))
+ sum(i_hydro$(hydro_map(i_hydro, i_bus)), P_hydro_contingency(i_hydro, i_contingency))
+ sum(i_pv$(pv_map(i_pv, i_bus)), P_pv_contingency(i_pv, i_contingency))
+ sum(i_wind$(wind_map(i_wind, i_bus)), P_wind_contingency(i_wind, i_contingency))
+ sum(i_rtpv$(rtpv_map(i_rtpv, i_bus)), P_rtpv_contingency(i_rtpv, i_contingency))
+ sum(i_branch, pfcontingency(i_branch, i_contingency)*branch_map(i_branch, i_bus))
=e= demand(i_bus);

P_thermal_cont(i_thermal, i_contingency)..  P_thermal_contingency(i_thermal, i_contingency) =e= P_thermal(i_thermal);

P_hydro_cont(i_hydro, i_contingency)..      P_hydro_contingency(i_hydro, i_contingency) =e= P_hydro(i_hydro);

P_pv_cont(i_pv, i_contingency)..      P_pv_contingency(i_pv, i_contingency) =e= P_pv(i_pv);

P_wind_cont(i_wind, i_contingency)..      P_wind_contingency(i_wind, i_contingency) =e= P_wind(i_wind);

P_rtpv_cont(i_rtpv, i_contingency)..        P_rtpv_contingency(i_rtpv, i_contingency) =e= P_rtpv(i_rtpv);

line_flow_0(i_branch)..         pf0(i_branch) =e= -branch_admittance(i_branch)*sum(i_bus, theta0(i_bus)*branch_map(i_branch, i_bus));

line_flow_contingency(i_branch, i_contingency)..         pfcontingency(i_branch, i_contingency) =e= (1-contingency_states(i_branch, i_contingency)) * branch_admittance(i_branch)*sum(i_bus, thetacontingency(i_bus, i_contingency)*branch_map(i_branch, i_bus));

line_capacity_min_0(i_branch)..   pf0(i_branch) =g= -0.95 * branch_max_N(i_branch);

line_capacity_max_0(i_branch)..   pf0(i_branch) =l= 0.95 * branch_max_N(i_branch);

line_capacity_min_contingency(i_branch, i_contingency)..   pfcontingency(i_branch, i_contingency) =g= -0.95 * (1-contingency_states(i_branch, i_contingency)) * branch_max_E(i_branch);

line_capacity_max_contingency(i_branch, i_contingency)..   pfcontingency(i_branch, i_contingency) =l= 0.95 * (1-contingency_states(i_branch, i_contingency)) * branch_max_E(i_branch);

voltage_angles_min_0(i_bus)..  theta0(i_bus) =g= -pi;

voltage_angles_max_0(i_bus)..  theta0(i_bus) =l= pi;

voltage_angles_min_ck(i_bus, i_contingency)..  thetacontingency(i_bus, i_contingency) =g= -pi;

voltage_angles_max_ck(i_bus, i_contingency)..  thetacontingency(i_bus, i_contingency) =l= pi;

***************************************************************
*** SOLVE
***************************************************************

model test /all/;

*option reslim = 300;
option Savepoint=1;
option optcr=0.0;

option qcp = cplex;
option mip = cplex;
option lp = cplex;
test.optfile=1;

solve test using lp minimizing total_cost;

scalar sol;
sol = test.modelstat;

execute_unload 'PostPSCDCOPF' total_cost, P_thermal, P_hydro, P_pv, P_wind, pf0, theta0, sol;
