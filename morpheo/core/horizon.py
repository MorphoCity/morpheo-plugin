""" Tools for computing horizon

    An horizon is the computation of topolgical distance against
    a number of selected features the  'mesh-structure')
""" 
import logging

from .errors import ErrorNoFeatures
from .layers import export_shapefile
from .mesh import features_from_attribute, features_from_geometry
from .algorithms import multiple_sources_shortest_path_length
from .sql import SQL, table_exists


def _create_horizon_table(cur, table):
    """ Create the table to store horizon
    """
    if not table_exists(cur, table):
        cur.execute(SQL("""
            CREATE TABLE {table}(
                OGC_FID integer PRIMARY KEY,
                WAY_ID  integer,
                HORIZON integer)
        """,table=table))
        cur.execute(SQL("""
            SELECT AddGeometryColumn(
                '{table}',
                'GEOMETRY',
                (
                    SELECT CAST(srid AS integer)
                    FROM geometry_columns
                    WHERE f_table_name='ways'
                ),
                'MULTILINESTRING',
                (
                    SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='ways'
                )
            );
        """,table=table))
    cur.execute(SQL("DELETE FROM {table}",table=table))
    return table


def horizon_from_way_list( conn, G, table, ways):
    """ Compute horizon from selected ways

        :param conn: connection to database
        :param G: Networkx graph
        :param table: The name of the table to store the results
        :param features: list of feature id
        :param output: complete path of text file to output data (optionel)

        The table *table* will be

    """
    # Compute all shortest path lengths
    data = multiple_sources_shortest_path_length(G, ways)

    logging.info("Horizon: computing horizon from %d features" % len(ways))

    cur = conn.cursor()

    _create_horizon_table(cur, table)
    cur.executemany(SQL("""
        INSERT INTO {table}(OGC_FID,WAY_ID,HORIZON,GEOMETRY)
        SELECT OGC_FID,WAY_ID,?,GEOMETRY FROM ways WHERE WAY_ID=?
    """,table=table), [(v,w) for w,v in data.items()])
    
         
def horizon_from_attribute( conn, G, table,  attribute, percentile):
    """ Compute horizon from a percentile of a numerical attributs

        :param conn: connection to database
        :param G: Way networkx graph
        :param table: The name of the table to store the results
        :param attribute: Attribute column
        :param percentile: Percentage of objects to retrieve from a list 
                         ordered in decreasing order of attribute value
        :param output: complete path of text file to output data (optionel)
    """
    logging.info("Horizon: computing horizon from %s (percentile %.2f)" % (attribute, percentile))
    ways = features_from_attribute(conn.cursor(), 'ways', attribute, percentile,
                                       fid_column='WAY_ID')

    if len(ways)==0:
        raise ErrorNoFeatures("No features found for attribute %s (percentile %.2f)" % (attribute, percentile)) 
 
    horizon_from_way_list(conn, G, table, ways)


def horizon_from_geometry( conn, G,  table, wkbgeom, within=False):
    """ Compute horizon from features selected from a geometry

        :param conn: connection to database
        :param G: Networkx graph
        :param table: The name of the table to store the results
        :param wkbgeom: Geometry in wkb format
        :param output: complete path of text file to output data (optionel)
    """
    ways = features_from_geometry(conn.cursor(), 'ways', wkbgeom, within=within,
                                  fid_column='WAY_ID')

    horizon_from_way_list(conn, G, table, ways) 


