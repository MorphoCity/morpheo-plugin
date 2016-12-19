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
from .logger import Progress
from .errors import BuilderError, ErrorGraphNotFound
from .sql import SQL, execute_sql, attr_table, table_exists
from .classes import compute_classes
from .layers import export_shapefile
from .edge_properties import iter_places, compute_angles


def compute_way_classes(attr_table, cur, attribute, classes):
    """ Helper for computing classes
    """
    if classes > 0:
        logging.info("Ways: computing classes for %s" % attribute)
        rows = list(compute_classes(cur,'ways','WAY_ID', attribute, classes))
        attr_table.update('ways','WAY_ID', attribute+'_CL',rows)


def _ways_graph_path( output ):
    """ Build ways graph path
    """
    basename = os.path.basename(output)
    return os.path.join(output,'way_graph_'+basename+'.gpickle')


def create_ways_graph(conn):
    """ Create a line graph from ways

        Each node is way,
        Each edge is connection between two intersecting ways
    """ 
    import networkx as nx
        
    # Build an adjacency matrix 
    cur  = conn.cursor()
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


def read_ways_graph( path ):
    """ Read way line graph as networkx object 
    """
    graph_path = _ways_graph_path(path)
    try:
        logging.info("Reading way graph %s" % graph_path)
        return nx.read_gpickle(graph_path)
    except Exception as e:
        raise ErrorGraphNotFound(
                "Error while reading graph {}: {}".format(graph_path,e))


def distance(x1,y1,x2,y2):
    return np.sqrt((x2-x1)*(x2-x1)+(y2-y1)*(y2-y1))


