#!/usr/bin/env python3
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

import os
import glob
import io
import pstats
import cProfile
from time import sleep
from multiprocessing import Process
from argparse import ArgumentParser

from . import filters
from .consts import *
from .system import PowerSystem
from .utils import elapsed
from .variables import preamble
from .routines import powerflow, timedomain


def cli_parse(writehelp=False, helpfile=None):
    """command line input argument parser"""

    parser = ArgumentParser(prog='andes')
    parser.add_argument('casename', nargs='*', default=[], help='Case file name.')

    # program general options
    parser.add_argument('-x', '--exit', help='Exit before solving the power flow. Enable this option to '
                                             'use andes ad a file format converter.', action='store_true')
    parser.add_argument('--no_preamble', action='store_true', help='Hide preamble')
    parser.add_argument('--license', action='store_true', help='Display MIT license and exit.')
    parser.add_argument('--version', action='store_true', help='Print current andes version and exit.')
    parser.add_argument('--warranty', action='store_true', help='Print warranty info and exit.')
    parser.add_argument('--what', action='store_true', help='Show me something and exit', default=None)
    parser.add_argument('-n', '--no_output', help='Force not to write any output, including log,'
                                                  'outputs and simulation dumps', action='store_true')
    parser.add_argument('--profile', action='store_true', help='Enable Python profiler.')

    parser.add_argument('-l', '--log', help='Specify the name of log file.')
    parser.add_argument('-d', '--dat', help='Specify the name of file to save simulation results.')
    parser.add_argument('-v', '--verbose', help='Program logging level, an integer from 1 to 5.'
                                                'The level corresponding to TODO=0, DEBUG=10, INFO=20, WARNING=30,'
                                                'ERROR=40, CRITICAL=50, ALWAYS=60. The default verbose level is 2.',
                        type=int)

    # file and format related
    parser.add_argument('-c', '--clean', help='Clean output files and exit.', action='store_true')
    parser.add_argument('-K', '--cleanall', help='Clean all output and auxillary files.', action='store_true')
    parser.add_argument('-p', '--path', help='Path to case files', default='')
    parser.add_argument('-s', '--settings', help='Specify a setting file. This will take precedence of .andesrc '
                                           'file in the home directory.')
    parser.add_argument('-i', '--input_format', help='Specify input case file format.')
    parser.add_argument('-o', '--output_format', help='Specify output case file format. For example txt, latex.')
    parser.add_argument('-O', '--output', help='Specify the output file name. For different routines the same name'
                                               'as the case file with proper suffix and extension wil be given.')
    parser.add_argument('-a', '--addfile', help='Include additional files used by some formats.')
    parser.add_argument('-D', '--dynfile', help='Include an additional dynamic file in dm format.')
    parser.add_argument('-J', '--gis', help='JML format GIS file.')
    parser.add_argument('-m', '--map', help='Visualize power flow results on GIS. Neglected if no GIS file is given.')
    parser.add_argument('-e', '--dump_raw', help='Dump RAW format case file.')  # consider being used as batch converter
    parser.add_argument('-Y', '--summary', help='Show summary and statistics of the data case.', action='store_true')

    # Solver Options
    parser.add_argument('-r', '--routine', help='Routine after power flow solution: t[TD], c[CPF], s[SS], o[OPF].')
    parser.add_argument('-j', '--checkjacs', help='Check analytical Jacobian using numerical differentation.')

    # helps and documentations
    parser.add_argument('-u', '--usage', help='Write command line usage', action='store_true')
    parser.add_argument('-C', '--category', help='Dump device names belonging to the specified category.')
    parser.add_argument('-L', '--dev_list', help='Dump the list of all supported devices.', action='store_true')
    parser.add_argument('-f', '--dev_format', help='Dump the format definition of all devices.', action='store_true')
    parser.add_argument('-W', '--dev_variables', help='Dump the variables of a specified device.')
    parser.add_argument('-G', '--group', help='Dump all the devices in the specified group.', action='store_true')
    parser.add_argument('-q', '--quick_help', help='Print a quick help of the device.')
    parser.add_argument('--help_option', help='Print a quick help of a setting parameter')
    parser.add_argument('--help_settings', help='Print a quick help of a given setting class. Use ALL'
                                                'for all setting classes.')
    parser.add_argument('-S', '--search', help='Search devices that match the given expression.')

    if writehelp:
        try:
            usagefile = open(helpfile, 'w')
            usagefile.writelines('[ANDES] Command Line Usage Help\n\n')
            parser.print_help(file=usagefile)
            usagefile.close()
            print('--> Command line usage written to file.')
        except IOError:
            print('I/O exception while writing help file.')
        return
    else:
        args = parser.parse_args()
        return args


