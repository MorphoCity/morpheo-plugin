# -*- coding: utf-8 -*-

"""
***************************************************************************
    MorpheoAlgorithmProvider.py
    ---------------------
    Date                 : February 2015
    Copyright            : (C) 2015 Oslandia
    Email                : vincent dot mora at oslandia dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = 'Vincent Mora'
__date__ = 'February 2015'
__copyright__ = '(C) 2015, Oslandia'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import time
from PyQt4.QtGui import *
from processing.core.AlgorithmProvider import AlgorithmProvider
from processing.core.ProcessingConfig import ProcessingConfig, Setting
from processing.core.ProcessingLog import ProcessingLog
from MorpheoAlgorithm import MorpheoAlgorithm

class MorpheoAlgorithmProvider(AlgorithmProvider):

    def __init__(self):
        AlgorithmProvider.__init__(self)
        self.activate = True

    def getDescription(self):
        return 'Morpheo (Graph metrics)'

    def getName(self):
        return 'morpheo'

    def getIcon(self):
        return QIcon(os.path.dirname(__file__) + '/morpheo.png')

    def initializeSettings(self):
        AlgorithmProvider.initializeSettings(self)
        #ProcessingConfig.addSetting(Setting(self.getDescription(),
        #                            'Morpheo_CLI',
        #                            'Morpheo command line tool',
        #                             ''))

    def unload(self):
        AlgorithmProvider.unload(self)
        #ProcessingConfig.removeSetting('Morpheo_CLI')

    def _loadAlgorithms(self):
        try:
            self.algs.append(MorpheoAlgorithm())
        except Exception, e:
            print "error: unable to load morpheo algo because ", e
            ProcessingLog.addToLog(ProcessingLog.LOG_ERROR, 
                'Could not create Morpheo algorithm')
            raise e

