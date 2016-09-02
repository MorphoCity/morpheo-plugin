# -*- encoding=utf-8 -*-
""" Place builder helper
"""
from __future__ import print_function

import os
import logging
import networkx as nx

from .logger import log_progress
from .errors import BuilderError, ErrorGraphNotFound
from .sql import (SQL, execute_sql, 
                  create_indexed_table,
                  delete_table, 
                  connect_database, table_exists)

from .layers import export_shapefile

BUFFER_TABLE='temp_buffer'


def _edge_graph_path( output ):
    """ Build edge graph path
    """
    basename = os.path.basename(output)
    return os.path.join(output,'edge_graph_'+basename+'.gpickle')


def build_edges_graph(conn, output):
    """ Build place edge graph and export file
    """
    cur  = conn.cursor()
    rows = cur.execute(SQL("SELECT START_PL, END_PL, LENGTH, OGC_FID FROM place_edges")).fetchall()

    # Edges are multigraph
    logging.info("Places: building edges graph")
    g = nx.MultiGraph()
    g.add_edges_from( (r[0],r[1],{'length': int(r[2]), 'fid': r[3]}) for r in rows)

    logging.info("Places: saving edges graph")
    nx.write_gpickle(g, _edge_graph_path(output))
    return g


def load_edge_graph( path ):
    """ Load edge NetworkX  graph

        :param path: of the morpheo data
        
        :return: A NetworkX graph
    """
    graph_path = _edge_graph_path(path)
    logging.info("Importing edge graph %s" % graph_path)
    try:
        return nx.read_gpickle(graph_path)
    except Exception as e:
        raise ErrorGraphNotFound(
                "Error while reading graph {}: {}".format(graph_path,e))


