#!/usr/bin/env python3
import sys
from collections import OrderedDict, defaultdict
import yaml

from verilogwriter import Signal, Wire, Instance, ModulePort, VerilogWriter

WB_MASTER_PORTS = [Signal('adr', 32),
                   Signal('dat', 32),
                   Signal('sel',  4),
                   Signal('we'),
                   Signal('cyc'),
                   Signal('stb'),
                   Signal('cti',  3),
                   Signal('bte',  2)]

WB_SLAVE_PORTS  = [Signal('rdt', 32),
                   Signal('ack'),
                   Signal('err'),
                   Signal('rty')]

WB_DATA_WIDTH = defaultdict(float, { 'dat': 1.0, 'rdt': 1.0 })

class Error(Exception):
  """Base error for wb_intercon_gen"""

class UnknownPropertyError(Error):
  """An unknown property was encounterned while parsing the config file."""

def parse_number(s):
    if type(s) == int:
        return s
    if s.startswith('0x'):
        return int(s, 16)
    else:
        return int(s)

class Master:
    def __init__(self, name, d=None):
        self.name = name
        self.datawidth = 32
        self.slaves = []
        if d:
            self.load_dict(d)

    def load_dict(self, d):
        for key, value in d.items():
            if key == 'slaves':
                # Handled in file loading, ignore here
                continue
            else:
                raise UnknownPropertyError(
                    "Unknown property '%s' in master section '%s'" % (
                    key, self.name))

class Slave:
    def __init__(self, name, d=None):
        self.name = name
        self.masters = []
        self.datawidth = 32
        self.offset = 0
        self.size = 0
        self.mask = 0
        if d:
            self.load_dict(d)

    def load_dict(self, d):
        for key, value in d.items():
            if key == 'datawidth':
                self.datawidth = parse_number(value)
            elif key == 'offset':
                self.offset = parse_number(value)
            elif key == 'size':
                self.size = parse_number(value)
                self.mask = ~(self.size-1) & 0xffffffff
            else:
                raise UnknownPropertyError(
                    "Unknown property '%s' in slave section '%s'" % (
                    key, self.name))

class Parameter:
    def __init__(self, name, value):
        self.name  = name
        self.value = value

