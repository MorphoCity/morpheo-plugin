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
            logging.info("Places: building places from buffers (buffer size={})".format(buffer_size))
            self.creates_places_from_buffer(buffer_size, input_places )
            self._conn.commit()
        finally:
            pass
            #delete_table(self._conn, self.BUFFER_TABLE)


    def creates_places_from_buffer(self, buffer_size, input_places ):
        """ Creates places from buffer
        """
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

        cur.execute(SQLP("""
            INSERT INTO  {buffer_table}(GEOMETRY)
            SELECT ST_Union(ST_Buffer( GEOMETRY, {buffer_size})) AS GEOMETRY FROM vertices 
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
        """
        

