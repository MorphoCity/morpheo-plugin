# -*- coding: utf-8 -*-
""" Module for computing shortest paths
"""
import os
import logging
import networkx as nx

from ..logger import Progress

from .errors  import BuilderError
from .sql     import connect_database, SQL, execute_sql, attr_table, table_exists
from .layers  import import_shapefile, export_shapefile

from math import atan2, pi

class ErrorInvalidFeature(BuilderError):
    pass


class ErrorPathNotFound(BuilderError):
    pass


def load_graph( path ):
    """ Load edge graph

        :param path: path location of the morpheo data

        :return: A networkx graph
    """
    basename = os.path.basename(path)
    graph_path = os.path.join(path, 'edge_graph_'+basename+'.gpickle') 
    logging.info("Itinerary: importing edge graph %s" % graph_path)
    if not os.path.exists(graph_path):
        raise BuilderError('Edge graph file {} not found'.format(graph_path))
    return nx.read_gpickle(graph_path)


def get_closest_feature( cur, table, radius, x, y, srid=None ):
        """ Return the closest feature from the given point 

            :param table: The table name 
            :param x: The E-W location 
            :param y: The N-S location
            :param radius: The search radius (in meters)

            :return: the fid of the closest feature from the input table
        """
        if srid is None:
            [srid] = cur.execute(SQL("SELECT srid FROM deometry_columns WHERE f_table_name='{table}'",table=table))
        result = cur.execute(SQL("""SELECT t.OGC_FID FROM {table} AS t, 
                (SELECT ST_Buffer(GeomFromText('POINT({x},{y})',{srid}),{radius}) AS GEOMETRY) AS p
                WHERE ST_Intersects(t.GEOMETRY,p.GEOMETRY)
                AND t.ROWID IN (
                    SELECT ROWID FROM SpatialIndex
                    WEHER f_table_name='{table}' AND search_frame=p.GEOMETRY
                )
                ORDER BY ST_Distance(t.GEOMETRY. p.GEOMETRY) LIMIT 1
        """, table=table,srid=srid,x=x,y=y,radius=radius)).fetchone()
    
        if len(result) == 0:
            raise ErrorInvalidFeature("No feature at {},{},radius={}".format(x,y,radius))

        return result[0]


def _create_itinerary_table(cur, path_type):
    """ Create the table to store itinerary results
    """
    if not table_exists(cur, table):
        cur.execute(SQL("""
            CREATE TABLE {table}(
                OGC_FID integer PRIMARY KEY,
                START_PL integer,
                END_PL integer)
        """,table=table))
        cur.execute(SQL("""
            SELECT AddGeometryColumn(
                '{table}',
                'GEOMETRY',
                (
                    SELECT CAST(srid AS integer)
                    FROM geometry_columns
                    WHERE f_table_name='place_edges'
                ),
                'LINESTRING',
                (
                    SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='place_edges'
                )
            ); 
        """,table=table))
    cur.execute(SQL("DELETE FROM {table}",table=table)) 
    return table


def _store_path(cur, dbname, edges, path_type, output, manifest):
    """ Store our shortest path result as a list of edges
    """
    table = _create_itinerary_table(cur, path_type)
    cur.execute(SQL("""
        INSERT INTO {table}(OGC_FID,START_PL,END_PL, GEOMETRY) 
        SELECT OGC_FID, START_PL, END_PL, GEOMETRY FROM place_edges
        WHERE OGC_FID IN ({list})
    """,list=','.join(str(fid) for fid in edges),table=table))
            
    if output is not None:
        export_shapefile(dbname, table, output)
        # Write manifest
        with open(os.path.join(output,'itinerary_%s_%s.manifest' % (path_type,output)),'w') as f:
            for k,v in manifest.iteritems():
                f.write("{}={}\n".format(k,v))


def _edge_shortest_path( dbname, path, fid_src, fid_dst, weight=None, output=None ):
    """ Compute the edge shortest path
    """
    G = load_graph(path)    

    path_type = 'shortest' if weight is not None else 'simplest'

    logging.info("Itinerary: computing {} edge path".format(path_type))
    p = nx.shortest_path(G, fid_src, fid_dst, weight=weight)
    p = zip(p[:-1],p[1:]) 
    # G is expected to be a Multigraph and then return a list of edges
    if G.is_multigraph():
        edges = [min(G[u][v].values(),key=lambda x: x['length'])['fid'] for u,v in p]
    else:
        edges = [G[u][v]['fid'] for u,v in p]

    conn = connect_database(dbname)

    cur = conn.cursor()
    _store_path(cur, dbname, edges, path_type, output=output, manifest=dict(
        input=path,
        source=fid_src,
        destination=fid_dst,
        type=path_type))

    cur.close()
    conn.commit()
    conn.close()
    return edges


