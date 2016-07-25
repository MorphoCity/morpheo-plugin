# -*- coding: utf-8 -*-

from __future__ import print_function
import os 
import sys
import pytest

sys.path.append(os.environ["QGIS_PYTHONPATH"])
from pyspatialite import dbapi2 as db

database = None


@pytest.fixture(scope="session")
def conn(request):
    connection = db.connect(database)
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


#def pytest_generate_tests(metafunc):
#    metafunc.parametrize(("conn"),((connection),))
