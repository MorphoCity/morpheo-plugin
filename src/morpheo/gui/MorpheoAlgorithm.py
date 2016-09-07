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
from PyQt4.QtXml import QDomDocument

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
from processing.core.outputs import OutputString, OutputFile
from processing.core.ProcessingConfig import ProcessingConfig
from processing.tools import dataobjects
from processing.tools.system import tempFolder

from math import pi
from ..core.errors import BuilderError
from ..core.graph_builder import SpatialiteBuilder
from ..core.structdiff import structural_diff
from ..core import horizon as hrz
from ..core.ways import read_ways_graph
from ..core.sql  import connect_database
from ..core.layers  import export_shapefile
from ..core import mesh

Builder = SpatialiteBuilder


def log_info(info):
    print "info: ", info
    ProcessingLog.addToLog(ProcessingLog.LOG_INFO, info)


def log_error(error):
    print "error: ", error
    ProcessingLog.addToLog(ProcessingLog.LOG_ERROR, error)

def add_vector_layer(dbname, table_name, layer_name):
        # Build URI
        uri = QgsDataSourceURI()
        uri.setDatabase(dbname)
        uri.setDataSource('', table_name, 'GEOMETRY')
        # Find already loaded layer
        layersByName = QgsMapLayerRegistry.instance().mapLayersByName(layer_name)
        if layersByName:
            vlayer = layersByName[0]
            XMLDocument = QDomDocument("style")
            XMLMapLayers = XMLDocument.createElement("maplayers")
            XMLMapLayer = XMLDocument.createElement("maplayer")
            vlayer.writeLayerXML(XMLMapLayer,XMLDocument)
            XMLMapLayer.firstChildElement("datasource").firstChild().setNodeValue(uri.uri())
            XMLMapLayers.appendChild(XMLMapLayer)
            XMLDocument.appendChild(XMLMapLayers)
            vlayer.readLayerXML(XMLMapLayer)
            vlayer.reload()
        else:
            vlayer = QgsVectorLayer(uri.uri(), layer_name, 'spatialite')
            QgsMapLayerRegistry.instance().addMapLayer(vlayer)


