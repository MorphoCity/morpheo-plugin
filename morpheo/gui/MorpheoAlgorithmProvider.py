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
__copyright__ = '(C) 2016-2018, 3Liz'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import traceback
import logging
import os
import time
from qgis.core import QgsProcessingProvider
from .MorpheoAlgorithm import (MorpheoBuildAlgorithm,
                               MorpheoWayAttributesAlgorithm,
                               MorpheoEdgeAttributesAlgorithm,
                               MorpheoEdgesGraphAlgorithm,
                               MorpheoWaysGraphAlgorithm,
                               MorpheoStructuralDiffAlgorithm,
                               MorpheoMeshAlgorithm,
                               MorpheoHorizonAlgorithm)

from qgis.PyQt.QtGui import QIcon


class MorpheoAlgorithmProvider(QgsProcessingProvider):

    def __init__(self):
        super().__init__()

    def getAlgs(self):
        algs = [
            MorpheoBuildAlgorithm(),
            MorpheoWayAttributesAlgorithm(),
            MorpheoEdgeAttributesAlgorithm(),
            MorpheoEdgesGraphAlgorithm(),
            MorpheoWaysGraphAlgorithm(),
            MorpheoStructuralDiffAlgorithm(),
            MorpheoMeshAlgorithm(),
            MorpheoHorizonAlgorithm()
        ]
        return algs

    def name(self):
        return 'Morpheo (Graph metrics)'

    def longNname(self):
        return 'Morpheo - Compute Graph metrics from spatial data'

    def id(self):
        return 'morpheo'

    def icon(self):
        return QIcon(':/plugins/Morpheo/morpheo.png')

    def loadAlgorithms(self):
        self.algs = self.getAlgs()
        for a in self.algs:
            self.addAlgorithm(a)

