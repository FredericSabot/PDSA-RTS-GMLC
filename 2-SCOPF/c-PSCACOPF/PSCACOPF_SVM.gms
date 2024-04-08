***************************************************************
*** SETS
***************************************************************

set i_thermal thermal generators;
set i_hydro hydro generators;
set i_pv utility scale pv generators;
set i_wind wind generators;
set i_rtpv rtpv generators;
set i_syncon synchronous condensers;
set i_bus buses;
set i_branch lines;
set i_contingency contingencies;


*needed for running twice through the same set in a single equation
alias(i_bus,j_bus);
alias(i_thermal,j_thermal);

***************************************************************
*** PARAMETERS
***************************************************************

parameter Epsilon;
Epsilon=1e-6;
parameter M;
M=1e4;
parameter Kg;
Kg=0.1;

*GENERATOR DATA

parameter thermal_map(i_thermal,i_bus) thermal generator map;
parameter hydro_map(i_hydro,i_bus) hydro generator map;
parameter pv_map(i_pv,i_bus) pv generator map;
parameter wind_map(i_wind, i_bus) wind generator map;
parameter rtpv_map(i_rtpv, i_bus) rtpv generator map;
parameter syncon_map(i_syncon,i_bus) SC map;

parameter thermal_min(i_thermal) generator minimum active generation;
parameter thermal_max(i_thermal) generator maximum active generation;
parameter hydro_max(i_hydro) hydro generator available power;
parameter pv_max(i_pv) PV generator available power;
parameter rtpv_max(i_rtpv) rtpv generator available power;
parameter wind_max(i_wind) wind generator available power;

parameter thermal_Qmin(i_thermal) generator minimum reactive generation;
parameter thermal_Qmax(i_thermal) generator maximum reactive generation;
parameter hydro_Qmin(i_hydro) generator minimum reactive generation;
parameter hydro_Qmax(i_hydro) generator maximum reactive generation;
parameter syncon_Qmin(i_syncon) SC minimum reactive generation;
parameter syncon_Qmax(i_syncon) SC maximum reactive generation;
parameter pv_Qmin(i_pv) pv minimum reactive generation;
parameter pv_Qmax(i_pv) pv maximum reactive generation;
parameter wind_Qmin(i_wind) wind minimum reactive generation;
parameter wind_Qmax(i_wind) wind maximum reactive generation;

parameter P_thermal_0(i_thermal) initial thermal output;
parameter Q_thermal_0(i_thermal) initial thermal reactive output;
parameter P_hydro_0(i_hydro) initial hydro output;
parameter Q_hydro_0(i_hydro) initial hydro reactive output;
parameter P_pv_0(i_pv) initial pv output;
parameter P_wind_0(i_wind) initial wind output;
parameter Q_syncon_0(i_syncon) initial syncon reactive output;
parameter Q_pv_0(i_pv) initial pv reactive output;
parameter Q_wind_0(i_wind) initial wind reactive output;
parameter Q_thermal_ck_0(i_thermal, i_contingency);
parameter Q_hydro_ck_0(i_hydro, i_contingency);
parameter Q_syncon_ck_0(i_syncon, i_contingency);
parameter Q_pv_ck_0(i_pv, i_contingency);
parameter Q_wind_ck_0(i_wind, i_contingency);

parameter P_thermal_dc(i_thermal) thermal output in DC solution (used as reference);
parameter P_hydro_dc(i_hydro) hydro output in DC solution (used as reference);
parameter P_pv_dc(i_pv) pv output in DC solution (used as reference);
parameter P_wind_dc(i_wind) wind output in DC solution (used as reference);

*BUS DATA

parameter demand(i_bus) active load at bus s;
parameter demandQ(i_bus) reactive load at bus s;

parameter V_0(i_bus);
parameter theta_0(i_bus);
parameter V_ck_0(i_bus, i_contingency);
parameter theta_ck_0(i_bus, i_contingency);


*LINES DATA

parameter branch_map(i_branch,i_bus) line map;
parameter Gff(i_branch) line conductances (from-from);
parameter Gft(i_branch) line conductances (from-to);
parameter Gtf(i_branch) line conductances (to-from);
parameter Gtt(i_branch) line conductances (to-to);
parameter Bff(i_branch) line susceptances (from-from);
parameter Bft(i_branch) line susceptances (from-to);
parameter Btf(i_branch) line susceptances (to-from);
parameter Btt(i_branch) line susceptances (to-to);

