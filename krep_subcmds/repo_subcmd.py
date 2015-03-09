
import os
import urlparse

from topics import Command, FileUtils, GitProject, Gerrit, Manifest, \
    SubCommandWithThread, DownloadError, RaiseExceptionIfOptionMissed


class RepoCommand(Command):
    """Executes a repo sub-command with specified parameters"""
    def __init__(self, *args, **kws):
        Command.__init__(self, *args, **kws)
        self.repo = FileUtils.find_execute('repo')

    def _execute(self, *args, **kws):
        cli = list()
        cli.append(self.repo)

        if len(args):
            cli.extend(args)

        self.new_args(cli, self.get_args())  # pylint: disable=E1101
        return self.wait(**kws)  # pylint: disable=E1101

    def init(self, *args, **kws):
        return self._execute('init', *args, **kws)

    def sync(self, *args, **kws):
        return self._execute('sync', *args, **kws)


class RepoSubcmd(SubCommandWithThread):
    REMOTE = 'refs/remotes/'
    COMMAND = 'repo'

    help_summary = 'Download and import git-repo manifest project'
    help_usage = """\
%prog [options] ...

Download the project managed with git-repo and import to the remote server.

The project need be controlled by git-repo (created with the command
"repo init" with the "--mirror" option, whose architecture guarantees the
managed sub-projects importing to the local server.

Not like the sub-command "repo-mirror", the manifest git would be handled with
this command.
"""

    def options(self, optparse):
        SubCommandWithThread.options(self, optparse, modules=globals())

        options = optparse.add_option_group('Repo tool options')
        options.add_option(
            '-u', '--manifest-url',
            dest='manifest', metavar='URL',
            help='Set the git-repo manifest url')
        options.add_option(
            '-b', '--branch', '--manifest-branch',
            dest='manifest_branch', metavar='REVISION',
            help='Set the project branch or revision')
        options.add_option(
            '-m', '--manifest-name',
            dest='manifest_name', metavar='NAME.xml',
            help='initialize the manifest name')
        options.add_option(
            '--mirror',
            dest='mirror', action='store_true', default=False,
            help='Create a replica of the remote repositories')
        options.add_option(
            '--reference',
            dest='reference', metavar='REFERENCE',
            help='Set the local project mirror')
        options.add_option(
            '--repo-url',
            dest='repo_url', metavar='URL',
            help='repo repository location')
        options.add_option(
            '--repo-branch',
            dest='repo_branch', metavar='REVISION',
            help='repo branch or revision')
        options.add_option(
            '--no-repo-verify',
            dest='no_repo_verify', action='store_true',
            help='Do not verify repo source code')

        options = optparse.get_option_group('--remote') or \
            optparse.add_option_group('Remote options')
        options.add_option(
            '--prefix',
            dest='prefix', metavar='PREFIX',
            help='prefix on the remote location.')

    @staticmethod
    def get_manifest(options):
        refsp = None
        if options.manifest:
            ulp = urlparse.urlparse(options.manifest)
            if ulp.path:
                refsp = os.path.dirname(ulp.path).lstrip('/')

        return Manifest(refspath=refsp, mirror=options.mirror)

    def fetch_projects_in_manifest(self, options):
        manifest = self.get_manifest(options)

        projects = list()
        logger = self.get_logger()  # pylint: disable=E1101
        for node in manifest.get_projects():
            if not os.path.exists(node.path):
                logger.warning('%s not existed, ignored' % node.path)
                continue

            name = '%s%s' % (options.prefix or '', node.name)
            projects.append(
                GitProject(
                    name,
                    worktree=os.path.join(options.working_dir, node.path),
                    revision=node.revision,
                    remote='%s/%s' % (options.remote, name)))

        return projects

    def execute(self, options, *args, **kws):
        SubCommandWithThread.execute(self, options, *args, **kws)

        if options.prefix and not options.endswith('/'):
            options.prefix += '/'

        if not options.offsite:
            RaiseExceptionIfOptionMissed(
                options.manifest, 'manifest (--manifest) is not set')

            repo = RepoCommand()
            # pylint: disable=E1101
            repo.add_args(options.manifest, before='-u')
            repo.add_args(options.manifest_branch, before='-b')
            repo.add_args(options.manifest_name, before='-m')
            repo.add_args('--mirror', condition=options.mirror)
            repo.add_args(options.reference, before='--reference')
            repo.add_args(options.repo_url, before='--repo-url')
            repo.add_args(options.repo_branch, before='--repo-branch')
            # pylint: enable=E1101

            res = 0
            if not os.path.exists('.repo'):
                res = repo.init(**kws)

            if res:
                raise DownloadError(
                    'Failed to init "%s"' % options.manifest)
            else:
                repo = RepoCommand()
                repo.add_args(options.job,  # pylint: disable=E1101
                              before='-j')
                res = repo.sync(**kws)
                if res:
                    raise DownloadError(
                        'Failed to sync "%s' % options.manifest)

        def _run(project):
            project_name = str(project)
            logger = self.get_logger(  # pylint: disable=E1101
                name=project_name)

            logger.info('Start processing ...')
            if not options.tryrun and options.gerrit:
                gerrit = Gerrit(options.gerrit)
                gerrit.createProject(project.name)

            res = 0
            # push the branches
            if not res and self.override_value(  # pylint: disable=E1101
                    options.branches, options.all):
                res = project.push_heads(
                    project.revision,
                    options.refs,
                    all_heads=options.all,
                    fullname=options.keep_name,
                    force=options.force,
                    tryrun=options.tryrun)
                if res != 0:
                    logger.error('failed to push heads')

            # push the tags
            if not res and self.override_value(  # pylint: disable=E1101
                    options.tags, options.all):
                res = project.push_tags(
                    None, options.refs,
                    fullname=options.keep_name,
                    force=options.force,
                    tryrun=options.tryrun)
                if res != 0:
                    logger.error('failed to push tags')

        # handle the schema of the remote
        ulp = urlparse.urlparse(options.remote)
        if not ulp.scheme:
            options.remote = 'git://%s' % options.remote

        projects = self.fetch_projects_in_manifest(options)
        return self.run_with_thread(  # pylint: disable=E1101
            options.job, projects, _run)