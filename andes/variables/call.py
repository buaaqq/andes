
all_calls = ['gcall',
             'gycall',
             'fcall',
             'fxcall',
             'init0',
             'pflow',
             'windup',
             'jac0',
             'init1',
             'shunt',
             'series',
             'flows',
             'connection',
             'times',
             'stagen',
             'dyngen',
             'gmcall',
             'fmcall',
             'dcseries',
             'opf',
             'obj']


class Call(object):
    """ Equation call mamager class for andes routines"""
    def __init__(self, system):
        self.system = system
        self.ndevice = 0
        self.devices = []
        call_strings = ['gcalls', 'fcalls', 'gycalls', 'fxcalls', 'jac0s',]

        self.gisland = 'system.Bus.gisland(system.DAE)\n'
        self.gyisland = 'system.Bus.gyisland(system.DAE)\n'

        for item in all_calls + call_strings:
            self.__dict__[item] = []

    def setup(self):
        """setup the call list after case file is parsed and jit models are loaded"""
        self.devices = self.system.DevMan.devices
        self.ndevice = len(self.devices)

        self.gcalls = [''] * self.ndevice
        self.fcalls = [''] * self.ndevice
        self.gycalls = [''] * self.ndevice
        self.fxcalls = [''] * self.ndevice
        self.jac0s = [''] * self.ndevice

        self.build_vec()
        self.build_strings()
        self._compile_newton()
        self._compile_fdpf()
        self._compile_pfload()
        self._compile_pfgen()
        self._compile_seriesflow()
        self._compile_int()

    def build_vec(self):
        """build call validity vector for each device"""
        for dev in self.devices:
            for item in all_calls:
                if self.system.__dict__[dev].n == 0:
                    val = False
                else:
                    val = self.system.__dict__[dev].calls.get(item, False)
                self.__dict__[item].append(val)

    def build_strings(self):
        """build call string for each device"""
        for idx, dev in enumerate(self.devices):
            header = 'system.' + dev
            self.gcalls[idx] = header + '.gcall(system.DAE)\n'
            self.fcalls[idx] = header + '.fcall(system.DAE)\n'
            self.gycalls[idx] = header + '.gycall(system.DAE)\n'
            self.fxcalls[idx] = header + '.fxcall(system.DAE)\n'
            self.jac0s[idx] = header + '.jac0(system.DAE)\n'

    def get_times(self):
        """return event times of Fault and Breaker"""
        times = []
        if self.system.Fault.n:
            times = self.system.Fault.get_times()
        if times:
            times = sorted(list(set(times)))

        return times

    def _compile_newton(self):
        """Newton power flow execution
                1. evaluate g and f;
                1.1. handle islanded buses by Bus.gisland()
                2. factorize when needed;
                3. evaluate Gy and Fx.
                3.1. take care of islanded buses by Bus.gyisland()
        """
        string = '"""\n'

        # evaluate algebraic equations g and differential equations f
        string += 'system.DAE.init_fg()\n'
        for pflow, gcall, call in zip(self.pflow, self.gcall, self.gcalls):
            if pflow and gcall:
                string += call
        string += '\n'
        for pflow, fcall, call in zip(self.pflow, self.fcall, self.fcalls):
            if pflow and fcall:
                string += call

        # handle islanded buses in algebraic equations
        string += self.gisland
        string += '\n'

        # rebuild constant Jacobian elements if factorization needed
        string += 'if system.DAE.factorize:\n'
        string += '    system.DAE.init_jac0()\n'
        for pflow, jac0, call in zip(self.pflow, self.jac0, self.jac0s):
            if pflow and jac0:
                string += '    ' + call

        # evaluate Jacobians Gy and Fx
        string += 'system.DAE.setup_Gy()\n'
        for pflow, gycall, call in zip(self.pflow, self.gycall, self.gycalls):
            if pflow and gycall:
                string += call

        # handle islanded buses in the Jacobian
        string += self.gyisland

        string += '"""'
        self.newton = compile(eval(string), '', 'exec')

    def _compile_fdpf(self):
        """Fast Decoupled Power Flow execution: Implement g(y)
        """
        string = '"""\n'
        string += 'system.DAE.init_g()\n'
        for pflow, gcall, call in zip(self.pflow, self.gcall, self.gcalls):
            if pflow and gcall:
                string += call
        string += '\n'
        string += '"""'
        self.fdpf = compile(eval(string), '', 'exec')

    def _compile_pfload(self):
        """Post power flow computation for load
                  S_gen  + S_line + [S_shunt  - S_load] = 0
        """
        string = '"""\n'
        string += 'system.DAE.init_g()\n'
        for gcall, pflow, shunt, stagen, call in zip(self.gcall, self.pflow, self.shunt, self.stagen, self.gcalls):
            if gcall and pflow and shunt and not stagen:
                string += call
        string += '\n'
        string += '"""'
        self.pfload = compile(eval(string), '', 'exec')

    def _compile_pfgen(self):
        """Post power flow computation for PV and SW"""
        string = '"""\n'
        string += 'system.DAE.init_g()\n'
        for gcall, pflow, shunt, series, stagen, call in zip(self.gcall, self.pflow, self.shunt,
                                                             self.series, self.stagen, self.gcalls):
            if gcall and pflow and (shunt or series) and not stagen:
                string += call
        string += '\n'
        string += '"""'
        self.pfgen = compile(eval(string), '', 'exec')

    def _compile_seriesflow(self):
        """Post power flow computation of series device flow"""
        string = '"""\n'
        for device, pflow, series in zip(self.devices, self.pflow, self.series):
            if pflow and series:
                string += 'system.'+device+'.seriesflow(system.DAE)\n'
        string += '\n'
        string += '"""'
        self.seriesflow = compile(eval(string), '', 'exec')

    def _compile_int(self):
        """Time Domain Simulation routine execution"""
        string = '"""\n'

        # evaluate the algebraic equations g
        string += 'system.DAE.init_fg()\n'
        for gcall, call in zip(self.gcall, self.gcalls):
            if gcall:
                string += call
        string += '\n'

        # handle islands
        string += self.gisland

        # evaluate differential equations f
        for fcall, call in zip(self.fcall, self.fcalls):
            if fcall:
                string += call
        string += '\n'

        # rebuild constant Jacobian elements if needed
        string += 'if system.DAE.factorize:\n'
        string += '    system.DAE.init_jac0()\n'
        for jac0, call in zip(self.jac0, self.jac0s):
            if jac0:
                string += '    ' + call

        # evaluate Jacobians Gy and Fx
        string += 'system.DAE.setup_FxGy()\n'
        for gycall, call in zip(self.gycall, self.gycalls):
            if gycall:
                string += call
        string += '\n'
        for fxcall, call in zip(self.fxcall, self.fxcalls):
            if fxcall:
                string += call
        string += self.gyisland

        string += '"""'
        self.int = compile(eval(string), '', 'exec')
