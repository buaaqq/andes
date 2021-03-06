"""Synchronous generator classes"""

from cvxopt import matrix, sparse, spmatrix
from cvxopt import mul, div, log, sin, cos
from .base import ModelBase
from ..consts import *
from ..utils.math import *


class SynBase(ModelBase):
    """Base class for synchronous generators"""
    def __init__(self, system, name):
        super().__init__(system, name)
        self._group = 'Synchronous'
        self._data.update({'fn': 60.0,
                           'bus': None,
                           'D': 0.0,
                           'M': 6,
                           'ra': 0.0,
                           'xl': 0.0,
                           'xq': 1.7,
                           'gammap': 1.0,
                           'gammaq': 1.0,
                           'coi': None,
                           'gen': None,
                           'kp': 0,
                           'kw': 0,
                           })
        self._params.extend(['D', 'M', 'ra', 'xl', 'xq', 'gammap', 'gammaq', 'gen', 'kp', 'kw'])
        self._descr.update({'fn': 'rated frequency',
                            'bus': 'interface bus id',
                            'D': 'rotor damping',
                            'M': 'machine start up time (2H)',
                            'ra': 'armature resistance',
                            'xl': 'leakage reactance',
                            'xq': 'q-axis synchronous reactance',
                            'gammap': 'active power ratio of all generators on this bus',
                            'gammaq': 'reactive power ratio',
                            'coi': 'center of inertia index',
                            'gen': 'static generator index',
                            'kp': 'active power feedback gain',
                            'kw': 'speed feedback gain',
                            })
        self._units.update({'M': 'MWs/MVA',
                            'D': 'pu',
                            'fn': 'Hz',
                            'ra': 'omh',
                            'xd': 'omh',
                            'gammap': 'pu',
                            'gammaq': 'pu',
                            })
        self.calls.update({'init1': True, 'dyngen': True,
                           'gcall': True, 'gycall': True,
                           'fcall': True, 'fxcall': True,
                           'jac0': True,
                           })
        self._ac = {'bus': ['a', 'v']}
        self._states = ['delta', 'omega']
        self._fnamex = ['\\delta', '\\omega']
        self._algebs = ['p', 'q', 'pm', 'vf', 'Id', 'Iq', 'vd', 'vq']
        self._fnamey = ['P', 'Q', 'P_m', 'V_f', 'I_d', 'I_q', 'V_d', 'V_q']
        self._powers = ['M', 'D']
        self._z = ['ra', 'xl', 'xq']
        self._zeros = ['M']
        self._mandatory = ['bus', 'gen']
        self._service = ['pm0', 'vf0', 'c1', 'c2', 'c3', 'ss', 'cc', 'iM']

    def build_service(self):
        """Build service variables"""
        self.iM = div(1, self.M)

    def setup(self):
        super().setup()
        self.build_service()

    def init1(self, dae):
        self.system.rmgen(self.gen)

        p0 = mul(self.u, self.system.Bus.Pg[self.a], self.gammap)
        q0 = mul(self.u, self.system.Bus.Qg[self.a], self.gammaq)
        v0 = mul(self.u, dae.y[self.v])
        theta0 = dae.y[self.a]
        v = polar(v0, theta0)
        S = p0 - q0*1j
        I = div(S, conj(v))
        E = v + mul(self.ra + self.xd1*1j, I)

        dae.y[self.p] = p0
        dae.y[self.q] = q0

        delta = log(div(E, abs(E) + 0j))
        dae.x[self.delta] = mul(self.u, delta.imag())
        dae.x[self.omega] = matrix(1.0, (self.n, 1), 'd')

        # d- and q-axis voltages and currents
        vdq = mul(self.u, mul(v, exp(jpi2 - delta)))
        idq = mul(self.u, mul(I, exp(jpi2 - delta)))
        vd = dae.y[self.vd] = vdq.real()
        vq = dae.y[self.vq] = vdq.imag()
        Id = dae.y[self.Id] = idq.real()
        Iq = dae.y[self.Iq] = idq.imag()

        # electro-mechanical torques / powers
        self.pm0 = mul(vq + mul(self.ra, Iq), Iq) + mul(vd + mul(self.ra, Id), Id)
        dae.y[self.pm] = self.pm0


    def gcall(self, dae):
        nzeros = [0] * self.n
        v = mul(self.u, dae.y[self.v])
        vd = dae.y[self.vd]
        vq = dae.y[self.vq]
        Id = dae.y[self.Id]
        Iq = dae.y[self.Iq]
        self.ss = sin(dae.x[self.delta] - dae.y[self.a])
        self.cc = cos(dae.x[self.delta] - dae.y[self.a])

        dae.g -= spmatrix(dae.y[self.p], self.a, nzeros, (dae.m, 1), 'd')
        dae.g -= spmatrix(dae.y[self.q], self.v, nzeros, (dae.m, 1), 'd')
        dae.g -= spmatrix(vd - mul(v, self.ss), self.vd, nzeros, (dae.m, 1), 'd')  # note d(vd)/d(delta)
        dae.g -= spmatrix(vq - mul(v, self.cc), self.vq, nzeros, (dae.m, 1), 'd')  # note d(vq)/d(delta)
        dae.g += spmatrix(mul(vd, Id) + mul(vq, Iq) - dae.y[self.p], self.p, nzeros, (dae.m, 1), 'd')
        dae.g += spmatrix(mul(vq, Id) - mul(vd, Iq) - dae.y[self.q], self.q, nzeros, (dae.m, 1), 'd')
        dae.g += spmatrix(dae.y[self.pm] - self.pm0, self.pm, nzeros, (dae.m, 1), 'd')
        dae.g += spmatrix(dae.y[self.vf] - self.vf0, self.vf, nzeros, (dae.m, 1), 'd')

    def saturation(self, e1q):
        """Saturation characteristic function"""
        return e1q

    def fcall(self, dae):
        dae.f[self.delta] = mul(self.u, self.system.Settings.wb, dae.x[self.omega] - 1)

    def jac0(self, dae):
        dae.add_jac(Gy0, -self.u, self.a, self.p)
        dae.add_jac(Gy0, -self.u, self.v, self.q)
        dae.add_jac(Gy0, -1.0, self.vd, self.vd)
        dae.add_jac(Gy0, -1.0, self.vq, self.vq)
        dae.add_jac(Gy0, -1.0, self.p, self.p)
        dae.add_jac(Gy0, -1.0, self.q, self.q)
        dae.add_jac(Gy0, 1.0, self.pm, self.pm)
        dae.add_jac(Gy0, 1.0, self.vf, self.vf)

        dae.add_jac(Fx0, self.u - 1 + 1e-6, self.delta, self.delta)
        dae.add_jac(Fx0, mul(self.u, self.system.Settings.wb), self.delta, self.omega)

    def gycall(self, dae):
        dae.add_jac(Gy, dae.y[self.Id], self.p, self.vd)
        dae.add_jac(Gy, dae.y[self.Iq], self.p, self.vq)
        dae.add_jac(Gy, dae.y[self.vd], self.p, self.Id)
        dae.add_jac(Gy, dae.y[self.vq], self.p, self.Iq)

        dae.add_jac(Gy, -dae.y[self.Iq], self.q, self.vd)
        dae.add_jac(Gy, dae.y[self.Id], self.q, self.vq)
        dae.add_jac(Gy, dae.y[self.vq], self.q, self.Id)
        dae.add_jac(Gy, -dae.y[self.vd], self.q, self.Iq)

        dae.add_jac(Gy, -mul(dae.y[self.v], self.cc), self.vd, self.a)
        dae.add_jac(Gy, self.ss, self.vd, self.v)

        dae.add_jac(Gy,  mul(dae.y[self.v], self.ss), self.vq, self.a)
        dae.add_jac(Gy, self.cc, self.vq, self.v)

    def fxcall(self, dae):
        dae.add_jac(Gx,  mul(dae.y[self.v], self.cc), self.vd, self.delta)
        dae.add_jac(Gx, -mul(dae.y[self.v], self.ss), self.vq, self.delta)


