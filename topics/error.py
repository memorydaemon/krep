
class KrepError(Exception):
    """Root exception for krep"""


class DownloadError(KrepError):
    """Indicate the unsuccessful download."""


class OptionMissedError(KrepError):
    """Indicate the missed option."""


class ProcessingError(KrepError):
    """Indicate the unsuccessful processing."""


class RaiseExceptionIfOptionMissed(object):
    """Raise OptionMissedError if the option or options are missed."""
    def __init__(self, option, prompt):
        if not option:
            raise OptionMissedError(prompt)


TOPIC_ENTRY = 'KrepError, DownloadError, OptionMissedError, ' \
              'ProcessingError, RaiseExceptionIfOptionMissed'
