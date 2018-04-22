"""
***************************************************************************
    MorpheoDiffAlgorithm.py
    ---------------------
    Date                 : April 2016
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

from ..core.structdiff import structural_diff
from ..core.sql  import connect_database

from .MorpheoAlgorithm import (
        as_layer,
        QgsProcessingParameterMorpheoDestination,
        MorpheoAlgorithm)


class MorpheoStructuralDiffAlgorithm((MorpheoAlgorithm)):
    """ Compute structural diff
    """

    DBPATH1 = 'DBPATH1'
    DBPATH2 = 'DBPATH2'

    DIRECTORY = 'DIRECTORY'
    DBNAME = 'DBNAME'

    TOLERANCE = 'TOLERANCE'

    # Ouput
    OUTPUT_PAIRED_EDGES  = 'OUTPUT_PAIRED_EDGES'
    OUTPUT_ADDED_EDGES   = 'OUTPUT_ADDED_EDGES'
    OUTPUT_REMOVED_EDGES = 'OUTPUT_REMOVED_EDGES'

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

        self.addParameter(QgsProcessingParameterString(self.DBNAME, 'Database and data directory name'))

        self.addParameter(QgsProcessingParameterNumber(self.TOLERANCE, 'Tolerance value in meters',
            type=QgsProcessingParameterNumber.Double,
            minValue=0., 
            defaultValue=1.))

        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_PAIRED_EDGES, "Paired Edges",
            type=QgsProcessing.TypeVectorLine ))
        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_ADDED_EDGES, "Added Edges",
            type=QgsProcessing.TypeVectorLine ))
        self.addParameter( QgsProcessingParameterMorpheoDestination( self.OUTPUT_REMOVED_EDGES, "Removed Edges",
            type=QgsProcessing.TypeVectorLine ))


    def processAlg(self, parameters, context, feedback):
        """ Compute structural difference
        """
        params = parameters

        def get_dbpath( name ):
            database = self.parameterAsFile(params, name, context)
            dbpath  = database.replace('.sqlite','')
            if not os.path.isfile(dbpath):
                raise QgsProcessingException("Database %s not found" % dbpath)
            return dbpath
           
        dbpath1 = get_dbpath( self.DBPATH1 )
        dbpath2 = get_dbpath( self.DBPATH2 )

        output = self.parameterAsFile(params  , self.DIRECTORY, context) or tempFolder()
        dbname = self.parameterAsString(params, self.DBNAME, context)

        buffersize = self.parameterAsDouble( params, self.TOLERANCE, context )

        output_path = os.path.join(output, dbname)

        structural_diff( dbpath1, dbpath2, output=output_path, buffersize=buffersize)

        # Return our layers
        db = output_path+'.sqlite'
        output_paired ,_ = self.asDestinationLayer( params, self.OUTPUT_PAIRED_EDGES , as_layer(db, 'paired_edges') , context)
        output_removed,_ = self.asDestinationLayer( params, self.OUTPUT_REMOVED_EDGES, as_layer(db, 'removed_edges'), context)
        output_added  ,_ = self.asDestinationLayer( params, self.OUTPUT_ADDED_EDGES  , as_layer(db, 'added_edges')  , context)

        return {
            self.OUTPUT_PAIRED_EDGES : output_paired,
            self.OUTPUT_REMOVED_EDGES: output_removed,
            self.OUTPUT_ADDED_EDGES  : output_added,
        }