class PlaceBuilder(object):

    def __init__(self, conn, chunks=100):
       self._conn   = conn
       self._chunks = chunks

    def export(self, dbname, output, export_graph=False ):
       logging.info("Places: Saving places to %s" % output)
       export_shapefile(dbname, 'places'     , output)
       export_shapefile(dbname, 'place_edges', output)
       if export_graph:
           build_edges_graph(self._conn, output)
       else:
          # Clean up existing graph
          path = _edge_graph_path(output)
          if os.path.exists(path):
              logging.info("Places: cleaning existing edge graph")
              os.remove(path)
   
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

        if buffer_size > 0:
            self.creates_places_from_buffer(buffer_size, input_places )
        else:
            self.creates_places_from_file(input_places)
        logging.info("Places: building edges")
        execute_sql(self._conn, "places.sql")
        self._conn.commit()

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
        def union_buffers():
            count = cur.execute(SQL("SELECT Max(OGC_FID) FROM {buffer_table}", buffer_table=BUFFER_TABLE)).fetchone()[0]
            if count <= self._chunks:
                cur.execute(SQL("""
                    INSERT INTO  {buffer_table}(GEOMETRY)
                    SELECT ST_Union(GEOMETRY) FROM {buffer_table}
                """, buffer_table=BUFFER_TABLE))
                cur.execute(SQL("DELETE FROM {buffer_table} WHERE OGC_FID <= {count}",
                        buffer_table=BUFFER_TABLE,count=count))
            else:            
                try:
                    # Create temporary buffer table
                    table = 'temp_buffer_table' 
                    create_indexed_table( cur, table, 'MULTIPOLYGON', BUFFER_TABLE)
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
                            SELECT ST_Multi(ST_Union(GEOMETRY)) AS GEOMETRY FROM {buffer_table}
                            WHERE OGC_FID>={start} AND OGC_FID<{end}
                        """, tmp_table=table, buffer_table=BUFFER_TABLE, 
                             buffer_size=buffer_size, start=start, end=end))
                        log_progress( end, count )
                    # Final merge into buffer_table
                    logging.info("Places: finalizing union...")
                    cur.execute(SQL("DELETE FROM {buffer_table}", buffer_table=BUFFER_TABLE))
                    cur.execute(SQL("""
                        INSERT INTO  {buffer_table}(GEOMETRY)
                        SELECT ST_Union(GEOMETRY)  FROM {tmp_table}
                    """, tmp_table=table, buffer_table=BUFFER_TABLE))
                finally:
                    delete_table(cur, table)

        cur = self._conn.cursor()

        create_indexed_table(cur, BUFFER_TABLE, 'MULTIPOLYGON', 'vertices')
        cur.execute(SQL("DELETE FROM places"))

        # Apply buffer to entities and merge them
        # This will make a one unique geometry that will be splitted into elementary
        # parts

        logging.info("Places: Creating buffers...")

        # Create a table of terminal vertices
        # We need to handle them in a special way

        cur.execute(SQL("CREATE TABLE IF NOT EXISTS left_vertices(OGC_FID integer PRIMARY KEY)"))
        cur.execute(SQL("DELETE FROM left_vertices"))

        # Index all vertices
        cur.execute(SQL("INSERT INTO left_vertices(OGC_FID) SELECT OGC_FID FROM vertices"))

        # Remove all vertices that are in input_places
        if input_places is not None:
            # Remove from left vertices all vertices included in places
            cur.execute(SQL("""DELETE FROM left_vertices WHERE OGC_FID IN (
                    SELECT v.OGC_FID FROM vertices AS v, {input_places} AS p 
                    WHERE ST_Within(v.GEOMETRY,p.GEOMETRY)
                    AND v.ROWID IN(
                        SELECT ROWID FROM SpatialIndex
                        WHERE f_table_name='vertices' AND search_frame=p.GEOMETRY))
            """,input_places=input_places))

        # Create buffers from left vertices vertices with degree > 1
        cur.execute(SQL("""
                INSERT INTO {buffer_table}(OGC_FID,GEOMETRY)
                SELECT v.OGC_FID, ST_Multi(ST_Buffer( v.GEOMETRY, {buffer_size})) 
                FROM vertices AS v, left_vertices AS l
                WHERE v.DEGREE>1 AND l.OGC_FID=v.OGC_FID
            """, buffer_table=BUFFER_TABLE, buffer_size=buffer_size))

        # Remove inserted vertices
        cur.execute(SQL("""
                DELETE FROM left_vertices WHERE OGC_FID IN (
                SELECT OGC_FID FROM {buffer_table})
        """,buffer_table=BUFFER_TABLE))

        # Create buffers
        union_buffers()

        # Explode buffer blob into elementary geometries
        logging.info("Places: computing convex hulls")
        cur.execute(SQL("""
           INSERT INTO places(GEOMETRY)
           SELECT ST_ConvexHull(GEOMETRY) FROM ElementaryGeometries WHERE f_table_name='{buffer_table}' AND origin_rowid=1
        """, buffer_table=BUFFER_TABLE))
        
        if input_places is not None:
            # Cleanup places
            # copy geometries into buffer table
            cur.execute(SQL("DELETE from {buffer_table}",buffer_table=BUFFER_TABLE))
            cur.execute(SQL("""
                    INSERT INTO {buffer_table}(GEOMETRY)
                    SELECT ST_Multi(CastToXYZ(GEOMETRY)) FROM {input_table}
            """,input_table=input_places, buffer_table=BUFFER_TABLE))
            union_buffers()
            self._conn.commit()
            create_indexed_table(cur, 'tmp_places', 'POLYGON', 'places')
            try:
                [rowid] = cur.execute(SQL("SELECT OGC_FID FROM {buffer_table} LIMIT 1",
                                    buffer_table=BUFFER_TABLE)).fetchone()
                cur.execute(SQL("""
                    INSERT INTO tmp_places(GEOMETRY)
                    SELECT GEOMETRY FROM ElementaryGeometries WHERE f_table_name='{buffer_table}' 
                    AND origin_rowid={rowid}
                """,buffer_table=BUFFER_TABLE, rowid=rowid))

                # now we need to check if we merge adjacent computed places in input places or not

                # Select all buffers that intersect places
                rows=cur.execute(SQL("""
                    SELECT b.OGC_FID AS buffer, p.OGC_FID AS place
                    FROM places AS b, tmp_places AS p 
                    WHERE ST_Intersects(b.GEOMETRY, p.GEOMETRY)
                        AND b.ROWID IN (
                            SELECT ROWID FROM SpatialIndex
                            WHERE f_table_name='places' AND search_frame=b.GEOMETRY
                        )""")).fetchall()

                to_merge = {place:[] for _,place in rows}

                for buf, place in rows:
                    # Fetch all vertices included in buffer
                    vertices=cur.execute(SQL("""
                        SELECT v.OGC_FID FROM vertices AS v, places AS b
                            WHERE ST_Within( v.GEOMETRY, b.GEOMETRY )
                            AND b.OGC_FID={buffer}
                            AND v.ROWID IN (
                                SELECT ROWID FROM SpatialIndex
                                WHERE f_table_name='vertices' AND search_frame=b.GEOMETRY)
                            """, buffer=buf)).fetchall()

                    # Test that they are connected to vertex in place
                    [rv] = cur.execute(SQL("""
                        SELECT Count(v.OGC_FID) FROM tmp_places AS p, vertices AS v
                        WHERE v.OGC_FID IN (
                            SELECT vtx FROM (
                                SELECT START_VTX AS vtx FROM edges WHERE END_VTX IN ({vertices})
                                UNION
                                SELECT END_VTX AS vtx FROM edges WHERE START_VTX IN ({vertices})
                            )
                        ) 
                        AND p.OGC_FID={place}
                        AND ST_Within( v.GEOMETRY, p.GEOMETRY )
                        AND v.ROWID IN (
                            SELECT ROWID FROM SpatialIndex
                            WHERE f_table_name='vertices' AND search_frame=p.GEOMETRY)
                        """, place=place, vertices=','.join(str(s[0]) for s in vertices))).fetchone()

                    if rv:
                        to_merge[place].append(buf)

                # Merge buffers into places
                for place, buffers in to_merge.iteritems():
                    if buffers:
                        bufstr = ','.join(str(b) for b in buffers)
                        cur.execute(SQL("""INSERT INTO places(GEOMETRY)
                            SELECT ST_Union(geom) FROM (
                                SELECT GEOMETRY AS geom FROM tmp_places WHERE OGC_FID={place}
                                UNION ALL
                                SELECT GEOMETRY AS geom FROM places WHERE OGC_FID in ({buffers})
                            )""",place=place, buffers=bufstr))
                    
                        # Clean up merged buffers
                        cur.execute(SQL("""DELETE FROM places WHERE OGC_FID in ({buffers})""",
                                        buffers=bufstr))
            finally:
                delete_table(cur, 'tmp_places')

        delete_table(cur, BUFFER_TABLE)
        
        # Checkout number of places
        rv = cur.execute(SQL("Select Count(*) FROM places")).fetchone()[0]
        if rv <= 0:
            raise BuilderError("No places created ! please check input data !")
        else:
           logging.info("Places: created {} places".format(rv))
         
           

