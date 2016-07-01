# -*- encoding=utf-8 -*-
""" Spatialite graph builder implementation
"""

import os
import logging
import string

from ..logger import log_progress

from .errors import BuilderError
from .sanitize import sanitize

class SQLNotFoundError(BuilderError):
    pass

class InvalidLayerError(BuilderError):
    pass

class FileNotFoundError(BuilderError):
    pass


def SQL( self, sql, **kwargs):
    sql = sql.format(**kwargs)
    logging.debug(sql)
    return sql


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
        self._input_table   = table or os.path.basename(os.path.splitext(dbname)[0]).lower()
        self._way_attribute = None

    def build_graph( self, snap_distance, min_edge_length, way_attribute=None ):
        """ Build morpheo topological graph

            This method will build the topological graph
            - The vertices table
            - The edges table

            :param snap_distance: The snap distance used to sanitize  the graph,
                 If the snap_distance is > 0 the graph will be sanitized (merge close vertices, 
                 remove unconnected features, the result will be a topological graph
            :param min_edge_length: The minimum edge length - edge below this length will be removed
            :param way_attribute: The attribute which will be used to build way from street name.
                If defined, this attribute has to be imported into the topological graph.
        """
        # sanitize graph
        if snap_distance > 0:
            logging.info("Builder: sanitizing graph")
            working_table = sanitize(self._conn, self._input_table, snap_distance, min_edge_length, 
                                     attribute=way_attribute)
        else:
            working_table = self._input_table
       
        self._way_attribute = way_attribute

        # Compute edges, way, vertices
        logging.info("Builder: Computing vertices and edges")

        self.execute_sql('edge_graph.sql', input_table=working_table)

        # Copy attribute to graph edge 
        if way_attribute:
            cur = self._conn.cursor()
            cur.execute(SQL("UPDATE edges SET NAME = ("
                                "SELECT {attribute} FROM {input_table} AS b "
                                "WHERE edges.OGC_FID = b.OGC_GID)",
                                input_table=working_table,
                                attribute=way_attribute))
        self._conn.commit()
        

    def build_ways(self,  threshold_angle, buffer_size, 
                   output_filei=None,
                   input_polygons=None,
                   output_loop_file=None):
        """ Build way's hypergraph

            :param threshold_angle:
            :param buffer_size:
            :param output_file: output shapefile to store results
            :param input_polygons: input polygon files for places
            :param output_loop_file: file to store computed loop polygons
        """
        raise NotImplementedError()

    def build_ways_from_attribute(self, output_file=None):
        """ Build way's hypergraph from street names.

            Note that the attribute name need to be spcified
            when  computing the topological graph

            :param output_file: Output shapefile to store result
        """
        if self._way_attribute is None:
            raise BuilderError("Way attribute is not defined !")

        raise NotImplementedError()

    def execute_sql(self, name, **kwargs):
        """ Execute statements from sql file
        """
        statements = self.load_sql(name, **kwargs).split(';')
        count = len(statements)
        cur   = self._conn.cursor()
        for i, statement in enumerate(statements):
            log_progress(i+1,count) 
            if statement:
                logging.debug(statement)
                cur.execute(statement)

    def load_sql(self, name, **kwargs):
        """ Load graph builder sql

            sql file is first searched as package data. If not
            found then __file__ path  is searched

            :raises: SQLNotFoundError
        """
        # Try to get schema from ressources
        import pkg_resources
        
        srcpath = pkg_resources.resource_filename("morpheo.core","builders")
        sqlfile = os.path.join(srcpath, name)
        if not os.path.exists(sqlfile):
            # If we are not in standard python installation,
            # try to get file locally
            logging.info("Builder: looking for sql file in %s" % __file__)
            sqlfile = os.path.join(os.path.dirname(__file__))

        if not os.path.exists(sqlfile):
            raise SQLNotFoundError("Cannot find file %s" % sqlfile)

        with open(sqlfile,'r') as f:
            sql = string.Template(f.read()).substitute(**kwargs)
        return sql

    @staticmethod
    def from_shapefile( path, dbname=None ):
        """ Build graph from shapefile definition

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





