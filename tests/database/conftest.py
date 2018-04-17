# -*- coding: utf-8 -*-

from __future__ import print_function
import os 
import sys
import pytest


def spatialite_connect(*args, **kwargs):
    """ Returns a dbapi2.Connection to a SpatiaLite db
    """
    import sqlite3
    con = sqlite3.dbapi2.connect(*args, **kwargs)
    con.enable_load_extension(True)
    cur = con.cursor()
    libs = [
        # SpatiaLite >= 4.2 and Sqlite >= 3.7.17, should work on all platforms
        ("mod_spatialite", "sqlite3_modspatialite_init"),
        # SpatiaLite >= 4.2 and Sqlite < 3.7.17 (Travis)
        ("mod_spatialite.so", "sqlite3_modspatialite_init"),
        # SpatiaLite < 4.2 (linux)
        ("libspatialite.so", "sqlite3_extension_init")
    ]
    found = False
    for lib, entry_point in libs:
        try:
            cur.execute("select load_extension('{}', '{}')".format(lib, entry_point))
            logging.info("Successfully loaded spatialite module '%s'", lib)
        except sqlite3.OperationalError:
            continue
        else:
            found = True
            break
    if not found:
        raise RuntimeError("Cannot find any suitable spatialite module")
    cur.close()
    con.enable_load_extension(False)
    return con


database = None


@pytest.fixture(scope="session")
def conn(request):
    connection = spatialite_connect(database, isolation_level = None)
    cursor     = connection.cursor()

    class Sql(object):
        @property
        def conn(self):
            return connection

        @property
        def database(self):
            return database

        def execute( self, query ):
            return cursor.execute(query)            

        def execfile( self, sqlfile ):
            with open(sqlfile,'r') as f:
                cursor.execute(f.read())

    def done():
        connection.close()

    request.addfinalizer(done)
    return Sql()

    

def pytest_addoption(parser):
    parser.addoption("--database", metavar="PATH", required=True, help="Path to sqlite database")


def pytest_configure(config):
    global database
    database = config.getoption('database')

