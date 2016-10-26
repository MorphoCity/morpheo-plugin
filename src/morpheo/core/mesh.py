# -*- coding: utf-8 -*-
""" Helpers for computinf mesh structures
"""
import logging
from .sql import SQL, create_indexed_table, delete_indexed_table


def create_indexed_table_from_attribute( cur, name, table, attribute, percentile, geomtype):
    """ Create a new table from features from a percentile of a given
         numerical attribute starting from the highest value

        :param cur: database cursor
        :param name: The name of the new table
        :param table: The table to get the features from
        :param attribute: Attribute column
        :param percentile: Percentage of objects to retrieve from a list
                           ordered in decreasing order of attribute value

    """
    assert 0 <= percentile <= 100
    [total] = cur.execute(SQL("SELECT Count(*) FROM {table} WHERE {attribute} NOT NULL",
                              table=table,attribute=attribute)).fetchone()
    if total == 0:
        logging.warn("No values set for %s in table %s" %(attribute,table))
    # Compute number to retrieve
    limit = int(total/100.0 * percentile)
    # Retrieve all
    delete_indexed_table(cur, name)
    create_indexed_table(cur, name, geomtype, table)
    rows = cur.execute(SQL("""INSERT INTO {name}(OGC_FID,GEOMETRY)
        SELECT OGC_FID,GEOMETRY FROM {table} WHERE {attribute} NOT NULL ORDER BY {attribute} DESC
        LIMIT {limit}
    """,name=name, table=table, attribute=attribute, limit=limit)).fetchall()

    return [r[0] for r in rows]


def create_indexed_table_from_edge_attribute( conn, name,  attribute, percentile):
    create_indexed_table_from_attribute(conn.cursor(), name, "place_edges",
                                        attribute, percentile, "LINESTRING")

    conn.commit()

def create_indexed_table_from_way_attribute( conn, name,  attribute, percentile):
    create_indexed_table_from_attribute(conn.cursor(), name, "ways",
                                        attribute, percentile, "MULTILINESTRING")
    conn.commit()



def features_from_attribute(cur, table, attribute, percentile, fid_column="OGC_FID"  ):
    """ Retrieve feature list from a percentile of a given
        numerical attribute starting from the highest value

        :param cur: database cursor
        :param table: The table to get the features from
        :param attribute: Attribute column
        :param percentile: Percentage of objects to retrieve from a list
                           ordered in decreasing order of attribute value

        :return: A list of features id
    """
    assert 0 <= percentile <= 100
    [total] = cur.execute(SQL("SELECT Count(*) FROM {table} WHERE {attribute} NOT NULL",
                              table=table,attribute=attribute)).fetchone()
    if total == 0:
        logging.warn("No values set for %s in table %s" %(attribute,table))
    # Compute number to retrieve
    limit = int(total/100.0 * percentile)
    # Retrieve all
    rows = cur.execute(SQL("""SELECT {column} FROM {table}
        WHERE {attribute} NOT NULL ORDER BY {attribute} DESC LIMIT {limit}
    """,table=table, attribute=attribute, limit=limit,
        column=fid_column)).fetchall()

    return [r[0] for r in rows]


def features_from_point_radius( cur, table, x, y, radius, fid_column="OGC_FID", within=False, srid=None ):
    """ Return features that are intersecting the  given geometry

        :param cur: database cursor
        :param table: The table to get the features from
        :param x: The E-W location
        :param y: The N-S location
        :param radius: The search radius (in meters)
        :param within: Get only features strictly included in
                       test geometry

        :return: A list of features id
    """
    if srid is None:
        [srid] = cur.execute(SQL("SELECT srid FROM geometry_columns WHERE f_table_name='{table}'",table=table)).fetchone()
    if within:
        rows = cur.execute(SQL("""SELECT {column} FROM {table} AS n,
            (SELECT ST_Buffer(GeomFromText('POINT({x} {y})',{srid}),{radius}) AS GEOM) AS t
            WHERE ST_Within(n.GEOMETRY,t.GEOM)
            AND n.ROWID IN (
                SELECT ROWID FROM SpatialIndex
                WHERE f_table_name='{table}' AND search_frame=t.GEOM
            )
        """,table=table,srid=srid,x=x,y=y,radius=radius,column=fid_column)).fetchall()
    else:
         rows = cur.execute(SQL("""SELECT {column} FROM {table} AS n,
            (SELECT ST_Buffer(GeomFromText('POINT({x} {y})',{srid}),{radius}) AS GEOM) AS t
            WHERE ST_Intersects(n.GEOMETRY,t.GEOM)
            AND n.ROWID IN (
                SELECT ROWID FROM SpatialIndex
                WHERE f_table_name='{table}' AND search_frame=t.GEOM
            )
        """,table=table,srid=srid,x=x,y=y,radius=radius,column=fid_column)).fetchall()

    return [r[0] for r in rows]


