# -*- encoding=utf-8 -*-

import os
import sys
import logging

from builders.spatialite import SpatialiteBuilder

Builder = SpatialiteBuilder

qgis_app = None

def setup_qgis():
    """ Setup qgis
    """
    # Get the qgis python path
    platform = os.uname()[0].lower()
    qgis_pythonpath = os.environ.get('QGIS_PYTHONPATH',{
          'darwin':'/Applications/QGIS.app/Contents/Resources/python',
          'linux' :'/usr/local/share/qgis/python',
        }.get(platform))

    if qgis_pythonpath is not None:
        logging.info("Qgis python path set to %s" % qgis_pythonpath)
        sys.path.append(qgis_pythonpath)

    global qgis_app
    # XXX Fail to  initialize Qgis in OSX 
    # because I don't know how to set the prefixpath
    # So use server to initialize qgis properly

    #from qgis.core import QgsApplication
    #qgis_app = QgsApplication([], False )
    #qgis_app.initQgis()

    # This will initialize Qgis correctly
    from qgis.server import QgsServer
    qgis_app = QgsServer()
    qgis_app.init()



def build_graph( path, snap_distance=0, min_edge_length=1, dbname=None, name_field=None ):
    """ Build a graph from a shapefile

        :param path: path of the shapefile
        :param snap_distance: the minimun snap distance
        :param min_edge_length: the minimun edfyge length
        :param dbname: the database name (optional)
        :param name_field: TODO ????
    """
    builder = Builder.from_shapefile( path, dbname )
    builder.build_graph(snap_distance, min_edge_length, name_field)
        

def build_graph_():
    """ Run 'build_graph' from command line
    """
    import argparse

    from .logger import setup_log_handler

    version = "{} {}".format(Builder.description, Builder.version)
    parser = argparse.ArgumentParser(description=version)
    parser.add_argument("shapefile", help="Shapefile path")
    parser.add_argument("--snap-distance"  , nargs='?', type=float, default=0, help="Snap distance")
    parser.add_argument("--min-edge-length", nargs='?', type=float, default=1, help="Min edge length")
    parser.add_argument("--name-field", nargs='?', default=None, help="?????")
    parser.add_argument("--dbname", nargs='?', default=None, help="Database name")
    parser.add_argument("--logging", choices=['debug','info','warning','error'], default='info', help="set log level")

    args = parser.parse_args()
    
    setup_log_handler(args.logging)
    setup_qgis()
    
    build_graph(args.shapefile,
                snap_distance   = args.snap_distance,
                min_edge_length = args.min_edge_length,
                dbname = args.dbname,
                name_field = args.name_field)

