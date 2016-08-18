# -*- encoding=utf-8 -*-
""" Place builder helper
"""
from __future__ import print_function

import os
import logging

import networkx as nx
import numpy as np

from numpy import sin
from numpy import pi
from functools import partial
from itertools import takewhile
from ..logger import Progress

from .errors import BuilderError
from .sql import SQL, execute_sql, attr_table
from .classes import compute_classes
from .layers import export_shapefile

def iter_places(rows):
    """ Generator for iterating throught places 

        :param rows: A ordered list of squences whose first element
                     is an place index which is the sort 
                     criteria. Thus, element which have the same index
                     are all adjacent in the list.

        At each invocation, the iterator return a tuple (place,list)
        where place is the place index and list the list of elements
        for the same index.
    """
    s = 0
    while s<len(rows):
        p = rows[s][0]
        l = list(takewhile(lambda x: x[0]==p,  rows[s:]))
        s = s+len(l)
        yield p,l


def compute_way_classes(attr_table, cur, attribute, classes):
    """ Helper for computing classes
    """
    if classes > 0:
        logging.info("Ways: computing classes for %s" % attribute)
        rows = list(compute_classes(cur,'ways','WAY_ID', attribute, classes))
        attr_table.update('ways','WAY_ID', attribute+'_CL',rows)