class Ord2(SynBase):
    """2nd order classical model"""
    def __init__(self, system, name):
        super().__init__(system, name)
        self._name = 'Syn2'
        self._data.update({'xd1': 1.9})
        self._params.extend(['xd1'])
        self._descr.update({'xd1': 'synchronous reactance'})
        self._units.update({'xd1': 'omh'})
        self._z.extend(['xd1'])

    def init1(self, dae):
        super().init1(dae)
        self.vf0 = dae.y[self.vq] + mul(self.ra, dae.y[self.Iq]) + mul(self.xd1, dae.y[self.Id])
        dae.y[self.vf] = self.vf0


class Flux0(object):
    """The simplified flux model as an appendix to generator models.
         0 = ra*id + psiq + vd
         0 = ra*iq - psid + vq
    """
    def __init__(self):
        self._algebs.extend(['psid', 'psiq'])
        self._fnamey.extend(['\\psi_d', '\\psi_q'])
        self._inst_meta()

    def init1(self, dae):
        dae.y[self.psiq] = -mul(self.ra, dae.y[self.Id]) - dae.y[self.vd]
        dae.y[self.psid] =  mul(self.ra, dae.y[self.Iq]) + dae.y[self.vq]

    def gcall(self, dae):
        dae.g[self.psiq] = mul(self.ra, dae.y[self.Id]) + dae.y[self.psiq] + dae.y[self.vd]
        dae.g[self.psid] = mul(self.ra, dae.y[self.Iq]) - dae.y[self.psid] + dae.y[self.vq]
        dae.g[self.Id] = dae.y[self.psid] + mul(self.xd1, dae.y[self.Id]) - dae.y[self.vf]
        dae.g[self.Iq] = dae.y[self.psiq] + mul(self.xd1, dae.y[self.Iq])

    def gycall(self, dae):
        dae.add_jac(Gy, self.ra, self.psiq, self.Id)
        dae.add_jac(Gy, self.ra, self.psid, self.Iq)

    def fcall(self, dae):
        dae.f[self.omega] = mul(self.iM, dae.y[self.pm] - mul(dae.y[self.psid], dae.y[self.Iq])
                                + mul(dae.y[self.psiq], dae.y[self.Id]) - mul(self.D, dae.x[self.omega] - 1))

    def fxcall(self, dae):
        dae.add_jac(Fy,  mul(dae.y[self.Id], self.iM), self.omega, self.psiq)
        dae.add_jac(Fy,  mul(dae.y[self.psiq], self.iM), self.omega, self.Id)
        dae.add_jac(Fy, -mul(dae.y[self.Iq], self.iM), self.omega, self.psid)
        dae.add_jac(Fy, -mul(dae.y[self.psid], self.iM), self.omega, self.Iq)

    def jac0(self, dae):
        dae.add_jac(Gy0, 1.0, self.psiq, self.psiq)
        dae.add_jac(Gy0, 1.0, self.psiq, self.vd)

        dae.add_jac(Gy0, -1.0, self.psid, self.psid)
        dae.add_jac(Gy0, 1.0, self.psid, self.vq)

        dae.add_jac(Gy0, 1.0, self.Id, self.psid)
        dae.add_jac(Gy0, self.xd1, self.Id, self.Id)
        dae.add_jac(Gy0, -1.0, self.Id, self.vf)

        dae.add_jac(Gy0, self.xd1, self.Iq, self.Iq)
        dae.add_jac(Gy0, 1.0, self.Iq, self.psiq)

        dae.add_jac(Fy0, -mul(self.iM, self.D) + 1 - self.u, self.omega, self.omega)
        dae.add_jac(Fy0, self.iM, self.omega, self.pm)


class Syn2(Ord2, Flux0):
    """2nd-order generator model. Inherited from (Ord2, Flux0)  """
    def __init__(self, system, name):
        Ord2.__init__(self, system, name)
        Flux0.__init__(self)

    def init1(self, dae):
        Ord2.init1(self, dae)
        Flux0.init1(self, dae)

    def gcall(self, dae):
        Ord2.gcall(self, dae)
        Flux0.gcall(self, dae)

    def fcall(self, dae):
        Ord2.fcall(self, dae)
        Flux0.fcall(self, dae)

    def jac0(self, dae):
        Ord2.jac0(self, dae)
        Flux0.jac0(self, dae)

    def gycall(self, dae):
        Ord2.gycall(self, dae)
        Flux0.gycall(self, dae)

    def fxcall(self, dae):
        Ord2.fxcall(self, dae)
        Flux0.fxcall(self, dae)
