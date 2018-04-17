# -*- encoding=utf-8 -*-
""" Spatialite graph builder implementation
"""

import os
import logging

from .logger import log_progress
from .errors import BuilderError, FileNotFoundError, DatabaseNotFound
from .sql import SQL, execute_sql, delete_table, connect_database, set_srid
from .layers import check_layer, import_as_layer, import_shapefile, export_shapefile
from .sanitize import sanitize


class SpatialiteBuilder(object):

    version     = "1.0"
    description = "Spatialite graph builder"

    def __init__(self, dbname, table=None):
        """ Initialize builder

            :param dbname: the path of the database
            :param table: name of the table containing input data
        """
        logging.info("Opening database %s" % dbname)
        self._conn     = connect_database(dbname)
        self._dbname   = dbname
        self._basename = os.path.basename(os.path.splitext(dbname)[0])

        self._input_table   = table or self._basename.lower()
        self._way_builder = None

    @property
    def way_builder(self):
        if self._way_builder is None:
            from .ways import WayBuilder
            self._way_builder = WayBuilder(self._conn)
        return self._way_builder

    @property
    def connection(self):
        return self._conn

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

            cur.close()
            if output is not None:
                self._conn.commit()
                logging.info("Builder saving sanitized graph")
                export_shapefile(self._dbname, working_table, output)
        else:
            working_table = self._input_table

        # Compute edges, way, vertices
        logging.info("Builder: Computing vertices and edges")

        self.execute_sql('graph.sql', input_table=working_table)

        # Copy attribute to graph edge
        if way_attribute:
            cur = self._conn.cursor()
            cur.execute(SQL("UPDATE edges SET NAME = ("
                            "SELECT {attribute} FROM {input_table} AS b "
                            "WHERE edges.OGC_FID = b.OGC_FID)",
                            input_table=working_table,
                            attribute=way_attribute))
            cur.close()

        # Update parameters

        self._conn.commit()
        if output is not None:
            logging.info("Builder: saving edges and vertices")
            export_shapefile(self._dbname, 'edges'   , output)
            export_shapefile(self._dbname, 'vertices', output)

            self.write_manifest(output,'build', 
                                snap_distance=snap_distance, 
                                min_edge_length=min_edge_length) 
            

    def write_manifest(self, output, suffix, **kwargs):
        """ Write  manifest as key=value file 
        """
        with open(os.path.join(output, "%s_%s.manifest" % (self._basename,suffix)),'w') as f:
            for k,v in kwargs.items():
                f.write("{}={}\n".format(k,v))

    def build_edges_graph(self, output):
        """ Build and export edge graph
        """
        from .places import build_edges_graph
        build_edges_graph(self._conn, output)

    def build_ways_graph(self, output):
        """ Build and export way line graph
        """
        builder = self.way_builder
        builder.save_line_graph(output, create=True)

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
        from .places import PlaceBuilder
        input_places_table = None
        if places is not None:
            input_places_table = 'input_places'
            # Delete table it it exists
            delete_table( self._conn.cursor(), input_places_table )
            import_as_layer( self._dbname, places, input_places_table)
            # Force srid
            set_srid(self._conn.cursor(), input_places_table, 'vertices')

        builder = PlaceBuilder(self._conn)
        builder.build_places(buffer_size, input_places_table)

        if output is not None:
            builder.export(self._dbname, output, export_graph=True)
            self.write_manifest(output,'places', buffer_size=buffer_size, input_file=places)

    def build_ways(self,  threshold, output=None, attributes=False, rtopo=False, **kwargs) :
        """ Build way's hypergraph

            :param threshold: Angle treshold
            :param output: output shapefile to store results
            :param attributes: compute attributes
        """
        builder = self.way_builder
        builder.build_ways(threshold)

        if rtopo:
            builder.compute_topological_radius()

        if attributes:
            self.compute_way_attributes( **kwargs )

        if output is not None:
            builder.export(self._dbname, output, export_graph=True)
            self.write_manifest(output,'ways', angle_threshold=threshold)


    def compute_way_attributes( self, orthogonality, betweenness, closeness, stress,
                                classes=10, rtopo=False, output=None):
        """ Compute attributes for ways:

            :param orthogonality: If True, compute orthogonality.
            :param betweenness:   If True, compute betweenness centrality.
            :param stress:        If True, compute stress centrality.
            :param closeness:     If True, compute closeness.
        """
        builder = self.way_builder
        builder.compute_local_attributes(orthogonality = orthogonality, classes=classes)

        if rtopo:
            builder.compute_topological_radius()

        if any((betweenness, closeness, stress)):
            builder.compute_global_attributes(
                    betweenness = betweenness,
                    closeness   = closeness,
                    stress      = stress,
                    classes     = classes)

        if output is not None:
            builder.export(self._dbname, output)

    def compute_edge_attributes( self, path, orthogonality, betweenness, closeness, stress,
                                 classes=10, output=None):
        """ Compute attributes for edges:

            :param orthogonality: If True, compute orthogonality.
            :param betweenness:   If True, compute betweenness centrality.
            :param stress:        If True, compute stress centrality.
            :param closeness:     If True, compute closeness.
        """
        import edge_properties as props
        props.compute_local_attributes(self._conn,orthogonality = orthogonality, classes=classes)

        if any((betweenness, closeness, stress)):
            props.compute_global_attributes(
                    self._conn,
                    path,
                    betweenness = betweenness,
                    closeness   = closeness,
                    stress      = stress,
                    classes     = classes)

        if output is not None:
            export_shapefile(self._dbname, 'place_edges', output)


    def build_ways_from_attribute(self, attribute, output=None, attributes=False, rtopo=False,
                   export_graph=False, **kwargs):
        """ Build way's hypergraph from street names.

            Note that the attribute name need to be spcified
            when  computing the topological graph

            :param output_file: Output shapefile to store result
        """
        builder = self.way_builder
        builder.build_ways_from_attribute(attribute)

        if rtopo:
            builder.compute_topological_radius()

        if attributes:
            self.compute_way_attributes( **kwargs )

        if output is not None:
            builder.export(self._dbname, output, export_graph=export_graph)


    def execute_sql(self, name, **kwargs):
        """ Execute statements from sql file
        """
        execute_sql(self._conn, name, **kwargs)

    def way_graph(self):
        """ Return the way line graph
        """
        return self.way_builder.get_line_graph()

    @staticmethod
    def from_shapefile( path, dbname=None ):
        """ Build graph from shapefile definition

            :param path: The path of the shapefile
            :param dbname: Optional name of the output database (default to file basename)
            :returns: A Builder object
        """
        basename = os.path.basename(os.path.splitext(path)[0])

        dbname = dbname or 'morpheo_'+basename.replace(" ", "_")
        dbname = dbname + '.sqlite'
        if os.path.isfile(dbname):
            logging.info("Removing existing database %s" % dbname)
            os.remove(dbname)

        layername = os.path.basename(os.path.splitext(dbname)[0]).lower()
        import_shapefile( dbname, path, layername, forceSinglePartGeometryType=True)
        return SpatialiteBuilder(dbname)

    @staticmethod
    def from_layer( layer, dbname=None ):
        """ Build graph from qgis layer

            :param layer: A QGis layer to build the graph from
            :returns: A builder object
        """
        from qgis.core import QgsVectorFileWriter, QGis

        check_layer(layer, (QGis.WKBLineString25D, QGis.WKBLineString))

        name   = dbname or 'morpheo_'+layer.name().replace(" ", "_")
        dbname = name + '.sqlite'
        if os.path.isfile(dbname):
            logging.info("Removing existing database %s" % dbname)
            os.remove(dbname)

        # Create database from layer
        logging.info("Creating database '%s' from layer" % dbname)
        #import_as_layer( dbname, layer, name, forceSinglePartGeometryType=True )
        error = QgsVectorFileWriter.writeAsVectorFormat(layer, dbname, "utf-8", None, "SpatiaLite")
        if error != QgsVectorFileWriter.NoError:
            raise IOError(u"Failed to create database '{}': error {}".format(dbname, error))

        return SpatialiteBuilder(dbname)

    @staticmethod
    def from_database( dbname ):
        """" Open existing database

             :param dbname: Path of the database:
             :returns: A builder object
        """
        dbname = dbname + '.sqlite'
        if not os.path.isfile( dbname ):
            raise DatabaseNotFound(dbname)

        return SpatialiteBuilder(dbname)