def _edge_mesh_shortest_path( conn, path, fid_src, fid_dst, attribute, cutoff, weight=None, 
                              output=None ):
    """ Compute the edge shortest path from mesh structure 

        The mesh structure is defined by taking the cutoff portion of the features 
        having the highest values of the given attributes 
    """

    raise NotImplementedError()

    cur = conn.cursor()
    # Get the number of features
    cur.execute(SQL("DELETE FROM mesh_struct"))
    count = cur.execute(SQL("SELECT Count(*) FROM place_edges"))
    limit = count * 100.0/cutoff

    cur.execute(SQL("""INSERT INTO mesh_struct(OGC_FID,START_PL,END_PL,GEOMETRY)
        SELECT OGC_FID,START_PL,END_PL,GEOMETRY FROM place_edges ORDER BY {attribute} 
        LIMIT {limit}
    """,attribute=attr_table,limit=limit))
    
    # Get all the nodes included/touching in the mesh
    nodes = cur.execute(SQL("""SELECT p 
          FROM (SELECT START_PL AS pl FROM mesh_struct
                UNION
                SELECT END_PL AS pl FROM mesh_struct)"""))


def shortest_path( dbname, path, fid_src, fid_dst, output=None ):
    """ Compute the edge shortest path in length

        :param conn: the connection to the morpheo working database
        :param path: the path location of morpheo data
        :param fid_src: The feature id of the starting node 
        :param fid_dst: The feature id of the destination node
        :param output: path to output results

        :return the list of edge feature id that represent the shortest path
    """
    return _edge_shortest_path(dbname, path, fid_src, fid_dst, output=output,
            weight='length')        


def simplest_path( dbname, path, fid_src, fid_dst, output=None ):
    """ Compute the unweighted edge shortest path

        Note that path is not unique and the function compute only one path

        :prama conn: the connection to the morpheo working database
        :param path: the path location of morpheo data
        :param fid_src: The feature id of the starting place
        :param fid_dst: The feature id of the destination place
        :param output: path to output results

        :return the list of edge feature id that represent the shortest path
    """
    return _edge_shortest_path(dbname, path, fid_src, fid_dst, output=output)        
 

def azimuth( x1, y1, x2, y2 ):
    return atan2( x2-x1, y2-y1)


def naive_azimuth_path(dbname, path, fid_src, fid_dst, output):
    """ Naive computation of  the azimuthal path

        :prama dbname: The path to the molpheo working database
        :param path: The path location of morpheo data
        :param fid_src: The feature id of the starting place
        :param fid_dst: The feature id of the destination place
        :param output: Path to output results

        We compute a path by selecting the edge that minimize the 
        difference with the overall direction at each step.

        :return the list of edge feature id that represent the shortest path
    """
    def angle(az1,az2):
        a = abs(az1-az2)
        if a > pi:
            a = 2*pi - a
        return a

    conn = connect_database(dbname)
    cur  = conn.cursor()

    # Compute the reference  azimuth
    def get_coordinates(node):
        [x,y] = cur.execute(SQL("""
                  SELECT ST_X(point),ST_Y(point) FROM (SELECT
                  ST_Centroid(GEOMETRY) AS point FROM places WHERE OGC_FID={node})
                """,node=node)).fetchone()
        return x,y

    n = fid_src
    edges  = {}
    level  = 0
    edgeid = -1
    while n!=fid_dst:
        # Get all edges accessibles from n
        # Compute the azimuth for the destination point
        az_dest = azimuth( *(get_coordinates(n)+get_coordinates(fid_dst)) )

        rows = cur.execute(SQL("""SELECT
            fid, next, ST_X(p1), ST_Y(p1), ST_X(p2), ST_Y(p2)
            FROM (
                SELECT OGC_FID AS fid, END_PL AS next,
                ST_StartPoint(GEOMETRY) AS p1,
                ST_PointN(GEOMETRY,2) AS p2
                FROM place_edges WHERE START_PL={node} AND OGC_FID<>{edgeid}
                UNION ALL
                SELECT OGC_FID AS fid, START_PL AS next,
                ST_EndPoint(GEOMETRY) AS p1,
                ST_PointN(GEOMETRY, ST_NumPoints(GEOMETRY)-1) AS p2
                FROM place_edges WHERE END_PL={node} AND OGC_FID<>{edgeid})
            """,node=n, edgeid=edgeid)).fetchall()
            
        # Select the next node from the the edge that mininize the
        # difference between azimuth
        edgeid,n = min(rows,key=lambda r:angle(azimuth(*r[2:]),az_dest))[0:2]

        if edgeid not in edges:
            edges[edgeid]=level
            level = level+1
        else:
            logging.error("Itinerary: Loop detected at edge {}".format(edgeid))
            break

    # Get edges in order
    edges = [e[0] for e in sorted(edges.items(),key=lambda x:x[1])]

    _store_path(cur, dbname, edges, 'naive_azimuth', output=output, manifest=dict(
        input=path,
        source=fid_src,
        destination=fid_dst,
        type='naive_azimuth'))

    cur.close()
    conn.commit()
    conn.close()
    return edges



