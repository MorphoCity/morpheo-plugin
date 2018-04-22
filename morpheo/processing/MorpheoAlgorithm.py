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

__author__ = 'René-Luc DHONT/David Marteau'
__date__ = 'August 2016'
__copyright__ = '(C) 2016-2018, 3Liz'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os

from .logger import init_log_custom_hooks

from qgis.core import (QgsProcessing,
                       QgsProperty,
                       QgsProcessingContext,
                       QgsProcessingParameterDefinition,
                       QgsProcessingOutputLayerDefinition,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterString,
                       QgsProcessingParameterVectorLayer,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterVectorDestination,
                       QgsProcessingParameterField,
                       QgsProcessingOutputVectorLayer,
                       QgsProcessingOutputFolder,
                       QgsProcessingOutputNumber,
                       QgsProcessingOutputString,
                       QgsProcessingAlgorithm,
                       QgsVectorLayer,
                       QgsDataSourceUri,
                       QgsProcessingException)

from qgis.PyQt.QtGui import QIcon

from ..core import horizon as hrz
from ..core.ways import read_ways_graph
from ..core.sql  import connect_database
from ..core import mesh


def as_layer(db, table, sql='', keyColumn=''):
    """ Create a layer from sqlite table
    """
    uri = QgsDataSourceUri()
    uri.setDatabase(db)
    uri.setDataSource('', table, 'GEOMETRY', aSql=sql, aKeyColumn=keyColumn)
    return QgsVectorLayer(uri.uri(), table, 'spatialite')


class QgsProcessingParameterMorpheoDestination(QgsProcessingParameterVectorDestination):
    def defaultFileExtension(self):
        return ""