class Port:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class WbIntercon:
    def __init__(self, name, config_file):
        self.verilog_writer = VerilogWriter(name)
        self.template_writer = VerilogWriter(name);
        self.name = name
        d = OrderedDict()
        self.slaves = OrderedDict()
        self.masters = OrderedDict()
        import yaml

        def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
            class OrderedLoader(Loader):
                pass
            def construct_mapping(loader, node):
                loader.flatten_mapping(node)
                return object_pairs_hook(loader.construct_pairs(node))
            OrderedLoader.add_constructor(
                yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                construct_mapping)
            return yaml.load(stream, OrderedLoader)
        data = ordered_load(open(config_file))

        config     = data['parameters']
        files_root = data['files_root']
        self.vlnv       = data['vlnv']

        valid_endians = ['big', 'little']
        if 'endian' in config:
            self.endian = config['endian']
            if self.endian not in valid_endians:
                raise UnknownPropertyError("Unknown data resizer endian '{}' specified. Valid endians: {}".format(config['endian'], valid_endians))
        else:
            self.endian = "big"

        print("Wishbone Data Resizer Endian: {}".format(self.endian))

        for k,v in config['masters'].items():
            print("Found master " + k)
            self.masters[k] = Master(k,v)
            d[k] = v['slaves']
        for k,v in config['slaves'].items():
            print("Found slave " + k)
            self.slaves[k] = Slave(k,v)

        #Create master/slave connections
        for master, slaves in d.items():
            for slave in slaves:
                self.masters[master].slaves += [self.slaves[slave]]
                self.slaves[slave].masters += [self.masters[master]]

        self.output_file = config.get('output_file', 'wb_intercon.v')

    def _dump(self):
        print("*Masters*")
        for master in self.masters.values():
            print(master.name)
            for slave in master.slaves:
                print(' ' + slave.name)

        print("*Slaves*")
        for slave in self.slaves.values():
            print(slave.name)
            for master in slave.masters:
                print(' ' + master.name)


    def _gen_mux(self, master):
        parameters = [Parameter('num_slaves', len(master.slaves))]
        match_addr = '{' + ', '.join(["32'h{addr:08x}".format(addr=s.offset) for s in master.slaves]) + '}'
        parameters += [Parameter('MATCH_ADDR', match_addr)]

        match_mask = '{' + ', '.join(["32'h{mask:08x}".format(mask=s.mask) for s in master.slaves]) + '}'
        parameters += [Parameter('MATCH_MASK', match_mask)]
        ports = [Port('wb_clk_i', 'wb_clk_i'),
                 Port('wb_rst_i', 'wb_rst_i')]
        m = master.name

        input_format = 'wb_%s_%s_i'
        output_format = 'wb_%s_%s_o'

        #Create mux master side connections
        for p in WB_MASTER_PORTS:
            ports += [Port('wbm_' + p.name + '_i', input_format % (m, p.name))]
        for p in WB_SLAVE_PORTS:
            _name = 'dat' if p.name == 'rdt' else p.name
            ports += [Port('wbm_' + _name + '_o', output_format % (m, p.name))]

        #Create mux slave side connections
        name_list = []
        for s in master.slaves:

            #If we have only one master the wb_mux is the last piece before
            #the slave. If the slave's datawidth is 32, we go straight from
            #the wb_mux to the slave.
            if len(s.masters) == 1 and int(s.datawidth) == 32:
                name_list += ['wb_' + s.name + '_{0}_{1}']
            #If not, we'll need a wb_data_resize and then new wires.
            elif len(s.masters) == 1 and int(s.datawidth) < 32:
                 name_list += ['wb_' + 'resize_' + s.name + '_{0}']
            #If there is more than on master for that slave, there will
            #be an arbiter and the wb_data_resize will be after that.
            else:
                name_list += ['wb_'+ m + '_' + s.name + '_{0}']

        for p in WB_MASTER_PORTS:
            ports += [Port('wbs_'+p.name+'_o', '{' + ', '.join(name_list).format(p.name, 'o')+'}')]
        for p in WB_SLAVE_PORTS:
            _name = 'dat' if p.name == 'rdt' else p.name
            ports += [Port('wbs_'+_name+'_i', '{' + ', '.join(name_list).format(p.name, 'i')+'}')]

        self.verilog_writer.add(Instance('wb_mux', 'wb_mux_'+m,parameters, ports))

    def _gen_arbiter(self, slave):
        parameters = [Parameter('num_masters', len(slave.masters))]
        ports = [Port('wb_clk_i', 'wb_clk_i'),
                 Port('wb_rst_i', 'wb_rst_i')]
        s = slave.name

        name_list = []
        for m in slave.masters:
            name_list += ['wb_'+ m.name + '_' + s + '_{0}']
        for p in WB_MASTER_PORTS:
            ports += [Port('wbm_'+p.name+'_i', '{' + ', '.join(name_list).format(p.name, 'i')+'}')]
        for p in WB_SLAVE_PORTS:
            _name = 'dat' if p.name == 'rdt' else p.name
            ports += [Port('wbm_'+_name+'_o', '{' + ', '.join(name_list).format(p.name, 'o')+'}')]

        #Create slave connections
        #If the slave's data width is 32, we don't need a wb_data_resize
        if int(slave.datawidth) == 32:
            input_format = 'wb_%s_%s_i'
            output_format = 'wb_%s_%s_o'
            for p in WB_MASTER_PORTS:
                ports += [Port('wbs_' + p.name + '_o', output_format % (s, p.name))]
            for p in WB_SLAVE_PORTS:
                _name = 'dat' if p.name == 'rdt' else p.name
                ports += [Port('wbs_' + _name + '_i', input_format % (s, p.name))]
        #Else, connect to the resizer
        else:
            for p in WB_MASTER_PORTS:
                ports += [Port('wbs_' + p.name + '_o', 'wb_resize_'+s+'_'+p.name)]
            for p in WB_SLAVE_PORTS:
                _name = 'dat' if p.name == 'rdt' else p.name
                ports += [Port('wbs_' + _name + '_i', 'wb_resize_'+s+'_'+p.name)]

        self.verilog_writer.add(Instance('wb_arbiter', 'wb_arbiter_'+s,parameters, ports))

    def _gen_resize(self, slave):
        parameters = [Parameter('aw', 32)]
        parameters += [Parameter('mdw', 32)]
        parameters += [Parameter('sdw', slave.datawidth)]
        parameters += [Parameter('endian', '"{}"'.format(self.endian))]
        s = slave.name

        ports =[]
        #Create master connections
        for p in WB_MASTER_PORTS:
            ports += [Port('wbm_'+p.name+'_i', 'wb_resize_'+s+'_'+p.name)]
        for p in WB_SLAVE_PORTS:
            _name = 'dat' if p.name == 'rdt' else p.name
            ports += [Port('wbm_'+_name+'_o', 'wb_resize_'+s+'_'+p.name)]

        input_format = 'wb_%s_%s_i'
        output_format = 'wb_%s_%s_o'

        #Create slave connections
        for p in WB_MASTER_PORTS:
            if p.name != "sel":
                ports.append(Port('wbs_' + p.name + '_o', output_format % (s, p.name)))
        for p in WB_SLAVE_PORTS:
            _name = 'dat' if p.name == 'rdt' else p.name
            ports.append(Port('wbs_' + _name + '_i', input_format % (s, p.name)))

        self.verilog_writer.add(Instance('wb_data_resize', 'wb_data_resize_'+s,parameters, ports))

        for p in WB_MASTER_PORTS:
            wirename = 'wb_resize_{slave}_{port}'.format(slave=s, port=p.name)
            self.verilog_writer.add(Wire(wirename, p.width))
        for p in WB_SLAVE_PORTS:
            wirename = 'wb_resize_{slave}_{port}'.format(slave=s, port=p.name)
            self.verilog_writer.add(Wire(wirename, p.width))

    def _gen_wishbone_master_port(self, master):
        template_ports = []
        for p in WB_MASTER_PORTS:
            portname = 'wb_{master}_{port}_i'.format(master=master.name, port=p.name)
            wirename = 'wb_{master}_{port}'.format(master=master.name, port=p.name)
            self.verilog_writer.add(ModulePort(portname, 'input', p.width))
            self.template_writer.add(Wire(wirename, p.width))
            template_ports += [Port(portname, wirename)]
        for p in WB_SLAVE_PORTS:
            portname = 'wb_{master}_{port}_o'.format(master=master.name, port=p.name)
            wirename = 'wb_{master}_{port}'.format(master=master.name, port=p.name)
            self.verilog_writer.add(ModulePort(portname, 'output', p.width))
            self.template_writer.add(Wire(wirename, p.width))
            template_ports += [Port(portname, wirename)]
        return template_ports

    def _gen_wishbone_port(self, slave):
        template_ports = []
        for p in WB_MASTER_PORTS:
            portname = 'wb_{slave}_{port}_o'.format(slave=slave.name, port=p.name)
            wirename = 'wb_{slave}_{port}'.format(slave=slave.name, port=p.name)
            dw = int(WB_DATA_WIDTH[p.name] * slave.datawidth) or p.width
            self.verilog_writer.add(ModulePort(portname, 'output', dw))
            self.template_writer.add(Wire(wirename, dw))
            template_ports += [Port(portname, wirename)]
        for p in WB_SLAVE_PORTS:
            portname = 'wb_{slave}_{port}_i'.format(slave=slave.name, port=p.name)
            wirename = 'wb_{slave}_{port}'.format(slave=slave.name, port=p.name)
            dw = int(WB_DATA_WIDTH[p.name] * slave.datawidth) or p.width
            self.verilog_writer.add(ModulePort(portname, 'input', dw))
            self.template_writer.add(Wire(wirename, dw))
            template_ports += [Port(portname, wirename)]
        return template_ports

    def _gen_bus_converter(self, bus, name, is_master, datawidth, datawidth_map, ports):
        converter_ports = [Port('wb_clk_i', 'wb_clk_i'),
            Port('wb_rst_i', 'wb_rst_i')]
        template_ports = []

        out_direction = 'm2s' if is_master else 's2m'

        # Wishbone side
        ms_type = 'm' if is_master else 's'
        # Foreign side
        f_ms_type = 's' if is_master else 'm'

        # Create Wishbone connections
        wb_ports = []
        wb_ports.extend([(p, 'm2s') for p in WB_MASTER_PORTS])
        wb_ports.extend([(p, 's2m') for p in WB_SLAVE_PORTS])
        for p, direction in wb_ports:
            pin_direction = 'output' if direction == out_direction else 'input'
            wirename = 'wb_{direction}_{name}_{port}'.format(
                direction=direction, name=name, port=p.name)
            converter_ports.append(
                Port('%s_%s_%s' % ('wbm' if ms_type == 'm' else 'wb', p.name,
                  pin_direction[0]), wirename))
            dw = int(WB_DATA_WIDTH[p.name] * datawidth) or p.width
            self.verilog_writer.add(Wire(wirename, dw))

        # Create foreign bus connections
        for p, direction in ports:
            pin_direction = 'output' if direction != out_direction else 'input'
            portname = '{d}_{bus}_{name}_{port}_{direction}'.format(
                d=f_ms_type, bus=bus, direction=pin_direction[0],
                name=name, port=p.name)
            wirename = '{bus}_{direction}_{name}_{port}'.format(
                bus=bus, direction=direction, name=name, port=p.name)
            converter_ports.append(
                Port('{d}_{bus}_{port}_{direction}'.format(
                    d=f_ms_type, bus=bus, direction=pin_direction[0],
                    port=p.name), portname))
            dw = int(datawidth_map[p.name] * datawidth) or p.width
            self.verilog_writer.add(
                ModulePort(portname, pin_direction, p.width))
            self.template_writer.add(Wire(wirename, dw))
            template_ports.append(Port(portname, wirename))

        return template_ports, converter_ports

    def write(self):
        file = self.output_file
        #Declare wires. Only conections between muxes and arbiters need explicit wires
        for key, value in self.masters.items():
            for slave in value.slaves:
                if len(slave.masters)>1:
                    for p in WB_MASTER_PORTS:
                        self.verilog_writer.add(Wire('wb_{0}_{1}_{2}'.format(key, slave.name, p.name), p.width))
                    for p in WB_SLAVE_PORTS:
                        self.verilog_writer.add(Wire('wb_{0}_{1}_{2}'.format(key, slave.name, p.name), p.width))

        self.verilog_writer.add(ModulePort('wb_clk_i', 'input'))
        self.verilog_writer.add(ModulePort('wb_rst_i', 'input'))

        template_ports = [Port('wb_clk_i', 'wb_clk'),
                          Port('wb_rst_i', 'wb_rst')]
        template_parameters = []

        for master in self.masters.values():
            self._gen_mux(master)
            master_template_ports = self._gen_wishbone_master_port(master)
            template_ports.extend(master_template_ports)

        for slave in self.slaves.values():
            if len(slave.masters) > 1:
                self._gen_arbiter(slave)
            if int(slave.datawidth) < 32:
                self._gen_resize(slave)
            slave_template_ports = self._gen_wishbone_port(slave)
            template_ports.extend(slave_template_ports)

        self.template_writer.add(Instance(self.name, self.name+'0',
                                          template_parameters, template_ports))

        self.verilog_writer.write(file)
        self.template_writer.write(file+'h')

        core_file = self.vlnv.split(':')[2]+'.core'
        vlnv = self.vlnv
        with open(core_file, 'w') as f:
            f.write('CAPI=2:\n')
            files = [{file     : {'file_type' : 'verilogSource'}},
                     {file+'h' : {'is_include_file' : True,
                                  'file_type' : 'verilogSource'}}
            ]
            coredata = {'name' : vlnv,
                        'targets' : {'default' : {}},
            }

            coredata['filesets'] = {'rtl' : {'files' : files}}
            coredata['targets']['default']['filesets'] = ['rtl']

            f.write(yaml.dump(coredata))

if __name__ == "__main__":
    #if len(sys.argv) < 3 or len(sys.argv) > 4:
        #print("wb_intercon_gen <config_file> <out_file> [module_name]")
        #exit(0)
    name = "wb_intercon"
    if len(sys.argv) == 4:
      name = sys.argv[3]
    try:
      g = WbIntercon(name, sys.argv[1])
      if len(sys.argv) > 2:
          g.output_file = sys.argv[2]
      print("="*80)
      g.write()
    except Error as e:
      print("Error: %s" % e)
      exit(1)
