# -*- coding: utf-8 -*-

import sys
import logging

# Lies between warning and error
PROGRESS = 21 # Progress log level

class ConsoleProgressHandler(logging.StreamHandler):
    def __init__(self):
        self._in_progress = False
        super(ConsoleProgressHandler, self).__init__()
    def emit(self, record):
        if record.levelno == PROGRESS:
            self._in_progress = True
            msg = self.format(record)
            sys.stdout.write("\r\x1b[K%s" % msg)
            sys.stdout.flush()
        else:
            if self._in_progress:
                sys.stdout.write('\n')
                self._in_progress = False
            super(ConsoleProgressHandler,self).emit(record)


def setup_log_handler(log_level, formatstr='%(levelname)s\t%(message)s', logger=None):
    """ Initialize log handler with the given log level
    """
    logging.addLevelName(PROGRESS,"PROGRESS")

    logger = logging.getLogger(logger)
    logger.setLevel(getattr(logging, log_level.upper()))
    if not logger.handlers:
        channel = ConsoleProgressHandler()
        channel.setFormatter(logging.Formatter(formatstr))
        logger.addHandler(channel)


def log_progress( value, max_value=100, lastv=None, logger=None ):
    """ Log PROGRESS value
    """
    progress = int(100*float(min(value,max_value))/max_value)
    if lastv != progress:
        logger = logger or logging
        logger.log(PROGRESS, "[%-20s] %d %%" % ("=" * int(progress/5.0),progress), extra={'progress': progress})
    return progress


class Progress(object):
    def __init__(self, total):
        self._total = total
        self._count = 0
        self._progr = -1
    
    def __call__(self, inc=1):
        self._count = self._count+inc
        self._progr = log_progress(self._count, self._total, lastv=self._progr)


