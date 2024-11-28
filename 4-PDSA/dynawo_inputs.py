from __future__ import annotations
from common import *
if WITH_LXML:
    from lxml import etree
else:
    import xml.etree.ElementTree as etree
import os
import job
from pathlib import Path
import shutil
import dynawo_protections
import dynawo_init_events
import pypowsybl as pp
import sys
sys.path.insert(1, '../3-DynData')
import add_dyn_data

def write_job_files(job : job.Job):
    """
    Write the input files for a given scenario
    """
    Path(job.working_dir).mkdir(parents=True, exist_ok=True)

    # Copy static file for the considered sample
    static_data_path = os.path.join('../2-SCOPF/d-Final-dispatch', f'{CASE}_{NETWORK_NAME}')
    iidm_file = os.path.join(static_data_path, str(job.static_id) + '.iidm')
    shutil.copy(iidm_file, os.path.join(job.working_dir, NETWORK_NAME + '.iidm'))

    # Add data to dyd and par files
    network = pp.network.load(iidm_file)
    dyn_data_path = '../3-DynData'
    if WITH_LXML:
        XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
        dyd_root = etree.parse(os.path.join(dyn_data_path, 'base.dyd'), XMLparser).getroot()
        par_root = etree.parse(os.path.join(dyn_data_path, 'base.par'), XMLparser).getroot()
    else:
        dyd_root = etree.parse(os.path.join(dyn_data_path, 'base.dyd')).getroot()
        par_root = etree.parse(os.path.join(dyn_data_path, 'base.par')).getroot()

    if NETWORK_NAME == 'RTS':
        if CASE == 'january':
            motor_share = 0.3
        elif CASE == 'july':
            motor_share = 0.5
        elif CASE == 'year':
            if int(job.static_id) > 3600 and int(job.static_id) < 6480:  # Around June to September
                motor_share = 0.5
            else:
                motor_share = 0.3
        else:
            raise NotImplementedError
    elif NETWORK_NAME == 'Texas':
        motor_share = 0
    else:
        raise NotImplementedError

    add_dyn_data.add_dyn_data(NETWORK_NAME, network, WITH_LXML, dyd_root, par_root, DYNAWO_NAMESPACE, motor_share, CONTINGENCY_MINIMUM_VOLTAGE_LEVEL)
    dynawo_init_events.add_init_events(dyd_root, par_root, job.contingency.init_events)
    dynawo_protections.add_protections(dyd_root, par_root, network, job.dynamic_seed, job.contingency.protection_hidden_failures)

    # Write dyd and par files
    if WITH_LXML:
        with open(os.path.join(job.working_dir, NETWORK_NAME + '.dyd'), 'wb') as doc:
            doc.write(etree.tostring(dyd_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
        with open(os.path.join(job.working_dir, NETWORK_NAME + '.par'), 'wb') as doc:
            doc.write(etree.tostring(par_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
    else:
        tree = etree.ElementTree(dyd_root)
        etree.indent(tree, space="\t")
        tree.write(os.path.join(job.working_dir, NETWORK_NAME + '.dyd'), xml_declaration=True, encoding='UTF-8')
        tree = etree.ElementTree(par_root)
        etree.indent(tree, space="\t")
        tree.write(os.path.join(job.working_dir, NETWORK_NAME + '.par'), xml_declaration=True, encoding='UTF-8')


    # Copy other input files
    shutil.copy(os.path.join(dyn_data_path, NETWORK_NAME + '.jobs'), job.working_dir)
    shutil.copy(os.path.join(dyn_data_path, NETWORK_NAME + '_alt_solver.jobs'), job.working_dir)
    if os.path.isfile(os.path.join(dyn_data_path, NETWORK_NAME + '.crv')):
        shutil.copy(os.path.join(dyn_data_path, NETWORK_NAME + '.crv'), job.working_dir)
    if os.path.isfile(os.path.join(dyn_data_path, NETWORK_NAME + '.fsv')):
        shutil.copy(os.path.join(dyn_data_path, NETWORK_NAME + '.fsv'), job.working_dir)
