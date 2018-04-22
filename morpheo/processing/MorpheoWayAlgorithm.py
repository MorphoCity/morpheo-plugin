"""
***************************************************************************
    MorpheoWayAlgorithm.py
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

from math import pi

from ..core.graph_builder import SpatialiteBuilder
from ..core.sql  import connect_database

Builder = SpatialiteBuilder

from .MorpheoAlgorithm import (
        as_layer,
        QgsProcessingParameterMorpheoDestination,
        MorpheoAlgorithm)

class MorpheoWayAlgorithm(MorpheoAlgorithm):

    INPUT_LAYER = 'INPUT_LAYER'
    DIRECTORY = 'DIRECTORY'
    DBNAME = 'DBNAME'

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
    OUTPUT_PLACES = 'OUTPUT_PLACES'
    OUTPUT_PLACE_EDGES = 'OUTPUT_PLACE_EDGES'
    OUTPUT_WAYS = 'OUTPUT_WAYS'

    def name(self):
        return "ways"

    def displayName(self):
        return "Compute Ways"

    def initAlgorithm( self, config=None ):
        """ Virtual override

           see https://qgis.org/api/classQgsProcessingAlgorithm.html
        """
        # Inputs
        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT_LAYER, 'Input layer',
                          [QgsProcessing.TypeVectorLine]))

        self.addParameter(QgsProcessingParameterFile(self.DIRECTORY, 'Output directory to store database and data', 
            behavior=QgsProcessingParameterFile.Folder))

        self.addParameter(QgsProcessingParameterString(self.DBNAME, 'Database name', optional=True))

        # Options controlling graph
        self.addParameter(QgsProcessingParameterNumber(self.SNAP_DISTANCE, 'Snap distance in meters (no cleanup if zero)', 
            type=QgsProcessingParameterNumber.Double, 
            minValue= 0., 
            defaultValue=.2))

        self.addParameter(QgsProcessingParameterNumber(self.MIN_EDGE_LENGTH, 'Min edge length (meters)', 
            type=QgsProcessingParameterNumber.Double,
            minValue=0., 
            defaultValue=4.))

        # Options controlling places
        self.addParameter(QgsProcessingParameterNumber(self.BUFFER, 'Place Buffer size (meters)', 
            type=QgsProcessingParameterNumber.Double,
            minValue=0., 
            defaultValue=4.))

        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT_PLACES, 'Default input polygons for places',
                          [QgsProcessing.TypeVectorPolygon], 
                          optional=True))

        # Options controlling ways
        self.addParameter(QgsProcessingParameterField(self.WAY_ATTRIBUTE,
            'Attribute for building street ways', 
            parentLayerParameterName=self.INPUT_LAYER, 
            type=QgsProcessingParameterField.String, 
            optional=True))

        self.addParameter(QgsProcessingParameterNumber(self.THRESHOLD, 'Threshold angle (in degree)', 
            minValue=0., 
            maxValue=180.0, 
            defaultValue=60.0))

        self.addParameter(QgsProcessingParameterBoolean(self.RTOPO, 'Compute topological radius', False, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.ATTRIBUTES, 'Compute attributes', False, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.ORTHOGONALITY, 'Compute orthogonality (require attributes)', False, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.BETWEENNESS, 'Compute betweenness centrality (require attributes)', False, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.CLOSENESS, 'Compute closeness centrality (require attributes)', False, optional=True))
        self.addParameter(QgsProcessingParameterBoolean(self.STRESS, 'Compute stress centrality (require attributes)', False, optional=True))

        self.addParameter(QgsProcessingParameterNumber( self.CLASSES, 'Number of classes', 
                minValue=2, 
                maxValue=99, 
                defaultValue=10,
                optional=True))

        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_PLACES, "Places", 
            type=QgsProcessing.TypeVectorPolygon ))
        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_PLACE_EDGES, "Edges with Places removed",
            type=QgsProcessing.TypeVectorLine ))
        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_WAYS, "Ways",
            type=QgsProcessing.TypeVectorLine ))


    def processAlg(self, parameters, context, feedback):
        """ Build all : graph, places and ways
        """
        params = parameters

        layer = self.parameterAsVectorLayer(params, self.INPUT_LAYER, context)

        output = self.parameterAsFile(params, self.DIRECTORY, context) or tempFolder()
        dbname = self.parameterAsString(params, self.DBNAME, context) or 'morpheo_'+layer.name().replace(" ", "_")

        db_output_path = os.path.join(output, dbname)

        if not os.path.exists(db_output_path):
            os.mkdir(db_output_path)

        builder = Builder.from_layer( layer, db_output_path )

        way_field = self.parameterAsFields(params, self.WAY_ATTRIBUTE, context) or None
        if way_field:
            way_field = way_field[0] 

        # Compute graph
        builder.build_graph(self.parameterAsDouble(params, self.SNAP_DISTANCE, context),
                            self.parameterAsDouble(params, self.MIN_EDGE_LENGTH, context),
                            way_field,
                            output=db_output_path)
        # Compute places
        builder.build_places(buffer_size = self.parameterAsDouble(params, self.BUFFER, context),
                             places      = self.parameterAsVectorLayer(params, self.INPUT_PLACES, context),
                             output      = db_output_path)

        # Compute ways attributes
        kwargs = dict(classes=self.parameterAsInt(params, self.CLASSES, context), 
                      rtopo=self.parameterAsBool(params, self.RTOPO, context))
        if self.parameterAsBool(params, self.ATTRIBUTES, context):
            kwargs.update(attributes=True,
                          orthogonality = self.parameterAsBool(params, self.ORTHOGONALITY, context),
                          betweenness   = self.parameterAsBool(params, self.BETWEENNESS, context),
                          closeness     = self.parameterAsBool(params, self.CLOSENESS, context),
                          stress        = self.parameterAsBool(params, self.STRESS, context))

        if way_field:
            feedback.pushInfo("Bulding way from attribute %s" % way_field)
            builder.build_ways_from_attribute(output=db_output_path, **kwargs)
        else:
            threshold = self.parameterAsDouble(params, self.THRESHOLD, context)
            feedback.pushInfo("Bulding way from geometry - threshold = %s" % threshold)
            builder.build_ways(threshold=threshold, output=db_output_path, **kwargs)

        # Return our layers
        db = db_output_path+'.sqlite'
        output_places,_      = self.asDestinationLayer( params, self.OUTPUT_PLACES, as_layer(db, 'places'), context)
        output_place_edges,_ = self.asDestinationLayer( params, self.OUTPUT_PLACE_EDGES, as_layer(db, 'place_edges'), context)
        output_ways,_        = self.asDestinationLayer( params, self.OUTPUT_WAYS, as_layer(db, 'ways'), context)

        return {
            self.OUTPUT_PLACES: output_places,
            self.OUTPUT_PLACE_EDGES: output_place_edges,
            self.OUTPUT_WAYS: output_ways
        }



class MorpheoWayAttributesAlgorithm((MorpheoAlgorithm)):

    DBPATH = 'DBPATH'

    # Options controlling ways
    RTOPO = 'RTOPO'
    ORTHOGONALITY = 'ORTHOGONALITY'
    BETWEENNESS = 'BETWEENNESS'
    CLOSENESS = 'CLOSENESS'
    STRESS = 'STRESS'
    CLASSES = 'CLASSES'

    # Ouput
    OUTPUT_WAYS = 'OUTPUT_WAYS'
 
    def name(self):
        return "way_attributes"

    def displayName(self):
        return "Compute Way attributes"

    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterFile(self.DBPATH, 'Morpheo database', 
                        extension='sqlite'))

        self.addParameter(QgsProcessingParameterBoolean(self.RTOPO, 'Compute topological radius', False))
        self.addParameter(QgsProcessingParameterBoolean(self.ORTHOGONALITY, 'Compute orthogonality (require attributes)', False))
        self.addParameter(QgsProcessingParameterBoolean(self.BETWEENNESS, 'Compute betweenness centrality (require attributes)', False))
        self.addParameter(QgsProcessingParameterBoolean(self.CLOSENESS, 'Compute closeness centrality (require attributes)', False))
        self.addParameter(QgsProcessingParameterBoolean(self.STRESS, 'Compute stress centrality (require attributes)', False))

        self.addParameter(QgsProcessingParameterNumber(self.CLASSES, 'Number of classes', 
                minValue=2, 
                maxValue=99, 
                defaultValue=10))

        # Outputs
        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_WAYS, "Ways",
            type=QgsProcessing.TypeVectorLine ))


    def processAlg(self, parameters, context, feedback):
        """ Compute way attributes
        """
        params = parameters

        dbpath = self.parameterAsFile(params, self.DBPATH, context)
        if not os.path.isfile(dbpath):
            raise QgsProcessingException("Database %s not found" % dbpath)
 
        db_output_path = dbpath.replace('.sqlite','')

        builder = Builder.from_database( db_output_path )
        builder.compute_way_attributes(
                orthogonality = self.parameterAsBool(params, self.ORTHOGONALITY, context),
                betweenness   = self.parameterAsBool(params, self.BETWEENNESS, context),
                closeness     = self.parameterAsBool(params, self.CLOSENESS, context),
                stress        = self.parameterAsBool(params, self.STRESS, context),
                rtopo         = self.parameterAsBool(params, self.RTOPO, context),
                classes       = self.parameterAsInt(params, self.CLASSES, context),
                output        = db_output_path)

        # Return our layers
        db = db_output_path+'.sqlite'
        output_ways,_ = self.asDestinationLayer( params, self.OUTPUT_WAYS, as_layer(db, 'ways'), context)

        return {
            self.OUTPUT_WAYS: output_ways
        }


class MorpheoEdgeAttributesAlgorithm((MorpheoAlgorithm)):

    DBPATH = 'DBPATH'

    # Options controlling edges
    ORTHOGONALITY = 'ORTHOGONALITY'
    BETWEENNESS = 'BETWEENNESS'
    CLOSENESS = 'CLOSENESS'
    STRESS = 'STRESS'
    CLASSES = 'CLASSES'

    # Ouput
    OUTPUT_PLACE_EDGES = 'OUTPUT_PLACE_EDGES'

    def name(self):
        return "edge_attributes"

    def displayName(self):
        return "Compute Way attributes"

    def initAlgorithm(self, config=None):

        self.addParameter(QgsProcessingParameterFile(self.DBPATH, 'Morpheo database', 
                        extension='sqlite'))

        self.addParameter(QgsProcessingParameterBoolean(self.ORTHOGONALITY, 'Compute orthogonality (require attributes)', False))
        self.addParameter(QgsProcessingParameterBoolean(self.BETWEENNESS, 'Compute betweenness centrality (require attributes)', False))
        self.addParameter(QgsProcessingParameterBoolean(self.CLOSENESS, 'Compute closeness centrality (require attributes)', False))
        self.addParameter(QgsProcessingParameterBoolean(self.STRESS, 'Compute stress centrality (require attributes)', False))

        self.addParameter(QgsProcessingParameterNumber(self.CLASSES, 'Number of classes', 
                minValue=2, 
                maxValue=99, 
                defaultValue=10))

        # Outputs
        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_PLACE_EDGES, "Edges with Places removed",
            type=QgsProcessing.TypeVectorLine ))


    def processAlg(self, parameters, context, feedback):
        """ Compute way attributes
        """
        params = parameters

        dbpath = self.parameterAsFile(params, self.DBPATH, context)
        if not os.path.isfile(dbpath):
            raise QgsProcessingException("Database %s not found" % dbpath)
 
        output = os.path.dirname(dbpath)
        dbname = os.path.basename(dbpath).replace('.sqlite','')

        db_output_path = os.path.join(output, dbname)

        builder = Builder.from_database( db_output_path )
        builder.compute_way_attributes(  db_output_path,
                orthogonality = self.parameterAsBool(params, self.ORTHOGONALITY),
                betweenness   = self.parameterAsBool(params, self.BETWEENNESS),
                closeness     = self.parameterAsBool(params, self.CLOSENESS),
                stress        = self.parameterAsBool(params, self.STRESS),
                classes       = self.parameterAsInt(params, self.CLASSES),
                output        = db_output_path)

        # Return our layers
        db = db_output_path+'.sqlite'
        output_place_edges,_ = self.asDestinationLayer( params, self.OUTPUT_PLACE_EDGES, as_layer(db, 'place_edges'), context)

        return {
            self.OUTPUT_PLACE_EDGES: output_place_edges,
        }


