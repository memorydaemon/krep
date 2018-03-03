
import os
import threading
import types

from command import Command
from logger import Logger


class SubCommand(object):
    """Supports to run as the tool running command."""
    _name = None
    _optparse = None

    def get_option_parser(self, opt):
        """Returns the option parser for the subcommand."""
        if self._optparse is None:
            try:
                usage = self.help_usage.replace(  # pylint: disable=E1101
                    '%prog', 'krep %s' % getattr(
                        self, 'COMMAND', self.NAME))  # pylint: disable=E1101
            except AttributeError:
                # it shouldn't be run here
                raise SyntaxError('Failed to read command attribute')

            self._optparse = opt
            self._optparse.set_usage(usage)
            self.options(self._optparse)

        return self._optparse

    def options(self, optparse, *args, **kws):  # pylint: disable=W0613
        """Handles the options for the subcommand."""
        options = optparse.add_option_group('File options')
        options.add_option(
            '--hook-dir',
            dest='hook_dir', action='store',
            help='Indicates the directory with the preinstalled hooks')

        self._options_jobs(optparse)
        # load options from the imported classes
        extra_list = self._options_loaded(optparse, kws.get('modules'))
        self._option_extra(optparse, extra_list)

    def _options_jobs(self, optparse):
        if self.support_jobs():
            options = optparse.get_option_group('--force') or \
                optparse.add_option_group('Other options')

            options.add_option(
                '-j', '--job',
                dest='job', action='store', type='int',
                help='jobs to run with specified threads in parallel')

    def _option_extra(self, optparse, extra_list=None):
        def _format_list(extra_items):
            item_list = list()

            if extra_items:
                items = list()

                # re-arrange the extra list with a flat format
                for opt, item in extra_items:
                    if not isinstance(item, (list, tuple)):
                        items.append((opt, item))
                    else:
                        items.append(opt)
                        items.extend(item[:])

                length = max([len(it[0]) for it in items if len(it) == 2])
                fmt = '  %%-%ds  %%s' % (length + 2)
                for item in items:
                    if len(item) == 2:
                        item_list.append(fmt % (item[0], item[1]))
                    else:
                        item_list.append('')
                        item_list.append(item)

            return '\n'.join(item_list)

        if extra_list or self.support_extra():
            item = _format_list(extra_list or [])

            options = optparse.get_option_group('--force') or \
                optparse.add_option_group('Other options')

            options.add_option(
                '--extra-option',
                dest='extra_option', action='append',
                help='extra options in internal group with prefix. '
                     'The format is like "inject-option"%s' % (
                         ':\n%s' % item if item else ''))

    @staticmethod
    def _options_loaded(optparse=None, modules=None):
        extra_list = list()

        logger = SubCommand.get_logger()
        # search the imported class to load the options
        for name, clazz in (modules or dict()).items():
            if isinstance(clazz, (types.ClassType, types.TypeType)):
                if optparse and hasattr(clazz, 'options'):
                    try:
                        logger.debug('Load %s', name)
                        clazz.options(optparse)
                    except TypeError:
                        pass

                if hasattr(clazz, 'extra_items'):
                    extra_list.extend(clazz.extra_items)

        return extra_list

    @staticmethod
    def get_logger(name=None, level=0):
        """Returns the encapusulated logger for subcommands."""
        return Logger.get_logger(name, level)

    @staticmethod
    def get_absolute_working_dir(options):
        return os.path.join(options.working_dir, options.relative_dir) \
            if options.relative_dir else options.working_dir

    def get_name(self, options):  # pylint: disable=W0613
        """Gets the subcommand name."""
        return self._name or \
            getattr(self, 'COMMAND', self.NAME)  # pylint: disable=E1101

    def set_name(self, name):
        """Sets the subcommand name."""
        self._name = name

    def support_jobs(self):  # pylint: disable=W0613
        """Indicates if the command can run with threading."""
        return False

    def support_inject(self):  # pylint: disable=W0613
        """Indicates if the command supports the injection option."""
        return False

    def support_extra(self):  # pylint: disable=W0613
        """Indicates if the command supports the extra option."""
        return False

    @staticmethod
    def override_value(va, vb=None):
        """Overrides the late values if it's not a boolean value."""
        return vb if vb is not None else va

    @staticmethod
    def do_hook(name, option, tryrun=False):
        # try option.hook-name first to support xml configurations
        hook = option.pop('hook-%s' % name)
        if hook:
            args = option.normalize('hook-%s-args' % name, attr=True)
            return SubCommand.run_hook(
                hook, args,
                SubCommand.get_absolute_working_dir(option),
                tryrun=tryrun)

        hook = None
        # try hook-dir with the hook name then
        if option.hook_dir:
            hook = os.path.join(option.hook_dir, name)
        elif 'KREP_HOOK_PATH' in os.environ:
            hook = os.path.join(os.environ['KREP_HOOK_PATH'], name)

        if hook:
            return SubCommand.run_hook(
                hook, None,
                SubCommand.get_absolute_working_dir(option),
                tryrun=tryrun)
        else:
            return 1

    @staticmethod
    def run_hook(hook, hargs, cwd=None, tryrun=False, *args, **kws):
        if hook:
            if os.path.exists(hook):
                cli = list([hook])
                if hargs:
                    cli.extend(hargs)
                if args:
                    cli.extend(args)

                cmd = Command(cwd=cwd, tryrun=tryrun)
                cmd.new_args(*cli)
                return cmd.wait(**kws)
            else:
                SubCommand.get_logger().debug("Error: %s not existed", hook)

    def execute(self, options, *args, **kws):  # pylint: disable=W0613
        # set the logger name at the beggining
        self.get_logger(self.get_name(options), level=1)

        return True


class SubCommandWithThread(SubCommand):
    """Commands with threading method to run with multiple jobs"""
    def support_jobs(self):  # pylint: disable=W0613
        return True

    def run_with_thread(self, jobs, tasks, func, *args):
        def _run(task, sem, event, func, args):
            try:
                if len(args) > 0:
                    func(task, *args)
                else:
                    func(task)
            except KeyboardInterrupt:
                if event:
                    event.set()
            except Exception, e:  # pylint: disable=W0703
                self.get_logger().exception(e)
                event.set()
            finally:
                sem.release()

        ret = True
        if jobs > 1:
            threads = set()
            sem = threading.Semaphore(jobs)
            event = threading.Event()

            for task in tasks:
                if event.isSet():
                    break

                sem.acquire()
                thread = threading.Thread(
                    target=_run,
                    args=(task, sem, event, func, args))
                threads.add(thread)
                thread.start()

            for thread in threads:
                thread.join()

            if event.isSet():
                self.get_logger().error('Exited due to errors')
                ret = False
        else:
            for task in tasks:
                ret = func(task, *args) and ret

        return ret


TOPIC_ENTRY = 'SubCommand, SubCommandWithThread'
