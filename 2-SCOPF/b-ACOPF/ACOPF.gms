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
set i_branch branches;

***************************************************************
*** PARAMETERS
***************************************************************

parameter Epsilon;
Epsilon = 1e-4;

parameter Kg;
Kg = 0.1;

*GENERATOR DATA

parameter thermal_map(i_thermal, i_bus) thermal generator map;
parameter hydro_map(i_hydro, i_bus) hydro generator map;
parameter pv_map(i_pv, i_bus) pv generator map;
parameter wind_map(i_wind, i_bus) wind generator map;
parameter rtpv_map(i_rtpv, i_bus) rtpv generator map;
parameter syncon_map(i_syncon, i_bus) SC map;

parameter P_thermal_0(i_thermal) initial thermal outputs;
parameter P_hydro_0(i_hydro) initial hydro outputs;
parameter P_pv_0(i_pv) initial pv outputs;
parameter P_wind_0(i_wind) initial wind outputs;
parameter Ppf_0(i_branch) initial line active power flows;

parameter thermal_min(i_thermal) thermal generator minimum generation;
parameter thermal_max(i_thermal) thermal generator maximum generation;
parameter hydro_max(i_hydro) hydro generator available power;
parameter pv_max(i_pv) pv generator available power;
parameter rtpv_max(i_rtpv) rtpv generator available power;
parameter wind_max(i_wind) wind generator available power;

parameter thermal_Qmin(i_thermal) thermal generator minimum reactive generation;
parameter thermal_Qmax(i_thermal) thermal generator maximum reactive generation;
parameter hydro_Qmin(i_hydro) hydro generator minimum reactive generation;
parameter hydro_Qmax(i_hydro) hydro generator maximum reactive generation;
parameter syncon_Qmin(i_syncon) syncon generator minimum reactive generation;
parameter syncon_Qmax(i_syncon) syncon generator maximum reactive generation;
parameter wind_Qmin(i_wind) wind generator minimum reactive generation;
parameter wind_Qmax(i_wind) wind generator maximum reactive generation;

*LINES DATA

parameter branch_map(i_branch,i_bus) line map;
parameter G(i_bus,i_bus) conductance matrix;
parameter B(i_bus,i_bus) susceptance matrix;
parameter Gff(i_branch) line conductance (from-from);
parameter Gft(i_branch) line conductance (from-to);
parameter Bff(i_branch) line susceptance (from-from);
parameter Bft(i_branch) line susceptance (from-to);

parameter branch_max_N(i_branch) line capacities;

*DEMAND DATA

parameter demand(i_bus) active load at bus s;
parameter demandQ(i_bus) reactive load at bus s;


$gdxin PreACOPF
$load i_thermal i_hydro i_pv i_rtpv i_wind i_syncon i_bus i_branch thermal_map hydro_map pv_map rtpv_map wind_map syncon_map thermal_min thermal_max hydro_max pv_max rtpv_max wind_max P_thermal_0 P_hydro_0 P_pv_0 P_wind_0 Ppf_0 thermal_Qmin thermal_Qmax hydro_Qmin hydro_Qmax syncon_Qmin syncon_Qmax wind_Qmin wind_Qmax demand demandQ G B Gff Gft Bff Bft branch_map branch_max_N
$gdxin

***************************************************************
*** VARIABLES
***************************************************************

variable deviation total deviation from initial dispatch

positive variable P_thermal(i_thermal) active thermal generator outputs
positive variable P_hydro(i_hydro) active hydro generator outputs
positive variable P_pv(i_pv) pv generator outputs
positive variable P_rtpv(i_rtpv) rtpv generator outputs
positive variable P_wind(i_wind) wind generator outputs

variable Q_thermal(i_thermal) reactive thermal generator outputs
variable Q_hydro(i_hydro) reactive hydro generator outputs
variable Q_syncon(i_syncon) reactive SC outputs
variable Q_wind(i_wind) reactive SC outputs

variable V(i_bus) bus voltage amplitude
variable theta(i_bus) bus voltage angles

variable Ppf(i_branch) active power flow through lines
variable Qpf(i_branch) reactive power flow through lines

variable pf(i_branch) power flow through lines

***************************************************************
*** EQUATION DECLARATION
***************************************************************

equations

