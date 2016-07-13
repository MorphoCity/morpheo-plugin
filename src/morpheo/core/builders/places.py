# -*- encoding=utf-8 -*-
""" Place builder helper
"""
import os
import logging

from functools import partial
from ..logger import log_progress

from .errors import BuilderError
from .sql import SQL, execute_sql, delete_table


class PlaceBuilder(object):

    BUFFER_TABLE='temp_buffer'

    def __init__(self, conn):
       self._conn = conn

    def build_places( self, buffer_size, input_places=None, loop_output=None):
        """ Build places

            Build places from buffer and/or external places definition.
            If buffer is defined and > 0 then a buffer is applied to all vertices for defining
            'virtual' places in the edge graph. 

            If places definition is used, these definition are used like the 'virtual' places definition. Intersecting
            places definition and 'virtual' places are merged. 

            :param buffer_size: buffer size applied to vertices
            :param input_places: path of an external shapefile containing places definitions
            :param loop_output: path of a shapefile to write computed places to.
        """

        # Use a minimum buffer_size
        buffer_size = max(buffer_size or 0, 0.1)

        try:
            self.creates_places_from_buffer(buffer_size, input_places )
            self.compute_edges()
            self._conn.commit()
        finally:
            delete_table(self._conn, self.BUFFER_TABLE)


    def creates_places_from_buffer(self, buffer_size, input_places ):
        """ Creates places from buffer
        """
        logging.info("Places: building places from buffers (buffer size={})".format(buffer_size))

        # Load temporary table definition
        delete_table(self._conn, self.BUFFER_TABLE)
        execute_sql(self._conn, "buffers.sql", buffer_table=self.BUFFER_TABLE, input_table="vertices")

        SQLP = partial(SQL,buffer_table=self.BUFFER_TABLE, buffer_size=buffer_size, input_places=input_places)

        cur = self._conn.cursor()

        cur.execute(SQLP("DELETE FROM places"))

        # Apply buffer to entities and merge them
        # This will make a one unique geometry that will be splitted into elementary
        # parts

        logging.info("Places: Creating buffers...")

        # Note that we exclude 'cul-de-sac' vertices from aggregation

        cur.execute(SQLP("""
            INSERT INTO  {buffer_table}(GEOMETRY)
            SELECT ST_Union(ST_Buffer( GEOMETRY, {buffer_size})) AS GEOMETRY FROM vertices
            WHERE DEGREE > 1
        """))

         # Explode buffer blob into elementary geometries
        cur.execute(SQLP("""
           INSERT INTO places(GEOMETRY)
           SELECT ST_ConvexHull(GEOMETRY) FROM ElementaryGeometries WHERE f_table_name='{buffer_table}' AND origin_rowid=1
        """))

        if input_places is not None:
            # Add input_places using the same merge ands split strategie
            # This will merge connexe input places as well as placse computed previously
            cur.execute(SQLP("DELETE FROM {buffer_table}"))
            cur.execute(SQLP("""
                INSERT INTO {buffer_table}(GEOMETRY)
                    SELECT ST_Union(geom) FROM (
                        SELECT GEOMETRY AS geom FROM places
                        UNION ALL
                        SELECT GEOMETRY AS geom FROM {input_places})
            """))
            # Split geometries again
            cur.execute(SQLP("DELETE FROM places"))
            cur.execute(SQLP("""
                INSERT INTO places(GEOMETRY)
                SELECT ST_MakePolygon(ST_ExteriorRing(GEOMETRY))
                FROM ElementaryGeometries WHERE f_table_name='{buffer_table}' AND origin_rowid=1
            """))

        # Checkout number of places
        rv = cur.execute(SQLP("Select Count(*) FROM places")).fetchone()[0]
        if rv <= 0:
            raise BuilderError("No places created ! please check input data !")
        else:
           logging.info("Places: created {} places".format(rv))
         
    def compute_edges(self):
        """ Compute edges between places

            This method compute a new graph from places as nodes, 
        """
        from qgis.core import QgsPoint

        logging.info("Building edges between places")
        execute_sql(self._conn, "places.sql")

        cur = self._conn.cursor()

        # Compute angles
        # Compute azimuth from egde end-points
        rows = cur.execute(SQL("""SELECT 
            fid,
            ST_X(ps1), ST_Y(ps1), ST_X(ps2), ST_Y(ps2),
            ST_X(ep1), ST_Y(ep1), ST_X(ep2), ST_Y(ep2)
            FROM (SELECT 
                OGC_FID AS fid,  
                ST_StartPoint(GEOMETRY) AS ps1, 
                ST_PointN(GEOMETRY,2) AS ps2,
                ST_EndPoint(GEOMETRY) AS ep1, 
                ST_PointN(GEOMETRY, ST_NumPoints(GEOMETRY)-1) AS ep2
                FROM place_edges)
        """)).fetchall()

        p1,p2 = QgsPoint(), QgsPoint()
        def calc_azimuth(x1,y1,x2,y2):
            p1.set(x1,y1)
            p2.set(x2,y2)
            return p1.azimuth(p2)

        azimuths = [(r[0],calc_azimuth(*r[1:5]),calc_azimuth(*r[5:9])) for r in rows]


    

