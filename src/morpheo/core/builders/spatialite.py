""" Spatialite builder implementation
"""
from pyspatialite import dbapi2 as db

import os
import logging

class SpatialiteBuilder(object):

    
    def __init__(self, dbname, table, build_graph=False):
        """ Initialize builder

            :param dbname: the path of the database
            :param load_schema: Reload the schema when initializing graph
        """
        self._conn = db.connect(dbname)
        self._build_graph = build_graph

    def build_graph( self, snap_distance, min_edge_length ):
        """ Load database schema
        """
        # sanitize graph
        self.sanitize(snap_distance, min_edge_length)

        # Try to get schema from ressources
        import pkg_resources
        
        srcpath = pkg_resources.resource_filename("morpheo","core","builders")
        sqlfile = os.path.join(srcpath, "build_graph.sql")
    
    def sanitize(self, snap_distance, min_edge_length ):
        """ Sanitize the input data

            The method will compute the following:
                
                - Remove unconnected features
                - Snap close geometries
                - Resolve intersection
        """
        self.remove_unconnected_features()
        self.snap_geometries(snap_distance)
        self.resolve_intersection()d
        self.remove_small_edges(min_edge_length)

    @staticmethod
    def from_shapefile( path, dbname=None ):
        """ Build graph from shapefile definition

            The method create a qgis layer. The layer is
            not owned by the builder and must be deleted 
            by the caller. 

            :param path: the path of the shapefile

            :returns: A qgis layer
        """
        from qgis.core import QgsVectorLayer

        basename = os,path.basename(os.path.splitext(path)[0])
        layer    = QgisVectorLayer(path, basename, 'ogr' )

        builder  = Builder.from_layer(layer, dbname)
        return builder

    @staticmethod
    def from_layer( layer, dbname=None ):
        """ Build graph from qgis layer

            :param layer: a QGis layer to build the graph from
        """
        from qgis.core import qgsvectorfilewriter        

        dbname = dbname or 'morpheo_'+layer.name().replace(" ", "_") + '.sqlite'
        if os.path.isfile(dbname):
            logging.warning("Removing existing database %s" % dbname)
            os.remove(dbname)
    
        # Create database from layer
        logging.info("Creating database %s from layer")
        QgsVectorFileWriter.writeAsVectorFormat(layer, dbname, "utf-8", None, "SQLite", False, None,
                                                ["SPATIALITE=YES", ])

        raw_data_table = os.path.basename(os.path.splitext(dbname)[0])
        return Builder(dbname, table=raw_data_table, build_graph=True)

    def remove_small_edges(self, min_edge_length):
        """ Remove small egdes and merge extremities

            All edges below min_edge_length will be removed an connected vertices
            will be merged at the centroid position of the removed geometry.
    
            :param min_edge_length: the minimun length for edges
        """
        raise NotImplementedError()

        
     def delete_unconnected_features(self):
        """
        """
        raise NotImplementedError()

    def snap_geometries(self, snap_distance):
        """
        """
        raise NotImplementedError()

    def resolve_intersections(self)
        """
        """
        raise NotImplementedError()


