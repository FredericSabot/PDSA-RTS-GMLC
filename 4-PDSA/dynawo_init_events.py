from common import *
if WITH_LXML:
    from lxml import etree
else:
    import xml.etree.ElementTree as etree

def add_init_events(dyd_root, par_root, init_events):
    """
    Add initiating events model to Dynawo input files
    """
    for init_event in init_events:
        if init_event.category == INIT_EVENT_CATEGORIES.BUS_FAULT:
                parID = init_event.category.name + init_event.fault_id
                add_bus_fault(dyd_root, par_root,  faultID=init_event.fault_id, busID=init_event.element, parID=parID,
                              t_init=init_event.time_start, t_clearing=init_event.time_end, r_fault=init_event.r, x_fault=init_event.x)
        elif init_event.category == INIT_EVENT_CATEGORIES.LINE_DISC:
                parID = init_event.category.name + init_event.element
                add_line_disc_to_dyd(dyd_root, par_root, lineID=init_event.element, t_disc=init_event.time_start, parID=parID)
        elif init_event.category == INIT_EVENT_CATEGORIES.GEN_DISC:
                parID = init_event.category.name + init_event.element
                add_gen_disc_to_dyd(dyd_root, par_root, genID=init_event.element, t_disc=init_event.time_start, parID=parID)
        else:
                raise NotImplementedError()


def add_bus_fault(dyd_root, par_root, faultID, busID, parID, t_init, t_clearing, r_fault, x_fault):
    """
    Add a bus fault to the dynawo model
    @param dyd_root etree root of the dyd file
    @param par_root etree root of the par file
    """
    # Add to dyd
    blackbox_attrib = {'id': faultID, 'lib': 'NodeFault', 'parFile': NETWORK_NAME + '.par', 'parId': parID}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), blackbox_attrib)
    connect_attrib = {'id1': faultID, 'var1': 'fault_terminal', 'id2': 'NETWORK', 'var2': busID + '_ACPIN'}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    # Add to par
    fault_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : parID})
    par_attribs = [
        {'type':'DOUBLE', 'name':'fault_RPu', 'value':'{}'.format(r_fault)},
        {'type':'DOUBLE', 'name':'fault_XPu', 'value':'{}'.format(x_fault)},
        {'type':'DOUBLE', 'name':'fault_tBegin', 'value': str(t_init)},
        {'type':'DOUBLE', 'name':'fault_tEnd', 'value': str(t_clearing)}
    ]
    for par_attrib in par_attribs:
        etree.SubElement(fault_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)

def add_line_disc_to_dyd(dyd_root, par_root,  lineID, t_disc, parID = 'LineDisc'):
    """
    Add a line disconnection to the dynawo model
    @param dyd_root etree root of the dyd file
    @param par_root etree root of the par file
    """
    # Add to dyd
    blackbox_attrib = {'id': 'DISC_' + lineID, 'lib': 'EventQuadripoleDisconnection', 'parFile': NETWORK_NAME + '.par', 'parId': parID}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), blackbox_attrib)
    connect_attrib = {'id1': 'DISC_' + lineID, 'var1': 'event_state1_value', 'id2': 'NETWORK', 'var2': lineID + '_state_value'}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    # Add to par
    line_disc_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : parID})
    par_attribs = [
        {'type':'DOUBLE', 'name':'event_tEvent', 'value': str(t_disc)},
        {'type':'BOOL', 'name':'event_disconnectOrigin', 'value':'true'},
        {'type':'BOOL', 'name':'event_disconnectExtremity', 'value':'true'},
    ]
    for par_attrib in par_attribs:
        etree.SubElement(line_disc_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)

def add_gen_disc_to_dyd(dyd_root, par_root,  genID, t_disc, parID = 'GenDisc'):
    """
    Add a generator disconnection to the dynawo model
    @param dyd_root etree root of the dyd file
    @param par_root etree root of the par file
    """
    blackbox_attrib = {'id': 'DISC_' + genID, 'lib': 'EventSetPointBoolean', 'parFile': NETWORK_NAME + '.par', 'parId': parID}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'blackBoxModel'), blackbox_attrib)
    connect_attrib = {'id1': 'DISC_' + genID, 'var1': 'event_state1', 'id2': genID, 'var2': 'generator_switchOffSignal2'}
    etree.SubElement(dyd_root, etree.QName(DYNAWO_NAMESPACE, 'connect'), connect_attrib)

    # Add to par
    gen_disc_par_set = etree.SubElement(par_root, etree.QName(DYNAWO_NAMESPACE, 'set'), {'id' : parID})
    par_attribs = [
        {'type':'DOUBLE', 'name':'event_tEvent', 'value': t_disc},
        {'type':'BOOL', 'name':'event_stateEvent1', 'value':'true'}
    ]
    for par_attrib in par_attribs:
        etree.SubElement(gen_disc_par_set, etree.QName(DYNAWO_NAMESPACE, 'par'), par_attrib)