def dumphelp(usage=None, group=None, category=None, dev_list=None, dev_format=None, dev_variables=None,
             quick_help=None, help_option=None, help_settings=None, **kwargs):
    if usage:
        cli_parse(writehelp=True, helpfile='cli_help.txt')
    if category:
        pass
    if dev_list:
        pass
    if dev_format:
        pass
    if dev_variables:
        pass
    if group:
        pass
    if quick_help:
        pass
    if help_option:
        pass
    if help_settings:
        pass


def cleanup(clean=False, cleanall=False):
    """Clean up function for generated files"""
    if not (clean or cleanall):
        return
    if clean:
        pass
    if cleanall:
        pass


def main():
    """Entry function"""
    t0, s = elapsed()
    args = cli_parse()
    cases = []
    kwargs = {}

    # run clean-ups and exit
    if args.clean or args.cleanall:
        cleanup(args.clean, args.cleanall)
        return

    # extract case names
    for item in args.casename:
        cases += glob.glob(os.path.join(args.path, item))
    args.casename = None

    # extract all arguments
    for arg, val in vars(args).items():
        if val is not None:
            kwargs[arg] = val

    # dump help and exit
    if dumphelp(**kwargs):
        return

    # exit if no case specified
    if len(cases) == 0:
        print(preamble(args.no_preamble))
        print('--> No valid data file or action is defined.')
        return

    # single case study
    elif len(cases) == 1:
        run(cases[0], **kwargs)
        t1, s = elapsed(t0)
        print('--> Single process finished in {0:s}.'.format(s))
        return

    # multiple studies on multiple processors
    else:
        jobs = []
        kwargs['verbose'] = ERROR
        for idx, casename in enumerate(cases):
            kwargs['pid'] = idx
            job = Process(name='Process {0:d}'.format(idx), target=run, args=(casename,), kwargs=kwargs)
            jobs.append(job)
            job.start()

        sleep(0.1)
        for job in jobs:
            job.join()
        t0, s0 = elapsed(t0)
        print('--> Multiple processing finished in {0:s}.'.format(s0))
        return


