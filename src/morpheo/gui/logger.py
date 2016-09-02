# -*- coding: utf-8 -*-

import logging
from logging import DEBUG, INFO, WARN, ERROR, CRITICAL 

from ..core.logger import PROGRESS, log_progress

class _Handler(logging.Handler):
    """ Wrapper for custom handling of log
        message
    """
    def __init__(self, level=logging.NOTSET, formatstr='%(message)s',
                 on_info=None, 
                 on_warn=None,
                 on_error=None,
                 on_critical=None,
                 on_progress=None):

        self._handlers = {
            INFO    : on_info,
            WARN    : on_warn,
            ERROR   : on_error,
            CRITICAL: on_critical,
            PROGRESS: on_progress
        }

        self.lastmsg = None

        super(_Handler, self).__init__(level)
        if formatstr is not None:
            self.setFormatter(logging.Formatter(formatstr))

    def emit(self, record):
        """ Publish log message
        """
        level   = record.levelno
        handler = self._handlers.get(level)
        if handler is None:
            return

        if level == PROGRESS:
            handler(record.__dict__['progress'],self.lastmsg)
        else:
            self.lastmsg = self.format(record)
            handler(self.lastmsg)

    def createlock(self):
        pass

    def acquire(self):
        pass

    def release(self):
        pass

    def flush(self):
        pass

    def close(self):
        pass


def init_log_custom_hooks( level=logging.INFO,
                           on_info=None, 
                           on_warn=None,
                           on_error=None,
                           on_critical=None,
                           on_progress=None):
    """ Setup custom log handlers

        Each hook is a function that takes a message
        except for the progress handler that takes
        a message and an integer value indicating the progress.
    """
    handler = _Handler(on_info=on_info,
                       on_warn=on_warn,
                       on_error=on_error,
                       on_critical=on_critical,
                       on_progress=on_progress)

    logging.addLevelName(PROGRESS,"PROGRESS")
    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(handler)

