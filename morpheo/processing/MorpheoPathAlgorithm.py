"""
***************************************************************************
    MorpheoAlgorithm.py
    ---------------------
    Date                 : April 2018
    Copyright            : (C) 2016-2018 3Liz
    Email                : dmarteau  at 3liz dot com
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

from ..core.sql  import connect_database
from ..core import itinerary as iti

from .MorpheoAlgorithm import (
        as_layer,
        QgsProcessingParameterMorpheoDestination,
        MorpheoAlgorithm)


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



