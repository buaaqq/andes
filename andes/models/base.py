"""
ANDES, a power system simulation tool for research.

Copyright 2015-2017 Hantao Cui

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from cvxopt import matrix, sparse, spmatrix
from logging import DEBUG, INFO, WARNING, ERROR, CRITICAL
from cvxopt import mul, div
import copy
import sys


class ModelBase(object):
    """base class for power system device models"""

    def __init__(self, system, name):
        """meta-data to be overloaded by subclasses"""
        self.system = system
        self.n = 0    # device count
        self.u = []   # device status
        self.idx = []    # internal index list
        self.int = {}    # external index to internal
        self.names = []  # element name list

        # identifications
        self._name = name
        self._group = None
        self._category = None

        # interfaces
        self._ac = {}    # ac bus variables
        self._dc = {}    # dc node variables
        self._ctrl = {}  # controller interfaces

        # variables
        self._states = []
        self._algebs = []

        # variable names
        self._unamex = []
        self._unamey = []
        self._fnamex = []
        self._fnamey = []

        # parameters to be converted to matrix
        self._params = ['u', 'Sn', 'Vn']

        # default parameter data
        self._data = {'u': 1,
                      'Sn': 100.0,
                      'Vn': 110.0,
                      }

        # units of parameters
        self._units = {'u': 'boolean',
                       'Sn': 'MVA',
                       'Vn': 'KV',
                       }

        # variable descriptions
        self._descr = {'u': 'connection status',
                       'Sn': 'power rating',
                       'Vn': 'voltage rating',
                       }
        # non-zero parameters
        self._zeros = ['Sn', 'Vn']

        # mandatory variables
        self._mandatory = []

        # service/temporary variables
        self._service = []

        # parameters to be per-unitized
        self._powers = []      # powers, inertia and damping
        self._voltages = []    # ac voltages
        self._currents = []    # ac currents
        self._z = []           # ac impedance
        self._y = []           # ac admittance

        self._dccurrents = []  # dc currents
        self._dcvoltages = []  # dc voltages
        self._r = []           # dc resistance
        self._g = []           # dc susceptance

        self._times = []       # time constants

        # property functions this device has

        self.calls = dict(pflow=False, addr1=False,
                          init0=False, init1=False,
                          jac0=False, windup=False,
                          gcall=False, fcall=False,
                          gycall=False, fxcall=False,
                          series=False, shunt=False,
                          flows=False, dcseries=False,
                          )
        self.addr = False
        self.ispu = False

    def _inst_meta(self):
        """instantiate meta-data defined in __init__().
        Call this function at the end of __init__() of child classes
        """
        if not self._name:
            self._name = self._group

        for item in self._data.keys():
            self.__dict__[item] = []
        for bus in self._ac.keys():
            for var in self._ac[bus]:
                self.__dict__[var] = []
        for node in self._dc.keys():
            for var in self._dc[node]:
                self.__dict__[var] = []

        for var in self._states:
            self.__dict__[var] = []
        for var in self._algebs:
            self.__dict__[var] = []
        for var in self._service:
            self.__dict__[var] = []
        if not self._unamey:
            self._unamey = self._algebs
        if not self._unamex:
            self._unamex = self._states

    def _alloc(self):
        """Allocate memory for DAE variable indices. Called after finishing adding components
        """
        zeros = [0] * self.n
        for var in self._states:
            self.__dict__[var] = zeros[:]
        for var in self._algebs:
            self.__dict__[var] = zeros[:]

    def remove_param(self, param):
        """Remove a param from this class"""
        if param in self._data.keys():
            self._data.pop(param)
        if param in self._descr.keys():
            self._descr.pop(param)
        if param in self._units:
            self._units.pop(param)
        if param in self._params:
            self._params.remove(param)
        if param in self._zeros:
            self._zeros.remove(param)
        if param in self._mandatory:
            self._mandatory.remove(param)

    def copy_param(self, model, src, dest=None, fkey=None, astype=None):
        """get a copy of the system.model.src as self.dest"""

        # input check
        dev_type = None
        val = list()
        if model in self.system.DevMan.devices:
            dev_type = 'model'
        elif model in self.system.DevMan.group.keys():
            dev_type = 'group'
        if not dev_type:
            self.message('Model or group <{0}> does not exist.'.format(model), ERROR)
            return

        # use default destination
        if not dest:
            dest = src

        # check destination type
        if astype and astype not in [list, matrix]:
            self.message('Wrong destination type <{0}>.'.format(astype), ERROR)
            if hasattr(self, dest):
                astype = type(self.__dict__[dest])
            else:
                astype = None

        # do param copy
        if dev_type == 'model':
            self.__dict__[dest] = self.system.__dict__[model]._slice(src, fkey)
        elif dev_type == 'group':
            if not fkey:
                fkey = self.system.DevMan.group.keys()
                if not fkey:
                    self.message('Group <{0}> does not have any element.'.format(model))
                    return
            for item in fkey:
                dev_name = self.system.DevMan.group[item]
                pos = self.system.__dict__[dev_name].int[item]
                val.append(self.system.__dict__[dev_name].__dict__[src][pos])
                if not astype:
                    astype = type(self.system.__dict__[dev_name].__dict__[src])
            self.__dict__[dest] = val

        # do conversion if needed
        if astype:
            self.__dict__[dest] = astype(self.__dict__[dest])

    def _slice(self, param, idx=None):
        """slice list or matrix with idx and return (type, sliced)"""
        ty = type(self.__dict__[param])
        if ty not in [list, matrix]:
            self.message('Unsupported type <{0}>to slice.'.format(ty))
            return None

        if not idx:
            idx = list(range(self.n))
        if type(idx) != list:
            idx = list(idx)

        if ty == list:
            return [self.__dict__[param][self.int[i]] for i in idx]
        elif ty == matrix:
            return self.__dict__[param][self.int[idx]]
        else:
            raise NotImplemented

    def add(self, idx=None, name=None, **kwargs):
        """add an element of this model"""
        idx = self.system.DevMan.register_element(dev_name=self._name, idx=idx)
        self.int[idx] = self.n
        self.idx.append(idx)
        self.n += 1

        if name is None:
            self.names.append(self._name + '_' + str(self.n))
        else:
            self.names.append(name)

        # check mandatory parameters
        for key in self._mandatory:
            if key not in kwargs.keys():
                self.message('Mandatory parameter <{:s}.{:s}> missing'.format(self.names[-1], key), ERROR)
                sys.exit(1)

        # set default values
        for key, value in self._data.items():
            self.__dict__[key].append(value)

        # overwrite custom values
        for key, value in kwargs.items():
            if key not in self._data:
                self.message('Parameter <{:s}.{:s}> is undefined'.format(self.names[-1], key), WARNING)
                continue
            self.__dict__[key][-1] = value

            # check data consistency
            if not value and key in self._zeros:
                if key == 'Sn':
                    default = self.system.Settings.mva
                elif key == 'fn':
                    default = self.system.Settings.freq
                else:
                    default = self._data[key]
                self.__dict__[key][-1] = default
                self.message('Using default value for <{:s}.{:s}>'.format(name, key), WARNING)

        return idx

    def remove(self, idx=None):
        if idx is not None:
            if idx in self.int:
                key = idx
                item = self.int[idx]
            else:
                self.message('The item <{:s}> does not exist.'.format(idx), ERROR)
                return None
        else:
            # nothing to remove
            return None

        convert = False
        if isinstance(self.__dict__[self._params[0]], matrix):
            self._param2list()
            convert = True

        self.n -= 1
        self.int.pop(key, '')
        self.idx.pop(item)

        for x, y in self.int.items():
            if y > item:
                self.int[x] = y - 1

        for param in self._data:
            self.__dict__[param].pop(item)

        for param in self._service:
            if len(self.__dict__[param]) == (self.n + 1):
                if isinstance(self.__dict__[param], list):
                    self.__dict__[param].pop(item)
                elif isinstance(self.__dict__[param], matrix):
                    service = list(self.__dict__[param])
                    service.pop(item)
                    self.__dict__[param] = matrix(service)

        for x in self._states:
            if len(self.__dict__[x]):
                self.__dict__[x].pop(item)

        for y in self._algebs:
            if self.__dict__[y]:
                self.__dict__[y].pop(item)

        for key, param in self._ac.items():
            if isinstance(param, list):
                for subparam in param:
                    if len(self.__dict__[subparam]):
                        self.__dict__[subparam].pop(item)
            else:
                self.__dict__[param].pop(item)

        for key, param in self._dc.items():
            self.__dict__[param].pop(item)

        self.names.pop(item)
        if convert and self.n:
            self._param2matrix()

    def base(self):
        """Per-unitize parameters. Store a copy."""
        if (not self.n) or self.ispu:
            return
        if 'bus' in self._ac.keys():
            bus_idx = self.__dict__[self._ac['bus'][0]]
        elif 'bus1' in self._ac.keys():
            bus_idx = self.__dict__[self._ac['bus1'][0]]
        else:
            bus_idx = []
        Sb = self.system.Settings.mva
        Vb = self.system.Bus.Vn[bus_idx]
        for var in self._voltages:
            self.__dict__[var] = mul(self.__dict__[var], self.Vn)
            self.__dict__[var] = div(self.__dict__[var], Vb)
        for var in self._powers:
            self.__dict__[var] = mul(self.__dict__[var], self.Sn)
            self.__dict__[var] /= Sb
        for var in self._currents:
            self.__dict__[var] = mul(self.__dict__[var], self.Sn)
            self.__dict__[var] = div(self.__dict__[var], self.Vn)
            self.__dict__[var] = mul(self.__dict__[var], Vb)
            self.__dict__[var] /= Sb
        if len(self._z) or len(self._y):
            Zn = div(self.Vn ** 2, self.Sn)
            Zb = (Vb ** 2) / Sb
            for var in self._z:
                self.__dict__[var] = mul(self.__dict__[var], Zn)
                self.__dict__[var] = div(self.__dict__[var], Zb)
            for var in self._y:
                if self.__dict__[var].typecode == 'd':
                    self.__dict__[var] = div(self.__dict__[var], Zn)
                    self.__dict__[var] = mul(self.__dict__[var], Zb)
                elif self.__dict__[var].typecode == 'z':
                    self.__dict__[var] = div(self.__dict__[var], Zn + 0j)
                    self.__dict__[var] = mul(self.__dict__[var], Zb + 0j)
        if len(self._dcvoltages) or len(self._dccurrents) or len(self._r) or len(self._g):
            Vdc = self.system.Node.Vdcn
            if Vdc is None:
                Vdc = matrix(self.Vdcn)
            else:
                Vbdc = matrix(0.0, (self.n, 1), 'd')
                temp = sorted(self._dc.keys())
                for item in range(self.n):
                    idx = self.__dict__[temp[0]][item]
                    Vbdc[item] = Vdc[self.system.Node.int[idx]]
            Ib = div(Sb, Vbdc)
            Rb = div(Vbdc, Ib)

        for var in self._dcvoltages:
            self.__dict__[var] = mul(self.__dict__[var], self.Vdcn)
            self.__dict__[var] = div(self.__dict__[var], Vbdc)

        for var in self._dccurrents:
            self.__dict__[var] = mul(self.__dict__[var], self.Idcn)
            self.__dict__[var] = div(self.__dict__[var], Ib)

        for var in self._r:
            self.__dict__[var] = div(self.__dict__[var], Rb)

        for var in self._g:
            self.__dict__[var] = mul(self.__dict__[var], Rb)

        self.ispu = True

    def setup(self):
        """
        Set up device parameters and variable addresses
        Called AFTER parsing the input file
        """
        self._interface()
        self._param2matrix()
        self._alloc()

    def _interface(self):
        """implement bus, node and controller interfaces"""
        self._ac_interface()
        self._dc_interface()
        self._ctrl_interface()

    def _ac_interface(self):
        """retrieve ac bus a and v addresses"""
        for key, val in self._ac.items():
            self.copy_param(model='Bus', src='a', dest=val[0], fkey=self.__dict__[key])
            self.copy_param(model='Bus', src='v', dest=val[1], fkey=self.__dict__[key])

    def _dc_interface(self):
        """retrieve v addresses of dc buses"""
        for key, val in self._dc.items():
            if type(val) == list:
                for item in val:
                    self.copy_param(model='Node', src='v', dest=item, fkey=self.__dict__[key])
            else:
                self.copy_param(model='Node', src='v', dest=val, fkey=self.__dict__[key])

    def _ctrl_interface(self):
        pass

    def _addr(self):
        """
        Assign address for xvars and yvars
        Function calls aggregated in class PowerSystem and called by main()
        """
        if self.addr is True:
            self.message('Address already assigned for <{}>'.format(self._name), WARNING)
            return
        for var in range(self.n):
            for item in self._states:
                self.__dict__[item][var] = self.system.DAE.n
                self.system.DAE.n += 1
            for item in self._algebs:
                m = self.system.DAE.m
                self.__dict__[item][var] = m
                self.system.DAE.m += 1
        self.addr = True

    def _varname(self):
        """ Set up xvars and yvars names in Varname"""
        if not self.addr:
            self.message('Unable to assign Varname before allocating address', ERROR)
            return
        if not self.n:
            return
        for idx, item in enumerate(self._states):
            self.system.VarName.append(listname='unamex', xy_idx=self.__dict__[item][:],
                                       var_name=self._unamex[idx], element_name=self.names)
        for idx, item in enumerate(self._algebs):
            self.system.VarName.append(listname='unamey', xy_idx=self.__dict__[item][:],
                                       var_name=self._unamey[idx], element_name=self.names)
        try:
            for idx, item in enumerate(self._states):
                self.system.VarName.append(listname='fnamex', xy_idx=self.__dict__[item][:],
                                           var_name=self._fnamex[idx], element_name=self.names)
            for idx, item in enumerate(self._algebs):
                self.system.VarName.append(listname='fnamey', xy_idx=self.__dict__[item][:],
                                           var_name=self._fnamey[idx], element_name=self.names)
        except IndexError:
            self.message('Formatted names missing in class <{0}> definition.'.format(self._name))

    def _param2matrix(self):
        """convert _params from list to matrix"""
        for item in self._params:
            self.__dict__[item] = matrix(self.__dict__[item])

    def _param2list(self):
        """convert _param from matrix to list"""
        for item in self._params:
            self.__dict__[item] = list(self.__dict__[item])

    def message(self, msg, level=INFO):
        """keep a line of message"""
        if level not in (DEBUG, INFO, WARNING, ERROR, CRITICAL):
            self.system.Log.error('Message logging level does not exist.')
            return
        self.system.Log.message(msg, level)

    def limit_check(self, data, min=None, max=None):
        """ check if data is within limits. reset if violates"""
        pass

    def add_jac(self, m, val, row, col):
        if m not in ['Fx', 'Fy', 'Gx', 'Gy', 'Fx0', 'Fy0', 'Gx0', 'Gy0']:
            raise NameError('Wrong Jacobian matrix name <{0}>'.format(m))

        size = self.system.DAE.__dict__[m].size
        self.system.DAE.__dict__[m] += spmatrix(val, row, col, size, 'd')

    def set_jac(self, m, val, row, col):
        if m not in ['Fx', 'Fy', 'Gx', 'Gy', 'Fx0', 'Fy0', 'Gx0', 'Gy0']:
            raise NameError('Wrong Jacobian matrix name <{0}>'.format(m))

        size = self.system.DAE.__dict__[m].size
        oldval = []
        if type(row) is int:
            row = [row]
        if type(col) is int:
            col = [col]
        if type(row) is range:
            row = list(row)
        if type(col) is range:
            col = list(col)
        for i, j in zip(row, col):
            oldval.append(self.system.DAE.__dict__[m][i, j])
        self.system.DAE.__dict__[m] -= spmatrix(oldval, row, col, size, 'd')
        self.system.DAE.__dict__[m] += spmatrix(val, row, col, size, 'd')
