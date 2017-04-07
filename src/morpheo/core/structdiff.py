# -*- coding: utf-8 -*-
""" Module for computing structural diff
"""
import os
import logging
import networkx as nx

from .logger import Progress
from .sql    import create_database, connect_database, SQL, execute_sql, attr_table
from .layers import import_shapefile, export_shapefile
from .ways   import read_ways_graph
from .errors import MorpheoException


def compute_accessibility_delta(conn, path1, path2):
    """ Compute accessibility delta

        :param conn: connection to database
        :param path1: path of the first location for way line graph
        :param path2: path of the second location for way line graph
    """
    G1 = read_ways_graph(path1)
    G2 = read_ways_graph(path2)

    path_length = nx.single_source_shortest_path_length

    cur = conn.cursor()

    added_edges   = cur.execute(SQL("SELECT WAY,LENGTH FROM added"  )).fetchall()
    removed_edges = cur.execute(SQL("SELECT WAY,LENGTH FROM removed")).fetchall()

    def contrib(cur, wref, g, data):
        """ Compute the contribution of the
            accessibility relativ to wref from the set of edges
            in table
        """
        sp = path_length(g,wref)
        return sum(sp[r[0]]*r[1] for r in data)

    edges    = cur.execute(SQL("SELECT EDGE2,WAY1,WAY2,DIFF FROM paired")).fetchall()
    progress = Progress(len(edges))

    def compute(edge, w1, w2, diff):
        # Compute contribution from from removed/added edges
        total_removed = contrib(cur,w1, G1, removed_edges)
        total_added   = contrib(cur,w2, G2, added_edges)
        delta = diff + total_removed - total_added
        progress()
        return edge, total_removed, total_added, delta

    logging.info("Structural Diff: comuputing accessibility delta")
    results = [compute(*r) for r in edges]

    # Update edge table
    logging.info("Structural Diff: updating edges table")
    with attr_table(cur, "edge_attr") as attrs:
        attrs.update('paired_edges', 'EDGE2', 'REMOVED', [(r[0],r[1]) for r in results])
        attrs.update('paired_edges', 'EDGE2', 'ADDED'  , [(r[0],r[2]) for r in results])
        attrs.update('paired_edges', 'EDGE2', 'DELTA'  , [(r[0],r[3]) for r in results])

    cur.close()
    

def split_edges( conn, edges, places ):
    """ Split edges with places 
    """
    cur = conn.cursor()
   
    logging.info("Structural Diff: splitting {} geometries with {}".format(edges,places))
    cur.execute(SQL("DELETE from edges_temp"))
    cur.execute(SQL("""
        INSERT INTO edges_temp(ACCES, WAY, EDGE, GEOMETRY) SELECT t.acces, t.way, t.fid, t.geom
            FROM (SELECT e.ACCES AS acces,  e.WAY AS way, e.OGC_FID AS fid, 
                   ST_Multi(ST_Difference(e.GEOMETRY, ST_Union(p.GEOMETRY))) AS geom
            FROM {edges} as e, {places} as p
            WHERE ST_Intersects(e.GEOMETRY, p.GEOMETRY) AND NOT ST_Within(e.GEOMETRY, p.GEOMETRY)
            AND e.ROWID IN (
                SELECT ROWID FROM Spatialindex
                WHERE f_table_name='{edges}' AND search_frame=p.GEOMETRY)
            GROUP BY e.OGC_FID) AS t
            WHERE t.geom IS NOT NULL
        """, edges=edges, places=places))

    # Insert remaining edges
    cur.execute(SQL("""
        INSERT INTO edges_temp(ACCES, WAY, EDGE, GEOMETRY)
            SELECT e.ACCES, e.WAY, e.OGC_FID, ST_Multi(e.GEOMETRY)
            FROM {edges} AS e
            WHERE e.OGC_FID NOT IN (SELECT EDGE from edges_temp)
        """, edges=edges))

    [n] = cur.execute(SQL("SELECT count(*) from edges_temp")).fetchone()
    logging.info("Structural Diff: splitted %d geometries" % n) 

    # Clean up original edge table
    cur.execute(SQL("DELETE FROM {edges}",edges=edges))

    logging.info("Structural Diff: inserting splitted geometries into {}".format(edges))
    # Split/insert each lines
    cur.execute(SQL("""
        INSERT INTO {edges}(ACCES,WAY,LENGTH,GEOMETRY)
        SELECT t.ACCES, t.WAY, ST_Length(t.GEOM), t.GEOM 
        FROM ( SELECT ACCES , WAY, ST_GeometryN(e.GEOMETRY,VALUE) AS GEOM
               FROM edges_temp AS e, counter 
               WHERE counter.VALUE <= ST_NumGeometries(e.GEOMETRY)) AS t
     """,edges=edges))

    [n] = cur.execute(SQL("SELECT count(*) FROM {edges}", edges=edges)).fetchone()
    logging.info("Structural Diff: total %d geometries in %s" % (n,edges)) 

    cur.close()