class MorpheoAlgorithm(QgsProcessingAlgorithm):
   
    def __init__(self):
            super().__init__()

    def createInstance(self, config={}):
        """ Virtual override

            see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        return self.__class__()

    def helpUrl(self):
        return "https://github.com/MorphoCity/morpheo-plugin"

    def group(self):
        return 'Morpheo Graph Analysis'

    def groupId(self):
        return 'morpheographanalysis'

    def icon(self):
        return QIcon(':/plugins/Morpheo/morpheo.png')

    def addLayerToLoad(self, layer, outputName, destName, context, destinationProject):
        layer.setName(destName)
        context.temporaryLayerStore().addMapLayer( layer )
        if destinationProject:
            context.addLayerToLoadOnCompletion( layer.id(),
                QgsProcessingContext.LayerDetails( destName, destinationProject, outputName ))
        return layer.id()

    def asDestinationLayer(self, params, outputName, layer, context ):
        """ Add layer to load in the final project
        """
        # Add layer store
        definition = self.parameterDefinition(outputName)
        destinationProject = None
        # Get the destination project
        p = params.get(outputName)
        if isinstance(p, QgsProcessingOutputLayerDefinition) and p.destinationProject:
            destName = p.destinationName
            if not destName:
                val = p.sink
                if isinstance(val, QgsProperty):
                    destName, _  = val.valueAsString( context.expressionContext(), definition.defaultValue())
                    destName = str(destName).rstrip('.')
                else:
                    destName = str(val) or definition.defaultValue()
            layer.setName(destName)
            destinationProject = p.destinationProject
        elif isinstance(p, QgsProperty):
            destName, _  = p.valueAsString( context.expressionContext(), definition.defaultValue())
        else:
            destName = p

        self.addLayerToLoad(layer, outputName, destName, context, destinationProject)
        return layer.id(), destinationProject

    def processAlgorithm(self, parameters, context, feedback):
        self.setLogHandler(feedback)
        try:
            return self.processAlg(parameters, context, feedback)
        finally:
            self.cleanLogHandler()

    def setLogHandler(self, feedback):

        def on_info(msg):
            feedback.pushInfo(msg)

        def on_warn(msg):
            feedback.pushInfo(msg)

        def on_error(msg):
            feedback.reportError(msg)

        def on_critical(msg):
            feedback.reportError(msg, fatalError=True)

        def on_progress(value, msg):
            feedback.setProgressText(msg)
            feedback.setProgress(value)

        init_log_custom_hooks(on_info=on_info,
                              on_warn=on_warn,
                              on_error=on_error,
                              on_critical=on_critical,
                              on_progress=on_progress)

    def cleanLogHandler(self):
        init_log_custom_hooks()


class MorpheoMeshAlgorithm((MorpheoAlgorithm)):

    DBPATH = 'DBPATH'
    WAY_LAYER = 'WAY_LAYER'
    WAY_ATTRIBUTE = 'WAY_ATTRIBUTE'
    PERCENTILE = 'PERCENTILE'
    USE_WAY = 'USE_WAY'

    OUTPUT_MESH = 'OUTPUT_MESH'

    def name(self):
        return "mesh"

    def displayName(self):
        return "Compute Mesh"

    def initAlgorithm(self, config = None):

        self.addParameter(QgsProcessingParameterFile(self.DBPATH, 'Morpheo database', 
                        extension='sqlite'))

        self.addParameter(QgsProcessingParameterVectorLayer(self.WAY_LAYER, 'Ways layer',
                          [QgsProcessing.TypeVectorLine]))

        # Options controlling ways
        self.addParameter(QgsProcessingParameterField(self.WAY_ATTRIBUTE,
            'Attribute for mesh structure', 
            parentLayerParameterName=self.WAY_LAYER, 
            type=QgsProcessingParameterField.String))

        self.addParameter(QgsProcessingParameterNumber(self.PERCENTILE, 'The percentile for computing the mesh structure', 
            minValue=1., 
            maxValue=99, 
            defaultValue=5))

        self.addParameter(QgsProcessingParameterBoolean(self.USE_WAY, 'Use ways for computing mesh components', False))

        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_MESH, "Mesh output",
            type=QgsProcessing.TypeVectorLine ))


    def processAlg(self, parameters, context, feedback):
        """ Compute mesh
        """
        params = parameters

        dbpath = self.parameterAsFile(params, self.DBPATH, context)
        if not os.path.isfile(dbpath):
            raise QgsProcessingException("Database %s not found" % dbpath)
 
        db_output_path = dbpath.replace('.sqlite','')

        attribute = self.parameterAsFields(params, self.WAY_ATTRIBUTE, context) or None
        if attribute:
            attribute = attribute[0] 

        percentile = self.parameterAsDouble(params, self.PERCENTILE, context)

        use_way = self.parameterAsBool(params, self.USE_WAY, context)
        table = use_way and 'ways' or 'edges'

        conn = connect_database(dbpath)
        name = 'mesh_%s_%s_%s' % (table, attribute, percentile)
        ids = mesh.features_from_attribute(conn.cursor(), table, attribute, percentile)

        # Create the destination layer
        dest_layer = as_layer(dbpath, table, sql='OGC_FID IN ('+','.join(str(i) for i in ids)+')', keyColumn='OGC_FID')

        output_mesh = self.asDestinationLayer( params, self.OUTPUT_MESH, dest_layer, context)

        return {
            self.OUTPUT_MESH: output_mesh     
        }


class MorpheoHorizonAlgorithm((MorpheoAlgorithm)):

    DBPATH = 'DBPATH'
    WAY_LAYER = 'WAY_LAYER'
    WAY_ATTRIBUTE = 'WAY_ATTRIBUTE'
    PERCENTILE = 'PERCENTILE'

    OUTPUT_HORIZON = 'OUTPUT_HORIZON'

    def name(self):
        return "mesh"

    def displayName(self):
        return "Compute Horizon"

    def initAlgorithm(self, config = None):

        self.addParameter(QgsProcessingParameterFile(self.DBPATH, 'Morpheo database', 
                        extension='sqlite'))

        self.addParameter(QgsProcessingParameterVectorLayer(self.WAY_LAYER, 'Ways layer',
                          [QgsProcessing.TypeVectorLine]))

        # Options controlling ways
        self.addParameter(QgsProcessingParameterField(self.WAY_ATTRIBUTE,
            'Attribute for building Horizon', 
            parentLayerParameterName=self.WAY_LAYER, 
            type=QgsProcessingParameterField.String))

        self.addParameter(QgsProcessingParameterNumber(self.PERCENTILE, 'Percentile of features', 
            minValue=1,
            maxValue=99, 
            defaultValue=5))

        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_HORIZON, "Horizon output",
            type=QgsProcessing.TypeVectorLine ))


    def processAlg(self, progress):
        """ Compute horizon
        """
        dbpath    = self.getParameterValue(self.DBPATH)
        if not os.path.isfile( dbpath ):
            raise QgsProcessingException("Database %s not found" % dbpath)

        db_output_path = dbpath.replace('.sqlite', '')

        attribute = self.parameterAsFields(params, self.WAY_ATTRIBUTE, context) or None
        if attribute:
            attribute = attribute[0] 

        percentile = self.parameterAsDouble(params, self.PERCENTILE, context)

        conn = connect_database(dbpath)
        G    = read_ways_graph(os.path.join(output, dbname))

        table = 'horizon_%s_%s' % (attribute, percentile)
        hrz.horizon_from_attribute(conn, G, table, attribute, percentile)

        output_horizon = self.asDestinationLayer( params, self.OUTPUT_HORIZON, as_layer(dbpath, table), context)

        return {
            self.OUTPUT_HORIZON: output_horizon    
        }