class WayBuilder(object):

    def __init__(self, conn):
       from math import atan2

       self._conn = conn
       self._line_graph = None

    def build_ways_from_attribute( self, name ):
        """ Compute ways using attribute name on edges
        """
        from itertools import combinations
        from .angles import (create_partition, resolve, update, num_partitions)
 
        # Invalidate current line graph
        self._line_graph = None
        cur = self._conn.cursor()

        # Clean up way id on edges
        cur.execute(SQL("UPDATE place_edges SET WAY = NULL"))

        # Get the (max) number of edges and places
        max_edges = cur.execute(SQL("SELECT Max(OGC_FID) FROM place_edges")).fetchone()[0]

        # Get the entry vector for edges in each place
        rows = cur.execute(SQL("""SELECT 
            pl, fid, name, ST_X(p1), ST_Y(p1)
            FROM (
                SELECT 
                OGC_FID AS fid,
                START_PL AS pl,
                NAME AS name,
                ST_StartPoint(GEOMETRY) AS p1
                FROM place_edges
                WHERE name NOT NULL
            UNION ALL
                SELECT 
                OGC_FID AS fid,
                END_PL AS pl,
                NAME AS name,
                ST_EndPoint(GEOMETRY) AS p1
                FROM place_edges)
                WHERE name NOT NULL
            ORDER BY pl
        """)).fetchall()
 
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

        logging.info("Ways: Pairing edges by name")

        progress = Progress(len(rows))
        count_places = 0
        for place, edges in iter_places(rows):
            count_places = count_places+1
            n = len(edges)
            progress(n)
            for (e1,e2) in combinations(edges,2):
                if e1[2] == e2[2]:
                    add_pair(e1,e2)

        # Update partition
        logging.info("Ways: updating partition")
        update(ways)
        num_ways = num_partitions(ways)

        logging.info("Ways: computed {} ways (num places={}, num edges={})".format(num_ways,count_places,max_edges))
       
        cur.execute(SQL("DELETE FROM way_partition"))
        cur.executemany(SQL("INSERT INTO way_partition(EDGE,WAY,DIST) SELECT ?,?,?"),
                [(fid,way,distances[fid]) for fid,way in enumerate(ways)])

        logging.info("Ways: build ways table")
        execute_sql(self._conn, "ways.sql")

        self._conn.commit()
        return num_ways


    def build_ways(self, threshold):
        """ Compute ways

            Pair edges for each place then resolve pairing as a partitioning
            set: each resulting classes will be a way.

            :param threshold: The angle threshold (in radian) for pairing edges at each place.
        """
        from .angles import (create_partition, resolve, update, num_partitions, get_index_table,
                             create_matrix, next_argmin, get_value, pop_args, get_remaining_elements,
                             azimuth, angle_from_azimuth)
      
        # Invalidate current line graph
        self._line_graph = None
        cur = self._conn.cursor()

        # Clean up way id on edges
        cur.execute(SQL("UPDATE place_edges SET WAY = NULL"))

        # Get the (max) number of edges and places
        max_edges  = cur.execute(SQL("SELECT Max(OGC_FID) FROM place_edges")).fetchone()[0]

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
       
        cur.execute(SQL("DELETE FROM way_partition"))
        cur.executemany(SQL("INSERT INTO way_partition(EDGE,WAY,DIST) SELECT ?,?,?"),
                [(fid,way,distances[fid]) for fid,way in enumerate(ways)])

        logging.info("Ways: build ways table")
        execute_sql(self._conn, "ways.sql")

        self._conn.commit()
        return num_ways

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
        """ Compute orthogonality on ways
        """
        from .edge_properties import compute_angles
        compute_angles(self._conn)   

        # Update orthogonality
        logging.info("Ways: computing orthogonality")

        cur = self._conn.cursor()
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


    def compute_global_attributes(self, betweenness=False, closeness=False, stress=False, 
                                  classes=0 ):
        r""" Compute global attributes
        
            :param closeness:   If True, compute closeness centrality.
            :param betweenness: If True, compute betweenness centrality.
            :param stress:      If True, compute stress centrality.
            :param classes: Number of classes of equals length

            These attributes are computed  with networkx package
            see: http://networkx.readthedocs.io/en/networkx-1.11/reference/algorithms.html

        """
        cur = self._conn.cursor()
        with attr_table(cur, "global_attributes") as attrs:
                       
            if betweenness:
                attrs.update('ways', 'WAY_ID', 'BETWEE', 
                        self.compute_betweenness().items())
                compute_way_classes(attrs, cur, 'BETWEE', classes)

            if closeness:
                attrs.update('ways', 'WAY_ID', 'CLOSEN', self.compute_closeness().items())
                compute_way_classes(attrs, cur, 'CLOSEN', classes)

            if stress:
                attrs.update('ways', 'WAY_ID', 'USE', 
                        self.compute_use().items())
                compute_way_classes(attrs, cur, 'USE', classes)

    def compute_betweenness(self):
        r""" Compute betweeness for each way

            .. math::
            
                c_B(v) =\sum_{s,t \in V} \frac{\sigma(s, t|v)}{\sigma(s, t)}

            where `V` is the set of nodes, `\sigma(s, t)` is the number of
            shortest `(s, t)`-paths,  and `\sigma(s, t|v)` is the number of those
            paths  passing through some  node `v` other than `s, t`.
            If `s = t`, `\sigma(s, t) = 1`, and if `v \in {s, t}`,:
            `\sigma(s, t|v) = 0`.

            see: http://networkx.readthedocs.io/en/networkx-1.11/reference/generated/networkx.algorithms.centrality.betweenness_centrality.html#networkx.algorithms.centrality.betweenness_centrality

       """
        G = self.get_line_graph()
        logging.info("Ways: computing betweenness centrality")
        return nx.betweenness_centrality(G, normalized=False)

    def compute_closeness(self):
        r""" Compute closeness for each way
 
            Note that the closeness is defined as 

            .. math::

                C(u) = \frac{n - 1}{\sum_{v=1}^{n-1} d(v, u)},

            where `d(v, u)` is the shortest-path distance between `v` and `u`,
            and `n` is the number of nodes in the graph.
        """
        G = self.get_line_graph()
        logging.info("Ways: computing closeness")
        return nx.closeness_centrality(G)

    def compute_use(self):
        r""" Compute stress/use centrality
 
            .. math::
            
                c_S(v) =\sum_{s,t \in V} \sigma(s, t|v)

            We use a modified algorithm of betweenness as described in 
            http://algo.uni-konstanz.de/publications/b-vspbc-08.pdf

        """
        from .algorithms import stress_centrality

        G = self.get_line_graph()
        logging.info("Ways: computing stress centrality")
        return stress_centrality(G, normalized=False)

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
        lengths = dict(cur.execute("SELECT WAY_ID,LENGTH FROM ways").fetchall())

        logging.info("Ways: computing topological radius and accessibility")

        progress = Progress(len(nodes))

        def compute( v ):
            sp = path_length(G,v)
            r = sum(sp.values())
            a = sum(sp[w]*lengths[w] for w in sp)
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
            UPDATE place_edges SET
                RTOPO = (SELECT RTOPO FROM ways WHERE ways.WAY_ID=place_edges.WAY),
                ACCES = (SELECT ACCES FROM ways WHERE ways.WAY_ID=place_edges.WAY)
        """))

        self._conn.commit()  

    def get_line_graph(self):
        if self._line_graph is None:
            self._line_graph = create_ways_graph(self._conn)
        return self._line_graph

    def save_line_graph(self, output, create=False):
        """ Save line graph

            :param output: Path to export graph
            :param create: If True, force graph creation
        """
        if create:
           self.get_line_graph()
        if self._line_graph is not None:
            logging.info("Ways: saving line graph")
            nx.write_gpickle(self._line_graph, _ways_graph_path(output))
        else:
            logging.warn("Ways: no graph to save")
   
    def export(self, dbname, output, export_graph=False):
       """ Export way files
       """
       # Delete previous way graph
       graph_path = _ways_graph_path(output)
       if os.path.exists(graph_path):
               os.remove(graph_path)

       logging.info("Ways: Saving ways to %s" % output)
       export_shapefile(dbname, 'ways'       , output)
       export_shapefile(dbname, 'place_edges', output)
       export_shapefile(dbname, 'edges'      , output)
       self.save_line_graph(output, create=export_graph)


