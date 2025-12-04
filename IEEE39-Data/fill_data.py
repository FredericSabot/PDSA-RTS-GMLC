import os
import pypowsybl as pp
import csv

n = pp.network.load("IEEE39.iidm")
lines = n.get_lines()

with open('branch.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["UID", "From Bus", "To Bus", "R", "X", "B", "Cont Rating", "LTE Rating",
                     "STE Rating", "Perm OutRate", "Duration", "Tr Ratio", "Tran OutRate", "Length"])

    for line_id in lines.index:
        X = lines.at[line_id, "x"]
        length = X / 0.3
        # Only the length is read from this file, so don't fill the rest
        writer.writerow([line_id] + ["N/A"] * 12 + [length])

loads = n.get_loads()
buses = n.get_bus_breaker_view_buses()
for bus_id in buses.index:
    vl_id = buses.at[bus_id, "voltage_level_id"]

    has_load = False
    for load_id in loads.index:
        load_vl_id = loads.at[load_id, "voltage_level_id"]
        load_bus_id = load_vl_id[:-2] + "TN"  # Pypowsybl does not return true bus name, so do this instead
        if load_bus_id == bus_id:
            has_load = True
            break

    if not has_load:
        # Create a dummy load to be able to add a short-circuit to the bus
        n.create_loads(id='L-' + bus_id, voltage_level_id=vl_id, bus_id=bus_id, p0=0, q0=0)

sol = pp.loadflow.run_ac(n)
n.dump("IEEE39.xiidm", 'XIIDM', {'iidm.export.xml.version' : '1.4'})
