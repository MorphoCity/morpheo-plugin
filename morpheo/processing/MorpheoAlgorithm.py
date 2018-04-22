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
import time
import sys
import logging

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
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterField,
                       QgsProcessingOutputVectorLayer,
                       QgsProcessingOutputFolder,
                       QgsProcessingOutputNumber,
                       QgsProcessingOutputString,
                       QgsProcessingAlgorithm,
                       QgsRasterFileWriter,
                       QgsRasterProjector,
                       QgsRasterPipe,
                       QgsVectorLayer,
                       QgsVectorDataProvider,
                       QgsDataSourceUri,
                       QgsProcessingException)

from qgis.PyQt.QtGui import QIcon

from math import pi

from ..core.errors import BuilderError
from ..core.graph_builder import SpatialiteBuilder
from ..core.structdiff import structural_diff
from ..core import horizon as hrz
from ..core.ways import read_ways_graph
from ..core.sql  import connect_database
from ..core.layers  import export_shapefile
from ..core import mesh
from ..core import itinerary as iti


Builder = SpatialiteBuilder



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


class MorpheoStructuralDiffAlgorithm((MorpheoAlgorithm)):
    """ Compute structural diff
    """

    DBPATH1 = 'DBPATH1'
    DBPATH2 = 'DBPATH2'

    DIRECTORY = 'DIRECTORY'
    DBNAME = 'DBNAME'

    TOLERANCE = 'TOLERANCE'

    # Ouput
    OUTPUT_DBPATH = 'OUTPUT_DBPATH'

    OUTPUT_PAIRED_EDGES = 'OUTPUT_PAIRED_EDGES'

    def name(self):
        return "structural_diff"

    def displayName(self):
        return "Compute Structural Diff"

    def initAlgorithm(self, config = None):

        self.addParameter(QgsProcessingParameterFile(self.DBPATH1, 'Initial Morpheo database', 
                          extension='sqlite'))

        self.addParameter(QgsProcessingParameterFile(self.DBPATH2, 'Final Morpheo database', 
                          extension='sqlite'))

        self.addParameter(QgsProcessingParameterFile(self.DIRECTORY, 'Output directory to store database and data', 
            behavior=QgsProcessingParameterFile.Folder))

        self.addParameter(QgsProcessingParameterString(self.DBNAME, 'Database and data directory name',
                          optional=True))

        self.addParameter(QgsProcessingParameterNumber(self.TOLERANCE, 'Tolerance value in meters',
            type=QgsProcessingParameterNumber.Double,
            minValue=0., 
            maxValue=99.99, 
            defaultValue=1.))

        # Outputs
        outputDBPath = QgsProcessingOutputString(self.OUTPUT_DBPATH, 'Structural difference database path')
        self.addOutput(outputDBPath)

        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_PAIRED_EDGES, "Paired Edges",
            type=QgsProcessing.TypeVectorLine ))


    def processAlg(self, parameters, context, feedback):
        """ Compute structural difference
        """
        params = parameters

        def check_dbpath(path):
            basename = os.path.basename(path)
            shp = os.path.join(path,'place_edges_%s.shp' % basename)
            gpickle = os.path.join(path,'way_graph_%s.gpickle' % basename)
            return os.path.isfile(shp) and os.path.isfile(gpickle)

        database1 = self.parameterAsFile(params, self.DBPATH1, context)
        dbpath1   = database1.replace('.sqlite','')
        if not check_dbpath(dbpath1):
            raise QgsProcessingException('Initial Morpheo directory is incomplete')

        database2  = self.parameterAsFile(params, self.DBPATH2, context)
        dbpath2    = database2.replace('.sqlite','')
        if not check_dbpath(dbpath2):
            raise QgsProcessingException('Final Morpheo directory is incomplete')

        output = self.parameterAsFile(params, self.DIRECTORY, context) or tempFolder()
        dbname = self.parameterAsString(params, self.DBNAME, context) or 'morpheo_%s_%s' % (dbname1, dbname2)

        db_output_path = os.path.join(output, dbname)

        structural_diff( dbpath1, dbpath2, output=db_output_path,
                         buffersize=self.getParameterValue(self.TOLERANCE))

        # Return our layers
        db = db_output_path+'.sqlite'
        output_paired_edges,_ = self.asDestinationLayer( params, self.OUTPUT_PAIRED_EDGES, as_layer(db, 'paired_edges'), context)

        return {
            self.OUTPUT_DBPATH: db,
            self.OUTPUT_PAIRED_EDGES: output_paired_edges,
        }


