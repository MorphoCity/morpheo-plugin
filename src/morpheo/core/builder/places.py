# -*- encoding=utf-8 -*-
""" Place builder helper
"""
from __future__ import print_function

import os
import logging

from ..logger import log_progress

from .errors import BuilderError
from .sql import SQL, execute_sql, delete_table, connect_database

BUFFER_TABLE='temp_buffer'


class PlaceBuilder(object):


    def __init__(self, conn, dbname, chunks=100):
       self._conn   = conn
       self._dbname = dbname
       self._chunks = chunks

    def build_places( self, buffer_size, input_places=None):
        """ Build places

            Build places from buffer and/or external places definition.
            If buffer is defined and > 0 then a buffer is applied to all vertices for defining
            'virtual' places in the edge graph. 

            If places definition is used, these definition are used like the 'virtual' places definition. Intersecting
            places definition and 'virtual' places are merged. 

            :param buffer_size: buffer size applied to vertices
            :param input_places: path of an external shapefile containing places definitions
        """

        # Use a minimum buffer_size
        buffer_size = buffer_size or 0

        try:
            if buffer_size > 0:
                self.creates_places_from_buffer(buffer_size, input_places )
            else:
                self.creates_places_from_file(input_places)
            logging.info("Building edges between places")
            execute_sql(self._conn, "places.sql")
            self._conn.commit()
        finally:
            pass
            #delete_table(self._conn, BUFFER_TABLE)


    def creates_places_from_file(self, input_places):
        """ Create places from input  file
        """
        cur = self._conn.cursor()
        cur.execute(SQL("DELETE FROM places"))
        cur.execute(SQL("INSERT INTO places(GEOMETRY) SELECT GEOMETRY FROM {input_table}",
                    input_table=input_places))


    def creates_places_from_buffer(self, buffer_size, input_places ):
        """ Creates places from buffer
        """
        logging.info("Places: building places from buffers (buffer size={})".format(buffer_size))

        # Load temporary table definition
        delete_table(self._conn, BUFFER_TABLE)
        execute_sql(self._conn, "buffers.sql", quiet=True, buffer_table=BUFFER_TABLE, input_table="vertices")

        cur = self._conn.cursor()

        cur.execute(SQL("DELETE FROM places"))

        # Apply buffer to entities and merge them
        # This will make a one unique geometry that will be splitted into elementary
        # parts

        logging.info("Places: Creating buffers...")

        # Note that we exclude 'cul-de-sac' vertices from aggregation

        cur.execute(SQL("""
                INSERT INTO {buffer_table}(GEOMETRY)
                SELECT ST_Multi(ST_Buffer( GEOMETRY, {buffer_size})) FROM vertices
                WHERE DEGREE > 1
            """, buffer_table=BUFFER_TABLE, buffer_size=buffer_size))

        def union_buffers( input_table ):
            table = 'temp_buffer_table' 
            # Create temporary buffer table

            delete_table(self._conn, table)
            execute_sql(self._conn, "buffers.sql", quiet=True, buffer_table=table, input_table=input_table)
        
            count = cur.execute(SQL("SELECT Max(OGC_FID) FROM {input_table}", input_table=input_table)).fetchone()[0]
            size  = count / self._chunks
            def iter_chunks():
                start = 1
                while start <= count:
                    yield (start, start+size)
                    start = start+size

            logging.info("Places: Building union of buffers")

            for start, end in iter_chunks():
                cur.execute(SQL("""
                    INSERT INTO  {tmp_table}(GEOMETRY)
                    SELECT ST_Union(GEOMETRY) AS GEOMETRY FROM {input_table}
                    WHERE OGC_FID>={start} AND OGC_FID < {end}
                """, tmp_table=table, input_table=input_table, buffer_size=buffer_size, start=start, end=end))
                log_progress( end, count )
            # Final merge into buffer_table
            logging.info("Places: finalizing union...")
            cur.execute(SQL("DELETE FROM {buffer_table}", buffer_table=BUFFER_TABLE))
            cur.execute(SQL("""
                INSERT INTO  {buffer_table}(GEOMETRY)
                SELECT ST_Union(GEOMETRY)  FROM {tmp_table}
            """, tmp_table=table, buffer_table=BUFFER_TABLE))
           
        union_buffers(BUFFER_TABLE)

        # Explode buffer blob into elementary geometries
        logging.info("Places: computing convex hulls")
        cur.execute(SQL("""
           INSERT INTO places(GEOMETRY)
           SELECT ST_ConvexHull(GEOMETRY) FROM ElementaryGeometries WHERE f_table_name='{buffer_table}' AND origin_rowid=1
        """, buffer_table=BUFFER_TABLE))

        self._conn.commit()

        if input_places is not None:
            # Add input_places using the same merge ands split strategie
            # This will merge connexe input places as well as places computed previously
            logging.info("Places: adding external places geometries") 
            cur.execute(SQL("DELETE FROM {buffer_table}", buffer_table=BUFFER_TABLE))
            cur.execute(SQL("""
                INSERT INTO {buffer_table}(GEOMETRY)
                    SELECT ST_Multi(geom) FROM (
                        SELECT GEOMETRY AS geom FROM places
                        UNION ALL
                        SELECT CastToXYZ(GEOMETRY) AS geom FROM {input_places})
            """, buffer_table=BUFFER_TABLE, input_places=input_places))
            union_buffers(BUFFER_TABLE)
            # Split geometries again
            cur.execute(SQL("DELETE FROM places"))
            cur.execute(SQL("""
                INSERT INTO places(GEOMETRY)
                SELECT ST_MakePolygon(ST_ExteriorRing(GEOMETRY))
                FROM ElementaryGeometries WHERE f_table_name='{buffer_table}' AND origin_rowid=1
            """, buffer_table=BUFFER_TABLE))

        # Checkout number of places
        rv = cur.execute(SQL("Select Count(*) FROM places")).fetchone()[0]
        if rv <= 0:
            raise BuilderError("No places created ! please check input data !")
        else:
           logging.info("Places: created {} places".format(rv))
         
           

