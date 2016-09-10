
import os
import subprocess

from logger import Logger


class SubCommandNotDetectedError(Exception):
    """Indicate the sub-command of a command cannot be found."""


class Command(object):  # pylint: disable=R0902
    """Executes a local executable command."""
    def __init__(self, cwd=None, provide_stdin=False, capture_stdout=False,
                 capture_stderr=True, tryrun=False, *args, **kws):
        self.cwd = cwd
        self.stdout = ''
        self.stderr = ''

        self.args = args or list()
        self.kws = kws or dict()

        self.tryrun = tryrun
        self.provide_stdin = provide_stdin
        self.capture_stdout = capture_stdout
        self.capture_stderr = capture_stderr

    def __call__(self, *args, **kws):
        if len(args) > 0:
            command = Command.normalize(args[0])
            if not hasattr(self, command):
                return getattr(self, command, *args[1:], **kws)
            else:
                raise SubCommandNotDetectedError('%s cannot found' % command)

        return None

    def add_args(self, args, before=None, after=None, condition=True):
        if args:
            def _append_args(arg):
                if arg:
                    if isinstance(arg, (list, tuple)):
                        self.args.extend(arg)
                    else:
                        self.args.append(arg)

        if condition and args:
            _append_args(before)
            _append_args(args)
            _append_args(after)

    def new_args(self, *args):
        self.args = list()
        for arg in args:
            self.add_args(arg)

    def get_args(self):
        return self.args[:]

    def wait(self, **kws):
        if kws:
            self.kws = kws

        cli = list()
        cli.extend([str(a) for a in self.args])

        cwd = kws.get('cwd', self.cwd or os.getcwd())
        tryrun = kws.get('tryrun', self.tryrun)
        # the config for the std device may be duplicated
        provide_stdin = kws.get('provide_stdin', self.provide_stdin)
        capture_stdout = kws.get('capture_stdout', self.capture_stdout)
        capture_stderr = kws.get('capture_stderr', self.capture_stderr)

        logger = Logger.get_logger()
        dbg = '(%s) ' % cwd
        dbg += '[-] ' if tryrun else ''
        if provide_stdin:
            dbg += '0<| '
        if capture_stdout:
            dbg += '1>| '
        if capture_stderr:
            dbg += '2>| '

        logger.info('%s%s', dbg, ' '.join(cli))

        # invoke 'true' instead if tryrun set
        if tryrun:
            cli = ['true']

        proc = subprocess.Popen(
            cli, cwd=cwd,
            env=os.environ,
            stdin=subprocess.PIPE if provide_stdin else None,
            stdout=subprocess.PIPE if capture_stdout else None,
            stderr=subprocess.PIPE if capture_stderr else None)

        self.stdout, self.stderr = proc.communicate()
        if self.stderr:
            if proc.returncode:
                logger.error('exec: %s', self.get_error())
            else:
                logger.info('stderr: %s', self.get_error())

        return proc.returncode

    @staticmethod
    def normalize(command):
        return command.replace('-', '_')

    def get_output(self):
        return self.stdout and self.stdout.strip()

    def get_out_lines(self):
        return (self.get_output or '').split('\n')

    def get_error(self):
        return self.stderr and self.stderr.strip()


TOPIC_ENTRY = "Command, SubCommandNotDetectedError"