parameter branch_max_N(i_branch) continuous line ratings;
parameter branch_max_E(i_branch) emergency line ratings;

parameter contingency_states(i_branch, i_contingency) line contingencies;

parameter P1_0(i_branch);
parameter Q1_0(i_branch);
parameter P2_0(i_branch);
parameter Q2_0(i_branch);
parameter P1_ck_0(i_branch, i_contingency);
parameter Q1_ck_0(i_branch, i_contingency);
parameter P2_ck_0(i_branch, i_contingency);
parameter Q2_ck_0(i_branch, i_contingency);

$gdxin PrePSCACOPF
$load i_thermal i_hydro i_pv i_rtpv i_wind i_syncon i_bus i_branch i_contingency thermal_map hydro_map pv_map rtpv_map wind_map syncon_map thermal_min thermal_max hydro_max thermal_Qmin thermal_Qmax hydro_Qmin hydro_Qmax syncon_Qmin syncon_Qmax pv_Qmin pv_Qmax wind_Qmin wind_Qmax P_thermal_0 Q_thermal_0 P_hydro_0 P_pv_0 P_wind_0 Q_hydro_0 Q_syncon_0 Q_pv_0 Q_wind_0 demand demandQ branch_max_N branch_max_E Gff Gft Gtf Gtt Bff Bft Btf Btt branch_map contingency_states theta_0 V_0 theta_ck_0 V_ck_0 P1_0 P2_0 Q1_0 Q2_0 P1_ck_0 P2_ck_0 Q1_ck_0 Q2_ck_0 Q_thermal_ck_0 Q_hydro_ck_0 Q_syncon_ck_0 Q_pv_ck_0 Q_wind_ck_0 P_thermal_dc P_hydro_dc P_pv_dc P_wind_dc pv_max rtpv_max wind_max
$gdxin

***************************************************************
*** VARIABLES
***************************************************************

variable deviation total deviation from initial dispatch

positive variable P_thermal(i_thermal) active generator outputs in base state
positive variable P_hydro(i_hydro) active generator outputs in base state
positive variable P_pv(i_pv) pv generator outputs
positive variable P_rtpv(i_rtpv) rtpv generator outputs
positive variable P_wind(i_wind) wind generator outputs

variable Q_thermal(i_thermal) reactive generator outputs in base state
variable Q_hydro(i_hydro) reactive generator outputs in base state
variable Q_syncon(i_syncon) reactive generator outputs in base state
variable Q_pv(i_pv) reactive generator outputs in base state
variable Q_wind(i_wind) reactive generator outputs in base state

positive variable P_thermal_ck(i_thermal, i_contingency) active generator outputs in line contingency state
positive variable P_hydro_ck(i_hydro, i_contingency) active generator outputs in line contingency state
variable Q_thermal_ck(i_thermal, i_contingency) reactive generator outputs in line contingency state
variable Q_hydro_ck(i_hydro, i_contingency) reactive generator outputs in line contingency state
variable Q_syncon_ck(i_syncon, i_contingency) reactive generator outputs in line contingency state
variable Q_pv_ck(i_pv, i_contingency) reactive generator outputs in line contingency state
variable Q_wind_ck(i_wind, i_contingency) reactive generator outputs in line contingency state

positive variable V(i_bus) bus voltage amplitude in base state
positive variable V_ck(i_bus, i_contingency) bus voltage amplitude in line contingency state
variable theta(i_bus) bus voltage angles in base state
variable theta_ck(i_bus, i_contingency) bus voltage angles in line contingency state

positive variable Vdev_pos_ck(i_bus, i_contingency) voltage deviation from generator setpoint;
positive variable Vdev_neg_ck(i_bus, i_contingency) voltage deviation from generator setpoint;

variable P1(i_branch) active power flow through lines in base state
variable Q1(i_branch) reactive power flow through lines in base state
variable P2(i_branch) active power flow through lines in base state
variable Q2(i_branch) reactive power flow through lines in base state

variable P1_ck(i_branch, i_contingency) active power flow through lines in line contingency state
variable Q1_ck(i_branch, i_contingency) reactive power flow through lines in line contingency state
variable P2_ck(i_branch, i_contingency) active power flow through lines in line contingency state
variable Q2_ck(i_branch, i_contingency) reactive power flow through lines in line contingency state

variable DeltaF_ck(i_contingency) frequency deviation after line contingency

***************************************************************
*** EQUATION DECLARATION
***************************************************************

equations

