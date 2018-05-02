"""
***************************************************************************
    MorpheoImportLayer.py
    ---------------------
    Date                 : April 2018
    Copyright            : (C) 2016-2018 3Liz
    Email                : dmarteau at 3liz dot com
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
__date__ = 'April 2018'
__copyright__ = '(C) 2016-2018, 3Liz'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os

from qgis.core import (QgsProcessing,
                       QgsProperty,
                       QgsProcessingContext,
                       QgsProcessingParameterDefinition,
                       QgsProcessingOutputLayerDefinition,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterFile,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterString,
                       QgsProcessingParameterVectorLayer,
                       QgsProcessingParameterVectorDestination,
                       QgsProcessingParameterField,
                       QgsProcessingOutputVectorLayer,
                       QgsProcessingOutputFolder,
                       QgsProcessingOutputNumber,
                       QgsProcessingOutputString,
                       QgsProcessingAlgorithm,
                       QgsVectorLayer,
                       QgsVectorFileWriter,
                       QgsDataSourceUri,
                       QgsProcessingException)


import gdal 
from processing.algs.gdal.GdalUtils import GdalUtils

from ..core.graph_builder import SpatialiteBuilder
from ..core.sql  import connect_database

Builder = SpatialiteBuilder

from .MorpheoAlgorithm import MorpheoAlgorithm

class MorpheoImportLayer(MorpheoAlgorithm):

    INPUT  = 'INPUT'
    NAME   = 'NAME'
    DBNAME = 'DBNAME'
    SINGLEPARTGEOMETRY = 'SINGLEPARTGEOMETRY'
    
    def name(self):
        return "importlayer"

    def displayName(self):
        return "Import layer to morpheo database"

    def initAlgorithm( self, config=None ):
        """ Virtual override

           see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        # Inputs
        self.addParameter(QgsProcessingParameterFeatureSource(self.INPUT, 'Input layer',
                       [QgsProcessing.TypeVectorLine]))

        self.addParameter(QgsProcessingParameterString(self.DBNAME, 'Database name'))
        self.addParameter(QgsProcessingParameterString(self.NAME, 'Database name'))

        self.addParameter(QgsProcessingParameterBoolean(self.SINGLEPARTGEOMETRY, 'Single part geometry'))

    def processAlgorithm(self, parameters, context, feedback):
        """ Import layer to the database
        """
        ogrLayer, layerName = self.getOgrCompatibleSource(self.INPUT, parameters, context, feedback)

        dbname = self.parameterAsString(parameters, self.DBNAME, context)
        name   = self.parameterAsString(parameters, self.NAME,   context)
        forceSinglepPartGeometry = self.parameterAsBool(parameters, self.SINGLEPARTGEOMETRY, context)

        srcDs = gdal.OpenEx(ogrLayer)
        if not srcDs:
            raise QgsProcessingException("Failed to open '%s'" % ogrLayer)

        options = []
        if forceSinglepPartGeometry:
            options.append('-explodecollections')

        if os.path.exists(dbname):
            options.append('-update')

        if feedback:
            feedback.setProgressText("Importing layer")
            def callback(pct, msg, data, **kwargs):
                if msg: 
                    feedback.setProgressText(msg)
                feedback.setProgress(100*pct)
        else:
            callback = None

        ds = gdal.VectorTranslate(dbname, srcDS=srcDs, format='SQLite', datasetCreationOptions=['SPATIALITE=y'],
             layerName=name, options=options, callback=callback)

        if ds:
            del ds
        else:
            raise QgsProcessingException("Failed to import '%s'" % ogrLayer)

        return {}

    def getOgrCompatibleSource(self, parameter_name, parameters, context, feedback):
        """
        Interprets a parameter as an OGR compatible source and layer name
        :param executing:
        """
        input_layer = self.parameterAsVectorLayer(parameters, parameter_name, context)

        ogr_data_path = None
        ogr_layer_name = None
        if input_layer is None or input_layer.dataProvider().name() == 'memory':
            # parameter is not a vector layer - try to convert to a source compatible with OGR
            # and extract selection if required
            ogr_data_path = self.parameterAsCompatibleSourceLayerPath(parameters, parameter_name, context,
                                                                      QgsVectorFileWriter.supportedFormatExtensions(),
                                                                      feedback=feedback)
            ogr_layer_name = GdalUtils.ogrLayerName(ogr_data_path)
        elif input_layer.dataProvider().name() == 'ogr':
            # parameter is a vector layer, with OGR data provider
            ogr_data_path  = str(input_layer.source()).split("|")[0]
            ogr_layer_name = GdalUtils.ogrLayerName(input_layer.dataProvider().dataSourceUri())
        else:
            # vector layer, but not OGR - get OGR compatible path
            # TODO - handle "selected features only" mode!!
            ogr_data_path  = GdalUtils.ogrConnectionString(input_layer.dataProvider().dataSourceUri(), context)[1:-1]
            ogr_layer_name = GdalUtils.ogrLayerName(input_layer.dataProvider().dataSourceUri())
        return ogr_data_path, ogr_layer_name



