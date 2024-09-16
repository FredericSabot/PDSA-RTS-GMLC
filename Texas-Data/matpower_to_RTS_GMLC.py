import scipy.io as sio
import csv
import geopy.distance


def AUX_line_parser(data_line: str):
    out = []
    part = ''
    open_parenthesis = False
    for char in data_line:
        if char == '"':
            open_parenthesis = not open_parenthesis
            if not open_parenthesis:
                out.append(part)
                part = ''
        elif char.isspace() and not open_parenthesis:
            if part != '':
                out.append(part)
                part = ''
        else:
            part += char
    return out


def bus_name_to_substation_name(bus_name):
    bus_name_split = bus_name.split(' ')
    substation_name = bus_name_split[0]
    for part in bus_name_split[1:]:
        substation_name += ' ' + part
        if part.isdigit():
            break
    # substation_name = ' '.join(bus_name.split(' ')[:2])  # Remove bus_id from bus_name

    # Manual correction of some inconsistencies
    if substation_name == 'EL DORADO 4':
        substation_name = 'ELDORADO 4'
    if substation_name == 'SAN PERALTA 3':
        substation_name = 'SAN PERLITA 3'
    if substation_name == '5_3_2021 1':
        substation_name = '5_3_2021'
    if substation_name == '5_1_2021 1':
        substation_name = '5_1_2021'
    if substation_name == '5_2_2021 1':
        substation_name = '5_2_2021'
    return substation_name


def get_substation_locations():
    substation_locations = {}
    with open('Texas7k_2030_20220923.AUX') as f:
        expect_start = False
        start = False
        while True:
            line = f.readline()
            if not expect_start:
                if line.startswith('DATA (Substation,'):
                    expect_start = True
            else:
                if not start:
                    if line.strip() == '{':
                        start = True
                else:
                    if line.strip() == '}':
                        break

                    data = AUX_line_parser(line)
                    substation_name = data[1]
                    latitude = data[3]
                    longitude = data[4]
                    substation_locations[substation_name] = [latitude, longitude]
            if not line:
                raise RuntimeError('End of file reached before finding necessary data')

    return substation_locations

substation_locations = get_substation_locations()


def fuel_translation(fuel):
    match fuel:
        case 'coal':
            return 'Coal'
        case 'hydro':
            return 'Hydro'
        case 'ng':
            return 'NG'
        case 'nuclear':
            return 'Nuclear'
        case 'solar':
            return 'PV'
        case 'wind':
            return 'Wind'
        case 'dfo':
            return 'Oil'
        case 'other':
            return 'Coal'  # Arbitrary
        case 'wasteheat':  # 2021 version only
            return 'Coal'
        case 'wood':
            return 'Coal'
        case _:
            raise NotImplementedError(fuel, 'is not considered')
        # else raise?


mpc = sio.loadmat('Texas2030.mat')['mpc']

# 0D data
baseMVA = mpc['baseMVA'][0][0][0][0]
mpc_version = mpc['version'][0][0][0][0]
if mpc_version != '2':
    raise NotImplementedError()

# 2D data
buses = mpc['bus'][0][0]  # Bus ID,Bus Name,BaseKV,Bus Type,MW Load,MVAR Load,V Mag,V Angle,MW Shunt G,MVAR Shunt B,Area,Sub Area,Zone,lat,lng
gens = mpc['gen'][0][0]  # bus	Pg	Qg	Qmax	Qmin	Vg	mBase	status	Pmax	Pmin	Pc1	Pc2	Qc1min	Qc1max	Qc2min	Qc2max	ramp_agc	ramp_10	ramp_30	ramp_q	apf	mu_Pmax	mu_Pmin	mu_Qmax	mu_Qmin
branches = mpc['branch'][0][0]  # fbus	tbus	r	x	b	rateA	rateB	rateC	ratio	angle	status	angmin	angmax	Pf	Qf	Pt	Qt	mu_Sf	mu_St	mu_angmin	mu_angmax
costs = mpc['gencost'][0][0]  # 2	startup	shutdown	n	c(n-1)	...	c0

