# -*- coding: utf-8 -*-

"""
***************************************************************************
    MorpheoAlgorithmProvider.py
    ---------------------
    Date                 : August 2016
    Copyright            : (C) 2016 3Liz
    Email                : rldhont at 3liz dot com
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = 'René-Luc DHONT'
__date__ = 'August 2016'
__copyright__ = '(C) 2016, 3Liz'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import time
from PyQt4.QtGui import *
from processing.core.AlgorithmProvider import AlgorithmProvider
from processing.core.ProcessingConfig import ProcessingConfig, Setting
from processing.core.ProcessingLog import ProcessingLog
from MorpheoAlgorithm import \
        MorpheoBuildAlgorithm, \
        MorpheoWayAttributesAlgorithm, \
        MorpheoEdgeAttributesAlgorithm, \
        MorpheoEdgesGraphAlgorithm, \
        MorpheoWaysGraphAlgorithm, \
        MorpheoStructuralDiffAlgorithm, \
        MorpheoHorizonAlgorithm

class MorpheoAlgorithmProvider(AlgorithmProvider):

    def __init__(self):
        AlgorithmProvider.__init__(self)
        self.activate = True

    def getDescription(self):
        return 'Morpheo (Graph metrics)'

    def getName(self):
        return 'morpheo'

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), '..', 'morpheo.png'))

    def initializeSettings(self):
        AlgorithmProvider.initializeSettings(self)

    def unload(self):
        AlgorithmProvider.unload(self)

    def _loadAlgorithms(self):
        try:
            self.algs.append(MorpheoBuildAlgorithm())
            self.algs.append(MorpheoWayAttributesAlgorithm())
            self.algs.append(MorpheoEdgeAttributesAlgorithm())
            self.algs.append(MorpheoEdgesGraphAlgorithm())
            self.algs.append(MorpheoWaysGraphAlgorithm())
            self.algs.append(MorpheoStructuralDiffAlgorithm())
            self.algs.append(MorpheoHorizonAlgorithm())
        except Exception, e:
            print "error: unable to load morpheo algo because ", e
            ProcessingLog.addToLog(ProcessingLog.LOG_ERROR,
                'Could not create Morpheo algorithm')
            raise e