def create_counter(conn):
    """ Create a table holding integer list
    """
    cur = conn.cursor()
    cur.execute(SQL("CREATE TABLE counter(VALUE integer)"))
    cur.executemany(SQL("INSERT INTO counter(VALUE) SELECT ?"),[(c,) for c in range(1,1001)] )
    cur.close()

def create_temp_table(conn):
    """ Create temporary table
    """
    cur = conn.cursor()
    cur.execute(SQL("""
        CREATE TABLE edges_temp (
        OGC_FID integer PRIMARY KEY,
        WAY     integer,
        ACCES   real,
        LENGTH  real,
        EDGE    integer)
    """))
    cur.execute(SQL("""
        SELECT AddGeometryColumn(
            'edges_temp',
            'GEOMETRY',
            (
                SELECT CAST(srid AS integer)
                FROM geometry_columns
                WHERE f_table_name='edges1'
            ),
            'MULTILINESTRING',
            (
                SELECT coord_dimension
                FROM geometry_columns
                WHERE f_table_name='edges1'
            )
        )"""))
    cur.execute(SQL("SELECT CreateSpatialIndex('edges_temp', 'GEOMETRY')"))
    cur.close()



def structural_diff(path1, path2, output, buffersize):
    """ Compute structural diff between two files

        :param path1: path of the first location for edges shapefile and way line graph
        :param path2: path of the second location for edges shapefile and way line graph
        :param output: path where to store output data

        Input edge files must have been computed using the morpheo graph builder
        and hold data about ways accessibility
    """

    # Import shapefiles
    dbname = output+'.sqlite'
    if os.path.exists(dbname):
        logging.info("Removing existing  database %s" % dbname)
        os.remove(dbname)

    create_database( dbname )

    def import_data(conn, path, sfx):
         basename = os.path.basename(path)
         logging.info("Structural diff: importing edge data from %s" % path)

         execute_sql(conn,"import_edges.sql", sfx=sfx, srcdb=path+'.sqlite')
    
    conn = connect_database(dbname)

    import_data(conn, path1, '1')
    import_data(conn, path2, '2')

    # Check that the srid of the two table are the same:
    [srid1] = conn.execute("SELECT CAST(srid AS integer) FROM geometry_columns WHERE f_table_name='edges1'").fetchone()
    [srid2] = conn.execute("SELECT CAST(srid AS integer) FROM geometry_columns WHERE f_table_name='edges2'").fetchone()
    if srid1 != srid2:
        logging.error("Table must have the same SRID ! Found %s and %s, please check that input have the same spatial référence")
        raise MorpheoException("Table must have the same SRID")

    accessibility_delta = True

    # Check that the accessibility is computed:
    for tab in ('edges1', 'edges2'):
        [bads] = conn.execute("SELECT Count(1) FROM %s WHERE ACCES IS NULL" % tab).fetchone()
        if bads > 0:
            logging.warn("Structural diff: Accessibility is not computed for %s delta will not be computed" % tab)
            accessibility_delta = False

    # Split edges
    create_counter(conn)
    create_temp_table(conn)
    split_edges(conn, 'edges1', 'places2')
    split_edges(conn, 'edges2', 'places1')

    conn.commit()

    # Compute paired edges
    logging.info("Structural Diff: computing paired edges with buffersize = %f" % buffersize)
    execute_sql(conn,"structdiff.sql", buffersize=buffersize)
    conn.commit()

    if accessibility_delta:
        compute_accessibility_delta(conn, path1, path2)
        conn.commit()
    
    cur = conn.cursor()
    [paired_count]  = cur.execute(SQL("SELECT COUNT(*) FROM paired_edges")).fetchone()
    [removed_count] = cur.execute(SQL("SELECT COUNT(*) FROM removed_edges")).fetchone()
    [added_count]   = cur.execute(SQL("SELECT COUNT(*) FROM added_edges")).fetchone()
    cur.close()

    conn.close()

    logging.info("Structural Diff: paired edges: %d, removed_edges: %d, added_edges: %d" % (paired_count, removed_count, added_count))

    # Export files
    logging.info("Diff: exporting files")
    export_shapefile(dbname, 'paired_edges', output)
    export_shapefile(dbname, 'removed_edges', output)
    export_shapefile(dbname, 'added_edges', output)


    # Write manifest
    with open(os.path.join(output,'morpheo_%s.manifest' % os.path.basename(output)),'w') as f:
            f.write("tolerance={}\n".format(buffersize))
            f.write("file1=%s\n" % path1)
            f.write("file2=%s\n" % path2)


