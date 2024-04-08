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
alias (i_branch, i_branchp);


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

parameter lincost(i_thermal) slope of each generator cost curve block;

parameter P_thermal_0(i_thermal) initial thermal outputs;
parameter P_hydro_0(i_hydro) initial hydro outputs;
parameter P_pv_0(i_pv) initial pv outputs;
parameter P_wind_0(i_wind) initial wind outputs;

parameter on_0(i_thermal) initial commitment statuts of generators;

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

parameter contingency_states(i_branch, i_branchp) line contingencies;

*DEMAND DATA

parameter demand(i_bus) demand at each bus;


$gdxin PrePSCDCOPF
$load i_thermal i_hydro i_pv i_wind i_rtpv i_bus i_branch thermal_map hydro_map pv_map wind_map rtpv_map lincost thermal_min thermal_max hydro_max pv_max wind_max rtpv_max branch_admittance branch_map branch_max_N branch_max_E demand contingency_states P_thermal_0 P_hydro_0 P_pv_0 P_wind_0 on_0
$gdxin

***************************************************************
*** VARIABLES
***************************************************************

variable total_cost objective function variable
variable c(i_thermal) operation cost for each thermal generator

variable deviation total deviation from initial dispatch
variable deviation_thermal(i_thermal) absolute deviation from initial thermal dispatch
variable deviation_hydro(i_hydro) absolute deviation from initial hydro dispatch
variable deviation_pv(i_pv) absolute deviation from initial pv dispatch
variable deviation_wind(i_wind) absolute deviation from initial wind dispatch

binary variable on(i_thermal) whether generator i in commited or not

positive variable startup(i_thermal) if gen i has to be started
positive variable shutdown(i_thermal) if gen i has to be shutdown

positive variable P_thermal(i_thermal) thermal generator outputs
positive variable P_hydro(i_hydro) hydro generator outputs
positive variable P_pv(i_pv) pv generator outputs
positive variable P_wind(i_wind) wind generator outputs
positive variable P_rtpv(i_rtpv) rtpv generator outputs

positive variable P_thermal_contingency(i_thermal, i_branchp) thermal generator output for contingency i
positive variable P_hydro_contingency(i_hydro, i_branchp) hydro generator output for contingency i
positive variable P_pv_contingency(i_pv, i_branchp) pv generator output for contingency i
positive variable P_wind_contingency(i_wind, i_branchp) wind generator output for contingency i
positive variable P_rtpv_contingency(i_rtpv, i_branchp) rtpv generator output generators for contingency i

variable pf0(i_branch) power flow through lines in initial state
variable pfcontingency(i_branch, i_branchp) power flow through lines in contingency i

variable theta0(i_bus) bus voltage angles
variable thetacontingency(i_bus, i_branchp) bus voltage angles in contingency i

***************************************************************
*** EQUATION DECLARATION
***************************************************************

equations

cost objective function
cost_sum(i_thermal) generation cost summation
dev_thermal_plus positive deviation from initial thermal dispatch
dev_thermal_minus negative deviation from initial thermal dispatch
dev_hydro_plus positive deviation from initial hydro dispatch
dev_hydro_minus negative deviation from initial hydro dispatch
dev_pv_plus positive deviation from initial pv dispatch
dev_pv_minus negative deviation from initial pv dispatch
dev_wind_plus positive deviation from initial wind dispatch
dev_wind_minus negative deviation from initial wind dispatch
start(i_thermal) generators that have to be turn on
shut(i_thermal) generators that have to be turn off
dev total deviation from initial dispatch
thermal_minP(i_thermal) minimum thermal generator output
thermal_maxP(i_thermal) maximum thermal generator output
hydro_maxP(i_hydro) maximum hydro generator output
pv_maxP(i_pv) maximum pv generator output
wind_maxP(i_wind) maximum wind generator output
rtpv_maxP(i_rtpv) maximum rtpv generator output
power_balance_0(i_bus) power balance for each bus
power_balance_contingency(i_bus, i_branchp) power balance for each bus for contingency i
P_thermal_cont(i_thermal, i_branchp) thermal outputs for contingency i
P_hydro_cont(i_hydro, i_branchp) hydro outputs for contingency i
P_pv_cont(i_pv, i_branchp) pv outputs for contingency i
P_wind_cont(i_wind, i_branchp) wind outputs for contingency i
P_rtpv_cont(i_rtpv, i_branchp) rtpv outputs for contingency i
line_flow_0(i_branch) defining power flow through lines
line_flow_contingency(i_branch, i_branchp) defining power flow through lines for contingency i
line_capacity_min_0(i_branch) line capacitiy negative limit
line_capacity_max_0(i_branch) line capacitiy positive limit
line_capacity_min_contingency(i_branch, i_branchp) line capacitiy negative limit for contingency i
line_capacity_max_contingency(i_branch, i_branchp) line capacitiy positive limit for contingency i
voltage_angles_min_0(i_bus) voltage angles negative limit
voltage_angles_max_0(i_bus) voltage angles positive limit
voltage_angles_min_ck(i_bus, i_branch) voltage angles negative limit for contingency i_states
voltage_angles_max_ck(i_bus, i_branch) voltage angles positive limit for contingency i_states
svm_1  Support vector machine constraint to represent dynamic stability
svm_2  Support vector machine constraint to represent dynamic stability
svm_3  Support vector machine constraint to represent dynamic stability
svm_4  Support vector machine constraint to represent dynamic stability
svm_5  Support vector machine constraint to represent dynamic stability
svm_6  Support vector machine constraint to represent dynamic stability
svm_7  Support vector machine constraint to represent dynamic stability
svm_8  Support vector machine constraint to represent dynamic stability
svm_9  Support vector machine constraint to represent dynamic stability
svm_10 Support vector machine constraint to represent dynamic stability
;