dev objective function
Pg_thermal_min(i_thermal) minimum generator active output
Pg_thermal_max(i_thermal) maximum generator active output
Pg_hydro_max(i_hydro) maximum generator active output
Pg_pv_max(i_pv) pv generator output
Pg_rtpv_max(i_rtpv) rtpv generator output
Pg_wind_max(i_wind) wind generator output
Qg_thermal_min(i_thermal) minimum generator reactive output
Qg_thermal_max(i_thermal) maximum generator reactive output
Qg_hydro_min(i_hydro) minimum generator reactive output
Qg_hydro_max(i_hydro) maximum generator reactive output
Qg_syncon_min(i_syncon) minimum SC generator reactive output
Qg_syncon_max(i_syncon) maximum SC generator reactive output
Qg_pv_min(i_pv) minimum pv generator reactive output
Qg_pv_max(i_pv) maximum pv generator reactive output
Qg_wind_min(i_wind) minimum wind generator reactive output
Qg_wind_max(i_wind) maximum wind generator reactive output
P_balance(i_bus) active power balance for each bus
Q_balance(i_bus) active power balance for each bus
Voltage_min(i_bus) voltage minimum limit
Voltage_max(i_bus) voltage maximum limit
Angles_min(i_bus) voltage angles negative limit
Angles_max(i_bus) voltage angles positive limit
line_P1(i_branch) defining power flow through lines
line_Q1(i_branch) defining power flow through lines
line_P2(i_branch) defining power flow through lines
line_Q2(i_branch) defining power flow through lines
line_max1(i_branch) continuous line rating
line_max2(i_branch) continuous line rating
TPowerDevck(i_thermal, i_contingency) power deviation after a line contingency
HPowerDevck(i_hydro, i_contingency) power deviation after a line contingency
Vdev(i_bus, i_contingency) voltage deviation from generator setpoint
Vdev2(i_bus, i_contingency) voltage deviation from generator setpoint
Qg_thermal_min_ck(i_thermal, i_contingency) minimum generator active output
Qg_thermal_max_ck(i_thermal, i_contingency) maximum generator active output
thermal_PQswitchMax(i_thermal, i_contingency) PQ switch
thermal_PQswitchMin(i_thermal, i_contingency) PQ switch
Qg_hydro_min_ck(i_hydro, i_contingency) minimum generator active output
Qg_hydro_max_ck(i_hydro, i_contingency) maximum generator active output
hydro_PQswitchMax(i_hydro, i_contingency) PQ switch
hydro_PQswitchMin(i_hydro, i_contingency) PQ switch
Qg_syncon_min_ck(i_syncon, i_contingency) minimum generator active output
Qg_syncon_max_ck(i_syncon, i_contingency) maximum generator active output
syncon_PQswitchMax(i_syncon, i_contingency) PQ switch
syncon_PQswitchMin(i_syncon, i_contingency) PQ switch
Qg_pv_min_ck(i_pv, i_contingency) minimum generator active output
Qg_pv_max_ck(i_pv, i_contingency) maximum generator active output
pv_PQswitchMax(i_pv, i_contingency) PQ switch
pv_PQswitchMin(i_pv, i_contingency) PQ switch
Qg_wind_min_ck(i_wind, i_contingency) minimum generator active output
Qg_wind_max_ck(i_wind, i_contingency) maximum generator active output
wind_PQswitchMax(i_wind, i_contingency) PQ switch
wind_PQswitchMin(i_wind, i_contingency) PQ switch
Voltage_min_ck(i_bus, i_contingency) voltage minimum limit
Voltage_max_ck(i_bus, i_contingency) voltage maximum limit
Angles_min_ck(i_bus, i_contingency) voltage angles negative limit
Angles_max_ck(i_bus, i_contingency) voltage angles positive limit
P_balance_ck(i_bus, i_contingency) active power balance for each bus
Q_balance_ck(i_bus, i_contingency) active power balance for each bus
line_P1_ck(i_branch, i_contingency) defining power flow through lines
line_Q1_ck(i_branch, i_contingency) defining power flow through lines
line_P2_ck(i_branch, i_contingency) defining power flow through lines
line_Q2_ck(i_branch, i_contingency) defining power flow through lines
line_max1_ck(i_branch, i_contingency) emergency line rating
line_max2_ck(i_branch, i_contingency) emergency line rating
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

