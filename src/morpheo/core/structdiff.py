# -*- coding: utf-8 -*-
""" Module for computing structural diff
"""
import os
import logging
import networkx as nx

from .logger import Progress
from .sql    import connect_database, SQL, execute_sql, attr_table
from .layers import import_shapefile, export_shapefile
from .ways   import read_ways_graph

def structural_diff( path1, path2, output, buffersize ):
    """ Compute structural diff between two files 

        :param path1: path of the first location for edges shapefile and way line graph 
        :param path2: path of the second location for edges shapefile and way line graph
        :param output: path where to store output data

        Input edge files must have been computed using the morpheo graph builder
        and hold data about ways accessebility
    """

    # Import shapefiles
    dbname = output+'.sqlite'
    if os.path.exists(dbname):
        logging.info("Removing existing  database %s" % dbname)
        os.remove(dbname)

    def import_data(path, table, create=False):
        basename = os.path.basename(path)
        shp = os.path.join(path,'place_edges_%s.shp' % basename)
        logging.info("Structural diff: importing %s" % shp)
        import_shapefile( dbname, shp, table)
        logging.info("Structural diff: importing way line graph")
        return read_ways_graph(path)

    G1 = import_data(path1, 'edges1')
    G2 = import_data(path2, 'edges2')

    # Connect to the database
    conn = connect_database(dbname)

    # Compute paired edges
    logging.info("Structural Diff: computing paired edges")
    execute_sql(conn,"structdiff.sql", buffersize=buffersize)

    path_length = nx.single_source_shortest_path_length

    cur = conn.cursor()

    added_edges   = cur.execute(SQL("SELECT WAY,LENGTH FROM added"  )).fetchall() 
    removed_edges = cur.execute(SQL("SELECT WAY,LENGTH FROM removed")).fetchall() 

    def contrib(cur, wref, g, data):
        """ Compute the contribution of the
            accessibility relativ to wref from the set of edges 
            in table
        """
        sp   = path_length(g,wref)
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
    with attr_table(cur, "edgge_attr") as attrs:
        attrs.update('paired_edges', 'EDGE2', 'REMOVED', [(r[0],r[1]) for r in results])
        attrs.update('paired_edges', 'EDGE2', 'ADDED'  , [(r[0],r[2]) for r in results])
        attrs.update('paired_edges', 'EDGE2', 'DELTA'  , [(r[0],r[3]) for r in results])

    cur.close()
    conn.commit()

    # Export files
    logging.info("Diff: exporting files")
    export_shapefile(dbname, 'paired_edges', output) 
    
    # Write manifest
    with open(os.path.join(output,'morpheo_%s.manifest' % output),'w') as f:
            f.write("tolerance={}".format(buffersize))
            f.write("file1=%s\n" % path1)
            f.write("file2=%s\n" % path2)


