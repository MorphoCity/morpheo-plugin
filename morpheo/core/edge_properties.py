# -*- encoding=utf-8 -*-

import logging
import networkx as nx
from numpy import sin
from .logger import Progress
from .sql import SQL, attr_table, table_exists
from .angles import azimuth, angle_from_azimuth
from .classes import compute_classes


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
    size = len(rows)
    def takew(p,s):
        while s<size:
            x = rows[s]
            if x[0]==p:
                yield x
                s = s+1
            else:
                break

    while s<size:
        p = rows[s][0]
        l = list(takew(p,s))
        s = s+len(l)
        yield p,l


def compute_angles(conn, force=False):
    """ Compute angles between edges at places

        :param force: if True, force recomputing angles
    """
    cur  = conn.cursor()
    if not force:
        [count] = cur.execute("SELECT Count(*)>0 FROM way_angles").fetchone()
        if count:
            return

    logging.info("Computing angles between edges")

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
    way_places = [(r[0],r[1],r[2], azimuth(*r[3:])) for r in rows]

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


def compute_edge_classes(attr_table, cur, attribute, classes):
    """ Helper for computing classes
    """
    if classes > 0:
        logging.info("Edges: computing classes for %s" % attribute)
        rows = list(compute_classes(cur,'place_edges','OGC_FID', attribute, classes))
        attr_table.update('place_edges','OGC_FID', attribute+'_CL',rows)


def compute_orthogonality(conn):
    """ Compute orthogonality

        Note the table way_angle must have been 
        computed !
    """
    compute_angles(conn)   

   # Update orthogonality
    logging.info("Edges: computing orthogonality")
    cur = conn.cursor()
    cur.execute(SQL("UPDATE place_edges SET ORTHOG = NULL"))
    cur.execute(SQL("""UPDATE place_edges SET ORTHOG = (
        SELECT Sum(inner)/place_edges.DEGREE FROM (
        SELECT Min(a) AS inner FROM (
        SELECT PLACE AS p, ANGLE AS a, EDGE2 AS e
        FROM way_angles WHERE EDGE1=place_edges.OGC_FID
        UNION ALL
        SELECT PLACE AS p, ANGLE AS a, EDGE1 AS e
        FROM way_angles WHERE EDGE2=place_edges.OGC_FID)
          GROUP BY p,e
        ))"""))


def compute_local_attributes(conn,  orthogonality=False, classes=0 ):
    """ Compute local way attributes

        Note that length, degree, connectivity and spacing are 
        computed 

        :param orthogonality: If set to True, compute orthogonality;
                              default to False.
        :param classes: Number of equal length classes
    """
    cur = conn.cursor()
    with attr_table(cur, "local_attributes") as attrs:

       # Compute spacing
       cur.execute(SQL("""UPDATE place_edges SET SPACING = (
                          SELECT place_edges.LENGTH/place_edges.DEGREE)
                          WHERE DEGREE>0"""))

       for attr in ('DEGREE','LENGTH','SPACING'):
            compute_edge_classes(attrs, cur, attr, classes)
           
       # Compute orthogonality
       if orthogonality:
            compute_orthogonality(conn)
            compute_edge_classes(attrs, cur, 'ORTHOG', classes)

    conn.commit()
 

def compute_global_attributes(conn, path, betweenness=False, closeness=False, stress=False, 
                              classes=0 ):
    r""" Compute global attributes
    
        :param conn: Database connection
        :param path: Path to morpheo data
        :param closeness:   If True, compute closeness centrality.
        :param betweenness: If True, compute betweenness centrality.
        :param stress:      If True, compute stress centrality.
        :param classes: Number of classes of equals length

        These attributes are computed  with networkx package
        see: http://networkx.readthedocs.io/en/networkx-1.11/reference/algorithms.html
    """
    from .places import load_edge_graph

    G   = load_edge_graph(path)
    LG  = nx.line_graph(G)
    cur = conn.cursor()
    with attr_table(cur, "global_attributes") as attrs:

        def items( results ): 
            return [(G[u][v][z]['fid'],value) for (u,v,z),value in results.iteritems()]

        if betweenness:
            attrs.update('place_edges', 'OGC_FID', 'BETWEE', items(compute_betweenness(LG)))
            compute_edge_classes(attrs, cur, 'BETWEE', classes)

        if closeness:
            attrs.update('place_edges', 'OGC_FID', 'CLOSEN', items(compute_closeness(LG)))
            compute_edge_classes(attrs, cur, 'CLOSEN', classes)

        if stress:
            attrs.update('place_edges', 'OGC_FID', 'USE', items(compute_use(LG)))
            compute_edge_classes(attrs, cur, 'USE', classes)


def compute_betweenness(G):
    r""" Compute betweeness for each way

        .. math::
            
            c_B(v) = \sum_{s,t \in V}\frac{\sigma(s, t|v)}{\sigma(s, t)}

        where `V` is the set of nodes, `\sigma(s, t)` is the number of
        shortest `(s, t)`-paths,  and `\sigma(s, t|v)` is the number of those
        paths  passing through some  node `v` other than `s, t`.
        If `s = t`, `\sigma(s, t) = 1`, and if `v \in {s, t}`,
        `\sigma(s, t|v) = 0`.

        see: http://networkx.readthedocs.io/en/networkx-1.11/reference/generated/networkx.algorithms.centrality.betweenness_centrality.html#networkx.algorithms.centrality.betweenness_centrality
    """
    logging.info("Edges: computing betweenness centrality")
    return nx.betweenness_centrality(G, normalized=False)


def compute_closeness(G):
    r""" Compute closeness for each way
 
        Note that the closeness is defined as 

        .. math::

            C(u) = \frac{n - 1}{\sum_{v=1}^{n-1} d(v, u)},

        where `d(v, u)` is the shortest-path distance between `v` and `u`,
        and `n` is the number of nodes in the graph.
    """
    logging.info("Edges: computing closeness")
    return nx.closeness_centrality(G)


def compute_use(G):
    """ Compute stress/use centrality
 
        .. math::
            
            c_S(v) =\sum_{s,t \in V} \sigma(s, t|v)

        We use a modified algorithm of betweenness as described in 
        http://algo.uni-konstanz.de/publications/b-vspbc-08.pdf
    """
    from .algorithms import stress_centrality

    logging.info("Edges: computing stress centrality")
    return stress_centrality(G, normalized=False)


def computed_properties(conn, ways=False):
    """ Return computed properties for edges or ways

        :param ways: Boolean, if False return the computed
                     properties
    """
    cur = conn.cursor()
    table = 'ways' if ways else 'place_edges'
    def check_property(prop):
        [ok] = cur.execute(SQL("SELECT Count(*) FROM {table} WHERE {prop} NOT NULL",
                               table=table,prop=prop))
       
        return prop if ok else None

    props = [
        'DEGREE',
        'SPACING',
        'ORTHOG',
        'BETWEE',
        'USE',
        'RTOPO',
        'ACCES'
    ]
    if ways: 
        props.append('CONN')

    return [p for p in props if check_property(p)]


