# -*- coding: utf-8 -*-

import logging

# Lies between warning and error
PROGRESS = 21 # Progress log level

def setup_log_handler(log_level, formatstr='%(levelname)s\t%(message)s', logger=None):
    """ Initialize log handler with the given log level
    """
    logging.addLevelName(PROGRESS,"PROGRESS")

    logger = logging.getLogger(logger)
    logger.setLevel(getattr(logging, log_level.upper()))
    if not logger.handlers:
        channel = logging.StreamHandler()
        channel.setFormatter(logging.Formatter(formatstr))
        logger.addHandler(channel)


def log_progress( value, max_value=100, lastv=None, logger=None ):
    """ Log PROGRESS value
    """
    progress = int(100*float(min(value,max_value))/max_value)
    if lastv != progress:
        logger = logger or logging
        logger.log(PROGRESS, msg="{}%".format(progress), extra={'progress': progress})
    return progress


class Progress(object):
    def __init__(self, total):
        self._total = total
        self._count = 0
        self._progr = -1
    
    def __call__(self, inc=1):
        self._count = self._count+inc
        self._progr = log_progress(self._count, self._total, lastv=self._progr)