def features_from_geometry( cur, table, wkbgeom, within=False, fid_column="OGC_FID" ):
    """ Return features that are intersecting the  given geometry

        :param cur: database cursor
        :param table: The table to get the features from
        :param wkbgeom: Test geometry in wkb format
        :param within: Get only features strictly included in
                       test geometry

        :return: A list of features id
    """
    if within:
        rows = cur.execute(SQL("""SELECT {column} FROM {table} AS n,
            (SELECT ST_GeomFromWKB({geom}) AS GEOM) AS t
            WHERE ST_Within(n.GEOMETRY,t.GEOM)
            AND n.ROWID IN (
                SELECT ROWID FROM SpatialIndex
                WHERE f_table_name='{table}' AND search_frame=t.GEOM)
            )
        """,table=table,geom=wkbgeom,column=fid_column)).fetchall()
    else:
         rows = cur.execute(SQL("""SELECT {column} FROM {table} AS n,
            (SELECT ST_GeomFromWKB({geom}) AS GEOM) AS t
            WHERE ST_Intersects(n.GEOMETRY,t.GEOM)
            AND n.ROWID IN (
                SELECT ROWID FROM SpatialIndex
                WHERE f_table_name='{table}' AND search_frame=t.GEOM)
            )
        """,table=table, geom=wkbgeom,column=fid_column)).fetchall()

    return [r[0] for r in rows]


def edges_from_edge_attribute(cur, attribute, percentile):
    """ Retrieve  list of edges

        The edges are selected from a percentile of a given
        numericable attribute starting from the highest value

        :param cur: database cursor
        :param attribute: Attribute column
        :param percentile: Percentage of objects to retrieve from a list
                           ordered in decreasing order of attribute value
        :param within: Get only features strictly included in
                       test geometry

        :return: A list of 3-tuples (start,end,length)
    """
    assert 1<= percentile <= 100
    [total] = cur.execute(SQL("SELECT Count(*) FROM place_edges")).fetchone()
    # Compute number to retrieve
    limit = int(total/100.0 * percentile)
    # Retrieve all
    rows = cur.execute(SQL("""SELECT START_PL,END_PL,LENGTH FROM place_edges
                              ORDER BY {attribute} DESC LIMIT {limit}
    """,attribute=attribute, limit=limit)).fetchall()

    return rows


def edges_from_way_attribute(cur, attribute, percentile, columns=["LENGTH"]):
    """ Retrieve list of edges from a selection of ways

        The ways are selected from a percentile of a given
        numerical attribute starting from the highest value

        :param cur: database cursor
        :param attribute: Attribute column
        :param percentile: Percentage of objects to retrieve from a list
                           ordered in decreasing order of attribute value
        :param columns: List of extra columns returned
        :return: A list of n-tuples (start,end, column 1,...)
    """
    columns = columns or ["OGC_FID"]

    assert 1<= percentile <= 100
    [total] = cur.execute(SQL("SELECT Count(*) FROM ways")).fetchone()
    # Compute number to retrieve
    limit = int(total/100.0 * percentile)
    # Retrieve all
    rows = cur.execute(SQL("""SELECT START_PL,END_PL,{columns} FROM place_edges
        WHERE WAY IN (
            SELECT WAY_ID FROM ways
            ORDER BY {attribute} DESC LIMIT {limit})
    """,attribute=attribute, limit=limit, columns=','.join(columns))).fetchall()

    return rows