dev objective function
Pg_thermal_min(i_thermal) minimum generator active output
Pg_thermal_max(i_thermal) maximum generator active output
Pg_hydro_max(i_hydro) maximum hydro generator active output
Pg_pv_max(i_pv)  maximum pv generator active output
Pg_rtpv_max(i_rtpv)  rtpv generator active output
Pg_wind_max(i_wind)  maximum wind generator active output
Qg_thermal_min(i_thermal) minimum thermal generator reactive output
Qg_thermal_max(i_thermal) maximum thermal generator reactive output
Qg_hydro_min(i_hydro) minimum hydro generator reactive output
Qg_hydro_max(i_hydro) maximum hydro generator reactive output
Qg_syncon_min(i_syncon) minimum SC generator reactive output
Qg_syncon_max(i_syncon) maximum SC generator reactive output
Qg_wind_min(i_wind) minimum SC generator reactive output
Qg_wind_max(i_wind) maximum SC generator reactive output
P_balance(i_bus) active power balance for each bus
Q_balance(i_bus) active power balance for each bus
Voltage_min(i_bus) voltage minimum limit
Voltage_max(i_bus) voltage maximum limit
Voltage_angles_min(i_bus) voltage angles negative limit
Voltage_angles_max(i_bus) voltage angles positive limit
line_Pflow(i_branch) defining power flow through lines
line_Qflow(i_branch) defining power flow through lines
line_flow(i_branch) defining power flow through lines
line_capacity(i_branch) line capacitiy limit;


***************************************************************
*** SETTINGS
***************************************************************

*setting the reference bus
theta.fx ('1') = 0;
theta.l(i_bus)=0;

V.l(i_bus)=1;

P_thermal.l(i_thermal) = P_thermal_0(i_thermal);
P_hydro.l(i_hydro) = P_hydro_0(i_hydro);
P_pv.l(i_pv) = P_pv_0(i_pv);
P_wind.l(i_wind) = P_wind_0(i_wind);
Ppf.l(i_branch) = Ppf_0(i_branch);

*needed for running twice through the same set in a single equation
alias(i_bus, jb);


***************************************************************
*** EQUATIONS
***************************************************************

dev..
deviation =e= sum(i_thermal, power(P_thermal(i_thermal) - P_thermal_0(i_thermal), 2)) + sum(i_hydro, power(P_hydro(i_hydro) - P_hydro_0(i_hydro), 2)) + sum(i_pv, power(P_pv(i_pv) - P_pv_0(i_pv), 2)) + sum(i_wind, power(P_wind(i_wind) - P_wind_0(i_wind), 2))  + Kg * sum(i_thermal, power(Q_thermal(i_thermal) - (thermal_Qmax(i_thermal) + thermal_Qmin(i_thermal))/2, 2) / power(thermal_Qmax(i_thermal) - thermal_Qmin(i_thermal) + Epsilon, 2)) + Kg * sum(i_hydro, power(Q_hydro(i_hydro) - (hydro_Qmax(i_hydro) + hydro_Qmin(i_hydro))/2, 2) / power(hydro_Qmax(i_hydro) - hydro_Qmin(i_hydro) + Epsilon, 2)) + Kg * sum(i_syncon, power(Q_syncon(i_syncon) - (syncon_Qmax(i_syncon) + syncon_Qmin(i_syncon))/2, 2) / power(syncon_Qmax(i_syncon) - syncon_Qmin(i_syncon) + Epsilon, 2)) + Kg * sum(i_wind, power(Q_wind(i_wind) - (wind_Qmax(i_wind) + wind_Qmin(i_wind))/2, 2) / power(wind_Qmax(i_wind) - wind_Qmin(i_wind) + Epsilon, 2));
* sum(i_thermal, power(P_thermal(i_thermal) - P_thermal_0(i_thermal), 2))
* + sum(i_hydro, power(P_hydro(i_hydro) - P_hydro_0(i_hydro), 2))
* + sum(i_pv, power(P_pv(i_pv) - P_pv_0(i_pv), 2))
* + sum(i_wind, power(P_wind(i_wind) - P_wind_0(i_wind), 2))
*
* + Kg * sum(i_thermal, power(Q_thermal(i_thermal) - (Q_thermal_max(i_thermal) + Q_thermal_min(i_thermal))/2, 2) / power(Q_thermal_max(i_thermal) - Q_thermal_min(i_thermal) + Epsilon, 2))
* + Kg * sum(i_hydro, power(Q_hydro(i_hydro) - (Q_hydro_max(i_hydro) + Q_hydro_min(i_hydro))/2, 2) / power(Q_hydro_max(i_hydro) - Q_hydro_min(i_hydro) + Epsilon, 2))
* + Kg * sum(i_syncon, power(Q_syncon(i_syncon) - (Q_syncon_max(i_syncon) + Q_syncon_min(i_syncon))/2, 2) / power(Q_syncon_max(i_syncon) - Q_syncon_min(i_syncon) + Epsilon, 2))
* + Kg * sum(i_wind, power(Q_wind(i_wind) - (Q_wind_max(i_wind) + Q_wind_min(i_wind))/2, 2) / power(Q_wind_max(i_wind) - Q_wind_min(i_wind) + Epsilon, 2))

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