def azimuth_path(dbname, path, fid_src, fid_dst, output):
    """ Compute the azimuthal path

        :prama dbname: The path to the molpheo working database
        :param path: The path location of morpheo data
        :param fid_src: The feature id of the starting place
        :param fid_dst: The feature id of the destination place
        :param output: Path to output results

        We compute a path by selecting the edge that minimize the 
        difference with the overall direction at each step.

        To prevent self crossing path, the incoming direction is 
        a 'plane cut' for calculating the angle.

        Avoid loop and dead-end

        We raise an exception if we reach an edge that have been 
        already included in the path

        :return the list of edge feature id that represent the shortest path
    """
    G = load_graph(path)    

    conn = connect_database(dbname)
    cur  = conn.cursor()

    # Compute the reference  azimuth
    def get_coordinates(node):
        [x,y] = cur.execute(SQL("""
                  SELECT ST_X(point),ST_Y(point) FROM (SELECT
                  ST_Centroid(GEOMETRY) AS point FROM places WHERE OGC_FID={node})
                """,node=node)).fetchone()
        return x,y

    def get_edge_azimuth(node, edge):
        row = cur.execute(SQL("""SELECT
            ST_X(p1), ST_Y(p1), ST_X(p2), ST_Y(p2)
            FROM (
                SELECT ST_StartPoint(GEOMETRY) AS p1, ST_PointN(GEOMETRY,2) AS p2
                FROM place_edges WHERE START_PL={node} AND OGC_FID={fid}
                UNION ALL
                SELECT ST_EndPoint(GEOMETRY) AS p1, ST_PointN(GEOMETRY, ST_NumPoints(GEOMETRY)-1) AS p2
                FROM place_edges WHERE END_PL={node} AND OGC_FID={fid})
        """,node=node,fid=edge)).fetchone()
        return azimuth(*row)

    def get_edge_candidates(node, edgeid=-1):
        rows = cur.execute(SQL("""SELECT
            fid, next, ST_X(p1), ST_Y(p1), ST_X(p2), ST_Y(p2)
            FROM (
                SELECT OGC_FID AS fid, END_PL AS next,
                ST_StartPoint(GEOMETRY) AS p1,
                ST_PointN(GEOMETRY,2) AS p2
                FROM place_edges WHERE START_PL={node} AND OGC_FID<>{edgeid} AND START_PL<>END_PL
                UNION ALL
                SELECT OGC_FID AS fid, START_PL AS next,
                ST_EndPoint(GEOMETRY) AS p1,
                ST_PointN(GEOMETRY, ST_NumPoints(GEOMETRY)-1) AS p2
                FROM place_edges WHERE END_PL={node} AND OGC_FID<>{edgeid} AND START_PL<>END_PL)
            """,node=node, edgeid=edgeid)).fetchall()
        return rows
 
    def angle_rel( az, ref ):
        a = az-ref
        if a<0:
            a = 2*pi + a
        return a

    def angle_abs(az1,az2):
        a = abs(az1-az2)
        if a > pi:
            a = 2*pi - a
        return a

    def angle_diff(coords, dst, ref):
        az = azimuth(*coords)
        return abs(angle_rel(az,ref)-angle_rel(dst,ref))

    n = fid_src

    # Get starting edge
    az_dst = azimuth( *(get_coordinates(n)+get_coordinates(fid_dst)) )
    edgeid,n = min(get_edge_candidates(n),key=lambda r:angle_abs(azimuth(*r[2:]),az_dst))[0:2] 
   
    level = 0
    edges = { edgeid: level }

    while n!=fid_dst:
        # Get all edges accessibles from n
        # Compute the azimuth for the destination point
        az_ref = get_edge_azimuth(n,edgeid)
        az_dst = azimuth( *(get_coordinates(n)+get_coordinates(fid_dst)) )

        rows = get_edge_candidates(n,edgeid)
        
        try:
            edgeid,n = next((r[0],r[1]) for r in rows if r[1]==fid_dst)
        except StopIteration:
            # Do not select dead-end
            rows = filter(lambda r:len(G.edges(r[1]))>1,rows)

            # Select the next node from the the edge that mininize the
            # difference benween angles
            edgeid,n = min(rows,key=lambda r:angle_diff(r[2:],az_dst,az_ref))[0:2]

        if edgeid not in edges:
            edges[edgeid]=level
            level = level+1
        else:
            logging.error("Itinerary: Loop detected at edge {}".format(edgeid))
            break

    # Get edges in order
    edges = [e[0] for e in sorted(edges.items(),key=lambda x:x[1])]

    _store_path(cur, dbname, edges, 'azimuth', output=output, manifest=dict(
        input=path,
        source=fid_src,
        destination=fid_dst,
        type='azimuth'))

    cur.close()
    conn.commit()
    conn.close()
    return edges


def way_simplest(dbname, path, fid_src, fid_dst, output):
    """ Compute the way simplest path

        The way simplest path is computed on the line graph of the ways connectivity:
        compute all paths from  all the accessibles ways from the starting place to all
        accessibles ways to the destination place and take the shortests in a topological
        sense.
            
        :prama conn: The path to  the morpheo working database
        :param path: The path location of morpheo data
        :param fid_src: The feature id of the starting place
        :param fid_dst: The feature id of the destination place
        :param output: Path to output results

        :return the list of edge feature id that represent the shortest path
    """
    raise NotImplementedError()     