P_thermal.l(i_thermal) = P_thermal_0(i_thermal);
P_hydro.l(i_hydro) = P_hydro_0(i_hydro);
P_pv.l(i_pv) = P_pv_0(i_pv);
P_rtpv.l(i_rtpv) = rtpv_max(i_rtpv);
P_wind.l(i_wind) = P_wind_0(i_wind);

Q_thermal.l(i_thermal) = Q_thermal_0(i_thermal);
Q_hydro.l(i_hydro) = Q_hydro_0(i_hydro);
Q_syncon.l(i_syncon) = Q_syncon_0(i_syncon);
Q_pv.l(i_pv) = Q_pv_0(i_pv);
Q_wind.l(i_wind) = Q_wind_0(i_wind);

P_thermal_ck.l(i_thermal, i_contingency) = P_thermal_0(i_thermal);
P_hydro_ck.l(i_hydro, i_contingency) = P_hydro_0(i_hydro);
Q_thermal_ck.l(i_thermal, i_contingency) = Q_thermal_ck_0(i_thermal, i_contingency);
Q_hydro_ck.l(i_hydro, i_contingency) = Q_hydro_ck_0(i_hydro, i_contingency);
Q_syncon_ck.l(i_syncon, i_contingency) = Q_syncon_ck_0(i_syncon, i_contingency);
Q_pv_ck.l(i_pv, i_contingency) = Q_pv_ck_0(i_pv, i_contingency);
Q_wind_ck.l(i_wind, i_contingency) = Q_wind_ck_0(i_wind, i_contingency);

V.l(i_bus) = V_0(i_bus);
V_ck.l(i_bus, i_contingency) = V_ck_0(i_bus, i_contingency);
theta.l(i_bus) = theta_0(i_bus);
theta_ck.l(i_bus, i_contingency) = theta_ck_0(i_bus, i_contingency);

P1.l(i_branch) = P1_0(i_branch);
Q1.l(i_branch) = Q1_0(i_branch);
P2.l(i_branch) = P2_0(i_branch);
Q2.l(i_branch) = Q2_0(i_branch);

P1_ck.l(i_branch, i_contingency) = P1_ck_0(i_branch, i_contingency);
Q1_ck.l(i_branch, i_contingency) = Q1_ck_0(i_branch, i_contingency);
P2_ck.l(i_branch, i_contingency) = P2_ck_0(i_branch, i_contingency);
Q2_ck.l(i_branch, i_contingency) = Q2_ck_0(i_branch, i_contingency);


***************************************************************
*** EQUATIONS
***************************************************************

dev..
deviation =e= sum(i_thermal, power(P_thermal(i_thermal) - P_thermal_dc(i_thermal), 2))
+ sum(i_hydro, power(P_hydro(i_hydro) - P_hydro_dc(i_hydro), 2))
+ sum(i_pv, power(P_pv(i_pv) - P_pv_dc(i_pv), 2))
+ sum(i_wind, power(P_wind(i_wind) - P_wind_dc(i_wind), 2))
+ Kg * sum(i_thermal, power(Q_thermal(i_thermal) - Q_thermal_0(i_thermal), 2))
+ Kg * sum(i_hydro, power(Q_hydro(i_hydro) - Q_hydro_0(i_hydro), 2))
+ Kg * sum(i_pv, power(Q_pv(i_pv) - Q_pv_0(i_pv), 2))
+ Kg * sum(i_syncon, power(Q_syncon(i_syncon) - Q_syncon_0(i_syncon), 2));

Pg_thermal_min(i_thermal)..
P_thermal(i_thermal) =g= thermal_min(i_thermal);

Pg_thermal_max(i_thermal)..
P_thermal(i_thermal) =l= thermal_max(i_thermal);

Pg_hydro_max(i_hydro)..
P_hydro(i_hydro) =l= hydro_max(i_hydro);

Pg_pv_max(i_pv)..
P_pv(i_pv) =l= pv_max(i_pv);

Pg_rtpv_max(i_rtpv)..
P_rtpv(i_rtpv) =e= rtpv_max(i_rtpv);

Pg_wind_max(i_wind)..
P_wind(i_wind) =l= wind_max(i_wind);

Qg_thermal_min(i_thermal)..
Q_thermal(i_thermal) =g= thermal_Qmin(i_thermal);

Qg_thermal_max(i_thermal)..
Q_thermal(i_thermal) =l= thermal_Qmax(i_thermal);

Qg_hydro_min(i_hydro)..
Q_hydro(i_hydro) =g= hydro_Qmin(i_hydro);

