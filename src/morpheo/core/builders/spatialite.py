# -*- encoding=utf-8 -*-
""" Spatialite graph builder implementation
"""

import os
import logging
import string

from .errors import BuilderError
from .sanitize import sanitize

class SQLNotFoundError(BuilderError):
    pass

class InvalidLayerError(BuilderError):
    pass

class FileNotFoundError(BuilderError):
    pass



class SpatialiteBuilder(object):

    version     = "1.0"
    description = "Spatialite graph builder"

    def __init__(self, dbname, table=None):
        """ Initialize builder

            :param dbname: the path of the database
            :param table: name of the table containing input data
        """
        from pyspatialite import dbapi2 as db

        logging.info("Opening database %s" % dbname)
        self._conn = db.connect(dbname)
        self._input_table = table or os.path.basename(os.path.splitext(dbname)[0]).lower()

    def build_graph( self, snap_distance, min_edge_length, name_field=None ):
        """ Build morpheo topological graph

            This method will build the topological graph
            - The vertices
            - The edges
            - The way (TODO link to definition)
            - The angles

            :param snap_distance: The snap distance used to sanitize  the graph,
                 If the snap_distance is > 0 the graph will be sanitized (merge close vertices, 
                    remove unconnected features, the result will be a topological graph
            :param min_edge_length: The minimum edge length - edge below this length will be removed
            :param name_field: TODO ????
        """
        # sanitize graph
        if snap_distance > 0:
            logging.info("Builder: sanitizing graph")
            sanitize(self._conn, self._input_table, snap_distance, min_edge_length, 
                     name_field=name_field)
        
         
        


    def load_sql(self):
        """ Load graph builder sql

            sql file is first searched as package data. If not
            found then __file__ path  is searched

            :raises: SQLNotFoundError
        """
        # Try to get schema from ressources
        import pkg_resources
        
        srcpath = pkg_resources.resource_filename("morpheo","core","builders")
        sqlfile = os.path.join(srcpath, "build_graph.sql")
        if not os.path.exists(sqlfile):
            # If we are not in standard python installation,
            # try to get file locally
            sqlfile = os.path.join(os.path.dirname(__file__))

        if not os.path.exists(sqlfile):
            raise SQLNotFoundError("Cannot find file %s" % sqlfile)

        with open(sqlfile,'r') as f:
            sql = string.Template(f.read()).substitute(input_table=self._input_table)

        return sql

    def sanitize(self, snap_distance, min_edge_length ):
        """ Sanitize the input data
        """

    @staticmethod
    def from_shapefile( path, dbname=None ):
        """ Build graph from shapefile definition

            The method create a qgis layer. The layer is
            not owned by the builder and must be deleted 
            by the caller. 

            :param path: the path of the shapefile

            :returns: A Builder object
        """
        from qgis.core import QgsVectorLayer

        path = os.path.abspath(path)
        if not os.path.exists(path):
            raise FileNotFoundError("Shapefile not found: %s" % path)

        basename = os.path.basename(os.path.splitext(path)[0])
        layer    = QgsVectorLayer(path, basename, 'ogr' )

        if not layer.isValid():
            raise InvalidLayerError("Failed to load layer %s" % path)

        builder  = SpatialiteBuilder.from_layer(layer, dbname)
        return builder

    @staticmethod
    def from_layer( layer, dbname=None ):
        """ Build graph from qgis layer

            :param layer: a QGis layer to build the graph from
            :returns: A builder object
        """
        from qgis.core import QgsVectorFileWriter, QGis
        
        if layer.wkbType() not in (QGis.WKBLineString25D, QGis.WKBLineString) :
            raise InvalidLayerError("Invalid geometry type for input layer {}".format(layer.wkbType()))

        if layer.crs().geographicFlag():
            raise InvalidLayerError("Invalid CRS (lat/long) for inputlayer")

        dbname = dbname or 'morpheo_'+layer.name().replace(" ", "_") + '.sqlite'
        if os.path.isfile(dbname):
            logging.info("Removing existing database %s" % dbname)
            os.remove(dbname)

        # Create database from layer
        error = QgsVectorFileWriter.writeAsVectorFormat(layer, dbname, "utf-8", None, "SpatiaLite")
        if error != QgsVectorFileWriter.NoError:
            raise IOError("Failed to create database '{}': error {}".format(dbname, error))

        logging.info("Creating database '%s' from layer" % dbname)

        return SpatialiteBuilder(dbname)





