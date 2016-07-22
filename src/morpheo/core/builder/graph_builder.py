# -*- encoding=utf-8 -*-
""" Spatialite graph builder implementation
"""

import os
import logging

from ..logger import log_progress

from .errors import BuilderError
from .sql import SQL, execute_sql, delete_table
from .layers import check_layer, open_shapefile, import_shapefile, export_shapefile
from .sanitize import sanitize


class InvalidLayerError(BuilderError):
    pass

class FileNotFoundError(BuilderError):
    pass

class DatabaseNotFound(BuilderError):
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
        self._dbname   = dbname
        self._basename = os.path.basename(os.path.splitext(dbname)[0])

        self._input_table   = table or self._basename.lower()
        self._ways_output   = None
        self._way_build_attribute = None

    def build_graph( self, snap_distance, min_edge_length, way_attribute=None, output=None ):
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
            # Because we still have rounding errors 
            # We need to round coordinates using
            
            precision = snap_distance/2.0
  
            logging.info("Builder: rounding coordinates to {} m precision".format(precision)) 
            cur = self._conn.cursor()
            cur.execute(SQL("UPDATE {table} SET"
                            " GEOMETRY = (SELECT ST_SnapToGrid({table}.GEOMETRY,{prec}))",
                            table=working_table,
                            prec=precision))

            if output is not None:
                logging.info("Builder saving sanitized graph")
                export_shapefile(self._dbname, working_table, output)
        else:
            working_table = self._input_table
       
        self._way_build_attribute = way_attribute

        # Compute edges, way, vertices
        logging.info("Builder: Computing vertices and edges")

        self.execute_sql('graph.sql', input_table=working_table)

        # Copy attribute to graph edge 
        if way_attribute:
            cur = self._conn.cursor()
            cur.execute(SQL("UPDATE edges SET NAME = ("
                                "SELECT {attribute} FROM {input_table} AS b "
                                "WHERE edges.OGC_FID = b.OGC_GID)",
                                input_table=working_table,
                                attribute=way_attribute))
        self._conn.commit()

    def build_places(self, buffer_size, places=None, output=None):
        """ Build places
            
            Build places from buffer and/or external places definition.
            If buffer is defined and > 0 then a buffer is applied to all vertices for defining
            'virtual' places in the edge graph. 

            If places definition is used, these definition are used like the 'virtual' places definition. Intersecting
            places definition and 'virtual' places are merged. 

            :param buffer_size: buffer size applied to vertices
            :param places: path of an external shapefile containing places definitions
            :param output: path of a shapefile to write computed places to.
        """
        input_places_table = None
        if places is not None:
            input_places_table = 'input_places'
            # Open the places shapefile and insert in as 'input_places' table
            from qgis.core import QGis
            # Delete table it it exists
            delete_table( self._conn, input_places_table )
            # Add shapefile
            import_shapefile( self._dbname, places, input_places_table, (QGis.WKBPolygon25D, QGis.WKBPolygon))

        from places import PlaceBuilder
        builder = PlaceBuilder(self._conn)
        builder.build_places(buffer_size, input_places_table) 

        if output is not None:
            logging.info("Builder: Saving places to %s" % output)
            export_shapefile(self._dbname, 'places', output)

    def export_ways(self):
        """ Export ways to shapefile
        """
        if self._ways_output is not None:
            export_shapefile(self._dbname, 'ways', self._ways_output)

    def build_ways(self,  threshold, output=None, attributes=False, **kwargs) :
        """ Build way's hypergraph

            :param threshold: Angle treshold
            :param output: output shapefile to store results
            :param attributes: compute attributes
        """
        from ways import WayBuilder
        builder = WayBuilder(self._conn)
        builder.build_ways(threshold)

        if attributes:
            self.compute_way_attributes( **kwargs )

        self._ways_output = output
        self.export_ways()

    def compute_way_attributes( self, orthogonality, betweenness, closeness, stress):
        """ Compute attributes for ways:

            :param orthogonality: If True, compute orthogonality.
            :param betweenness:   If True, compute betweenness centrality.
            :param stress:        If True, compute stress centrality.
            :param closeness:     If True, compute closeness.
        """
        from ways import WayBuilder
        builder = WayBuilder(self._conn)
        builder.compute_local_attributes(orthogonality = orthogonality)
        if any((betweenness, closeness, stress)):
            builder.compute_global_attributes(
                    betweenness = betweenness,
                    closeness   = closeness,
                    stress      = stress)


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
            :param dbname: Optional name of the output database (default to file basename)
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
        