Qg_hydro_max(i_hydro)..
Q_hydro(i_hydro) =l= hydro_Qmax(i_hydro);

Qg_syncon_min(i_syncon)..
Q_syncon(i_syncon) =g= syncon_Qmin(i_syncon);

Qg_syncon_max(i_syncon)..
Q_syncon(i_syncon) =l= syncon_Qmax(i_syncon);

Qg_pv_min(i_pv)..
Q_pv(i_pv) =g= pv_Qmin(i_pv);

Qg_pv_max(i_pv)..
Q_pv(i_pv) =l= pv_Qmax(i_pv);

Qg_wind_min(i_wind)..
Q_wind(i_wind) =g= wind_Qmin(i_wind);

Qg_wind_max(i_wind)..
Q_wind(i_wind) =l= wind_Qmax(i_wind);

Voltage_min(i_bus)..
V(i_bus) =g= 0.95;

Voltage_max(i_bus)..
V(i_bus) =l= 1.05;

Angles_min(i_bus)..
theta(i_bus) =g= -pi;

Angles_max(i_bus)..
theta(i_bus) =l=pi;


P_balance(i_bus)..
sum(i_thermal$(thermal_map(i_thermal,i_bus)),P_thermal(i_thermal))+sum(i_hydro$(hydro_map(i_hydro,i_bus)),P_hydro(i_hydro))+sum(i_pv$(pv_map(i_pv,i_bus)),P_pv(i_pv))+sum(i_rtpv$(rtpv_map(i_rtpv,i_bus)),P_rtpv(i_rtpv))+sum(i_wind$(wind_map(i_wind,i_bus)),P_wind(i_wind))-demand(i_bus)
=e=
sum(i_branch$(branch_map(i_branch,i_bus) = 1),P1(i_branch))+sum(i_branch$(branch_map(i_branch,i_bus) = -1),P2(i_branch));

Q_balance(i_bus)..
sum(i_thermal$(thermal_map(i_thermal,i_bus)),Q_thermal(i_thermal))+sum(i_hydro$(hydro_map(i_hydro,i_bus)),Q_hydro(i_hydro))+sum(i_syncon$(syncon_map(i_syncon,i_bus)),Q_syncon(i_syncon))+sum(i_pv$(pv_map(i_pv,i_bus)),Q_pv(i_pv))+sum(i_wind$(wind_map(i_wind,i_bus)),Q_wind(i_wind))-demandQ(i_bus)
=e=
sum(i_branch$(branch_map(i_branch,i_bus) = 1),Q1(i_branch))+sum(i_branch$(branch_map(i_branch,i_bus) = -1),Q2(i_branch));

line_P1(i_branch)..
P1(i_branch)
=e=
sum(i_bus$(branch_map(i_branch,i_bus) = 1),(sum(j_bus$(branch_map(i_branch,j_bus)=-1), V(i_bus)*(V(i_bus)*Gff(i_branch)+V(j_bus)*Gft(i_branch)*cos(theta(i_bus)-theta(j_bus))+V(j_bus)*Bft(i_branch)*sin(theta(i_bus)-theta(j_bus))))));

line_Q1(i_branch)..
Q1(i_branch)
=e=
sum(i_bus$(branch_map(i_branch,i_bus) = 1),(sum(j_bus$(branch_map(i_branch,j_bus)=-1), V(i_bus)*(-V(i_bus)*Bff(i_branch)+V(j_bus)*Gft(i_branch)*sin(theta(i_bus)-theta(j_bus))-V(j_bus)*Bft(i_branch)*cos(theta(i_bus)-theta(j_bus))))));

line_P2(i_branch)..
P2(i_branch)
=e=
sum(i_bus$(branch_map(i_branch,i_bus) = -1),(sum(j_bus$(branch_map(i_branch,j_bus)=1), V(i_bus)*(V(i_bus)*Gtt(i_branch)+V(j_bus)*Gtf(i_branch)*cos(theta(i_bus)-theta(j_bus))+V(j_bus)*Btf(i_branch)*sin(theta(i_bus)-theta(j_bus))))));

line_Q2(i_branch)..
Q2(i_branch)
=e=
sum(i_bus$(branch_map(i_branch,i_bus) = -1),(sum(j_bus$(branch_map(i_branch,j_bus)=1), V(i_bus)*(-V(i_bus)*Btt(i_branch)+V(j_bus)*Gtf(i_branch)*sin(theta(i_bus)-theta(j_bus))-V(j_bus)*Btf(i_branch)*cos(theta(i_bus)-theta(j_bus))))));