class MorpheoBuildAlgorithm(GeoAlgorithm):

    INPUT_LAYER = 'INPUT_LAYER'
    DIRECTORY = 'DIRECTORY'
    DBNAME = 'DBNAME'

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

    # Ouput
    OUTPUT_DBPATH = 'OUTPUT_DBPATH'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo build algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:build'

    def defineCharacteristics(self):
        self.name = 'Build all : graph, places and ways'
        self.group = 'Build'

        self.addParameter(ParameterVector(self.INPUT_LAYER, 'Input layer',
                          [ParameterVector.VECTOR_TYPE_LINE]))

        self.addParameter(ParameterFile(self.DIRECTORY, 'Output directory to store database and data',
                          isFolder=True))

        self.addParameter(ParameterString(self.DBNAME, 'Database and data directory name',
                          optional=True))

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
            ParameterNumber(self.CLASSES, 'Number of classes', 2, 99, 10))

        outputDBPath = OutputString(self.OUTPUT_DBPATH, 'Database path')
        outputDBPath.hidden = True
        self.addOutput(outputDBPath)

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Build all : graph, places and ways
        """
        layer = dataobjects.getObjectFromUri(self.getParameterValue(self.INPUT_LAYER))

        output    = self.getParameterValue(self.DIRECTORY) or tempFolder()
        dbname    = self.getParameterValue(self.DBNAME) or 'morpheo_'+layer.name().replace(" ", "_")

        if not os.path.exists(os.path.join(output, dbname)):
            os.mkdir(os.path.join(output, dbname))

        builder = Builder.from_layer( layer, os.path.join(output, dbname) )

        # Compute graph
        builder.build_graph(self.getParameterValue(self.SNAP_DISTANCE),
                            self.getParameterValue(self.MIN_EDGE_LENGTH),
                            self.getParameterValue(self.WAY_ATTRIBUTE),
                            output=os.path.join(output, dbname))
        # Compute places
        builder.build_places(buffer_size=self.getParameterValue(self.BUFFER),
                             places=self.getParameterValue(self.INPUT_PLACES),
                             output=os.path.join(output, dbname))

        # Compute ways
        kwargs = dict(classes=self.getParameterValue(self.CLASSES), rtopo=self.getParameterValue(self.RTOPO))
        if self.getParameterValue(self.ATTRIBUTES):
            kwargs.update(attributes=True,
                          orthogonality = self.getParameterValue(self.ORTHOGONALITY),
                          betweenness   = self.getParameterValue(self.BETWEENNESS),
                          closeness     = self.getParameterValue(self.CLOSENESS),
                          stress        = self.getParameterValue(self.STRESS))

        if self.getParameterValue(self.WAY_ATTRIBUTE) is not None:
            builder.build_ways_from_attribute(output=os.path.join(output, dbname), **kwargs)
        else:
            builder.build_ways(threshold=self.getParameterValue(self.THRESHOLD)/180.0 * pi,
                           output=os.path.join(output, dbname), **kwargs)

        # Visualize data
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'places', "%s_%s" % ('places',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'place_edges', "%s_%s" % ('place_edges',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'ways', "%s_%s" % ('ways',dbname))

        self.setOutputValue(self.OUTPUT_DBPATH, os.path.join(output, dbname)+'.sqlite')

    def write_output_table(self, output_param, table, cursor):
        cursor.execute("pragma table_info("+table+")")
        fields = [name for [cid,name,typ,notnull,dflt_value,pk] in cursor.fetchall()
                if name != 'GEOMETRY']
        table_writer = self.getOutputFromName(output_param).getTableWriter(fields)
        cursor.execute("SELECT "+','.join(fields)+" FROM "+table)
        table_writer.addRecords(cursor.fetchall())


class MorpheoWayAttributesAlgorithm(GeoAlgorithm):

    DBPATH = 'DBPATH'

    # Options controlling ways
    RTOPO = 'RTOPO'
    ORTHOGONALITY = 'ORTHOGONALITY'
    BETWEENNESS = 'BETWEENNESS'
    CLOSENESS = 'CLOSENESS'
    STRESS = 'STRESS'
    CLASSES = 'CLASSES'

    # Ouput
    OUTPUT_DBPATH = 'OUTPUT_DBPATH'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo way_attributes algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:way_attributes'

    def defineCharacteristics(self):
        self.name = 'Compute attributes on ways'
        self.group = 'Compute'

        self.addParameter(ParameterFile(self.DBPATH, 'Morpheo database path',
                          isFolder=False, optional=False, ext='sqlite'))

        # Options controlling ways
        self.addParameter(ParameterBoolean(self.RTOPO, 'Compute topological radius', False))
        self.addParameter(ParameterBoolean(self.ORTHOGONALITY, 'Compute orthogonality', False))
        self.addParameter(ParameterBoolean(self.BETWEENNESS, 'Compute betweenness centrality', False))
        self.addParameter(ParameterBoolean(self.CLOSENESS, 'Compute closeness centrality', False))
        self.addParameter(ParameterBoolean(self.STRESS, 'Compute stress centrality', False))
        self.addParameter(
            ParameterNumber(self.CLASSES, 'Number of classes', 2, 99, 10))

        outputDBPath = OutputString(self.OUTPUT_DBPATH, 'Database path')
        outputDBPath.hidden = True
        self.addOutput(outputDBPath)

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Compute way attributes
        """
        dbpath    = self.getParameterValue(self.DBPATH)
        if not os.path.isfile( dbpath ):
            log_error('Morpheo database path not found')

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')

        builder = Builder.from_database( os.path.join(output, dbname) )
        builder.compute_way_attributes(
                orthogonality = self.getParameterValue(self.ORTHOGONALITY),
                betweenness   = self.getParameterValue(self.BETWEENNESS),
                closeness     = self.getParameterValue(self.CLOSENESS),
                stress        = self.getParameterValue(self.STRESS),
                rtopo         = self.getParameterValue(self.RTOPO),
                classes       = self.getParameterValue(self.CLASSES),
                output        = os.path.join(output, dbname))

        # Visualize data
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'places', "%s_%s" % ('places',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'place_edges', "%s_%s" % ('place_edges',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'ways', "%s_%s" % ('ways',dbname))

        self.setOutputValue(self.OUTPUT_DBPATH, os.path.join(output, dbname)+'.sqlite')


class MorpheoEdgeAttributesAlgorithm(GeoAlgorithm):

    DBPATH = 'DBPATH'

    # Options controlling edges
    ORTHOGONALITY = 'ORTHOGONALITY'
    BETWEENNESS = 'BETWEENNESS'
    CLOSENESS = 'CLOSENESS'
    STRESS = 'STRESS'
    CLASSES = 'CLASSES'

    # Ouput
    OUTPUT_DBPATH = 'OUTPUT_DBPATH'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo way_attributes algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:edge_attributes'

    def defineCharacteristics(self):
        self.name = 'Compute attributes on edges'
        self.group = 'Compute'

        self.addParameter(ParameterFile(self.DBPATH, 'Morpheo database path',
                          isFolder=False, optional=False, ext='sqlite'))

        # Options controlling ways
        self.addParameter(ParameterBoolean(self.ORTHOGONALITY, 'Compute orthogonality', False))
        self.addParameter(ParameterBoolean(self.BETWEENNESS, 'Compute betweenness centrality', False))
        self.addParameter(ParameterBoolean(self.CLOSENESS, 'Compute closeness centrality', False))
        self.addParameter(ParameterBoolean(self.STRESS, 'Compute stress centrality', False))
        self.addParameter(
            ParameterNumber(self.CLASSES, 'Number of classes', 2, 99, 10))

        outputDBPath = OutputString(self.OUTPUT_DBPATH, 'Database path')
        outputDBPath.hidden = True
        self.addOutput(outputDBPath)

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Compute way attributes
        """
        dbpath    = self.getParameterValue(self.DBPATH)
        if not os.path.isfile( dbpath ):
            log_error('Morpheo database path not found')

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')

        builder = Builder.from_database( os.path.join(output, dbname) )
        builder.compute_edge_attributes( os.path.join(output, dbname),
                orthogonality = self.getParameterValue(self.ORTHOGONALITY),
                betweenness   = self.getParameterValue(self.BETWEENNESS),
                closeness     = self.getParameterValue(self.CLOSENESS),
                stress        = self.getParameterValue(self.STRESS),
                classes       = self.getParameterValue(self.CLASSES),
                output        = os.path.join(output, dbname))

        # Visualize data
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'place_edges', "%s_%s" % ('place_edges',dbname))

        self.setOutputValue(self.OUTPUT_DBPATH, os.path.join(output, dbname)+'.sqlite')


class MorpheoEdgesGraphAlgorithm(GeoAlgorithm):

    DBPATH = 'DBPATH'

    # Ouput
    OUTPUT_DBPATH = 'OUTPUT_DBPATH'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo edges_graph algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:edges_graph'

    def defineCharacteristics(self):
        self.name = 'Build edges graph'
        self.group = 'Build'

        self.addParameter(ParameterFile(self.DBPATH, 'Morpheo database path',
                          isFolder=False, optional=False, ext='sqlite'))

        outputDBPath = OutputString(self.OUTPUT_DBPATH, 'Database path')
        outputDBPath.hidden = True
        self.addOutput(outputDBPath)

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Build edges graph
        """
        dbpath    = self.getParameterValue(self.DBPATH)
        if not os.path.isfile( dbpath ):
            log_error('Morpheo database path not found')

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')

        builder = Builder.from_database( os.path.join(output, dbname) )
        builder.build_edges_graph(os.path.join(output, dbname))

        self.setOutputValue(self.OUTPUT_DBPATH, os.path.join(output, dbname)+'.sqlite')


class MorpheoWaysGraphAlgorithm(GeoAlgorithm):

    DBPATH = 'DBPATH'

    # Ouput
    OUTPUT_DBPATH = 'OUTPUT_DBPATH'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo ways_graph algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:ways_graph'

    def defineCharacteristics(self):
        self.name = 'Build ways graph'
        self.group = 'Build'

        self.addParameter(ParameterFile(self.DBPATH, 'Morpheo database path',
                          isFolder=False, optional=False, ext='sqlite'))

        outputDBPath = OutputString(self.OUTPUT_DBPATH, 'Database path')
        outputDBPath.hidden = True
        self.addOutput(outputDBPath)

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Build edges graph
        """
        dbpath    = self.getParameterValue(self.DBPATH)
        if not os.path.isfile( dbpath ):
            log_error('Morpheo database path not found')

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')

        builder = Builder.from_database( os.path.join(output, dbname) )
        builder.build_ways_graph(os.path.join(output, dbname))

        self.setOutputValue(self.OUTPUT_DBPATH, os.path.join(output, dbname)+'.sqlite')


class MorpheoStructuralDiffAlgorithm(GeoAlgorithm):

    DBPATH1 = 'DBPATH1'
    DBPATH2 = 'DBPATH2'

    DIRECTORY = 'DIRECTORY'
    DBNAME = 'DBNAME'

    TOLERANCE = 'TOLERANCE'

    # Ouput
    OUTPUT_DBPATH = 'OUTPUT_DBPATH'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo structural_diff algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:structural_diff'

    def defineCharacteristics(self):
        self.name = 'Compute structural difference'
        self.group = 'Compute'

        self.addParameter(ParameterFile(self.DBPATH1, 'Initial Morpheo directory',
                          isFolder=False, optional=False, ext='sqlite'))

        self.addParameter(ParameterFile(self.DBPATH2, 'Final Morpheo directory',
                          isFolder=False, optional=False, ext='sqlite'))

        self.addParameter(ParameterFile(self.DIRECTORY, 'Output directory to store database and data',
                          isFolder=True))

        self.addParameter(ParameterString(self.DBNAME, 'Database and data directory name',
                          optional=True))

        self.addParameter(
            ParameterNumber(self.TOLERANCE, 'Tolerance value', 0., 99.99, 1.))

        outputDBPath = OutputString(self.OUTPUT_DBPATH, 'Structural difference database path')
        outputDBPath.hidden = True
        self.addOutput(outputDBPath)

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Compute structural difference
        """

        def check_dbpath(path):
            basename = os.path.basename(path)
            shp = os.path.join(path,'place_edges_%s.shp' % basename)
            gpickle = os.path.join(path,'way_graph_%s.gpickle' % basename)
            return os.path.isfile(shp) and os.path.isfile(gpickle)

        dbpath1   = self.getParameterValue(self.DBPATH1)
        dirname1  = os.path.dirname(dbpath1)
        dbname1   = os.path.basename(dbpath1).replace('.sqlite','')
        if not check_dbpath(os.path.join(dirname1, dbname1)):
            log_error('Initial Morpheo directory is incomplete')

        dbpath2    = self.getParameterValue(self.DBPATH2)
        dirname2  = os.path.dirname(dbpath2)
        dbname2   = os.path.basename(dbpath2).replace('.sqlite','')
        if not check_dbpath(os.path.join(dirname2, dbname2)):
            log_error('Final Morpheo directory is incomplete')

        output    = self.getParameterValue(self.DIRECTORY) or tempFolder()
        dbname    = self.getParameterValue(self.DBNAME) or 'morpheo_%s_%s' % (dbname1, dbname2)

        structural_diff( os.path.join(dirname1, dbname1), os.path.join(dirname2, dbname2),
                         output=os.path.join(output, dbname),
                         buffersize=self.getParameterValue(self.TOLERANCE))

        # Visualize data
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'paired_edges', "%s_%s" % ('paired_edges',dbname))

        self.setOutputValue(self.OUTPUT_DBPATH, os.path.join(output, dbname)+'.sqlite')


