# -*- encoding=utf-8 -*-

import os
import string
import logging

from contextlib import contextmanager

from .errors import BuilderError

from ..logger import log_progress

class SQLNotFoundError(BuilderError):
    pass


def connect_database( dbname ):
    """ Connect to database 'dbname'
    """
    from pyspatialite import dbapi2 as db
    return db.connect(dbname, check_same_thread=False)


def SQL( sql, **kwargs):
    """ Wrap SQL statement 
    """
    sql = sql.format(**kwargs)
    logging.debug(sql)
    return sql


def load_sql(name, **kwargs):
    """ Load graph builder sql

        sql file is first searched as package data. If not
        found then __file__ path  is searched

        :raises: SQLNotFoundError
    """
    # Try to get schema from ressources
    import pkg_resources
        
    srcpath = pkg_resources.resource_filename("morpheo.core","builder")
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


def delete_table( conn, table ):
    """ Safely delete spatialite table """
    cur = conn.cursor()
    rv  = cur.execute(SQL("""
        SELECT Count(*) from sqlite_master 
        WHERE type='table' AND name='{table}'
    """, table=table)).fetchall()
    if rv and int(rv[0][0]) == 1:
        cur.execute(SQL("SELECT DisableSpatialIndex('%s', 'GEOMETRY')" % table));
        cur.execute(SQL("SELECT DiscardGeometryColumn('%s', 'GEOMETRY')" % table));
        cur.execute(SQL("DROP TABLE idx_%s_GEOMETRY" % table))
        cur.execute(SQL("DROP TABLE %s" % table))
        cur.execute(SQL("VACUUM"))
    conn.commit()


def create_attribute_table( cur, name,  dtype='real'):
    """ Create a table for storing temporary results 
    """
    cur.execute(SQL("CREATE TABLE {name}(ID integer,VALUE {dtype})",name=name,dtype=dtype))
    cur.execute(SQL("CREATE INDEX {name}_ID_idx ON {name}(ID)",name=name))
    return name


def fill_attribute_table( cur, name, rows ):
    """ Update attribute table with data
    """
    cur.execute(SQL("DELETE FROM {name}",name=name))
    cur.executemany(SQL("INSERT INTO %s(ID,VALUE) SELECT ?,?" % name),rows)


def delete_attr_table( cur, name):
    """ Delete attribute table
    """
    rv  = cur.execute(SQL("""
        SELECT Count(*) from sqlite_master 
        WHERE type='table' AND name='{table}'
    """, table=name)).fetchall()
    if rv and int(rv[0][0]) == 1:
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