***************************************************************
*** SETTINGS
***************************************************************

*setting the reference bus
theta0.fx ('1') = 0;
thetacontingency.fx('1', i_branchp)= 0;


***************************************************************
*** EQUATIONS
***************************************************************

cost..
total_cost =e= sum(i_thermal, c(i_thermal));

cost_sum(i_thermal)..       c(i_thermal) =e= P_thermal(i_thermal) * lincost(i_thermal);

dev_thermal_plus(i_thermal)..
deviation_thermal(i_thermal) =g= P_thermal(i_thermal) - P_thermal_0(i_thermal);

dev_thermal_minus(i_thermal)..
deviation_thermal(i_thermal) =g= -(P_thermal(i_thermal) - P_thermal_0(i_thermal));

dev_hydro_plus(i_hydro)..
deviation_hydro(i_hydro) =g= P_hydro(i_hydro) - P_hydro_0(i_hydro);

dev_hydro_minus(i_hydro)..
deviation_hydro(i_hydro) =g= -(P_hydro(i_hydro) - P_hydro_0(i_hydro));

dev_pv_plus(i_pv)..
deviation_pv(i_pv) =g= P_pv(i_pv) - P_pv_0(i_pv);

dev_pv_minus(i_pv)..
deviation_pv(i_pv) =g= -(P_pv(i_pv) - P_pv_0(i_pv));

dev_wind_plus(i_wind)..
deviation_wind(i_wind) =g= P_wind(i_wind) - P_wind_0(i_wind);

dev_wind_minus(i_wind)..
deviation_wind(i_wind) =g= -(P_wind(i_wind) - P_wind_0(i_wind));

start(i_thermal)..
startup(i_thermal) =g= on(i_thermal) - on_0(i_thermal);

shut(i_thermal)..
shutdown(i_thermal) =g= on_0(i_thermal) - on(i_thermal);

dev..
deviation =e= 10 * sum(i_thermal, startup(i_thermal) + shutdown(i_thermal)) + sum(i_thermal, deviation_thermal(i_thermal)) + sum(i_hydro, deviation_hydro(i_hydro)) + sum(i_pv, deviation_pv(i_pv)) + sum(i_wind, deviation_wind(i_wind));

*dev..
*deviation =e= sum(i_thermal, (P_thermal(i_thermal) - P_thermal_0(i_thermal)) * (P_thermal(i_thermal) - P_thermal_0(i_thermal))) + sum(i_hydro, (P_hydro(i_hydro) - P_hydro_0(i_hydro)) * (P_hydro(i_hydro) - P_hydro_0(i_hydro))) + sum(i_pv, (P_pv(i_pv) - P_pv_0(i_pv)) * (P_pv(i_pv) - P_pv_0(i_pv))) + sum(i_wind, (P_wind(i_wind) - P_wind_0(i_wind)) * (P_wind(i_wind) - P_wind_0(i_wind)));

thermal_minP(i_thermal)..   P_thermal(i_thermal) =g= on(i_thermal) * thermal_min(i_thermal);

thermal_maxP(i_thermal)..   P_thermal(i_thermal) =l= on(i_thermal) * thermal_max(i_thermal);

hydro_maxP(i_hydro)..       P_hydro(i_hydro) =l= hydro_max(i_hydro);

pv_maxP(i_pv)..       P_pv(i_pv) =l= pv_max(i_pv);

wind_maxP(i_wind)..       P_wind(i_wind) =l= wind_max(i_wind);

rtpv_maxP(i_rtpv)..         P_rtpv(i_rtpv) =e= rtpv_max(i_rtpv);

power_balance_0(i_bus)..    sum(i_thermal$(thermal_map(i_thermal, i_bus)), P_thermal(i_thermal)) + sum(i_hydro$(hydro_map(i_hydro, i_bus)), P_hydro(i_hydro)) + sum(i_pv$(pv_map(i_pv, i_bus)), P_pv(i_pv)) + sum(i_wind$(wind_map(i_wind, i_bus)), P_wind(i_wind)) + sum(i_rtpv$(rtpv_map(i_rtpv, i_bus)), P_rtpv(i_rtpv)) - sum(i_branch, pf0(i_branch)*branch_map(i_branch, i_bus))
                            =e= demand(i_bus);