class MorpheoPathAlgorithm(MorpheoAlgorithm):

    DBPATH = 'DBPATH'

    PLACE_START = 'PLACE_START'
    PLACE_END   = 'PLACE_END'

    # Use attribute for computing ways
    ATTRIBUTE  = 'ATTRIBUTE'
    PERCENTILE = 'PERCENTILE'
    
    # Use way for computing mesh component
    USE_WAY = 'USE_WAY'

    # Path type
    PATH_TYPE = 'PATH_TYPE'

    # Output
    OUTPUT_PATH = 'OUTPUT_PATH'
    OUTPUT_MESH = 'OUTPUT_MESH'

    PERCENTILE_DEFAULT = 5.

    def name(self):
        return "path"

    def displayName(self):
        return "Compute Mesh"

    def initAlgorithm(self, config = None):

        self.addParameter(QgsProcessingParameterFile(self.DBPATH, 'Morpheo database', 
                        extension='sqlite'))

        self.addParameter(QgsProcessingParameterString(self.PATH_TYPE,'Path type'))
        self.addParameter(QgsProcessingParameterNumber(self.PLACE_START,'FID of starting place'))
        self.addParameter(QgsProcessingParameterNumber(self.PLACE_END,  'FID of destination place'))

        self.addParameter(QgsProcessingParameterString(self.ATTRIBUTE , 'Attribute name for mesh structure', optional=True))
        self.addParameter(QgsProcessingParameterNumber(self.PERCENTILE, 'Specify attribute name for mesh structure',
            type=QgsProcessingParameterNumber.Double,
            minValue=1., 
            maxValue=99., 
            defaultValue=self.PERCENTILE_DEFAULT,
            optional=True))
        
        self.addParameter(QgsProcessingParameterBoolean(self.USE_WAY , 'Use ways for computing mesh components', 
            defaultValue=False,
            optional=True))

        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_PATH, "Path output",
            type=QgsProcessing.TypeVectorLine ))

    def processAlg(self, parameters, context, feedback):
        """ Compute mesh
        """
        params = parameters

        dbpath = self.parameterAsFile(params, self.DBPATH, context)
        if not os.path.isfile(dbpath):
            raise QgsProcessingException("Database %s not found" % dbpath)
 
        attribute = self.parameterAsString(params, self.ATTRIBUTE, context) or None
        if attribute:
            percentile = self.parameterAsDouble(params, self.PERCENTILE, context) or self.PERCENTILE_DEFAULT
            use_way    = self.parameterAsBool(params, self.USE_WAY, context ) or False

        path_type = self.parameterAsString(params, self.PATH_TYPE, context)

        conn = connect_database(dbpath)

        source      = self.parameterAsInt(params, self.PLACE_START, context)
        destination = self.parameterAsInt(params, self.PLACE_END,   context)

        if attribute:
            if use_way:
                _edges = iti.edges_from_way_attribute
            else:
                _edges = iti.edges_from_edge_attribute

            check_attribute(conn, attribute, ways=use_way)

            if path_type=='shortest':
                _path_fun = iti.mesh_shortest_path
            elif path_type=='simplest':
                _path_fun = iti.mesh_simplest_path
            else:
                feedback.reportError("Attribute is only supported for simplest or shortest path type")
                raise QgsProcessingException("Invalid path type")

            mesh_ids = _edges(conn, args.attribute, args.percentile)

            _path_fun = partial(_path_fun, edges=mesh_ids)
        else:
            if path_type=='shortest':
                _path_fun = iti.shortest_path
            elif path_type=='simplest':
                _path_fun = iti.simplest_path
            elif path_type=='azimuth':
                _path_fun = iti.azimuth_path
            elif path_type=='naive-azimuth':
                _path_fun = iti.naive_azimuth_path
            else:
                feedback.reportError("Unknown path type '%s'" % path_type)
                raise QgsProcessingException("Invalid path type")

        ids = _path_fun(dbpath, dbpath.replace('.sqlite',''), source, destination, conn=conn, store_path=False) 
        path_layer = as_layer(dbpath, 'place_edges', sql='OGC_FID IN ('+','.join(str(i) for i in ids)+')', keyColumn='OGC_FID')
 
        # Get the path layer
        output_path,destinationProject = self.asDestinationLayer( params, self.OUTPUT_PATH, path_layer, context)
        results = {
            self.OUTPUT_PATH: output_path
        }

        if attribute:
            # Add the mesh layer to the results
            destName    = 'mesh_'+path_layer.name()
            mesh_layer  = as_layer(dbpath, 'place_edges', sql='OGC_FID IN ('+','.join(str(i) for i in mesh_ids)+')', keyColumn='OGC_FID')
            output_mesh = self.addLayerToLoad( mesh_layer, self.OUTPUT_MESH, destName, context, destinationProject)
            restults[self.OUTPUT_MESH] = output_mesh

        return results



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


