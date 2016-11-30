# -*- encoding=utf-8 -*-

import os
import string
import logging

from contextlib import contextmanager

from .errors import BuilderError
from .logger import log_progress

class SQLNotFoundError(BuilderError):
    pass


def connect_database( dbname ):
    """ Connect to database 'dbname'
    """
    from pyspatialite import dbapi2 as db
    conn = db.connect(dbname)
    cur  = conn.cursor()
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.close()
    return conn


def SQL( sql, **kwargs):
    """ Wrap SQL statement 
    """
    sql = sql.format(**kwargs)
    logging.debug(sql)
    return sql


def create_database( dbname ):
    """ Create an empty database
    """
    if not os.path.exists(dbname):
        from pyspatialite import dbapi2 as db
        conn = db.connect(dbname)
        cur  = conn.cursor()
        cur.execute('SELECT initspatialmetadata(1)')
        cur.close()
        conn.commit()
        conn.close()
 

def load_sql(name, **kwargs):
    """ Load graph builder sql

        sql file is first searched as package data. If not
        found then __file__ path  is searched

        :raises: SQLNotFoundError
    """
    # Try to get schema from ressources
    try:
        import pkg_resources    
        srcpath = pkg_resources.resource_filename("morpheo","core")
    except ImportError:
        # If we are executed as qgis plugin, the moprheo package does not exists
        # try to load resource from module path
        srcpath = os.path.dirname(__file__)

    sqlfile = os.path.join(srcpath, name)
    if not os.path.exists(sqlfile):
        # If we are not in standard python installation,
        # try to get file locally
        lookupdir = os.path.dirname(__file__)
        logging.info("Builder: looking for sql file in %s" % lookupdir)
        sqlfile = os.path.join(lookupdir)

    if not os.path.exists(sqlfile):
        raise SQLNotFoundError("Cannot find file %s" % sqlfile)

    with open(sqlfile,'r') as f:
        sql = string.Template(f.read()).substitute(**kwargs)
    return sql


def execute_sql(conn, name, quiet=False, **kwargs):
    """ Execute statements from sql file

        All extra named arguments will be used as substitution parameters
        for $<name> expressions in the sql file.

        :param conn: the database connection
        :param name: of the sql file to execute
    """
    statements = load_sql(name, **kwargs).split(';')
    count = len(statements)
    cur   = conn.cursor()
    for i, statement in enumerate(statements):
        if not quiet:
            log_progress(i+1,count) 
        if statement:
            cur.execute(SQL(statement))
    conn.commit()


def table_exists( cur, name ):
    """ Test if table exists
    """
    cur.execute(SQL("""SELECT Count(*) FROM sqlite_master 
        WHERE type='table' AND name='{table}'""",table=name))
    return int(cur.fetchone()[0])==1


def create_indexed_table( cur, table, geomtype, table_ref  ):
    """ Create a spatially indexed table 
    """
    if not table_exists(cur, table):
        cur.execute(SQL("CREATE TABLE {table}(OGC_FID integer primary key)",table=table))
        cur.execute(SQL("""
            SELECT AddGeometryColumn(
                '{table}',
                'GEOMETRY',
                (
                    SELECT CAST(srid AS integer)
                    FROM geometry_columns
                    WHERE f_table_name='{table_ref}'
                ),
                '{geomtype}',
                (
                    SELECT coord_dimension
                    FROM geometry_columns
                    WHERE f_table_name='{table_ref}'
                )
           )""",table=table, table_ref=table_ref, geomtype=geomtype))
        cur.execute(SQL("SELECT CreateSpatialIndex('{table}', 'GEOMETRY')", table=table))
    cur.execute(SQL("DELETE FROM {table}",table=table)) 


def delete_table( cur, table ):
    """ Safely delete spatialite table """
    if table_exists(cur, table):
        cur.execute(SQL("SELECT DisableSpatialIndex('%s', 'GEOMETRY')" % table));
        cur.execute(SQL("SELECT DiscardGeometryColumn('%s', 'GEOMETRY')" % table));
        cur.execute(SQL("DROP TABLE idx_%s_GEOMETRY" % table))
        cur.execute(SQL("DROP TABLE %s" % table))
        cur.execute(SQL("VACUUM"))

delete_indexed_table = delete_table


def set_srid( cur, table, from_table ):
    """ Force srid for table
    """
    [srid_to]   = cur.execute(SQL("SELECT srid FROM geometry_columns WHERE f_table_name='{table}'",
                              table=from_table)).fetchone()
    [srid_from] = cur.execute(SQL("SELECT srid FROM geometry_columns WHERE f_table_name='{table}'",
                              table=table)).fetchone()

    if srid_to != srid_from:
        cur.execute(SQL("UPDATE geometry_columns SET srid = {srid} WHERE f_table_name = '{table}'",
                        table=table, srid=srid_to))
        cur.execute(SQL("UPDATE {table} SET GEOMETRY = SetSRID(GEOMETRY, {srid})",
                        table=table, srid=srid_to))


def create_attribute_table( cur, name,  dtype='real'):
    """ Create a table for storing temporary results 
    """
    cur.execute(SQL("CREATE TABLE IF NOT EXISTS {name}(ID integer,VALUE {dtype})",name=name,dtype=dtype))
    cur.execute(SQL("CREATE INDEX IF NOT EXISTS {name}_ID_idx ON {name}(ID)",name=name))
    cur.execute(SQL("DELETE FROM {name}",name=name))
    return name


def fill_attribute_table( cur, name, rows ):
    """ Update attribute table with data
    """
    cur.execute(SQL("DELETE FROM {name}",name=name))
    cur.executemany(SQL("INSERT INTO %s(ID,VALUE) SELECT ?,?" % name),rows)


def delete_attr_table( cur, name):
    """ Delete attribute table
    """
    if table_exists(cur, name):
        cur.execute(SQL("DROP INDEX %s_ID_idx" % name))
        cur.execute(SQL("DROP TABLE %s" % name))
        cur.execute(SQL("VACUUM"))


class AttrTable(object):
    def __init__(self, cur, name, dtype='real'):
        self._cur  = cur
        self._name = create_attribute_table(cur, name, dtype=dtype)

    def fill( self, rows ):
        fill_attribute_table( self._cur, self._name, rows ) 

    @property
    def name(self):
        return self._name

    def update( self, dest_table, dest_id, dest_colunm, rows=None ):
        """ Update destination table
        """
        if rows is not None:
            self.fill(rows)
        self._cur.execute(SQL("""
            UPDATE {table} SET {column} = (SELECT VALUE FROM {attr_table} WHERE ID={table}.{fid})
        """,table=dest_table,column=dest_colunm,fid=dest_id,attr_table=self._name))


@contextmanager
def attr_table( cur, name, dtype='real'):
    attr_tab = AttrTable(cur, name, dtype=dtype) 
    try:
        yield attr_tab
    finally:
        delete_attr_table(cur, name)


