# -*- coding: utf-8 -*-
""" Helpers for computinf mesh structures
"""
import logging
from .sql import SQL


def features_from_attributes(cur, table, attribute, percentile, fid_column="OGC_FID"  ):
    """ Retrieve feature list from a percentile of a given
        numericable attribute starting from the highest value

    """
    assert 1<= percentile <= 100
    [total] = cur.execute(SQL("SELECT Count(*) FROM {table}",table=table)).fetchone()
    # Compute number to retrieve
    limit = int(total/100.0 * percentile)
    # Retrieve all 
    rows = cur.execute(SQL("""SELECT {column} FROM {table}
        ORDER BY {attribute} DESC LIMIT {limit} 
    """,table=table, attribute=attribute, limit=limit,
        column=fid_column)).fetchall()

    return [r[0] for r in rows]
    

def features_from_geometry( cur, table, wkbgeom, within=False ):
    """ Return features that are intersecting the  given geometry

        :param cur: database cursor
        :param table: The table to get the features from
        :param wkbgeom: Test geometry in wkb format
        :param within: Get only features strictly included in 
                       test geometry

        :return: A list of features id
    """
    if within:
        rows = cur.execute(SQL("""SELECT OGC_FID FROM {table} AS n, 
            (SELECT ST_GeomFromWKB({geom}) AS GEOM) AS t 
            WHERE ST_Within(n.GEOMETRY,t.GEOM)
            AND n.ROWID IN (
                SELECT ROWID FROM SpatialIndex
                WHERE f_table_name='{table}' AND search_frame=t.GEOM) 
            )
        """,table=table,geom=wkbgeom)).fetchall()
    else:
         rows = cur.execute(SQL("""SELECT OGC_FID FROM {table} AS n, 
            (SELECT ST_GeomFromWKB({geom}) AS GEOM) AS t 
            WHERE ST_Intersects(n.GEOMETRY,t.GEOM)
            AND n.ROWID IN (
                SELECT ROWID FROM SpatialIndex
                WHERE f_table_name='{table}' AND search_frame=t.GEOM) 
            )
        """,table=table, geom=wkbgeom)).fetchall()

    return [r[0] for r in rows]
 