line_max1(i_branch)..
P1(i_branch)*P1(i_branch)+Q1(i_branch)*Q1(i_branch) =l= branch_max_N(i_branch)*branch_max_N(i_branch);

line_max2(i_branch)..
P2(i_branch)*P2(i_branch)+Q2(i_branch)*Q2(i_branch) =l= branch_max_N(i_branch)*branch_max_N(i_branch);

TPowerDevck(i_thermal, i_contingency)..
P_thermal_ck(i_thermal, i_contingency)=e=P_thermal(i_thermal) - DeltaF_ck(i_contingency) * thermal_max(i_thermal);

HPowerDevck(i_hydro, i_contingency)..
P_hydro_ck(i_hydro, i_contingency)=e=P_hydro(i_hydro) - DeltaF_ck(i_contingency) * hydro_max(i_hydro);

Vdev(i_bus, i_contingency)..
V_ck(i_bus, i_contingency) - V(i_bus) - Vdev_pos_ck(i_bus, i_contingency) + Vdev_neg_ck(i_bus, i_contingency) =e= 0;

Vdev2(i_bus, i_contingency)..
Vdev_pos_ck(i_bus, i_contingency) * Vdev_neg_ck(i_bus, i_contingency) =l= 0;

Qg_thermal_min_ck(i_thermal, i_contingency)..
Q_thermal_ck(i_thermal, i_contingency) =g= thermal_Qmin(i_thermal);

Qg_thermal_max_ck(i_thermal, i_contingency)..
Q_thermal_ck(i_thermal, i_contingency) =l= thermal_Qmax(i_thermal);

thermal_PQswitchMax(i_thermal, i_contingency)..
(Q_thermal_ck(i_thermal, i_contingency) - thermal_Qmax(i_thermal)) * sum(i_bus$(thermal_map(i_thermal,i_bus)), Vdev_neg_ck(i_bus, i_contingency)) =e= 0;

thermal_PQswitchMin(i_thermal, i_contingency)..
(Q_thermal_ck(i_thermal, i_contingency) - thermal_Qmin(i_thermal)) * sum(i_bus$(thermal_map(i_thermal,i_bus)), Vdev_pos_ck(i_bus, i_contingency)) =e= 0;

Qg_hydro_min_ck(i_hydro, i_contingency)..
Q_hydro_ck(i_hydro, i_contingency) =g= hydro_Qmin(i_hydro);

Qg_hydro_max_ck(i_hydro, i_contingency)..
Q_hydro_ck(i_hydro, i_contingency) =l= hydro_Qmax(i_hydro);

hydro_PQswitchMax(i_hydro, i_contingency)..
(Q_hydro_ck(i_hydro, i_contingency) - hydro_Qmax(i_hydro)) * sum(i_bus$(hydro_map(i_hydro,i_bus)), Vdev_neg_ck(i_bus, i_contingency)) =e= 0;

hydro_PQswitchMin(i_hydro, i_contingency)..
(Q_hydro_ck(i_hydro, i_contingency) - hydro_Qmin(i_hydro)) * sum(i_bus$(hydro_map(i_hydro,i_bus)), Vdev_pos_ck(i_bus, i_contingency)) =e= 0;

Qg_syncon_min_ck(i_syncon, i_contingency)..
Q_syncon_ck(i_syncon, i_contingency) =g= syncon_Qmin(i_syncon);

Qg_syncon_max_ck(i_syncon, i_contingency)..
Q_syncon_ck(i_syncon, i_contingency) =l= syncon_Qmax(i_syncon);

syncon_PQswitchMax(i_syncon, i_contingency)..
(Q_syncon_ck(i_syncon, i_contingency) - syncon_Qmax(i_syncon)) * sum(i_bus$(syncon_map(i_syncon,i_bus)), Vdev_neg_ck(i_bus, i_contingency)) =e= 0;

syncon_PQswitchMin(i_syncon, i_contingency)..
(Q_syncon_ck(i_syncon, i_contingency) - syncon_Qmin(i_syncon)) * sum(i_bus$(syncon_map(i_syncon,i_bus)), Vdev_pos_ck(i_bus, i_contingency)) =e= 0;

Qg_pv_min_ck(i_pv, i_contingency)..
Q_pv_ck(i_pv, i_contingency) =g= pv_Qmin(i_pv);

