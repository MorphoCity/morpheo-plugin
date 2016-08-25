# -*- coding: utf-8 -*-

"""
***************************************************************************
    MorpheoAlgorithm.py
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
import sys

from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from processing.core.GeoAlgorithm import GeoAlgorithm
from processing.core.GeoAlgorithmExecutionException import \
        GeoAlgorithmExecutionException
from processing.core.ProcessingLog import ProcessingLog
from processing.core.parameters import \
        ParameterString, \
        ParameterVector, \
        ParameterNumber, \
        ParameterBoolean, \
        ParameterSelection, \
        ParameterTableField, \
        ParameterFile
from processing.core.outputs import OutputTable
from processing.core.ProcessingConfig import ProcessingConfig
from processing.tools import dataobjects
from processing.tools.system import tempFolder

from math import pi
from ..core.builder.errors import BuilderError
from ..core.builder.graph_builder import SpatialiteBuilder

Builder = SpatialiteBuilder


def log_info(info):
    print "info: ", info
    ProcessingLog.addToLog(ProcessingLog.LOG_INFO, info)


def log_error(error):
    print "error: ", error
    ProcessingLog.addToLog(ProcessingLog.LOG_ERROR, error)


class MorpheoAlgorithm(GeoAlgorithm):

    INPUT_LAYER = 'INPUT_LAYER'
    DIRECTORY = 'DIRECTORY'

    COMPUTE = 'COMPUTE'

    # Options controlling graph
    SNAP_DISTANCE = 'SNAP_DISTANCE'
    MIN_EDGE_LENGTH = 'MIN_EDGE_LENGTH'

    # Options controlling places
    BUFFER = 'BUFFER'
    INPUT_PLACES = 'INPUT_PLACES'

    # Options controlling ways
    WAY_ATTRIBUTE = 'WAY_ATTRIBUTE'
    THRESHOLD = 'THRESHOLD'
    RTOPO = 'RTOPO'
    ATTRIBUTES = 'ATTRIBUTES'
    ORTHOGONALITY = 'ORTHOGONALITY'
    BETWEENNESS = 'BETWEENNESS'
    CLOSENESS = 'CLOSENESS'
    STRESS = 'STRESS'
    CLASSES = 'CLASSES'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:analyse'

    def defineCharacteristics(self):
        self.name = 'Provide graph metric'
        self.group = 'Analysis'

        self.addParameter(ParameterVector(self.INPUT_LAYER, 'Input layer',
                          [ParameterVector.VECTOR_TYPE_LINE]))

        self.addParameter(ParameterFile(self.DIRECTORY, 'Output morpheo project',
                          isFolder=True))

        # Options controlling graph
        self.addParameter(
            ParameterNumber(self.SNAP_DISTANCE, 'Snap distance (no cleanup if zero)', 0., 99., 0.2))
        self.addParameter(
            ParameterNumber(self.MIN_EDGE_LENGTH, 'Min edge length', 0., 99., 4.))

        # Options controlling places
        self.addParameter(
            ParameterNumber(self.BUFFER, 'Place Buffer size', 0., 99.99, 4.))
        self.addParameter(ParameterVector(self.INPUT_PLACES, 'Default input polygons for places',
                          [ParameterVector.VECTOR_TYPE_POLYGON], optional=True))

        # Options controlling ways
        self.addParameter(ParameterTableField(self.WAY_ATTRIBUTE,
            'Attribute for building street ways', self.INPUT_LAYER, ParameterTableField.DATA_TYPE_STRING, True))
        self.addParameter(
            ParameterNumber(self.THRESHOLD, 'Threshold angle (in degree)', 0., 99.99, 30.))
        self.addParameter(ParameterBoolean(self.RTOPO, 'Compute topological radius', False))
        self.addParameter(ParameterBoolean(self.ATTRIBUTES, 'Compute attributes', False))
        self.addParameter(ParameterBoolean(self.ORTHOGONALITY, 'Compute orthogonality (require attributes)', False))
        self.addParameter(ParameterBoolean(self.BETWEENNESS, 'Compute betweenness centrality (require attributes)', False))
        self.addParameter(ParameterBoolean(self.CLOSENESS, 'Compute closeness centrality (require attributes)', False))
        self.addParameter(ParameterBoolean(self.STRESS, 'Compute stress centrality (require attributes)', False))
        self.addParameter(
            ParameterNumber(self.CLASSES, 'Number of classes', 0, 1999, 10))

        #self.addOutput(OutputTable(self.VERTICES_OUTPUT, 'Vertices output table'))
        #self.addOutput(OutputTable(self.EDGES_OUTPUT, 'Edges output table'))
        #self.addOutput(OutputTable(self.STREET_OUTPUT, 'Streets output table'))
        #self.addOutput(OutputTable(self.WAY_OUTPUT, 'Ways output table'))
        #self.addOutput(OutputTable(self.ANGLE_OUTPUT, 'Angles output table'))

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Build all : graph, places and ways
        """
        os.environ.update(OGR2OGR='ogr2ogr')
        layer = dataobjects.getObjectFromUri(self.getParameterValue(self.INPUT_LAYER))

        output    = self.getParameterValue(self.DIRECTORY) or os.join(tempFolder(), 'morpheo_'+layer.name().replace(" ", "_"))
        dbname    = output

        compute = self.getParameterValue(self.COMPUTE)

        builder = Builder.from_layer( layer, dbname )

        # Compute graph
        builder.build_graph(self.getParameterValue(self.SNAP_DISTANCE),
                            self.getParameterValue(self.MIN_EDGE_LENGTH),
                            self.getParameterValue(self.WAY_ATTRIBUTE),
                            output=output)
        # Compute places
        builder.build_places(buffer_size=self.getParameterValue(self.BUFFER),
                             places=self.getParameterValue(self.INPUT_PLACES),
                             output=output)

        # Compute ways
        kwargs = dict(classes=self.getParameterValue(self.CLASSES), rtopo=self.getParameterValue(self.RTOPO))
        if self.getParameterValue(self.ATTRIBUTES):
            kwargs.update(attributes=True,
                          orthogonality = self.getParameterValue(self.ORTHOGONALITY),
                          betweenness   = self.getParameterValue(self.BETWEENNESS),
                          closeness     = self.getParameterValue(self.CLOSENESS),
                          stress        = self.getParameterValue(self.STRESS))

        if self.getParameterValue(self.WAY_ATTRIBUTE) is not None:
            builder.build_ways_from_attribute(output=args.output, **kwargs)
        else:
            builder.build_ways(threshold=self.getParameterValue(self.THRESHOLD)/180.0 * pi,
                           output=output, **kwargs)

        #'place_edges','places' et ways

    def write_output_table(self, output_param, table, cursor):
        cursor.execute("pragma table_info("+table+")")
        fields = [name for [cid,name,typ,notnull,dflt_value,pk] in cursor.fetchall()
                if name != 'GEOMETRY']
        table_writer = self.getOutputFromName(output_param).getTableWriter(fields)
        cursor.execute("SELECT "+','.join(fields)+" FROM "+table)
        table_writer.addRecords(cursor.fetchall())

    def add_vector_layer(self, layer_name, dbname):
            uri = QgsDataSourceURI()
            uri.setDatabase(dbname)
            uri.setDataSource('', Terminology.tr(layer_name), 'GEOMETRY')
            vlayer = QgsVectorLayer(uri.uri(), Terminology.tr(layer_name), 'spatialite')
            QgsMapLayerRegistry.instance().addMapLayer(vlayer)


