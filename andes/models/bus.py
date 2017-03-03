from .base import ModelBase
from cvxopt import matrix, spmatrix, uniform

class Bus(ModelBase):
    """AC bus model"""
    def __init__(self, system, name):
        """constructor of an AC bus object"""
        super().__init__(system, name)
        self._group = 'Topology'
        self._data.pop('Sn')
        self._data.update({'Vn': 110.0,
                           'voltage': 1.0,
                           'angle': 0.0,
                           'vmax': 1.1,
                           'vmin': 0.9,
                           'area': 0,
                           'region': 0,
                           'owner': 0,
                           'xcoord': None,
                           'ycoord': None,
                           })
        self._params = ['u',
                        'Vn',
                        'voltage',
                        'angle',
                        'vmax',
                        'vmin',]
        self._descr.update({'voltage': 'voltage magnitude in p.u.',
                            'angle': 'voltage angle in radian',
                            'vmax': 'maximum voltage in p.u.',
                            'vmin': 'minimum voltage in p.u.',
                            'area': 'area code',
                            'region': 'region code',
                            'owner': 'owner code',
                            'xcoord': 'x coordinate',
                            'ycoord': 'y coordinate',
                            })
        self._service = ['Pg',
                         'Qg',
                         'Pl',
                         'Ql']
        self._zeros = ['Vn']
        self._mandatory = ['Vn']
        self.calls.update({'init0': True,
                           'pflow': True,
                           })
        self._inst_meta()
        self.a = list()
        self.v = list()
        self.islanded_buses = list()
        self.island_sets = list()

    def setup(self):
        """set up bus class after data parsing - manually assign angle and voltage indices"""
        if not self.n:
            self.system.Log.error('Powersystem instance contains no <Bus> element.')
            return
        self.a = list(range(0, self.n))
        self.v = list(range(self.n, 2*self.n))
        self.system.DAE.m = 2*self.n
        self._list2matrix()

    def _varname(self):
        """customize varname for bus class"""
        if not self.addr:
            self.system.Log.error('Unable to assign Varname before allocating address')
            return
        self.system.VarName.append(listname='unamey', xy_idx=self.a, var_name='theta', element_name=self.a)
        self.system.VarName.append(listname='unamey', xy_idx=self.v, var_name='vm', element_name=self.a)
        self.system.VarName.append(listname='fnamey', xy_idx=self.a, var_name='\\theta', element_name=self.a)
        self.system.VarName.append(listname='fnamey', xy_idx=self.v, var_name='V', element_name=self.a)

    def init0(self, dae):
        """Set bus Va and Vm initial values"""
        if not self.system.SPF.flatstart:
            dae.y[self.a] = self.angle + 1e-10*uniform(self.n)
            dae.y[self.v] = self.voltage
        else:
            dae.y[self.a] = matrix(0.0, (self.n, 1), 'd') + 1e-10*uniform(self.n)
            dae.y[self.v] = matrix(1.0, (self.n, 1), 'd')

    def gisland(self,dae):
        """Reset g(x) for islanded buses and areas"""
        if not self.islanded_buses:
            return

        # for islanded buses
        a = self.islanded_buses
        v = [self.n + item for item in a]
        dae.g[a] = 0
        dae.g[v] = 0

        # for islanded areas without a slack bus
        for island in self.island_sets:
            if self.system.refbus not in island:
                a = island
                v = [self.n + item for item in a]
                # dae.g[a] = 0
                # dae.g[v] = 0

    def gyisland(self,dae):
        """Reset gy(x) for islanded buses and areas"""
        if self.system.Bus.islanded_buses:
            a = self.system.Bus.islanded_buses
            v = [self.system.Bus.n + item for item in a]
            self.set_jac('Gy', 1e-6, a, a)
            self.set_jac('Gy', 1e-6, v, v)