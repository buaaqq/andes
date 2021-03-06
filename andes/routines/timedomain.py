from cvxopt import matrix, spmatrix, sparse
from cvxopt.klu import numeric, symbolic, solve, linsolve


def first_time_step(system):
    """compute first time step"""
    settings = system.TDS
    # estimate minimum time step
    if not system.DAE.n:
        freq = 1.0
    elif system.DAE.n == 1:
        B = matrix(system.DAE.Gx)
        linsolve(system.DAE.Gy, B)
        As = system.DAE.Fx - system.DAE.Fy*B
        freq = abs(As[0, 0])
    else:
        freq = 20.0

    if freq > system.Settings.freq:
        freq = float(system.Settings.freq)

    if not freq:
        freq = 20.0

    # set the minimum time step

    Tspan = abs(settings.tf - settings.t0)
    Tcycle = 1/freq
    settings.deltatmax = min(5*Tcycle, Tspan/100.0)
    settings.deltat = min(Tcycle, Tspan/100.0)
    settings.deltatmin = min(Tcycle/64, settings.deltatmax/20)

    if settings.fixt:
        if settings.tstep <= 0:
            system.Log.warning('Fixed time step is negative or zero')
            system.Log.warning('Switching to automatic time step')
            settings.fixt = False
        else:
            settings.deltat = settings.tstep
            if settings.tstep < settings.deltatmin:
                system.Log.warning('Fixed time step is below the estimated minimum')
    return settings.deltat


def run(system):

    dae = system.DAE
    settings = system.TDS
    # check settings
    maxit = settings.maxit
    tol = settings.tol
    n = system.DAE.n  # state var
    m = system.DAE.m  # algebraic var
    In = spmatrix(1, range(n), range(n), (n, n), 'd')

    # initialization
    t = settings.t0
    step = 0
    inc = matrix(0, (n+m, 1), 'd' )
    dae.factorize = True
    dae.mu = 1.0
    dae.kg = 0.0
    switch = 0
    nextpc = 0.1
    h = first_time_step(system)

    # time vector for faults and breaker events
    fixed_times = system.Call.get_times()  # todo: to implement
    # fixed_times = [] # hardcoded, todo: implement the line above
    # compute max rotor angle difference
    diff_max = anglediff()

    system.VarOut.store(t)  # store the initial value

    # main loop
    while t <= settings.tf and t + h > t and not diff_max:

        # last time step length
        if t + h > settings.tf:
            h = settings.tf - t
        # avoid freezing at t == settings.tf

        if h == 0:  # does not converge and reached minimum time step
            break
        actual_time = t + h

        #check for the occurrence of a disturbance
        for item in fixed_times:
            if item > t and item < t+h:  # not to skip events
                actual_time = item
                h = actual_time - t
                switch = True
                break

        # set global time
        system.DAE.t = actual_time

        # backup actual variables
        xa = matrix(dae.x)
        ya = matrix(dae.y)

        # initialize NR loop
        niter = 0
        fn = matrix(dae.f)

        # apply fixed_time interventions and perturbations
        if switch:
            system.Fault.checktime(actual_time)
            # system.Breaker.get_times(actual_time)
            switch = False

        if settings.disturbance:
            system.Call.disturbance(actual_time)

        # main loop of Newton iteration
        settings.error = tol + 1 # force at least one iteration
        while settings.error > tol and niter < maxit:
            # note: dae.x, dae.y, dae.f, dae.g are updated in each iteration

            # DAE equations
            exec(system.Call.int)

            # complete Jacobian matrix DAE.Ac
            if settings.method == 'euler':
                dae.Ac = sparse([[In - h*dae.Fx, dae.Gx],
                                 [   - h*dae.Fy, dae.Gy]], 'd')
                dae.q = dae.x - xa - h*dae.f
            elif settings.method == 'trapezoidal':  # use implicit trapezoidal method by default
                dae.Ac = sparse([[In - h*0.5*dae.Fx, dae.Gx],
                                 [   - h*0.5*dae.Fy, dae.Gy]], 'd')
                dae.q = dae.x - xa - h*0.5*(dae.f + fn)

            # anti-windup limiters
            #     exec(system.Call.windup)

            if dae.factorize:
                F = symbolic(dae.Ac)
                dae.factorize = False
            inc = -matrix([dae.q, dae.g])

            # write_mat('TDS_Gy.mat', [dae.Ac, inc], ['TDS_Ac', 'mis'])

            try:
                N = numeric(dae.Ac, F)
                solve(dae.Ac, F, N, inc)
            except ArithmeticError:
                system.Log.error('Singular matrix')
                niter = maxit + 1  # force quit
            except ValueError:
                system.Log.warning('Unexpected symbolic factorization')
                F = symbolic(dae.Ac)
                try:
                    N = numeric(dae.Ac, F)
                    solve(dae.Ac, F, N, inc)
                except ArithmeticError:
                    system.Log.error('Singular matrix')
                    niter = maxit + 1
            dae.x += inc[:n]
            dae.y += inc[n: m+n]
            settings.error = max(abs(inc))
            niter += 1

        if niter >= maxit:
            h = time_step(system, False, niter, t)
            system.Log.debug('Reducing time step (delta t={:.5g}s)'.format(h))
            dae.x = matrix(xa)
            dae.y = matrix(ya)
            dae.f = matrix(fn)
            continue

        # update output variables and time step
        t = actual_time
        step += 1

        system.VarOut.store(t)

        h = time_step(system, True, niter, t)

        # plot variables and display iteration status
        perc = (t - settings.t0) / (settings.tf - settings.t0)
        if perc > nextpc:
            system.Log.info(' * Simulation time = {:.4f}s, {:.1f}%'.format(dae.t, perc*100))
            system.Log.debug(' * Simulation time = {:.4f}s, step = {}, max mismatch = {:.4f}, niter = {}'.format(t, step, settings.error, niter))
            nextpc += 0.1

        # compute max rotor angle difference
        diff_max = anglediff()


def time_step(system, convergence, niter, t):
    """determine the time step during time domain simulations
        convergence: 1 - last step computation converged
                     0 - last step not converged
        niter:  number of iterations """
    settings = system.TDS
    if convergence:
        if niter >= 15:
            settings.deltat = max(settings.deltat*0.9, settings.deltatmin)
        elif niter <= 10:
            settings.deltat = min(settings.deltat*1.2, settings.deltatmax)

        if settings.fixt:  # adjust fixed time step if niter is high
            settings.deltat = min(settings.tstep, settings.deltat)
    else:
        settings.deltat *= 0.5
        if settings.deltat < settings.deltatmin:
            settings.deltat = 0

    # if istime(Fault, t):
    #     settings.deltat = min(settings.deltat, 0.0025);

    return settings.deltat


def anglediff():
    """compute angle difference"""
    return False