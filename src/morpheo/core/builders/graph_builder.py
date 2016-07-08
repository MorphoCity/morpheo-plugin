# -*- encoding=utf-8 -*-
""" Spatialite graph builder implementation
"""

import os
import logging

from ..logger import log_progress

from .errors import BuilderError
from .sql import SQL, execute_sql, delete_table
from .sanitize import sanitize


class InvalidLayerError(BuilderError):
    pass

class FileNotFoundError(BuilderError):
    pass

class DatabaseNotFound(BuilderError):
    pass


def check_layer(layer, wkbtypes):
    """ Check layer validity
    """
    if wkbtypes and layer.wkbType() not in wkbtypes:
        raise InvalidLayerError("Invalid geometry type for layer {}".format(layer.wkbType()))

    if layer.crs().geographicFlag():
       raise InvalidLayerError("Invalid CRS (lat/long) for layer")


def open_shapefile( path, name ):
    """ Open a shapefile as a qgis layer
    """
    from qgis.core import QgsVectorLayer

    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError("Shapefile not found: %s" % path)

    layer = QgsVectorLayer(path, name, 'ogr' )
    if not layer.isValid():
        raise InvalidLayerError("Failed to load layer %s" % path)

    return layer


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
        self._dbname = dbname

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

    def add_shapefile( self, path, name, wkbtypes ):
        """ Add shapefile as new table in database
        """
        from subprocess import call

        # Delete table it it exists
        delete_table( self._conn, name )

        layer = open_shapefile(path, name)
        check_layer(layer, wkbtypes)

        # Append layer to  database
        ogr2ogr = os.environ['OGR2OGR']
        rc = call([ogr2ogr,'-update', self._dbname, path, '-nln', name]) 
        if rc != 0:
            raise IOError("Failed to add layer to database '{}'".format(self._dbname))

    def build_places(self, buffer_size, places=None, loop_output=None):
        """ Build places
            
            Build places from buffer and/or external places definition.
            If buffer is defined and > 0 then a buffer is applied to all vertices for defining
            'virtual' places in the edge graph. 

            If places definition is used, these definition are used like the 'virtual' places definition. Intersecting
            places definition and 'virtual' places are merged. 

            :param buffer_size: buffer size applied to vertices
            :param places: path of an external shapefile containing places definitions
            :param loop_output: path of a shapefile to write computed places to.
        """
        if places is not None:
            # Open the places shapefile and insert in as 'input_places' table
            from qgis.core import QGis
            self.add_shapefile( places, 'input_places', (QGis.WKBPolygon25D, QGis.WKBPolygon))

        from places import PlaceBuilder
        builder = PlaceBuilder(self._conn)
        builder.build_places(buffer_size, 'input_places', loop_output=loop_output) 

    def build_ways(self,  threshold, buffer_size, 
                   output=None,
                   places=None,
                   loop_output=None):
        """ Build way's hypergraph

            :param threshold: 
            :param buffer_size:
            :param output: output shapefile to store results
            :param places: input polygon files for places
            :param loop_output: file to store computed loop polygons
        """
        raise NotImplementedError()
        

    def build_ways_from_attribute(self, output=None):
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
        execute_sql(self._conn, name, **kwargs)

    @staticmethod
    def from_shapefile( path, dbname=None ):
        """ Build graph from shapefile definition

            :param path: The path of the shapefile
            :returns: A Builder object
        """
        basename = os.path.basename(os.path.splitext(path)[0])
        layer    = open_shapefile( path, basename) 
        builder  = SpatialiteBuilder.from_layer(layer, dbname)
        return builder

    @staticmethod
    def from_layer( layer, dbname=None ):
        """ Build graph from qgis layer

            :param layer: A QGis layer to build the graph from
            :returns: A builder object
        """
        from qgis.core import QgsVectorFileWriter, QGis
       
        check_layer(layer, (QGis.WKBLineString25D, QGis.WKBLineString))

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

    @staticmethod
    def from_database( dbname ):
        """" Open existing database 

             :param dbname: Path of the database:
             :returns: A builder object
        """
        if not os.path.isfile( dbname ):
            raise DatabaseNotFound(dbname)
        
        return SpatialiteBuilder(dbname)
        





