from cvxopt import matrix, spdiag, mul, div, spmatrix, sparse
from .base import ModelBase
from ..consts import *
from ..utils.math import *


class Line(ModelBase):
    """AC transmission line lumped model"""
    def __init__(self, system, name):
        super().__init__(system, name)
        self._group = 'Line'
        self._name = 'Line'
        self._data.update({'r': 0.0,
                           'x': 1e-6,
                           'b': 0.0,
                           'g': 0.0,
                           'b1': 0.0,
                           'g1': 0.0,
                           'b2': 0.0,
                           'g2': 0.0,
                           'bus1': None,
                           'bus2': None,
                           'Vn2': 110.0,
                           'xcoord': None,
                           'ycoord': None,
                           'trasf': False,
                           'tap': 1.0,
                           'phi': 0,
                           'fn': 60,
                           'owner': 0,
                           })
        self._units.update({'r': 'pu',
                            'x': 'pu',
                            'b': 'pu',
                            'g': 'pu',
                            'b1': 'pu',
                            'g1': 'pu',
                            'b2': 'pu',
                            'g2': 'pu',
                            'bus1': 'na',
                            'bus2': 'na',
                            'Vn2': 'kV',
                            'xcoord': 'deg',
                            'ycoord': 'deg',
                            'transf': 'na',
                            'tap': 'na',
                            'phi': 'deg',
                            'fn': 'Hz',
                            'owner': 'na',
                            })
        self._descr.update({'r': 'connection line resistance',
                            'x': 'connection line reactance',
                            'g': 'shared shunt conductance',
                            'b': 'shared shunt susceptance',
                            'g1': 'from-side conductance',
                            'b1': 'from-side susceptance',
                            'g2': 'to-side conductance',
                            'b2': 'to-side susceptance',
                            'bus1': 'idx of from bus',
                            'bus2': 'idx of to bus',
                            'Vn2': 'rated voltage of bus2',
                            'xcoord': 'x coordinates',
                            'ycoord': 'y coordinates',
                            'trasf': 'transformer branch flag',
                            'tap': 'transformer branch tap ratio',
                            'phi': 'transformer branch phase shift in rad',
                            'fn': 'rated frequency',
                            'owner': 'owner code',
                            })
        self._params.extend(['r',
                             'x',
                             'b',
                             'g',
                             'b1',
                             'g1',
                             'b2',
                             'g2',
                             'tap',
                             'phi',
                             'fn',
                             ])
        self._service.extend(['a', 'v', 'a1', 'a2', 'S1', 'S2'])
        self.calls.update({'gcall': True, 'gycall': True,
                           'init0': True, 'pflow': True,
                           'series': True, 'flows': True})
        self.Y = []
        self.C = []
        self.Bp = []
        self.Bpp = []
        self._inst_meta()

    def setup(self):
        self._param2matrix()
        self.a = self.system.Bus.a
        self.v = self.system.Bus.v
        self.a1 = self.system.Bus._slice('a', self.bus1)
        self.a2 = self.system.Bus._slice('a', self.bus2)
        self.nb = int(self.system.Bus.n)
        self.system.Settings.nseries += self.n

        self.r += 1e-10
        self.b += 1e-10

        self.g1 += 0.5 * self.g
        self.b1 += 0.5 * self.b
        self.g2 += 0.5 * self.g
        self.b2 += 0.5 * self.b

    def build_y(self):
        """Build transmission line admittance matrix into self.Y"""
        y1 = mul(self.u, self.g1 + self.b1 * 1j)
        y2 = mul(self.u, self.g2 + self.b2 * 1j)
        y12 = div(self.u, self.r + self.x * 1j)
        m = polar(self.tap, self.phi * deg2rad)
        m2 = abs(m) ** 2

        # build self and mutual admittances into Y
        self.Y = spmatrix(div(y12 + y1, m2), self.a1, self.a1, (self.nb, self.nb), 'z')
        self.Y -= spmatrix(div(y12, conj(m)), self.a1, self.a2, (self.nb, self.nb), 'z')
        self.Y -= spmatrix(div(y12, m), self.a2, self.a1, (self.nb, self.nb), 'z')
        self.Y += spmatrix(y12 + y2, self.a2, self.a2, (self.nb, self.nb), 'z')

        # avoid singularity
        for item in range(self.nb):
            if abs(self.Y[item, item]) == 0:
                self.Y[item, item] = 1e-6 + 0j

    def build_b(self):
        """build Bp and Bpp for fast decoupled method"""
        solver = self.system.SPF.solver.lower()

        # Build B prime matrix
        y1 = mul(self.u, self.g1)  # y1 neglects line charging shunt, and g1 is usually 0 in HV lines
        y2 = mul(self.u, self.g2)  # y2 neglects line charging shunt, and g2 is usually 0 in HV lines
        m = polar(1.0, self.phi * deg2rad)  # neglected tap ratio
        m2 = matrix(1.0, (self.n, 1), 'z')
        if solver is 'fdxb':
            # neglect line resistance in Bp in XB method
            y12 = div(self.u, self.x * 1j)
        else:
            y12 = div(self.u, self.r + self.x * 1j)
        self.Bp = spmatrix(div(y12 + y1, m2), self.a1, self.a1, (self.nb, self.nb), 'z')
        self.Bp -= spmatrix(div(y12, conj(m)), self.a1, self.a2, (self.nb, self.nb), 'z')
        self.Bp -= spmatrix(div(y12, m), self.a2, self.a1, (self.nb, self.nb), 'z')
        self.Bp += spmatrix(y12 + y2, self.a2, self.a2, (self.nb, self.nb), 'z')
        self.Bp = self.Bp.imag()

        # Build B double prime matrix
        y1 = mul(self.u, self.g1 + self.b1 * 1j)  # y1 neglected line charging shunt, and g1 is usually 0 in HV lines
        y2 = mul(self.u, self.g2 + self.b2 * 1j)  # y2 neglected line charging shunt, and g2 is usually 0 in HV lines
        m = self.tap + 0j  # neglected phase shifter
        m2 = abs(m) ** 2 + 0j
        if solver is 'fdbx' or 'fdpf':
            # neglect line resistance in Bpp in BX method
            y12 = div(self.u, self.x * 1j)
        else:
            y12 = div(self.u, self.r + self.x * 1j)
        self.Bpp = spmatrix(div(y12 + y1, m2), self.a1, self.a1, (self.nb, self.nb), 'z')
        self.Bpp -= spmatrix(div(y12, conj(m)), self.a1, self.a2, (self.nb, self.nb), 'z')
        self.Bpp -= spmatrix(div(y12, m), self.a2, self.a1, (self.nb, self.nb), 'z')
        self.Bpp += spmatrix(y12 + y2, self.a2, self.a2, (self.nb, self.nb), 'z')
        self.Bpp = self.Bpp.imag()

        for item in range(self.nb):
            if abs(self.Bp[item, item]) == 0:
                self.Bp[item, item] = 1e-6 + 0j
            if abs(self.Bpp[item, item]) == 0:
                self.Bpp[item, item] = 1e-6 + 0j

    def incidence(self):
        """Build incidence matrix into self.C"""
        self.C = spmatrix(self.u, range(self.n), self.a1, (self.n, self.nb), 'd') -\
                 spmatrix(self.u, range(self.n), self.a2, (self.n, self.nb), 'd')

    def connectivity(self, bus):
        """check connectivity of network using Goderya's algorithm"""
        n = self.nb
        fr = self.a1
        to = self.a2
        os = [0] * self.n

        # find islanded buses
        diag = list(matrix(spmatrix(1.0, to, os, (n, 1), 'd') + spmatrix(1.0, fr, os, (n, 1), 'd')))
        nib = bus.n_islanded_buses = diag.count(0)
        bus.islanded_buses = []
        for idx in range(n):
            if diag[idx] == 0:
                bus.islanded_buses.append(idx)

        # find islanded areas
        temp = spmatrix(1.0, fr + to + fr + to, to + fr + fr + to, (n, n), 'd')
        cons = temp[0, :]
        nelm = len(cons.J)
        conn = spmatrix([], [], [], (1, n), 'd')
        bus.island_sets = []
        idx = islands = 0
        enum = 0

        while 1:
            while 1:
                cons = cons*temp
                new_nelm = len(cons.J)
                if new_nelm == nelm:
                    break
                nelm = new_nelm
            if len(cons.J) == n:  # all buses are interconnected
                return
            bus.island_sets.append(list(cons.J))
            conn += cons
            islands += 1
            nconn = len(conn.J)
            if nconn >= (n - nib):
                bus.island_sets = [i for i in bus.island_sets if i != []]
                break

            for element in conn.J[idx:]:
                if not diag[idx]:
                    enum += 1 # skip islanded buses
                if element <= enum:
                    idx += 1
                    enum += 1
                else:
                    break

            cons = temp[enum, :]

    def init0(self, dae):
        solver = self.system.SPF.solver.lower()
        self.build_y()
        self.incidence()
        if solver in ('fdpf', 'fdbx', 'fdxb'):
            self.build_b()

    def gcall(self, dae):
        vc = polar(dae.y[self.v], dae.y[self.a])
        Ic = self.Y*vc
        S = mul(vc, conj(Ic))
        dae.g[self.a] += S.real()
        dae.g[self.v] += S.imag()

    def gycall(self, dae):
        gy = self.build_gy(dae)
        dae.add_jac(Gy, gy.V, gy.I, gy.J)

    def build_gy(self, dae):
        """Build line Jacobian matrix"""
        if not self.n:
            idx = range(dae.m)
            dae.set_jac(Gy, 1e-6, idx, idx)
            return

        Vn = polar(1.0, dae.y[self.a])
        Vc = mul(dae.y[self.v], Vn)
        Ic = self.Y * Vc

        diagVn = spdiag(Vn)
        diagVc = spdiag(Vc)
        diagIc = spdiag(Ic)

        dS = self.Y * diagVn
        dS = diagVc * conj(dS)
        dS += conj(diagIc) * diagVn

        dR = diagIc
        dR -= self.Y * diagVc
        dR = diagVc.H.T * dR
        return sparse([[dR.imag(), dR.real()], [dS.real(), dS.imag()]])

    def seriesflow(self, dae):
        """Compute the flow through the line after solving PF, including: terminal injections, line losses"""
        y1 = mul(self.u, self.g1 + self.b1 * 1j)
        y2 = mul(self.u, self.g2 + self.b2 * 1j)
        y12 = div(self.u, self.r + self.x * 1j)
        m = polar(self.tap, self.phi*deg2rad)
        mconj = conj(m)
        m2 = abs(m)**2 + 0j

        Vm = dae.y[self.v]
        Va = dae.y[self.a]
        V1 = polar(Vm[self.a1], Va[self.a1])
        V2 = polar(Vm[self.a2], Va[self.a2])

        I1 = mul(V1, div(y12 + y1, m2)) - mul(V2, div(y12, mconj))
        I2 = mul(V2, y12+y2) - mul(V1, div(y12, m))
        self.S1 = mul(V1, conj(I1))
        self.S2 = mul(V2, conj(I2))

        self.chg1 = mul(self.b1, div(V1 ** 2, m2))
        self.chg2 = mul(self.b2, V2 ** 2)