Qg_wind_min(i_wind)..
Q_wind(i_wind) =g= wind_Qmin(i_wind);

Qg_wind_max(i_wind)..
Q_wind(i_wind) =l= wind_Qmax(i_wind);

P_balance(i_bus)..
sum(i_thermal$(thermal_map(i_thermal, i_bus)), P_thermal(i_thermal)) + sum(i_hydro$(hydro_map(i_hydro, i_bus)), P_hydro(i_hydro)) + sum(i_pv$(pv_map(i_pv, i_bus)), P_pv(i_pv)) + sum(i_rtpv$(rtpv_map(i_rtpv, i_bus)), P_rtpv(i_rtpv)) + sum(i_wind$(wind_map(i_wind, i_bus)), P_wind(i_wind)) - demand(i_bus)
=e=
V(i_bus) * sum(jb,V(jb) * (G(i_bus,jb) * cos(theta(i_bus)-theta(jb)) + B(i_bus,jb) * sin(theta(i_bus)-theta(jb))));

Q_balance(i_bus)..
sum(i_thermal$(thermal_map(i_thermal,i_bus)),Q_thermal(i_thermal)) + sum(i_hydro$(hydro_map(i_hydro,i_bus)),Q_hydro(i_hydro)) + sum(i_syncon$(syncon_map(i_syncon,i_bus)),Q_syncon(i_syncon)) + sum(i_wind$(wind_map(i_wind,i_bus)),Q_wind(i_wind)) - demandQ(i_bus)
=e=
V(i_bus) * sum(jb,V(jb) * (G(i_bus,jb) * sin(theta(i_bus)-theta(jb)) - B(i_bus,jb) * cos(theta(i_bus)-theta(jb))));

Voltage_min(i_bus)..
V(i_bus) =g= 0.95;

Voltage_max(i_bus)..
V(i_bus) =l= 1.05;

Voltage_angles_min(i_bus)..
theta(i_bus) =g= -pi;

Voltage_angles_max(i_bus)..
theta(i_bus) =l= pi;

line_Pflow(i_branch)..
Ppf(i_branch) =e=
sum(i_bus$(branch_map(i_branch,i_bus) = 1), (sum(jb$(branch_map(i_branch,jb)=-1), V(i_bus) * V(jb) * (Gft(i_branch) * cos(theta(i_bus)-theta(jb)) + Bft(i_branch) * sin(theta(i_bus)-theta(jb))) + Gff(i_branch) * power(V(i_bus), 2) )));

line_Qflow(i_branch)..
Qpf(i_branch) =e=
sum(i_bus$(branch_map(i_branch,i_bus) = 1),(sum(jb$(branch_map(i_branch,jb)=-1), V(i_bus) * V(jb) * (Gft(i_branch) * sin(theta(i_bus)-theta(jb)) - Bft(i_branch) * cos(theta(i_bus)-theta(jb))) - Bff(i_branch) * power(V(i_bus), 2) )));

line_flow(i_branch)..
pf(i_branch) =e= Ppf(i_branch) * Ppf(i_branch) + Qpf(i_branch) * Qpf(i_branch);

line_capacity(i_branch)..
pf(i_branch) =l= branch_max_N(i_branch) * branch_max_N(i_branch);

***************************************************************
*** SOLVE
***************************************************************

model test /all/;
option nlp=ipopt;
solve test using nlp minimizing deviation;

scalar sol;
sol = test.modelstat;

execute_unload 'PostACOPF' deviation, P_thermal, Q_thermal, P_hydro, Q_hydro, P_pv, P_wind, Q_wind, Q_syncon, V, theta, pf, sol;
