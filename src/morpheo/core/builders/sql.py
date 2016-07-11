# -*- encoding=utf-8 -*-

import os
import string
import logging

from .errors import BuilderError

from ..logger import log_progress

class SQLNotFoundError(BuilderError):
    pass


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
        
    srcpath = pkg_resources.resource_filename("morpheo.core","builders")
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


def execute_sql(conn, name, **kwargs):
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
        log_progress(i+1,count) 
        if statement:
            logging.debug(statement)
            cur.execute(statement)
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

