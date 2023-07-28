from common import *
from lxml import etree
import os
from job import Job
from pathlib import Path
import shutil
import dynawo_protections
import dynawo_init_events


def write_job_files(job : Job):
    output_dir = os.path.join('./simulations', CASE, str(job.static_id), str(job.dynamic_seed), job.contingency.id)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Copy static file for the considered sample
    static_data_path = os.path.join('../2-SCOPF/d-Final-dispatch', CASE)
    iidm_file = os.path.join(static_data_path, str(job.static_id) + '.iidm')
    shutil.copy(iidm_file, os.path.join(output_dir, NETWORK_NAME + '.iidm'))

    # Add data to dyd and par files
    dyn_data_path = '../3-DynData'
    XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
    dyd_root = etree.parse(os.path.join(dyn_data_path, NETWORK_NAME + '.dyd'), XMLparser).getroot()
    par_root = etree.parse(os.path.join(dyn_data_path, NETWORK_NAME + '.par'), XMLparser).getroot()

    dynawo_init_events.add_init_events(dyd_root, par_root, job.contingency.init_events)
    dynawo_protections.add_protections(dyd_root, par_root, iidm_file, job.dynamic_seed)

    # Write dyd and par files
    with open(os.path.join(output_dir, NETWORK_NAME + '.dyd'), 'wb') as doc:
        doc.write(etree.tostring(dyd_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
    with open(os.path.join(output_dir, NETWORK_NAME + '.par'), 'wb') as doc:
        doc.write(etree.tostring(par_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))

    # Copy other input files
    shutil.copy(os.path.join(dyn_data_path, NETWORK_NAME + '.jobs'), output_dir)
    if os.path.isfile(os.path.join(dyn_data_path, NETWORK_NAME + '.crv')):
        shutil.copy(os.path.join(dyn_data_path, NETWORK_NAME + '.crv'), output_dir)
    if os.path.isfile(os.path.join(dyn_data_path, NETWORK_NAME + '.fsv')):
        shutil.copy(os.path.join(dyn_data_path, NETWORK_NAME + '.fsv'), output_dir)

    return output_dir
