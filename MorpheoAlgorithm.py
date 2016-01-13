# -*- coding: utf-8 -*-

"""
***************************************************************************
    MorpheoAlgorithm.py
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

# TODO
# - replace 'voie' by appropriate english term (street, way?)
# - translate methods

__author__ = 'Vincent Mora'
__date__ = 'February 2015'
__copyright__ = '(C) 2015, Oslandia'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import time
import sys
import traceback
from pyspatialite import dbapi2 as db

from qgis.core import *
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from processing.core.GeoAlgorithm import GeoAlgorithm
from processing.core.GeoAlgorithmExecutionException import \
        GeoAlgorithmExecutionException
from processing.core.ProcessingLog import ProcessingLog
from processing.core.parameters import \
        ParameterVector, \
        ParameterNumber, \
        ParameterBoolean, \
        ParameterSelection, \
        ParameterTableField, \
        ParameterFile
from processing.core.outputs import OutputTable
from processing.core.ProcessingConfig import ProcessingConfig
from processing.tools import dataobjects

from Graph import Graph
from Ways import Ways
from Streets import Streets
from Edges import Edges
import Terminology 


def log_info(info):
    print "info: ", info
    ProcessingLog.addToLog(ProcessingLog.LOG_INFO, info)


def log_error(error):
    print "error: ", error
    ProcessingLog.addToLog(ProcessingLog.LOG_ERROR, error)


class MorpheoAlgorithm(GeoAlgorithm):

    OVERWRITE = 'OVERWRITE'
    DIRECTORY = 'DIRECTORY'

    # cleanup
    SNAP_RADIUS = 'SNAP_RADIUS'
    MINIMUN_EDGE_LENGTH = 'MINIMUN_EDGE_LENGTH'

    # layers
    INPUT_LAYER = 'INPUT_LAYER'
    NAME_FIELD = 'NAME_FIELD'
    THRESHOLD = 'THRESHOLD'

    # what must be computed
    NB_CLASSES = 'NB_CLASSES'

    WAYS_ACCESSIBILITY = 'WAYS_ACCESSIBILITY'
    WAYS_ORTHOGONALITY = 'WAYS_ORTHOGONALITY'
    WAYS_USE = 'WAYS_USE'
    WAYS_STRUCT_POT = 'WAYS_STRUCT_POT'
    WAYS_BETWEENNESS = 'WAYS_BETWEENNESS'

    STREETS_ACCESSIBILITY = 'STREETS_ACCESSIBILITY'
    STREETS_ORTHOGONALITY = 'STREETS_ORTHOGONALITY'
    STREETS_USE = 'STREETS_USE'
    STREETS_STRUCT_POT = 'STREETS_STRUCT_POT'

    EDGES_ACCESSIBILITY = 'EDGES_ACCESSIBILITY'
    EDGES_ORTHOGONALITY = 'EDGES_ORTHOGONALITY'
    EDGES_USE = 'EDGES_USE'
    EDGES_STRUCT_POT = 'EDGES_STRUCT_POT'

    # output
    VERTICES_OUTPUT = 'VERTICES_OUTPUT'
    EDGES_OUTPUT = 'EDGES_OUTPUT'
    STREET_OUTPUT = 'STREET_OUTPUT'
    WAY_OUTPUT = 'WAY_OUTPUT'
    ANGLE_OUTPUT = 'ANGLE_OUTPUT'


    def __init__(self):
        GeoAlgorithm.__init__(self)
        print "loading morpheo algo at ", time.strftime("%H:%M:%S")

    def getIcon(self):
        return QIcon(os.path.dirname(__file__) + '/morpheo.png')

    def helpFile(self):
        return None

    def commandLineName(self):
        return 'morpheo:analyse'

    def defineCharacteristics(self):
        self.name = 'Provide graph metric'
        self.group = 'Analysis'

        self.addParameter(ParameterFile(self.DIRECTORY, 'Output directory',
                          isFolder=True))
        self.addParameter(
            ParameterBoolean(self.OVERWRITE, 'Overwrite database', True))

        self.addParameter(
            ParameterNumber(self.SNAP_RADIUS, 'Snap distance (no cleanup if zero)', 0., 99., 0.2))
        self.addParameter(
            ParameterNumber(self.MINIMUN_EDGE_LENGTH, 'Minimum edge length', 0., 99., 4.))

        self.addParameter(ParameterVector(self.INPUT_LAYER, 'Input layer',
                          [ParameterVector.VECTOR_TYPE_LINE]))

        self.addParameter(
            ParameterNumber(self.THRESHOLD, 'Max angle between ways (no ways if zero)', 0., 99.99, 60.))

        self.addParameter(ParameterTableField(self.NAME_FIELD,
            'Street name field (no streets if empty', self.INPUT_LAYER, ParameterTableField.DATA_TYPE_STRING, True))

        self.addParameter(
            ParameterNumber(self.NB_CLASSES, 'Number of classes', 0, 1999, 10))

        self.addParameter(ParameterBoolean(self.WAYS_ACCESSIBILITY, 'Ways accessibility', True))
        self.addParameter(ParameterBoolean(self.WAYS_ORTHOGONALITY, 'Ways orthogonality', True))
        self.addParameter(ParameterBoolean(self.WAYS_USE, 'Ways use', True))
        self.addParameter(ParameterBoolean(self.WAYS_STRUCT_POT, 'Ways structural potential', True))
        self.addParameter(ParameterBoolean(self.WAYS_BETWEENNESS, 'Ways betweenness', False))

        self.addParameter(ParameterBoolean(self.STREETS_ACCESSIBILITY, 'Streets accessibility', False))
        self.addParameter(ParameterBoolean(self.STREETS_ORTHOGONALITY, 'Streets orthogonality', False))
        self.addParameter(ParameterBoolean(self.STREETS_USE, 'Streets use', False))
        self.addParameter(ParameterBoolean(self.STREETS_STRUCT_POT, 'Streets structural potential', False))
        
        self.addParameter(ParameterBoolean(self.EDGES_ACCESSIBILITY, 'Edges accessibility', False))
        self.addParameter(ParameterBoolean(self.EDGES_ORTHOGONALITY, 'Edges orthogonality', False))
        self.addParameter(ParameterBoolean(self.EDGES_USE, 'Edges use', False))
        self.addParameter(ParameterBoolean(self.EDGES_STRUCT_POT, 'Edges structural potential', False))

        self.addOutput(OutputTable(self.VERTICES_OUTPUT, 'Vertices output table'))
        self.addOutput(OutputTable(self.EDGES_OUTPUT, 'Edges output table'))
        self.addOutput(OutputTable(self.STREET_OUTPUT, 'Streets output table'))
        self.addOutput(OutputTable(self.WAY_OUTPUT, 'Ways output table'))
        self.addOutput(OutputTable(self.ANGLE_OUTPUT, 'Angles output table'))

    def checkBeforeOpeningParametersDialog(self):
        return None

    def processAlgorithm(self, progress):

        debug = False  # todo: create parameter ?

        # todo: On connecte les logger de la database, pour afficher
        # les messages dans la boite de dialogue,
        # Est-ce nécessaire dans ce cas ?
        # Normalement les layer de sorti sont des shapefile
        # (est-ce encore vrai?),
        # il faut peut-être une connection
        # à une base si il y a une analyse au niveau de la base
        # une base spatialite est plus facile d'accès (portabilité)

        try:
            log_info("Start")
            start = time.time()

            

            folder = os.path.abspath(
                ProcessingConfig.getSetting(ProcessingConfig.OUTPUT_FOLDER))
            if self.getParameterValue(self.DIRECTORY):
                folder = self.getParameterValue(self.DIRECTORY)
                if not os.path.exists(folder):
                    os.makedirs(folder)

            layer = dataobjects.getObjectFromUri(
                self.getParameterValue(self.INPUT_LAYER))

            if layer.wkbType() not in [QGis.WKBLineString25D, QGis.WKBLineString] :
                raise Exception("Invalid geometry type for input layer (multi?)")
            if layer.crs().geographicFlag():
                raise Exception("Invalid CRS (lat/long) for inputlayer")


            brut_arcs_table = "morpheo_"+layer.name().replace(" ", "_")
            dbname = os.path.join(folder, brut_arcs_table + '.sqlite')

            if os.path.isfile(dbname) and  self.getParameterValue(self.OVERWRITE):
                os.remove(dbname)

            recompute = True
            graph = None;
            if not os.path.isfile(dbname):
                log_info("Writing "+dbname)
                QgsVectorFileWriter.writeAsVectorFormat(
                    layer,
                    dbname,
                    "utf-8",
                    None,
                    "SQLite",
                    False,
                    None,
                    ["SPATIALITE=YES", ])
                graph_needed = True
                progress.setText('Graph in progress')
                conn = db.connect(os.path.join(dbname))
                graph = Graph(conn, 
                        brut_arcs_table, 
                        self.getParameterValue(self.NAME_FIELD), 
                        progress, 
                        self.getParameterValue(self.MINIMUN_EDGE_LENGTH),
                        self.getParameterValue(self.SNAP_RADIUS))
                log_info("Graph created")
            else:
                conn = db.connect(os.path.join(dbname))
                graph = Graph(conn)
                recompute = False

            if self.getParameterValue(self.THRESHOLD):
                progress.setText("Ways in progress")
                ways = Ways(graph,
                           folder,
                           self.getParameterValue(self.THRESHOLD),
                           progress, 
                           recompute)
                log_info("Ways created")

                if self.getParameterValue(self.WAYS_ACCESSIBILITY) or\
                        self.getParameterValue(self.WAYS_STRUCT_POT):
                    ways.compute_structurality(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

                if self.getParameterValue(self.WAYS_ORTHOGONALITY):
                    ways.compute_orthogonality(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

                if self.getParameterValue(self.WAYS_USE):
                    ways.compute_use(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)
                
                if self.getParameterValue(self.WAYS_STRUCT_POT):
                    ways.compute_inclusion(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

                if self.getParameterValue(self.WAYS_BETWEENNESS):
                    ways.compute_betweenness()
            
            if self.getParameterValue(self.NAME_FIELD):
                progress.setText("Streets in progress")
                streets = Streets(graph, folder, progress, recompute)
                log_info("Streets created")

                if self.getParameterValue(self.STREETS_ACCESSIBILITY) or\
                        self.getParameterValue(self.STREETS_STRUCT_POT):
                    streets.compute_structurality(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

                if self.getParameterValue(self.STREETS_ORTHOGONALITY):
                    streets.compute_orthogonality(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

                if self.getParameterValue(self.STREETS_USE):
                    streets.compute_use(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)
                
                if self.getParameterValue(self.STREETS_STRUCT_POT):
                    streets.compute_inclusion(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

            if self.getParameterValue(self.EDGES_ACCESSIBILITY) or\
                    self.getParameterValue(self.EDGES_ORTHOGONALITY) or\
                    self.getParameterValue(self.EDGES_USE) or\
                    self.getParameterValue(self.EDGES_STRUCT_POT):
                progress.setText("Edges in progress")
                edges = Edges(graph, folder, progress, recompute);
                progress.setText("Edges created")

                if self.getParameterValue(self.EDGES_ACCESSIBILITY) or\
                        self.getParameterValue(self.EDGES_STRUCT_POT):
                    edges.compute_structurality(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

                if self.getParameterValue(self.EDGES_ORTHOGONALITY):
                    edges.compute_orthogonality(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)

                if self.getParameterValue(self.EDGES_USE):
                    edges.compute_use(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)
                
                if self.getParameterValue(self.EDGES_STRUCT_POT):
                    edges.compute_inclusion(
                            self.getParameterValue(self.NB_CLASSES),
                            progress)


            end = time.time()
            log_info("End")
            elapsed = end - start
            log_info("Total execution time %.2f min (%.2f sec)"%((elapsed / 60.), elapsed))

            cur = Terminology.TrCursor(graph.conn.cursor())

            # vertices are a bit peculiar because we also output geometry in X,Y,Z columns
            cur.execute("SELECT OGC_FID, X(GEOMETRY), Y(GEOMETRY), Z(GEOMETRY), DEGREE FROM $vertices")
            fields = ['OGC_FID', 'X', 'Y', 'Z', 'DEGREE']
            table_writer = self.getOutputFromName(self.VERTICES_OUTPUT).getTableWriter(fields)
            table_writer.addRecords(cur.fetchall())

            self.write_output_table(self.EDGES_OUTPUT, '$edges', cur) 
            self.write_output_table(self.ANGLE_OUTPUT, 'angles', cur) 
            self.write_output_table(self.STREET_OUTPUT, 'streets', cur) 
            self.write_output_table(self.WAY_OUTPUT, 'ways', cur) 

            self.add_vector_layer('$vertices', dbname)
            self.add_vector_layer('$edges', dbname)
            if  self.getParameterValue(self.THRESHOLD):
                self.add_vector_layer('ways', dbname)
            if  self.getParameterValue(self.NAME_FIELD):
                self.add_vector_layer('streets', dbname)


        except Exception, e:
            traceback.print_exc(file=sys.stdout)
            log_error(str(e))

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