class MorpheoMeshAlgorithm(GeoAlgorithm):

    DBPATH = 'DBPATH'
    WAY_LAYER = 'WAY_LAYER'
    WAY_ATTRIBUTE = 'WAY_ATTRIBUTE'
    PERCENTILE = 'PERCENTILE'
    USE_WAY = 'USE_WAY'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo mesh algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:mesh'

    def defineCharacteristics(self):
        self.name = 'Compute mesh'
        self.group = 'Compute'

        self.addParameter(ParameterFile(self.DBPATH, 'Morpheo database path',
                          isFolder=False, optional=False, ext='sqlite'))

        self.addParameter(ParameterVector(self.WAY_LAYER, 'Ways layer',
                          [ParameterVector.VECTOR_TYPE_LINE]))

        self.addParameter(ParameterTableField(self.WAY_ATTRIBUTE,
            'Attribute for mesh structure', self.WAY_LAYER, ParameterTableField.DATA_TYPE_NUMBER, True))

        self.addParameter(
            ParameterNumber(self.PERCENTILE, 'The percentile for computing the mesh structure', 1, 99, 5))

        self.addParameter(ParameterBoolean(self.USE_WAY, 'Use ways for computing mesh components', False))

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Compute mesh
        """
        dbpath    = self.getParameterValue(self.DBPATH)
        if not os.path.isfile( dbpath ):
            log_error('Morpheo database path not found')

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')

        attribute = self.getParameterValue(self.WAY_ATTRIBUTE)
        percentile = self.getParameterValue(self.PERCENTILE)

        use_way = self.getParameterValue(self.USE_WAY)

        conn = connect_database(dbpath)
        name = 'mesh_%s_%s_%s' % (use_way and 'way' or 'edge', attribute, percentile)

        if use_way:
            mesh_fun = mesh.create_indexed_table_from_way_attribute
        else:
            mesh_fun = mesh.create_indexed_table_from_edge_attribute

        mesh_fun(conn, name, attribute, percentile)

        export_shapefile(dbpath, name, os.path.join(output, dbname))

        # Visualize data
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', name, "%s_%s" % (name,dbname))


class MorpheoHorizonAlgorithm(GeoAlgorithm):

    DBPATH = 'DBPATH'
    WAY_LAYER = 'WAY_LAYER'
    WAY_ATTRIBUTE = 'WAY_ATTRIBUTE'
    PERCENTILE = 'PERCENTILE'

    #output param
    PLOT_BINS = 'PLOT_BINS'
    PLOT_COLOR = 'PLOT_COLOR'
    PLOT_WIDTH = 'PLOT_WIDTH'
    PLOT_HEIGHT = 'PLOT_HEIGHT'

    #output
    PLOT = 'PLOT'

    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo horizon algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.join(os.path.dirname(__file__),'..','morpheo.png'))

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:horizon'

    def defineCharacteristics(self):
        self.name = 'Compute horizon'
        self.group = 'Compute'

        self.addParameter(ParameterFile(self.DBPATH, 'Morpheo database path',
                          isFolder=False, optional=False, ext='sqlite'))

        self.addParameter(ParameterVector(self.WAY_LAYER, 'Ways layer',
                          [ParameterVector.VECTOR_TYPE_LINE]))

        self.addParameter(ParameterTableField(self.WAY_ATTRIBUTE,
            'Attribute for building horizon', self.WAY_LAYER, ParameterTableField.DATA_TYPE_NUMBER, True))

        self.addParameter(
            ParameterNumber(self.PERCENTILE, 'Percentile of features', 1, 99, 5))

        self.addParameter(
            ParameterNumber(self.PLOT_BINS, 'Number of bins in histogram', 2, 99, 20))
        self.addParameter(
            ParameterString(self.PLOT_COLOR, 'Histogram color', 'blue'))
        self.addParameter(
            ParameterNumber(self.PLOT_WIDTH, 'Width of image histogram', 10, 2000, 400))
        self.addParameter(
            ParameterNumber(self.PLOT_HEIGHT, 'Height of image histogram', 10, 2000, 300))

        plot = OutputFile(self.PLOT, 'Path to save image to', ext='png')
        plot.hidden = True
        self.addOutput(plot)

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):
        """ Compute horizon
        """
        dbpath    = self.getParameterValue(self.DBPATH)
        if not os.path.isfile( dbpath ):
            log_error('Morpheo database path not found')

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')

        attribute = self.getParameterValue(self.WAY_ATTRIBUTE)
        percentile = self.getParameterValue(self.PERCENTILE)

        conn = connect_database(dbpath)
        G    = read_ways_graph(os.path.join(output, dbname))
        data = hrz.horizon_from_attribute(conn, G, attribute, percentile,
                                          output=os.path.join(output, dbname, '%s_%s_%s.txt' % (attribute, percentile, dbname)))

        hrz.plot_histogram(data, os.path.join(output, dbname, '%s_%s_%s.png' % (attribute, percentile, dbname)),
                           bins=self.getParameterValue(self.PLOT_BINS),
                           color=self.getParameterValue(self.PLOT_COLOR),
                           size=(self.getParameterValue(self.PLOT_WIDTH), self.getParameterValue(self.PLOT_HEIGHT)))

        self.setOutputValue(self.PLOT, os.path.join(output, dbname, '%s_%s_%s.png' % (attribute, percentile, dbname)))