power_balance_contingency(i_bus, i_branchp)..   sum(i_thermal$(thermal_map(i_thermal, i_bus)), P_thermal_contingency(i_thermal, i_branchp)) + sum(i_hydro$(hydro_map(i_hydro, i_bus)), P_hydro_contingency(i_hydro, i_branchp)) + sum(i_pv$(pv_map(i_pv, i_bus)), P_pv_contingency(i_pv, i_branchp)) + sum(i_wind$(wind_map(i_wind, i_bus)), P_wind_contingency(i_wind, i_branchp)) + sum(i_rtpv$(rtpv_map(i_rtpv, i_bus)), P_rtpv_contingency(i_rtpv, i_branchp)) + sum(i_branch, pfcontingency(i_branch, i_branchp)*branch_map(i_branch, i_bus))
                            =e= demand(i_bus);

P_thermal_cont(i_thermal, i_branchp)..  P_thermal_contingency(i_thermal, i_branchp) =e= P_thermal(i_thermal);

P_hydro_cont(i_hydro, i_branchp)..      P_hydro_contingency(i_hydro, i_branchp) =e= P_hydro(i_hydro);

P_pv_cont(i_pv, i_branchp)..      P_pv_contingency(i_pv, i_branchp) =e= P_pv(i_pv);

P_wind_cont(i_wind, i_branchp)..      P_wind_contingency(i_wind, i_branchp) =e= P_wind(i_wind);

P_rtpv_cont(i_rtpv, i_branchp)..        P_rtpv_contingency(i_rtpv, i_branchp) =e= P_rtpv(i_rtpv);

line_flow_0(i_branch)..         pf0(i_branch) =e= -branch_admittance(i_branch)*sum(i_bus, theta0(i_bus)*branch_map(i_branch, i_bus));

line_flow_contingency(i_branch, i_branchp)..         pfcontingency(i_branch, i_branchp) =e= contingency_states(i_branch, i_branchp)*branch_admittance(i_branch)*sum(i_bus, thetacontingency(i_bus, i_branchp)*branch_map(i_branch, i_bus));

line_capacity_min_0(i_branch)..   pf0(i_branch) =g= -0.95 * branch_max_N(i_branch);

line_capacity_max_0(i_branch)..   pf0(i_branch) =l= 0.95 * branch_max_N(i_branch);

line_capacity_min_contingency(i_branch, i_branchp)..   pfcontingency(i_branch, i_branchp) =g= -0.95 * contingency_states(i_branch, i_branchp)*branch_max_E(i_branch);

line_capacity_max_contingency(i_branch, i_branchp)..   pfcontingency(i_branch, i_branchp) =l= 0.95 * contingency_states(i_branch, i_branchp)*branch_max_E(i_branch);

voltage_angles_min_0(i_bus)..  theta0(i_bus) =g= -pi;

voltage_angles_max_0(i_bus)..  theta0(i_bus) =l= pi;

voltage_angles_min_ck(i_bus, i_branchp)..  thetacontingency(i_bus, i_branchp) =g= -pi;

voltage_angles_max_ck(i_bus, i_branchp)..  thetacontingency(i_bus, i_branchp) =l= pi;

svm_1..  0.45017137285781000 * P_wind('4')     + 1.4511474189932392 * pf0('90')       - 0.2544157843938867  =l= 0;
svm_2..  0.36892945093405843 * P_wind('4')     - 2.6886343464174383 * pf0('5')        + 0.31811346036419885 =l= 0;
svm_3..  0.38535113102319460 * P_wind('4')     + 0.9137304919300593 * pf0('23')       - 0.32850729202066187 =l= 0;
svm_4..  -1.1804841909523123 * pf0('40')       - 6.206937504035894  * P_pv('17')      - 2.904383293391409   =l= 0;
svm_5..  3.5921365997743906  * P_thermal('43') - 0.9824928341534342 * P_thermal('43') - 10.501771475531958  =l= 0;
svm_6..  0.42710377767560626 * P_wind('4')     - 0.4362250841019868 * P_thermal('17') - 0.6867878502588066  =l= 0;
svm_7..  0.47400399512328034 * P_wind('4')     - 0.0574923375272207 * sum(i_bus, demand(i_bus)) + 0.9844128696545276 =l= 0;
svm_8..  -0.6453051354856414 * pf0('40')       - 4.191761732091726  * P_thermal('3')  + 1.6882925314959483  =l= 0;
svm_9..  0.8836073396293335  * pf0('103')      + 0.2016951707479213 * P_thermal('17') - 0.1734804018105374  =l= 0;
svm_10.. -1.8966016034683593 * pf0('38')       + 3.927877460808147  * P_thermal('19') - 4.9691996422740115  =l= 0;

***************************************************************
*** SOLVE
***************************************************************

model test /all/;

option reslim = 1000000;
option Savepoint=1;
option optcr=0.0;

option qcp = cplex;
option mip = cplex;

solve test using mip minimizing deviation;

scalar sol;
sol = test.modelstat;

execute_unload 'PostPSCDCOPF' total_cost, c, deviation, on, P_thermal, P_hydro, P_pv, P_wind, pf0, theta0, sol;