class WayBuilder(object):

    def __init__(self, conn):

       from qgis.core import QgsPoint
       self._conn = conn

       # Define helper functions
       p1,p2 = QgsPoint(), QgsPoint()
       def azimuth(x1,y1,x2,y2):
           p1.set(x1,y1)
           p2.set(x2,y2)
           return p1.azimuth(p2) / 180.0 * pi

       def distance(x1,y1,x2,y2):
           p1.set(x1,y1)
           p2.set(x2,y2)
           return np.sqrt(p1.sqrDist(p2))

       self.azimuth  = azimuth
       self.distance = distance

       self._line_graph = None

    def build_ways(self, threshold):
        """ Compute ways

            Pair edges for each place then resolve pairing as a partitioning
            set: each resulting classes will be a way.

            :param threshold: The angle threshold (in radian) for pairing edges at each place.
        """
        from .angles import (create_partition, resolve, update, num_partitions, get_index_table,
                             create_matrix, next_argmin, get_value, pop_args, get_remaining_elements,
                             angle_from_azimuth)
      
        # Invalidate current line graph
        self._line_graph = None

        # Dereference helper functions
        azimuth  = self.azimuth
        distance = self.distance

        cur = self._conn.cursor()

        # Clean up way id on edges
        cur.execute(SQL("UPDATE place_edges SET WAY = NULL"))

        # Get the (max) number of edges and places
        max_edges  = cur.execute(SQL("SELECT Max(OGC_FID) FROM place_edges")).fetchone()[0]
        max_places = cur.execute(SQL("SELECT Max(OGC_FID) FROM places")).fetchone()[0] 

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

        logging.info("Ways: computing azimuth")
        edges_az = [(r[0],r[1],azimuth(*r[2:6]),r[2],r[3]) for r in rows]

        def compute_angles( edges ):
            return create_matrix(edges, lambda e1,e2: angle_from_azimuth(e1[2],e2[2]))

        def compute_coeffs( edges ):
            return create_matrix(edges, lambda e1,e2: deviation(e1[2], e1[3], e1[4],
                                                                e2[2], e2[3], e2[4]))

        # Compute candidates pair for each places
        # Each edge is given a way number, 
        # Places with degree=2 are automatically paired together

        # Array to store distance corrections for ways
        distances = np.zeros(max_edges+1)
  
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

        logging.info("Ways: Pairing edges")

        progress     = Progress(len(edges_az))
        count_places = 0
        for place, edges in iter_places(edges_az):
            count_places = count_places+1
            n = len(edges)
            progress(n)
            if n>2:
                # Compute angles between edges
                angles = compute_angles(edges)
                # compute coeffs between edges
                coeffs = compute_coeffs(edges)
                for e1,e2 in next_argmin(coeffs):
                    if get_value(angles,e1,e2) < threshold: 
                        add_pair(edges[e1],edges[e2])
                        pop_args(coeffs,e1,e2)
                # Store end places from lonely edges
                for e in get_remaining_elements(coeffs):
                    pass
            elif n==2:
                # pair those 2 edge
                add_pair(edges[0],edges[1]) 
            else:
                # No pairing: place has only one edge.
                pass

        # Update partition
        logging.info("Ways: updating partition")
        update(ways)
        num_ways = num_partitions(ways)

        logging.info("Ways: computed {} ways (num places={}, num edges={})".format(num_ways,count_places,max_edges))
        
        self._build_way_table(cur, ways, distances)
        self._conn.commit()
        return num_ways
        
    def _build_way_table( self, cur, ways, distances ):
        """ Write back way partition

            Create a table holding the partition mapping for edges. The table
            also contains the distance corrections.
        """
        cur.execute(SQL("DELETE FROM way_partition"))
        cur.executemany(SQL("INSERT INTO way_partition(EDGE,WAY,DIST) SELECT ?,?,?"),
                [(fid,way,distances[fid]) for fid,way in enumerate(ways)])

        logging.info("Ways: updating place edges with way id") 
        cur.execute(SQL("""UPDATE place_edges
            SET WAY = (SELECT WAY FROM way_partition WHERE way_partition.EDGE=place_edges.OGC_FID)
        """))

        logging.info("Ways: build ways table")
        execute_sql(self._conn, "ways.sql")

    def compute_local_attributes(self,  orthogonality=False, classes=0 ):
        """ Compute local way attributes

            Note that length, degree, connectivity and spacing are 
            computed 

            :param orthogonality: If set to True, compute orthogonality;
                                  default to False.
            :param classes: Number of equal length classes
        """
        cur = self._conn.cursor()
        #with attr_table(cur, "local_classes") as cl_attrs:
        with attr_table(cur, "local_attributes") as attrs:

           for attr in ('DEGREE','LENGTH','CONN','SPACING'):
                compute_way_classes(attrs, cur, attr, classes)
           
           # Compute orthogonality
           if orthogonality:
                self.compute_orthogonality()
                compute_way_classes(attrs, cur, 'ORTHOG', classes)

        self._conn.commit()
    
    def compute_orthogonality(self):
        """ Compute orthogonality
        """
        from .angles import angle_from_azimuth

        logging.info("Ways: computing orthogonality")

        f_azimuth = self.azimuth

        cur  = self._conn.cursor()
        rows = cur.execute(SQL("""SELECT 
            pl, way, edge,  ST_X(p1), ST_Y(p1), ST_X(p2), ST_Y(p2)
            FROM (
                SELECT 
                START_PL AS pl,
                WAY AS way,
                OGC_FID AS edge,
                ST_StartPoint(GEOMETRY) AS p1, 
                ST_PointN(GEOMETRY,2) AS p2
                FROM place_edges
            UNION ALL
                SELECT
                END_PL AS pl,
                WAY AS way,
                OGC_FID AS edge,
                ST_EndPoint(GEOMETRY) AS p1, 
                ST_PointN(GEOMETRY, ST_NumPoints(GEOMETRY)-1) AS p2
                FROM place_edges)
            ORDER BY pl
        """)).fetchall()

        # compute azimuths
        way_places = [(r[0],r[1],r[2], f_azimuth(*r[3:])) for r in rows]

        # Compute all angles for each pairs of way 
        # for each places

        progress = Progress(len(way_places))

        def compute_angles():
            for place, ways in iter_places(way_places):
                n = len(ways)
                progress(n)
                if n==1:
                    continue
                for i in range(n-1):
                    w1 = ways[i]
                    i1 = w1[1]
                    for j in range(i+1,n):
                        w2 = ways[j]
                        i2 = w2[1]  
                        if i1 != i2:
                            angle = sin( angle_from_azimuth(w1[3],w2[3]) )
                            yield (place,angle,i1,w1[2],i2,w2[2])

        # Build way_angles table
        logging.info("Ways: computing angles")
        cur.execute(SQL("DELETE FROM way_angles"))
        cur.executemany(SQL("INSERT INTO way_angles(PLACE,ANGLE,WAY1,EDGE1,WAY2,EDGE2) SELECT ?,?,?,?,?,?"),
                [(pl,angle,way1,e1,way2,e2) for pl,angle,way1,e1,way2,e2 in compute_angles()])

        # Update orthogonality
        logging.info("Ways: computing orthogonality")
        cur.execute(SQL("UPDATE ways SET ORTHOG = NULL"))
        cur.execute(SQL("""UPDATE ways SET ORTHOG = (
            SELECT Sum(inner)/ways.CONN FROM (
            SELECT Min(a) AS inner FROM (
                SELECT PLACE AS p, ANGLE AS a, WAY2 AS w, EDGE2 AS e
                FROM way_angles WHERE WAY1=ways.WAY_ID
                UNION ALL
                SELECT PLACE AS p, ANGLE AS a, WAY1 AS w, EDGE1 AS e
                FROM way_angles WHERE WAY2=ways.WAY_ID)
                GROUP BY p,e
           ))"""))


    def compute_global_attributes(self, betweenness=False, closeness=False, stress=False, classes=0):
        r""" Compute global attributes
        
            :param closeness:   If True, compute closeness.
            :param betweenness: If True, compute betweenness centrality.
            :param stress:      If True, compute stress centrality.
            :param classes: Number of classes of equals length

            These attributes with networkx package
            see: http://networkx.readthedocs.io/en/networkx-1.10/reference/algorithms.html

       """
        cur = self._conn.cursor()
        with attr_table(cur, "global_attributes") as attrs:
                
            if betweenness:
                attrs.update('ways', 'WAY_ID', 'BETWEE', self.compute_betweenness().items())
                compute_way_classes(attrs, cur, 'BETWEE', classes)

            if closeness:
                attrs.update('ways', 'WAY_ID', 'CLOSEN', self.compute_closeness().items())
                compute_way_classes(attrs, cur, 'CLOSEN', classes)

            if stress:
                attrs.update('ways', 'WAY_ID', 'USE'   , self.compute_use().items())
                compute_way_classes(attrs, cur, 'USE', classes)

    def compute_betweenness(self):
        """ Compute betweeness for each way
        """
        G = self.get_line_graph()
        logging.info("Ways: computing betweenness centrality")
        return nx.betweenness_centrality(G)

    def compute_closeness(self):
        r""" Compute closeness for each way
 
            Note that the closeness is defined as 

            .. math::

                C(u) = \frac{n - 1}{\sum_{v=1}^{n-1} d(v, u)},

            where `d(v, u)` is the shortest-path distance between `v` and `u`,
            and `n` is the number of nodes in the graph.
        """
        G = self.get_line_graph()
        logging.info("Ways: computing closeness centrality")
        return nx.closeness_centrality(G)

    def compute_use(self):
        """ Compute stress centrality
        """
        # TODO Implement me !!
        logging.info("Ways: computing stress centrality")
        raise NotImplementedError("Stress Centrality")

    def compute_topological_radius(self):
        """ Compute the topological radius for all ways
           
            The toplogical radius will be also assigned to the edges of the
            viary graph.

            The topological radius is defined as:

            .. math::
                
                r_{topo}(u) = \sum_{v=1}^{n-1} d(v, u),

            where `d(v, u)` is the shortest-path distance between `v` and `u`,
            and `n` is the number of nodes in the graph.
        """

        G = self.get_line_graph()
        path_length = nx.single_source_shortest_path_length
        
        nodes = G.nodes()
        cur   = self._conn.cursor()

        # Get the length for each ways
        lengths = cur.execute("SELECT WAY_ID,LENGTH FROM ways").fetchall()

        logging.info("Ways: computing topological radius and accessibility")

        progress = Progress(len(nodes))

        def compute( v ):
            sp = path_length(G,v)
            r = sum(sp.values())
            a = sum(sp[r[0]]*r[1] for r in lengths)
            progress()
            return v,r,a

        r_topo = [compute(v) for v in nodes]

        # Update ways and edges with topological radius
        logging.info("Ways: Updating ways with topological radius")
        with attr_table(cur, "topo_radius") as attrs:
            attrs.update('ways', 'WAY_ID', 'RTOPO',[(r[0],r[1]) for r in r_topo])
            attrs.update('ways', 'WAY_ID', 'ACCES',[(r[0],r[2]) for r in r_topo])

        # Update edges
        logging.info("Ways: Updating edges with topological radius")
        cur.execute(SQL("""
            UPDATE edges SET
                RTOPO = (SELECT RTOPO FROM ways WHERE ways.WAY_ID=edges.WAY_ID),
                ACCES = (SELECT ACCES FROM ways WHERE ways.WAY_ID=edges.WAY_ID)
        """))

    def get_line_graph(self):
        if self._line_graph is None:
            self._line_graph = self.create_line_graph()
        return self._line_graph

    def save_line_graph(self, output):
        if self._line_graph is not None:
            logging.info("Ways: saving line graph")
            basename = os.path.basename(output)
            nx.write_gpickle(self._line_graph, os.path.join(output,'way_graph_'+basename+'.gpickle'))
        else:
            logging.warn("Ways: no graph to save")
    
    def export(self, dbname, output ):
       """ Export way files
       """
       logging.info("Ways: Saving ways to %s" % output)
       export_shapefile(dbname, 'ways'      , output)
       self.save_line_graph(output)

    def create_line_graph(self):
        """ Create a line graph from ways

            Each node is way,
            Each edge is connection between two intersecting ways
        """ 
        import networkx as nx
        
        # Build an adjacency matrix 
        cur  = self._conn.cursor()
        rows = cur.execute(SQL("SELECT PLACE,WAY_ID FROM way_places ORDER BY PLACE")).fetchall()

        # Undirected, simple (not multi-) graph 
        g = nx.Graph()

        logging.info("Ways: creating line graph")    

        progress = Progress(len(rows))

        for p,ways in iter_places(rows):
            n = len(ways)
            progress(n)
            if n==1: continue
            for i in xrange(n-1):
                w1 = ways[i][1]
                for j in xrange(i+1,n):
                    w2 = ways[j][1]
                    g.add_edge(w1,w2,place=p)

        return g

