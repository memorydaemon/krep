
import os
import re

from topics import ConfigFile, SubCommandWithThread, \
    RaiseExceptionIfOptionMissed
from options import Values


class BatchSubcmd(SubCommandWithThread):
    COMMAND = 'batch'

    help_summary = 'Load and execute projects from specified files'
    help_usage = """\
%prog [options] ...

Read project configurations from files and executes per project configuration.

The project is implemented to read configations from the config file and
execute. With the support, "%prog" would extend as the batch method to run as
a single command to accomplish multiple commands.

The format of the plain-text configuration file can refer to the topic
"config_file", which is used to define the projects in the file.
"""

    def options(self, optparse):
        SubCommandWithThread.options(self, optparse)

        options = optparse.add_option_group('File options')
        options.add_option(
            '-f', '--file', '--batch-file',
            dest='batch_file', action='append', metavar='FILE',
            help='Set the batch config file')
        options.add_option(
            '-u', '--group',
            dest='group', metavar='GROUP1,GROUP2,...',
            help='Set the handling groups')
        options.add_option(
            '--list',
            dest='list', action='store_true',
            help='List the selected projects')

        options = optparse.add_option_group('Error handling options')
        options.add_option(
            '--ierror', '--ignore-errors',
            dest='ignore_errors', action='store_true',
            help='Ignore the running error and continue for next command')

    def support_inject(self):  # pylint: disable=W0613
        return True

    def execute(self, options, *args, **kws):
        SubCommandWithThread.execute(self, options, *args, **kws)

        logger = self.get_logger()  # pylint: disable=E1101

        def _in_group(limits, groups):
            allminus = True

            for limit in limits:
                opposite = False
                if limit.startswith('-'):
                    limit = limit[1:]
                    opposite = True
                else:
                    allminus = False

                if limit in groups:
                    return not opposite

            if (allminus or 'default' in limits) and \
                    'notdefault' not in groups and '-default' not in groups:
                return True

            return False

        def _filter_with_group(project, name, limit):
            limits = re.split(r'\s*,\s*', limit or 'default')

            groups = re.split(r'\s*,\s*', project.pop('group', ''))
            groups.extend([name, os.path.basename(name)])
            if _in_group(limits, groups):
                return True
            else:
                logger.debug('%s: %s not in %s',
                             getattr(project, 'name'), limits, groups)

                return False

        def _run(project):
            largs = options.args or list()
            ignore_error = options.ignore_error or False

            # ensure to construct thread logger
            self.get_logger(project.name, level=2)  # pylint: disable=E1101
            self._run(project.schema,  # pylint: disable=E1101
                      project,
                      largs,
                      ignore_except=ignore_error)

        def _batch(batch):
            conf = ConfigFile(batch)

            projs, nprojs, tprojs = list(), list(), list()
            for name in conf.get_names('project') or list():
                projects = conf.get_values(name)
                if not isinstance(projects, list):
                    projects = [projects]

                # handle projects with the same name
                for project in projects:
                    proj = Values()
                    # remove the prefix 'project.'
                    proj_name = conf.get_subsection_name(name)
                    setattr(proj, 'name', proj_name)
                    if _filter_with_group(project, proj_name, options.group):
                        optparse = self._cmdopt(project.schema)  # pylint: disable=E1101
                        # recalculate the attribute types
                        proj.join(project, option=optparse)
                        proj.join(options, option=optparse, override=False)
                        if len(projects) == 1:
                            tprojs.append(proj)
                        else:
                            projs.append(proj)

            for project in tprojs:
                try:
                    multiple = self._cmd(  # pylint: disable=E1101
                        project.schema).support_jobs()
                except AttributeError:
                    raise SyntaxError(
                        'schema is not recognized or undefined in %s' %
                        project)

                working_dir = project.pop('working_dir')
                if working_dir:
                    setattr(
                        project, 'working_dir', os.path.abspath(working_dir))

                if multiple:
                    projs.append(project)
                else:
                    nprojs.append(project)

            if options.list:
                def _inc(dicta, key):
                    if key in dicta:
                        dicta[key] += 1
                    else:
                        dicta[key] = 1

                print '\nFile: %s' % batch
                print '=================================='
                if len(nprojs):
                    print 'Parallel projects with %s job(s)' % (options.job or 1)
                    print '---------------------------------'
                    results = dict()
                    for project in nprojs:
                        _inc(results, '[%s] %s' % (
                            project.schema, project.name))

                    for k, result in enumerate(sorted(results.keys())):
                        print '  %2d. %s' % (k + 1, result)

                if len(projs):
                    print '\nNon-parallel projects'
                    print '---------------------------------'
                    results = dict()
                    for project in projs:
                        _inc(results, '[%s] %s' % (
                            project.schema, project.name))

                    for k, result in enumerate(sorted(results.keys())):
                        print '  %2d. %s%s' % (
                            k + 1, result, ' (%d)' % results[result]
                            if results[result] > 1 else '')

                print
                return True
            else:
                ret = self.run_with_thread(  # pylint: disable=E1101
                    options.job, nprojs, _run)
                ret = self.run_with_thread(  # pylint: disable=E1101
                    1, projs, _run) and ret

                return ret

        RaiseExceptionIfOptionMissed(
            options.batch_file or args, "batch file (--batch-file) is not set")

        ret = True
        files = (options.batch_file or list())[:]
        files.extend(args[:])

        for batch in files:
            if os.path.exists(batch):
                ret = _batch(batch) and ret
            else:
                logger.error('cannot open batch file %s', batch)
                ret = False

            if not ret and not options.ignore_errors:
                break

        return ret
