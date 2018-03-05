import ipyxact.ipyxact as ipyxact

class Signal(object):
    def __init__(self, name, width=0, low=0, asc=False):
        self.name = name
        self.width=width
        self.low = low
        self.asc = asc

class Vector(ipyxact.Vector):
    def __init__(self, width=0, low=0, asc=False):
        if asc:
            self.left  = low
            self.right = low+width-1
        else:
            self.left  = low+width-1
            self.right = low
        
class Port(ipyxact.Port):
    def __init__(self, name, direction, width=0, low=0, asc=False):
        self.name = name
        self.wire = ipyxact.Wire()
        self.wire.direction = direction
        if width > 0:
            self.wire.vector = Vector(width, low, asc)

def wb_master_ports(datawidth=32):
    p = [Signal('adr', 32),
         Signal('dat', datawidth)]
    if datawidth == 32:
        p.append(Signal('sel',  4))
    p += [Signal('we'),
          Signal('cyc'),
          Signal('stb'),
          Signal('cti',  3),
          Signal('bte',  2)]
    return(p)

def wb_slave_ports(datawidth=32):
    return [Signal('dat', datawidth),
            Signal('ack'),
            Signal('err'),
            Signal('rty')]

class WBBusInterface(ipyxact.BusInterface):
    def __init__(self, name, mode, datawidth):
        super(WBBusInterface, self).__init__()
        self.name = name
        self.datawidth = datawidth

        if mode == 'master':
            self.master = ''
            self.mdir = 'o'
            self.sdir = 'i'
        else:
            self.slave = ''
            self.mdir = 'i'
            self.sdir = 'o'

        busname = "wishbone"
        if datawidth == 8:
            busname += "8"

        abstractionType = ipyxact.AbstractionType()
        abstractionType.vendor  = "librecores.org"
        abstractionType.library = "wishbone"
        abstractionType.name    = busname+".absDef"
        abstractionType.version = "b3"
        self.abstractionType = abstractionType

        busType = ipyxact.BusType()
        busType.vendor  = "librecores.org"
        busType.library = "wishbone"
        busType.name    = busname
        busType.version = "b3"
        self.busType = busType


    def connect(self, prefix):
        self.portMaps = ipyxact.PortMaps()
        self.portMaps.portMap = []
        for p in wb_master_ports(self.datawidth):
            portMap = ipyxact.PortMap()

            physicalPort = ipyxact.PhysicalPort()
            physicalPort.name = "{}_{}_{}".format(prefix, p.name, self.mdir)
            if p.width > 0:
                physicalPort.vector = Vector(p.width)
            portMap.physicalPort = physicalPort

            logicalPort = ipyxact.LogicalPort()
            logicalPort.name = "{}_o".format(p.name)
            if p.width > 0:
                logicalPort.vector = Vector(p.width)
            portMap.logicalPort = logicalPort

            self.portMaps.portMap.append(portMap)

        for p in wb_slave_ports(self.datawidth):
            portMap = ipyxact.PortMap()

            physicalPort = ipyxact.PhysicalPort()
            physicalPort.name = "{}_{}_{}".format(prefix, p.name, self.sdir)
            if p.width > 0:
                physicalPort.vector = Vector(p.width)
            portMap.physicalPort = physicalPort

            logicalPort = ipyxact.LogicalPort(name="{}_i".format(p.name))
            if p.width > 0:
                logicalPort.vector = Vector(p.width)
            portMap.logicalPort = logicalPort

            self.portMaps.portMap.append(portMap)

class IpxactWriter(object):

    def __init__(self, masters, slaves, filename, vlnv_string):

        vlnv = vlnv_string.split(':')
        component= ipyxact.Component(vendor  = vlnv[0],
                                     library = vlnv[1],
                                     name    = vlnv[2],
                                     version = vlnv[3])
        component.nsversion = '1.5'

        component.model = ipyxact.Model()

        ports = ipyxact.Ports()

        ports.port.append(Port('wb_clk_i', 'in'))
        ports.port.append(Port('wb_rst_i', 'in'))
        
        for m in masters:
            for p in wb_master_ports(m.datawidth):
                mp = Port('wb_{}_{}_i'.format(m.name, p.name), 'in', p.width)
                ports.port.append(mp)

            for p in wb_slave_ports(m.datawidth):
                mp = Port('wb_{}_{}_o'.format(m.name, p.name), 'out', p.width)
                ports.port.append(mp)

        for s in slaves:
            for p in wb_master_ports(s.datawidth):
                mp = Port('wb_{}_{}_o'.format(s.name, p.name), 'out', p.width)
                ports.port.append(mp)

            for p in wb_slave_ports(s.datawidth):
                mp = Port('wb_{}_{}_i'.format(s.name, p.name), 'in', p.width)
                ports.port.append(mp)

        component.model.ports = ports

        component.busInterfaces = ipyxact.BusInterfaces()

        for m in masters:
            busif = WBBusInterface("wb_"+m.name, "slave", m.datawidth)
            busif.connect("wb_"+m.name)

            component.busInterfaces.busInterface.append(busif)

        for s in slaves:
            busif = WBBusInterface("wb_"+s.name, "master", s.datawidth)
            busif.connect("wb_"+s.name)

            component.busInterfaces.busInterface.append(busif)
            
        component.write('wb_intercon.xml')