def run(case, **kwargs):
    """Run a single case study"""
    profile = kwargs.pop('profile', False)
    dump_raw = kwargs.pop('dump_raw', False)
    summary = kwargs.pop('summary', False)
    exitnow = kwargs.pop('exit', False)
    no_preamble = kwargs.pop('no_preamble', False)
    pid = kwargs.get('pid', -1)
    pr = cProfile.Profile()

    # enable profiler if requested
    if profile:
        pr.enable()

    # create a power system object
    system = PowerSystem(case, **kwargs)

    # print preamble
    if pid == -1:
        system.Log.info(preamble(no_preamble))

    t0, _ = elapsed()

    # parse input file
    if not filters.guess(system):
        system.Log.error('Unable to determine case format.')
        return
    if not filters.parse(system):
        system.Log.error('Parse input file failed.')
        return

    t1, s = elapsed(t0)
    system.Log.info('Case file {:s} parsed in {:s}.'.format(system.Files.fullname, s))

    # dump system as raw file if requested
    if dump_raw:
        if filters.dump_raw(system):
            t2, s = elapsed(t1)
            system.Log.info('Raw dump {:s} written in {:s}.'.format(system.Files.dump_raw, s))
        else:
            system.Log.error('Dump raw file failed.')

    # print summary only
    if summary:
        t2, s = elapsed(t1)
        system.Report.writey(content='summary')
        system.Log.info('Summary of written in {:s}'.format(s))
        return

    # exit without solving power flow
    if exitnow:
        system.Log.info('Exiting before solving power flow.')
        return

    # set up everything in system
    system.setup()

    # per-unitize parameters
    if system.Settings.base:
        system.base()

    # initialize power flow study
        system.init_pf()
    t2, s = elapsed(t1)
    system.Log.info('System models initialized in {:s}.\n'.format(s))

    # check for bus islanding
    system.check_islands()

    if len(system.Bus.islanded_buses) == 0 and len(system.Bus.island_sets) == 0:
        system.Log.info('System is interconnected.\n')
    else:
        system.Log.info('System contains {:d} islands and {:d} islanded buses.\n'.format
                        (len(system.Bus.island_sets), len(system.Bus.islanded_buses)))

    # Choose PF solver and run_pf
    if system.SPF.solver.lower() not in powerflow.solvers.keys():
        system.SPF.solver = 'NR'

    system.Log.info('Power Flow Analysis:')
    system.Log.info('Sparse Library: ' + system.Settings.sparselib.upper())
    system.Log.info('Solution Method: ' + system.SPF.solver.upper())
    system.Log.info('Flat-start: ' + ('Yes' if system.SPF.flatstart else 'No') + '\n')

    powerflow.run(system)
    t3, s = elapsed(t2)
    if not system.SPF.solved:
        system.Log.info('Power flow failed to converge in {:s}.'.format(s))
    else:
        system.Log.info('Power flow converged in {:s}.'.format(s))
        system.td_init()  # initialize variables for output even if not running TDS
        t4, s = elapsed(t3)
        if system.DAE.n:
            system.Log.info('Dynamic models initialized in {:s}.'.format(s))
        else:
            system.Log.info('No dynamic model loaded.')
        if not system.Files.no_output:
            system.Report.write(content='powerflow')
            t5, s = elapsed(t4)
            system.Log.info('Static report written in {:s}.'.format(s))

    # run more studies
    t0, s = elapsed()
    routine = kwargs.pop('routine', None)
    if not routine:
        pass
    elif routine.lower() in ['time', 'td', 't']:
        routine = 'td'
    elif routine.lower() in ['cpf', 'c']:
        routine = 'cpf'
    elif routine.lower() in ['small', 'ss', 'sssa', 's']:
        routine = 'sssa'
    if routine is 'td':
        t1, s = elapsed(t0)
        system.Log.info('')
        system.Log.info('Time Domain Simulation:')
        system.Log.info('Integration Method: {0}'.format(system.TDS.method))
        timedomain.run(system)
        t2, s = elapsed(t1)
        system.Log.info('Time domain simulation finished in {:s}.'.format(s))
        if not system.Files.no_output:
            system.VarOut.dump()
            t3, s = elapsed(t2)
            system.Log.info('Simulation data dumped in {:s}.'.format(s))

    # Disable profiler and output results
    if profile:
        pr.disable()
        if system.Files.no_output:
            s = io.StringIO()
            nlines = 20
            ps = pstats.Stats(pr, stream=s).sort_stats('time')
            ps.print_stats(nlines)
            print(s.getvalue())
            s.close()
        else:
            s = open(system.Files.prof, 'w')
            nlines = 50
            ps = pstats.Stats(pr, stream=s).sort_stats('time')
            ps.print_stats(nlines)
            s.close()
            system.Log.info('cProfile results for job{:s} written.'.format(' ' + str(pid) if pid >= 0 else ''))

    if pid >= 0:
        t3, s = elapsed(t0)
        system.Log.always('Process {:d} finished in {:s}.'.format(pid, s))


if __name__ == '__main__':
    main()
