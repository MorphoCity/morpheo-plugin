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