Qg_pv_max_ck(i_pv, i_contingency)..
Q_pv_ck(i_pv, i_contingency) =l= pv_Qmax(i_pv);

pv_PQswitchMax(i_pv, i_contingency)..
(Q_pv_ck(i_pv, i_contingency) - pv_Qmax(i_pv)) * sum(i_bus$(pv_map(i_pv,i_bus)), Vdev_neg_ck(i_bus, i_contingency)) =e= 0;

pv_PQswitchMin(i_pv, i_contingency)..
(Q_pv_ck(i_pv, i_contingency) - pv_Qmin(i_pv)) * sum(i_bus$(pv_map(i_pv,i_bus)), Vdev_pos_ck(i_bus, i_contingency)) =e= 0;

Qg_wind_min_ck(i_wind, i_contingency)..
Q_wind_ck(i_wind, i_contingency) =g= wind_Qmin(i_wind);

Qg_wind_max_ck(i_wind, i_contingency)..
Q_wind_ck(i_wind, i_contingency) =l= wind_Qmax(i_wind);

wind_PQswitchMax(i_wind, i_contingency)..
(Q_wind_ck(i_wind, i_contingency) - wind_Qmax(i_wind)) * sum(i_bus$(wind_map(i_wind,i_bus)), Vdev_neg_ck(i_bus, i_contingency)) =e= 0;

wind_PQswitchMin(i_wind, i_contingency)..
(Q_wind_ck(i_wind, i_contingency) - wind_Qmin(i_wind)) * sum(i_bus$(wind_map(i_wind,i_bus)), Vdev_pos_ck(i_bus, i_contingency)) =e= 0;

Voltage_min_ck(i_bus, i_contingency)..
V_ck(i_bus, i_contingency) =g= 0.85;

Voltage_max_ck(i_bus, i_contingency)..
V_ck(i_bus, i_contingency) =l= 1.15;

Angles_min_ck(i_bus, i_contingency)..
theta_ck(i_bus, i_contingency) =g= -pi;

Angles_max_ck(i_bus, i_contingency)..
theta_ck(i_bus, i_contingency) =l= pi;

P_balance_ck(i_bus, i_contingency)..
sum(i_thermal$(thermal_map(i_thermal,i_bus)),P_thermal_ck(i_thermal, i_contingency))+sum(i_hydro$(hydro_map(i_hydro,i_bus)),P_hydro_ck(i_hydro, i_contingency))+sum(i_pv$(pv_map(i_pv,i_bus)),P_pv(i_pv))+sum(i_rtpv$(rtpv_map(i_rtpv,i_bus)),P_rtpv(i_rtpv))+sum(i_wind$(wind_map(i_wind,i_bus)),P_wind(i_wind))-demand(i_bus)
=e=
sum(i_branch$(branch_map(i_branch,i_bus) = 1),P1_ck(i_branch, i_contingency))+sum(i_branch$(branch_map(i_branch,i_bus) = -1),P2_ck(i_branch, i_contingency));

Q_balance_ck(i_bus, i_contingency)..
sum(i_thermal$(thermal_map(i_thermal,i_bus)),Q_thermal_ck(i_thermal, i_contingency))+sum(i_hydro$(hydro_map(i_hydro,i_bus)),Q_hydro_ck(i_hydro, i_contingency))+sum(i_syncon$(syncon_map(i_syncon,i_bus)),Q_syncon_ck(i_syncon, i_contingency))+sum(i_pv$(pv_map(i_pv,i_bus)),Q_pv_ck(i_pv, i_contingency))+sum(i_wind$(wind_map(i_wind,i_bus)),Q_wind_ck(i_wind, i_contingency))-demandQ(i_bus)
=e=
sum(i_branch$(branch_map(i_branch,i_bus) = 1),Q1_ck(i_branch, i_contingency))+sum(i_branch$(branch_map(i_branch,i_bus) = -1),Q2_ck(i_branch, i_contingency));

line_P1_ck(i_branch, i_contingency)..
P1_ck(i_branch, i_contingency)
=e=
contingency_states(i_branch, i_contingency)*sum(i_bus$(branch_map(i_branch,i_bus) = 1),(sum(j_bus$(branch_map(i_branch,j_bus)=-1), V_ck(i_bus, i_contingency)*(V_ck(i_bus, i_contingency)*Gff(i_branch)+V_ck(j_bus, i_contingency)*Gft(i_branch)*cos(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))+V_ck(j_bus, i_contingency)*Bft(i_branch)*sin(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))))));

