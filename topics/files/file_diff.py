
import filecmp
import os
import shutil

from file_pattern import FilePattern, GitFilePattern, SccsFilePattern
from file_utils import FileUtils


class FileDiff(object):
    """Supports to handle the difference between two directories."""

    def __init__(self, source, dest, pattern=None,
                 prefix=None, enable_sccs_pattern=False):
        if prefix:
            source = '%s/%s' % (self._normalize(source), prefix)

        self.src = self._normalize(source)
        if not os.path.exists(self.src):
            os.makedirs(self.src)

        self.dest = self._normalize(dest)

        self._timestamp = 0
        if isinstance(pattern, FilePattern):
            self.pattern = pattern
        else:
            self.pattern = FilePattern(pattern)

        if enable_sccs_pattern:
            self.sccsp = SccsFilePattern()
            self.pattern += self.sccsp
        else:
            self.sccsp = GitFilePattern()

    @staticmethod
    def _normalize(path):
        return path and path.rstrip('/')

    @staticmethod
    def _equal_link(old, new):
        if os.path.islink(old) and os.path.islink(new):
            return os.readlink(old) == os.readlink(new)

        return False

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value):  # pylint: disable=W0613
        raise IOError('set cannot be set')

    def diff(self, ignore_dir=False):  # pylint: disable=R0911
        slen = len(self.src) + 1
        dlen = len(self.dest) + 1

        for root, dirs, files in os.walk(self.src):
            for name in files:
                oldf = os.path.join(root, name)
                if self.pattern.match(oldf[slen:]):
                    continue

                newf = oldf.replace(self.src, self.dest)
                if not os.path.lexists(newf):
                    return True

            if not ignore_dir:
                for dname in dirs:
                    oldd = os.path.join(root, dname)
                    if self.pattern.match_dir(oldd[slen:]):
                        continue

                    newd = oldd.replace(self.src, self.dest)
                    if not os.path.lexists(newd):
                        return True

        for root, dirs, files in os.walk(self.dest):
            if not ignore_dir:
                for dname in dirs:
                    newd = os.path.join(root, dname)
                    if self.pattern.match(newd[dlen:]):
                        continue

                    oldd = newd.replace(self.dest, self.src)
                    if not os.path.lexists(oldd):
                        return True

            for name in files:
                newf = os.path.join(root, name)
                oldf = newf.replace(self.dest, self.src)
                if not os.path.lexists(oldf) or not os.path.lexists(newf):
                    return True
                else:
                    if os.path.islink(newf) or os.path.islink(oldf):
                        return not self._equal_link(oldf, newf)
                    elif not filecmp.cmp(newf, oldf):
                        return True

        return False

    def sync(self, gitcmd=None, logger=None):  # pylint: disable=R0915
        changes = 0

        def info(msg):
            if logger:
                logger.info(msg)

        slen = len(self.src) + 1
        dlen = len(self.dest) + 1
        # remove files
        for root, dirs, files in os.walk(self.src):
            for name in files:
                oldf = os.path.join(root, name)
                if self.sccsp.match(oldf[slen:]):
                    continue
                elif self.pattern.match(oldf[slen:]):
                    info('filter out %s' % oldf)
                    continue

                newf = oldf.replace(self.src, self.dest)
                if not os.path.lexists(newf):
                    info('remove file %s' % oldf)
                    changes += 1
                    if gitcmd:
                        gitcmd.rm(oldf)
                    else:
                        os.unlink(oldf)

            for dname in dirs:
                oldd = os.path.join(root, dname)
                if self.sccsp.match_dir(oldd[slen:]):
                    continue
                elif self.pattern.match_dir(oldd[slen:]):
                    info('filter out %s' % oldd)
                    continue

                newd = oldd.replace(self.src, self.dest)
                if not os.path.lexists(newd):
                    info('remove directory %s' % oldd)
                    changes += 1
                    if gitcmd:
                        gitcmd.rm('-r', oldd)
                    else:
                        shutil.rmtree(oldd)

        for root, dirs, files in os.walk(self.dest):
            for dname in dirs:
                newd = os.path.join(root, dname)
                oldd = newd.replace(self.dest, self.src)
                if self.pattern.match(newd[dlen:]):
                    info('filter out %s' % oldd)
                elif not os.path.lexists(os.path.dirname(oldd)):
                    info('ignored %s without dir' % oldd)
                elif not os.path.lexists(oldd):
                    info('makedir %s' % oldd)
                    os.makedirs(oldd)
                elif not os.path.isdir(oldd):
                    info('type changed %s' % oldd)
                    os.unlink(oldd)
                    os.makedirs(oldd)
                else:
                    info('no change %s' % oldd)

            for name in files:
                newf = os.path.join(root, name)
                timest = os.lstat(newf)
                if timest.st_mtime > self._timestamp:
                    self._timestamp = timest.st_mtime

                oldf = newf.replace(self.dest, self.src)
                if self.pattern.match(newf[dlen:]):
                    info('filter out %s' % oldf)
                elif not os.path.lexists(os.path.dirname(oldf)):
                    info('ignored %s without dir' % oldf)
                elif os.path.islink(newf):
                    if not self._equal_link(oldf, newf):
                        info('copy the link file %s' % oldf)
                        FileUtils.copy_file(newf, oldf)
                        if gitcmd:
                            gitcmd.add(oldf)
                        changes += 1
                elif not os.path.lexists(oldf):
                    info('p: add file %s' % newf)
                    dirn = os.path.dirname(oldf)
                    if not os.path.lexists(dirn):
                        os.makedirs(dirn)

                    FileUtils.copy_file(newf, oldf)
                    if gitcmd:
                        gitcmd.add(oldf)
                    changes += 1
                else:
                    if os.path.islink(oldf):
                        info('link file %s' % newf)
                        FileUtils.copy_file(newf, oldf)
                        if gitcmd:
                            gitcmd.add(oldf)
                        changes += 1
                    elif not filecmp.cmp(newf, oldf):
                        info('change file %s' % newf)
                        FileUtils.copy_file(newf, oldf)
                        if gitcmd:
                            gitcmd.add(oldf)
                        changes += 1
                    else:
                        info('no change %s' % newf)

        return changes

TOPIC_ENTRY = 'FileDiff'
