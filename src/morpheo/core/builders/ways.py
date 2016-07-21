# -*- encoding=utf-8 -*-
""" Place builder helper
"""
from __future__ import print_function

import os
import logging


import numpy as np

from numpy import sin
from functools import partial
from itertools import takewhile
from ..logger import log_progress

from .errors import BuilderError
from .sql import SQL, execute_sql, delete_table


class WayBuilder(object):

    def __init__(self, conn):

       from qgis.core import QgsPoint
       self._conn = conn

       # Define helper functions
       p1,p2 = QgsPoint(), QgsPoint()
       def azimuth(x1,y1,x2,y2):
           p1.set(x1,y1)
           p2.set(x2,y2)
           return p1.azimuth(p2) / 180.0 * np.pi

       def distance(x1,y1,x2,y2):
           p1.set(x1,y1)
           p2.set(x2,y2)
           return np.sqrt(p1.sqrDist(p2))

       self.azimuth  = azimuth
       self.distance = distance

    def build_ways(self, threshold):
        """ Compute ways

            Pair edges for each place then resolve pairing as a partitioning
            set: each resulting classes will be a way.

            :params threshold: The angle threshold (in radian) for pairing edges at each place.
        """
        from .angles import (create_partition, resolve, update, num_partitions, get_index_table,
                             create_matrix, next_argmin, get_value, pop_args, get_remaining_elements,
                             angle_from_azimuth)
       
        # Dereference helper functions
        azimuth  = self.azimuth
        distance = self.distance

        cur = self._conn.cursor()

        # Get the (max) number of edges and places
        max_edges  = cur.execute("SELECT Max(OGC_FID) from place_edges").fetchone()[0]
        max_places = cur.execute("SELECT Max(OGC_FID) from places").fetchone()[0] 

        # Get the entry vector for edges in each place
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

        def deviation( az1, x1, y1, az2, x2, y2 ):
            """ Computei deviation  coefficient 

                C.Lagesse, ph.d thesis, p. 151
            """
            a1 = azimuth(x1,y1,x2,y2)
            a2 = azimuth(x2,y2,x1,y1)
            d  = distance(x1,y1,x2,y2)
            return (abs( sin(angle_from_azimuth(az1,a1))) +
                    abs( sin(angle_from_azimuth(az2,a2)))) * d 

        edges_az = [(r[0],r[1],azimuth(*r[2:6]),r[2],r[3]) for r in rows]

        def compute_angles( edges ):
            return create_matrix(edges, lambda e1,e2: angle_from_azimuth(e1[2],e2[2]))

        def compute_coeffs( edges ):
            return create_matrix(edges, lambda e1,e2: deviation(e1[2], e1[3], e1[4],
                                                                e2[2], e2[3], e2[4]))

        # Compute candidates pair for each places
        # Each edge is given a way number, 
        # Places with degree=2 are automatically paired together

        # Iterate through places, returning the set of edges/vector for
        # that place
        def places():
            s = 0
            while s<len(rows):
                p = edges_az[s][0]
                l = list(takewhile(lambda x: x[0]==p, edges_az[s:]))
                s = s+len(l)
                yield p,l
 
        # Array to store distance corrections for ways
        distances = np.zeros(max_edges+1)
       
        # Array to store starting places
        startplaces = np.zeros(max_edges+1, dtype=int)
        endplaces   = np.zeros(max_edges+1, dtype=int)

        def add_end( e, place ):
            fid = e[1]
            if startplaces[fid] == 0: 
                startplaces[fid] = place
            else:
                if endplaces[fid] != 0:
                    logging.error("build_way: extraneous end place for edge {}".format(fid))
                    raise BuilderError("Cannot set more than two ends for one way") 
                endplaces[fid] = place

        # Way partition: resolve each pair by assigning them
        # to the same equivalent class. Partition are computed 
        # by resolving transitive relationship. 
        ways = create_partition(max_edges+1)
        def add_pair( e1, e2 ):
            resolve(ways,e1[1],e2[1])
            # Compute distance correction
            # Split the distance between the two paired edges
            # The correction will be the sum of all values for the same way
            d = distance(e1[3],e1[4],e2[3],e2[4])
            distances[e1[1]] = distances[e1[1]] + d/2.0
            distances[e2[1]] = distances[e2[1]] + d/2.0

        num_places = 0
        for place, edges in places():
            n = len(edges)
            num_places = num_places+1
            if n>2:
                # Compute angles between edges
                angles = compute_angles(edges)
                # compute coeffs between edges
                coeffs = compute_coeffs(edges)
                for e1,e2 in next_argmin(coeffs):
                    if get_value(angles,e1,e2) < threshold: 
                        add_pair(e1,e2)
                        pop_args(coeffs,e1,e2)
                # Store end places from lonely edges
                for e in get_remaining_elements(coeffs):
                    add_end(e,place)
            elif n==2:
                # pair those 2 edge
                add_pair(edges[0],edges[1]) 
            else:
                # No pairing: place has only one edge.
                add_end(edges[0],place)

        # Update partition
        update(ways)
        num_ways = num_partitions(ways)

        logging.info("Computed {} ways (num places={}, num edges={})".format(num_ways,num_places,max_edges))
        
        self._build_way_table(cur, ways, distances, startplaces, endplaces)
        self._conn.commit()
        return num_ways
        
    def _build_way_table( self, cur, ways, distances, startplaces, endplaces ):
        """ Write back way partition

            Create a table holding the partition mapping for edges. The table
            also contains the distance corrections.
        """
        cur.execute(SQL("DELETE FROM way_partition"))
        cur.executemany(SQL("INSERT INTO way_partition(PEDGE,WAY,DIST,START_PL,END_PL) SELECT ?,?,?,?,?"),
                [(fid,way,distances[fid],startplaces[fid],endplaces[fid]) for fid,way in enumerate(ways)])

        logging.info("Updating place edges with way id") 
        cur.execute(SQL("""UPDATE place_edges
            SET WAY = (SELECT WAY FROM way_partition WHERE PEDGE=place_edges.OGC_FID)
        """))

        logging.info("Build ways table")
        execute_sql(self._conn, "ways.sql")

    def compute_local_attributes(self,  orthogonality=False ):
        """ Compute local way attributes

            See ways.sql for other attributes computed

            :param orthogonality: If set to True, compute orthogonality;
                                  default to False.
        """
        logging.info("Computing local attributes")
        execute_sql(self._conn, "way_local.sql")

        # Compute orthogonality
        if orthogonality:
            self.compute_orthogonality()

        self._conn.commit()
    
    def compute_orthogonality(self):
        """ Compute orthogonality
        """
        from .angles import angle_from_azimuth

        logging.info("Computing orthogonality")

        f_azimuth = self.azimuth

        cur  = self._conn.cursor()
        rows = cur.execute(SQL("""SELECT 
            pl, way, ST_X(p1), ST_Y(p1), ST_X(p2), ST_Y(p2)
            FROM (
                SELECT 
                START_PL AS pl,
                WAY AS way,
                ST_StartPoint(GEOMETRY) AS p1, 
                ST_PointN(GEOMETRY,2) AS p2
                FROM place_edges
            UNION ALL
                SELECT
                END_PL AS pl,
                WAY AS way,
                ST_EndPoint(GEOMETRY) AS p1, 
                ST_PointN(GEOMETRY, ST_NumPoints(GEOMETRY)-1) AS p2
                FROM place_edges)
            ORDER BY pl
        """)).fetchall()

        # compute azimuths
        way_places = [(r[0],r[1],f_azimuth(*r[2:])) for r in rows]

        # Compute all angles for each pairs of way 
        # for each places

        def places():
            s = 0
            while s<len(rows):
                p = way_places[s][0]
                l = list(takewhile(lambda x: x[0]==p, way_places[s:]))
                s = s+len(l)
                yield p,l
        
        def compute_angles():
            for place, ways in places():
                n = len(ways)
                if n==1:
                    continue
                for i in xrange(n-1):
                    w1 = ways[i]
                    i1 = w1[1]
                    for j in xrange(i+1,n):
                        w2 = ways[j]
                        i2 = w2[1]  
                        if i1 != i2:
                            angle = sin( angle_from_azimuth(w1[2],w2[2]) )
                            yield (place,angle,min(i1,i2),max(i1,i2))

        # Build way_angles table
        cur.execute(SQL("DELETE FROM way_angles"))
        cur.executemany(SQL("INSERT INTO way_angles(PLACE,ANGLE,WAY1,WAY2) SELECT ?,?,?,?"),
                [(pl,angle,way1,way2) for pl,angle,way1,way2 in compute_angles()])

        # Update orthogonality
        cur.execute(SQL("""UPDATE ways SET ORTHOGONALITY = (
            SELECT Sum(inner)/ways.CONNECTIVITY FROM (
            SELECT Min(a) AS inner FROM (
                SELECT PLACE AS p, ANGLE AS a, WAY2 AS w
                FROM way_angles WHERE WAY1=ways.WAY_ID
                UNION ALL
                SELECT PLACE AS p, ANGLE AS a, WAY1 AS w
                FROM way_angles WHERE WAY2=ways.WAY_ID)
                GROUP BY p,w)
           ) WHERE ways.CONNECTIVITY > 0"""))