line_Q1_ck(i_branch, i_contingency)..
Q1_ck(i_branch, i_contingency)
=e=
contingency_states(i_branch, i_contingency)*sum(i_bus$(branch_map(i_branch,i_bus) = 1),(sum(j_bus$(branch_map(i_branch,j_bus)=-1), V_ck(i_bus, i_contingency)*(-V_ck(i_bus, i_contingency)*Bff(i_branch)+V_ck(j_bus, i_contingency)*Gft(i_branch)*sin(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))-V_ck(j_bus, i_contingency)*Bft(i_branch)*cos(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))))));

line_P2_ck(i_branch, i_contingency)..
P2_ck(i_branch, i_contingency)
=e=
contingency_states(i_branch, i_contingency)*sum(i_bus$(branch_map(i_branch,i_bus) = -1),(sum(j_bus$(branch_map(i_branch,j_bus)=1), V_ck(i_bus, i_contingency)*(V_ck(i_bus, i_contingency)*Gtt(i_branch)+V_ck(j_bus, i_contingency)*Gtf(i_branch)*cos(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))+V_ck(j_bus, i_contingency)*Btf(i_branch)*sin(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))))));

line_Q2_ck(i_branch, i_contingency)..
Q2_ck(i_branch, i_contingency)
=e=
contingency_states(i_branch, i_contingency)*sum(i_bus$(branch_map(i_branch,i_bus) = -1),(sum(j_bus$(branch_map(i_branch,j_bus)=1), V_ck(i_bus, i_contingency)*(-V_ck(i_bus, i_contingency)*Btt(i_branch)+V_ck(j_bus, i_contingency)*Gtf(i_branch)*sin(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))-V_ck(j_bus, i_contingency)*Btf(i_branch)*cos(theta_ck(i_bus, i_contingency)-theta_ck(j_bus, i_contingency))))));

line_max1_ck(i_branch, i_contingency)..
P1_ck(i_branch, i_contingency)*P1_ck(i_branch, i_contingency)+Q1_ck(i_branch, i_contingency)*Q1_ck(i_branch, i_contingency) =l= branch_max_E(i_branch)*branch_max_E(i_branch);

line_max2_ck(i_branch, i_contingency)..
P2_ck(i_branch, i_contingency)*P2_ck(i_branch, i_contingency)+Q2_ck(i_branch, i_contingency)*Q2_ck(i_branch, i_contingency) =l= branch_max_E(i_branch)*branch_max_E(i_branch);

svm_1..  0.45017137285781000 * P_wind('4')     + 1.4511474189932392 * P1('90')        - 0.2544157843938867  =l= 0;
svm_2..  0.36892945093405843 * P_wind('4')     - 2.6886343464174383 * P1('5')         + 0.31811346036419885 =l= 0;
svm_3..  0.38535113102319460 * P_wind('4')     + 0.9137304919300593 * P1('23')        - 0.32850729202066187 =l= 0;
svm_4..  -1.1804841909523123 * P1('40')        - 6.206937504035894  * P_pv('17')      - 2.904383293391409   =l= 0;
svm_5..  3.5921365997743906  * P_thermal('43') - 0.9824928341534342 * P_thermal('43') - 10.501771475531958  =l= 0;
svm_6..  0.42710377767560626 * P_wind('4')     - 0.4362250841019868 * P_thermal('17') - 0.6867878502588066  =l= 0;
svm_7..  0.47400399512328034 * P_wind('4')     - 0.0574923375272207 * sum(i_bus, demand(i_bus)) + 0.9844128696545276 =l= 0;
svm_8..  -0.6453051354856414 * P1('40')        - 4.191761732091726  * P_thermal('3')  + 1.6882925314959483  =l= 0;
svm_9..  0.8836073396293335  * P1('103')       + 0.2016951707479213 * P_thermal('17') - 0.1734804018105374  =l= 0;
svm_10.. -1.8966016034683593 * P1('38')        + 3.927877460808147  * P_thermal('19') - 4.9691996422740115  =l= 0;

***************************************************************
*** SOLVE
***************************************************************

model test /all/;

*option reslim = 600;
option nlp=ipopt;
test.optfile=1;

solve test using nlp minimizing deviation;

scalar sol;
sol = test.modelstat;

execute_unload 'PostPSCACOPF' deviation, P_thermal, Q_thermal, P_hydro, Q_hydro, P_pv, P_wind, Q_wind, Q_pv, Q_syncon, V, theta, sol,  V_ck;
