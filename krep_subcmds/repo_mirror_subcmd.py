
import os

from repo_subcmd import RepoSubcmd
from topics import GitProject, Pattern


class RepoMirrorSubcmd(RepoSubcmd):
    COMMAND = 'repo-mirror'

    help_summary = 'Download and import git-repo mirror project'
    help_usage = """\
%prog [options] ...

Download the mirror project managed with git-repo and import to the local
server.

The project need be controlled by git-repo and should be a mirrored project,
(created with the command line "repo init ... --mirror") whose architecture
guarantees the managed sub-projects importing to the local server.

All projects inside .repo/default.xml will be managed and imported. Exactly,
the manifest git will be detected and converted to the actual location to
import either. (For example, the android manifest git in .repo/manifests is
acutally in platform/manifest.git within a mirror.)
"""

    def options(self, optparse):
        RepoSubcmd.options(self, optparse)
        optparse.suppress_opt('--mirror', True)

    def fetch_projects_in_manifest(self, options):
        manifest = self.get_manifest(options)

        projects = list()
        logger = self.get_logger()  # pylint: disable=E1101
        pattern = Pattern(options.pattern)

        for node in manifest.get_projects():
            path = os.path.join(
                self.get_absolute_working_dir(options),  # pylint: disable=E1101
                '%s.git' % node.name)
            if not os.path.exists(path):
                logger.warning('%s not existed, ignored', path)
                continue
            elif not pattern.match('p,project', node.name):
                logger.debug('%s ignored by the pattern', node.name)
                continue

            name = '%s%s' % (
                options.prefix or '',
                pattern.replace('p,project', node.name, name=node.name))
            projects.append(
                GitProject(
                    name,
                    worktree=path,
                    gitdir=path,
                    revision=node.revision,
                    remote='%s/%s' % (options.remote, name),
                    bare=True,
                    pattern=pattern,
                    source=node.name,
                    copyfiles=node.copyfiles,
                    linkfiles=node.linkfiles))

        return projects
