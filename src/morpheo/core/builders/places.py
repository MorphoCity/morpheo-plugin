# -*- encoding=utf-8 -*-
""" Place builder helper
"""
from __future__ import print_function

import os
import logging

from functools import partial
from itertools import takewhile
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
            logging.info("Building edges between places")
            execute_sql(self._conn, "places.sql")
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
         
    def build_ways(self, threshold):
        """ Compute ways

            Pair edges for each place then resolve pairing as a partitioning
            set: each resulting classes will be a way. 
        """
        import numpy as np
        from qgis.core import QgsPoint
        from .angles import (create_partition, resolve, update, num_partitions, get_index_table,
                             create_matrix, pop_argmin, next_argmin, get_value, pop_args,
                             angle_from_azimuth)
                                 
        cur  = self._conn.cursor()

        # Get the (max) number of edges and places
        max_edges  = cur.execute("SELECT Max(OGC_FID) from place_edges").fetchone()[0]
        max_places = cur.execute("SELECT Max(OGC_FID) from places").fetchone()[0] 

        # Get the nb_vertices for places
        # We use an index array instead of a dictionnary
        # This will hold as long as fid is a auto-incremented index 
        vertices = np.zeros(max_places+1, dtype=int)
        rows     = cur.execute("SELECT OGC_FID, NB_VTX from places").fetchall()
        vertices[[r[0] for r in rows]] = [r[1] for r in rows]   

        rows = cur.execute(SQL("""SELECT 
            pl, fid, ST_X(p1), ST_Y(p1), ST_X(p2), ST_Y(p2)
            FROM (
                SELECT 
                OGC_FID AS fid,
                START_PL AS pl,
                ST_StartPoint(GEOMETRY) AS p1, 
                ST_PointN(GEOMETRY,2) AS p2
                FROM place_edges
            UNION ALL
                SELECT 
                OGC_FID AS fid,
                END_PL AS pl,
                ST_EndPoint(GEOMETRY) AS p1, 
                ST_PointN(GEOMETRY, ST_NumPoints(GEOMETRY)-1) AS p2
                FROM place_edges)
            ORDER BY pl
        """)).fetchall()

        p1,p2 = QgsPoint(), QgsPoint()
        def azimuth(x1,y1,x2,y2):
            p1.set(x1,y1)
            p2.set(x2,y2)
            return p1.azimuth(p2) / 180.0 * np.pi

        def distance(x1,y1,x2,y2):
            p1.set(x1,y1)
            p2.set(x2,y2)
            return np.sqrt(p1.sqrDist(p2))

        def deviation( az1, x1, y1, az2, x2, y2 ):
            """ Computei deviation  coefficient 

                C.Lagesse, ph.d thesis, p. 151
            """
            a1 = azimuth(x1,y1,x2,y2)
            a2 = azimuth(x2,y2,x1,y1)
            d  = distance(x1,y1,x2,y2)
            return (abs( np.sin(angle_from_azimuth(az1,a1))) +
                    abs( np.sin(angle_from_azimuth(az2,a2)))) * d 

        edges_az = [(r[0],r[1],azimuth(*r[2:]),r[2],r[3]) for r in rows]

        def compute_angles( edges ):
            return create_matrix(edges, lambda e1,e2: angle_from_azimuth(e1[2],e2[2]))

        def compute_coeffs( edges ):
            return create_matrix(edges, lambda e1,e2: deviation(e1[2], e1[3], e1[4],
                                                                e2[2], e2[3], e2[4]))

        # Compute candidates pair for each places
        # Each edge is given a way number, 
        # Places with degree=2 are automatically paired together
        
        def places():
            s = 0
            while s<len(rows):
                p = edges_az[s][0]
                l = list(takewhile(lambda x: x[0]==p, edges_az[s:]))
                s = s+len(l)
                yield p,l
       
        # Way partition
        ways = create_partition(max_edges+1)
        def add_pair( e1, e2 ):
            resolve(ways,e1[1],e2[1])

        num_places = 0
        for place, edges in places():
            n = len(edges)
            num_places = num_places+1
            if n>2:
                # Compute pairing
                # Compute angles between edges
                angles = compute_angles(edges)
                # compute coeffs between edges
                coeffs = compute_coeffs(edges)
                for e1,e2 in next_argmin(coeffs):
                    if get_value(angles,e1,e2) < threshold: 
                        add_pair(e1,e2)
                        pop_args(coeffs,e1,e2)
            elif n==2:
                # pair those 2 edge
                add_pair(edges[0],edges[1]) 
            else:
                # No pairing: place has only one edge.
                pass
                  
        # Update partition
        update(ways)
        num_ways = num_partitions(ways)

        logging.info("Computed {} ways (num places={}, num edges={})".format(num_ways,num_places,max_edges))
       
        # Write back ways
        cur.execute(SQL("DELETE FROM way_partition"))
        cur.executemany(SQL("INSERT INTO way_partition(PEDGE,WAY) SELECT ?,?"),
                [(fid,way) for fid,way in enumerate(ways)])

        logging.info("Updating place edges with way id") 
        cur.execute(SQL("""UPDATE place_edges
            SET WAY = (SELECT WAY FROM way_partition WHERE PEDGE=place_edges.OGC_FID)
        """))

        logging.info("Build ways table")
        execute_sql(self._conn, "ways.sql")

        self._conn.commit()
        return num_ways
        
    