# 1D data
gen_fuels = [fuel[0][0] for fuel in mpc['genfuel'][0][0]]
gen_fuels = [fuel_translation(fuel) for fuel in gen_fuels]
bus_names = [bus_names[0][0] for bus_names in mpc['bus_name'][0][0]]

bus_id_to_name = {}
for i, bus in enumerate(buses):
    bus_id = int(bus[0])
    bus_id_to_name[bus_id] = bus_names[i]


parallel_line_count = {}
with open('branch.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow('UID,From Bus,To Bus,R,X,B,Cont Rating,LTE Rating,STE Rating,Perm OutRate,Duration,Tr Ratio,Tran OutRate,Length'.split(','))  # Output format

    for branch in branches:
        from_bus = int(branch[0])
        to_bus = int(branch[1])
        branch_id = f'{from_bus}-{to_bus}'
        if branch_id in parallel_line_count:
            parallel_line_count[branch_id] += 1
        else:
            parallel_line_count[branch_id] = 1
        branch_id += '_' + str(parallel_line_count[branch_id])

        r = branch[2]
        x = branch[3]
        b = branch[4]
        rate_A = branch[5]
        rate_B = max(branch[6], rate_A)  # Clean-up: emergency rating should be higher or equal to continuous rating
        rate_C = max(branch[7], rate_B)
        if rate_B > 1.05 * branch[6] or rate_C > 1.05 * branch[7]:
            print('Warning: inconsistent line limits (emergency lower than continuous) for line', branch_id, branch[5], branch[6], branch[7])
        permanent_outage_rate = 0
        outage_duration = 0
        ratio = branch[8]
        transient_outage_rate = 0
        location_from = substation_locations[bus_name_to_substation_name(bus_id_to_name[from_bus])]
        location_to   = substation_locations[bus_name_to_substation_name(bus_id_to_name[to_bus])]
        length = geopy.distance.geodesic(location_from, location_to).km
        if from_bus < 10000 or to_bus < 10000:
            if ratio == 0:
                ratio = 1
                print(f'Warning: new element {branch_id} for 2030 version is considered to be a transformer (no new lines have been modelled)')
            if length != 0:
                length = 0
                print(f'Warning: new element {branch_id} for 2030 version is considered to be a transformer (no new lines have been modelled)')
        if length == 0:
            if ratio == 0:
                ratio = 1
                print(f'Warning: line {branch_id} has zero length and has thus been replaced by a transformer')
        writer.writerow([branch_id, from_bus, to_bus, r, x, b, rate_A, rate_B, rate_C, permanent_outage_rate, outage_duration, ratio, transient_outage_rate, length])

with open('bus.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow('Bus ID,Bus Name,BaseKV,Bus Type,MW Load,MVAR Load,V Mag,V Angle,MW Shunt G,MVAR Shunt B,Area,Sub Area,Zone,lat,lng'.split(','))

    for i, bus in enumerate(buses):
        # bus_i	type	Pd	Qd	Gs	Bs	area	Vm	Va	baseKV	zone	Vmax	Vmin	lam_P	lam_Q	mu_Vmax	mu_Vmin
        bus_id = int(bus[0])
        bus_name = bus_names[i]
        base_kv = bus[9]
        if bus_id < 10000:
            if base_kv == 345:
                print(f'Warning: new bus {bus_id} for 2030 version is considered to be at a low voltage level (no new lines have been added, only generators)')
                base_kv = 138
        if bus[1] == 1:
            bus_type = 'PQ'
        else:
            bus_type = 'PV'
        P = bus[2]
        Q = bus[3]
        V = bus[7]
        phi = bus[8]
        G = bus[4]
        B = bus[5]
        area = int(bus[6])
        sub_area = int(bus[10])
        zone = 1
        substation_name = bus_name_to_substation_name(bus_name)
        # if substation_name in substation_locations:
        #     latitude, longitude = substation_locations[substation_name]
        # else:
        #     print(bus_name, substation_name)
        latitude, longitude = substation_locations[substation_name]

        writer.writerow([bus_id, bus_name, base_kv, bus_type, P, Q, V, phi, G, B, area, sub_area, zone, latitude, longitude])

with open('dc_branch.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow('UID,From Bus,To Bus,Control Mode,R Line,MW Load,V Mag kV,R Compound,Margin,Metered end,Line FOR Perm,Line FOR Trans,MTTR Line Hours,From Station FOR Active,From Station FOR Passive,From Station Scheduled Maint Rate,From Station Scheduled Maint Hours,From Switching Time Hours,To Station FOR Active,To Station FOR Passive,To Station Scheduled Maint Rate,To Station Scheduled Maint Dur Hours,To Switching Time Hours,Line Outage Prob 0,Line Outage Prob 1,Line Outage Prob 2,Line Outage Prob 3,Line Outage Rate 0,Line Outage Rate 1,Line Outage Rate 2,Line Outage Rate 3,Line Outage Dur 0,Line Outage Dur 1,Line Outage Dur 2,Line Outage Dur 3,Line Outage Loading 1,Line Outage Loading 2,Line Outage Loading 3,From Series Bridges,From Max Firing Angle,From Min Firing Angle,From R Commutating,From X Commutating,From baseKV,From Tr Ratio,From Tap Setpoint,From Tap Max,From Tap Min,From Tap Step,To Series Bridges,To Max Firing Angle,To Min Firing Angle,To R Commutating,To X Commutating,To baseKV,To Tr Ratio,To Tap Setpoint,To Tap Max,To Tap Min,To Tap Step'.split(','))

    pass  # No HVDC in the network


with open('gen.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow('GEN UID,Bus ID,Gen ID,Unit Group,Unit Type,Category,Fuel,MW Inj,MVAR Inj,V Setpoint p.u.,PMax MW,PMin MW,QMax MVAR,QMin MVAR,Min Down Time Hr,Min Up Time Hr,Ramp Rate MW/Min,Start Time Cold Hr,Start Time Warm Hr,Start Time Hot Hr,Start Heat Cold MBTU,Start Heat Warm MBTU,Start Heat Hot MBTU,Non Fuel Start Cost $,Non Fuel Shutdown Cost $,FOR,MTTF Hr,MTTR Hr,Scheduled Maint Weeks,Fuel Price $/MMBTU,Output_pct_0,Output_pct_1,Output_pct_2,Output_pct_3,Output_pct_4,HR_avg_0,HR_incr_1,HR_incr_2,HR_incr_3,HR_incr_4,VOM,Fuel Sulfur Content %,Emissions SO2 Lbs/MMBTU,Emissions NOX Lbs/MMBTU,Emissions Part Lbs/MMBTU,Emissions CO2 Lbs/MMBTU,Emissions CH4 Lbs/MMBTU,Emissions N2O Lbs/MMBTU,Emissions CO Lbs/MMBTU,Emissions VOCs Lbs/MMBTU,Damping Ratio,Inertia MJ/MW,Base MVA,Transformer X p.u.,Unit X p.u.,Pump Load MW,Storage Roundtrip Efficiency'.split(','))

    f2 = open('generator_locations.csv', 'w')  # Not part of RTS-GMLC format, but used to generate timeseries data
    writer2 = csv.writer(f2)
    writer2.writerow('GEN UID,Max Power (MW),Latitude,Longitude'.split(','))

    substation_generator_count = {}
    gen_uids = []

    for gen, gen_cost, fuel in zip(gens, costs, gen_fuels):
        bus_id = int(gen[0])
        bus_name = bus_id_to_name[bus_id]
        substation_name = bus_name_to_substation_name(bus_name)
        if substation_name in substation_generator_count:
            substation_generator_count[substation_name] += 1
        else:
            substation_generator_count[substation_name] = 1
        gen_id = substation_generator_count[substation_name]
        gen_uid = str(bus_id) + '_' + fuel.upper() + '_' + str(gen_id)
        gen_uids.append(gen_uid)
        unit_group = fuel  # TODO: multiple categories per size?
        unit_type = fuel  # No info regarding combined-cycle vs. open-cycle gas turbines
        category = fuel
        fuel = fuel
        P = gen[1]
        Q = gen[2]
        V = gen[5]
        Pmax = gen[8]
        if fuel in ['Wind', 'PV', 'Hydro']:  # What madman sets minimum power on PV plants
            Pmin = 0
        else:
            Pmin = gen[9]
        Qmax = gen[3]
        Qmin = gen[4]
        if fuel in ['Wind', 'PV', 'Hydro']:  # Based on average values from RTS-GMLC data
            min_down_time = 0
            min_up_time = 0
        elif fuel == 'Nuclear':
            min_down_time = 48
            min_up_time = 24
        elif fuel == 'NG':
            min_down_time = 2
            min_up_time = 2
        elif fuel == 'Coal':
            min_down_time = 8
            min_up_time = 8
        elif fuel == 'Oil':
            min_down_time = 1
            min_up_time = 1
        else:
            raise NotImplementedError

        if fuel in ['Wind', 'PV', 'Hydro']:
            ramp_rate = Pmax
        else:
            ramp_rate = gen[16]
        start_time_cold = 0  # Assume always need to cold start
        start_time_warm = 0
        start_time_hot = 0
        start_heat_cold = 0  # Modelled as constant start cost in Matpower (actually set to 0, more info in Texas7k_May29_GenParams.xlsx, but not for 2030 version)
        start_heat_warm = 0
        start_heat_hot = 0
        non_fuel_start_cost = gen_cost[1]
        non_fuel_shutdown_cost = gen_cost[2]
        forced_outage_rate = 0  # Does not seem to be used anyway in Prescient
        MTTF = 999
        MTTR = 0
        scheduled_maintenance_weeks = 0
        fuel_price = 1000  # Conversion from $/MMBTU*BTU/kWh to $/MWh
        price_model  = gen_cost[0]
        if price_model != 1:
            raise NotImplementedError()

        P0 = gen_cost[4]
        c0 = gen_cost[5]
        Pn = gen_cost[-2]
        cn = gen_cost[-1]
        Output_pct_0 = P0 / Pmax
        Output_pct_1 = Pn / Pmax  # Just use a single line, because that's basically the input data
        Output_pct_2 = 'NA'
        Output_pct_3 = 'NA'
        Output_pct_4 = 'NA'
        HR_avg_0 = c0  # Cost in $/hr in Matpower
        if cn - c0 <= 0:
            HR_incr_1 = 0
        else:
            HR_incr_1 = (cn - c0) / (Pn - P0)
        HR_incr_2 = 'NA'
        HR_incr_3 = 'NA'
        HR_incr_4 = 'NA'
        VOM = 0  # Not documented
        sulfur = 0  # Polution data, probably not used (no cost associated)
        SO2 = 0
        NOX = 0
        particles = 0
        CO2 = 0
        CH4 = 0
        N2O = 0
        CO = 0
        VOCs = 0
        damping = 0
        if fuel in ['Wind', 'PV']:  # Inertia based on average values from RTS-GMLC data
            inertia = 0
        elif fuel == 'Hydro':
            inertia = 3.5
        elif fuel == 'Nuclear':
            inertia = 5
        elif fuel == 'NG':
            inertia = 3.4  # 2.8 for open-cycle, 5 for combined, average from RTS-GMLC data
        elif fuel == 'Coal':
            inertia = 3
        elif fuel == 'Oil':
            inertia = 2.8  # Only open-cycle
        else:
            raise NotImplementedError
        base = gen[6]  # Equals 100 for all generators, hopefully not used, TODO: check
        transformer_X = 0.1  # Not used
        unit_X = 0.3  # Not used
        pump = 0
        storage_efficiency = 0  # No storage

        writer.writerow([gen_uid, bus_id, gen_id, unit_group, unit_type, category, fuel, P, Q, V, Pmax, Pmin, Qmax, Qmin, min_down_time, min_up_time, ramp_rate, start_time_cold, start_time_warm, start_time_hot, start_heat_cold, start_heat_warm, start_heat_hot, non_fuel_start_cost, non_fuel_shutdown_cost, forced_outage_rate, MTTF, MTTR, scheduled_maintenance_weeks, fuel_price, Output_pct_0, Output_pct_1, Output_pct_2, Output_pct_3, Output_pct_4, HR_avg_0, HR_incr_1, HR_incr_2, HR_incr_3, HR_incr_4, VOM, sulfur, SO2, NOX, particles, CO2, CH4, N2O, CO, VOCs, damping, inertia, base, transformer_X, unit_X, pump, storage_efficiency])

        latitude, longitude = substation_locations[substation_name]
        writer2.writerow([gen_uid, Pmax, latitude, longitude])
    f2.close()


with open('timeseries_pointers.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow('Simulation,Category,Object,Parameter,Scaling Factor,Data File'.split(','))

    for period in ['DAY_AHEAD', 'REAL_TIME']:  # Actually, the same data are used for both (as for the RTS)
        for i, gen in enumerate(gens):
            fuel = gen_fuels[i]
            if fuel in ['Wind', 'PV']:  # No data for hydro since it has a very low share (0.5% of total installed capacity)
                gen_uid = gen_uids[i]
                Pmax = gen[8]
                fuel = fuel.upper()
                fuel_lower = fuel.lower()
                writer.writerow([period, 'Generator', gen_uid, 'PMax MW', Pmax, f'timeseries_data_files/{fuel}/{period}_{fuel_lower}.csv'])

        for area in range(1, 8+1):
            total_area_load = 0
            for i, bus in enumerate(buses):
                P = bus[2]
                bus_area = int(bus[6])
                if bus_area == area:
                    total_area_load += P
            writer.writerow([period, 'Area', area, 'MW Load', total_area_load, f'timeseries_data_files/Load/{period}_regional_Load.csv'])  # Identical for day-ahead and real-time


with open('simulation_objects.csv', 'w') as f:
    f.write('Simulation_Parameters,Description,DAY_AHEAD,REAL_TIME\n'
            'Periods_per_Step,the number of descrete periods represented in each simulation step,24,1\n'
            'Period_Resolution,period resolution in seconds,3600,3600\n'
            'Date_From,simulation beginning period,1/1/20 0:00,1/1/20 0:00\n'
            'Date_To,simulation ending period (must acconunt for lookahed data availability),12/31/20 0:00,12/31/20 0:00\n'
            'Look_Ahead_Periods_per_Step,the number of look ahead periods included in each optimization step,24,2\n'
            'Look_Ahead_Resolution,look-ahead period resolution,3600,3600\n'
            'Reserve_Products,list of reserve products scheduled,"(Spin_Up)","(Spin_Up)"\n')


with open('reserves.csv', 'w') as f:
    writer = csv.writer(f)
    writer.writerow('Reserve Product,Timeframe (sec),Requirement (MW),Eligible Regions,Eligible Device Categories,Eligible Device SubCategories,Direction'.split(','))

    # 3GW of spinning reserve shared amonst areas based on share of load, and rounded up
    writer.writerow(['Spin_Up_R1', 600, 150,  1, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
    writer.writerow(['Spin_Up_R2', 600, 150,  2, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
    writer.writerow(['Spin_Up_R3', 600, 100,  3, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
    writer.writerow(['Spin_Up_R4', 600, 250,  4, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
    writer.writerow(['Spin_Up_R5', 600, 1200, 5, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
    writer.writerow(['Spin_Up_R6', 600, 500,  6, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
    writer.writerow(['Spin_Up_R7', 600, 900,  7, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
    writer.writerow(['Spin_Up_R8', 600, 150,  8, '(Generator)', '(Coal,Hydro,NG,Nuclear,Oil)', 'Up'])
