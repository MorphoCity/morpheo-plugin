# -*- encoding=utf-8 -*-

from __future__ import print_function

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
        sys.path.append(qgis_pythonpath)

    qgis_home = os.environ.get('QGIS_HOME',{
            'darwin':'/Applications/QGIS.app/Contents/MacOS',
            'linux' :'/usr/local/',
        }.get(platform))


    logging.info("QGIS_PYTHONPATH set to '%s'" % qgis_pythonpath)
    logging.info("QGIS_HOME set to '%s'" % qgis_home)

    global qgis_app
    from qgis.core import QgsApplication, QgsMessageLog, QgsProviderRegistry
    qgis_app = QgsApplication([], False )
    QgsApplication.setPrefixPath(qgis_home, True)
    QgsApplication.initQgis()

    # Add a hook to qgis  message log 
    def writelogmessage(message, tag, level):
        logging.info('Qgis: {}({}): {}'.format( tag, level, message ))

    QgsMessageLog.instance().messageReceived.connect( writelogmessage )


def build_graph( path, snap_distance=0, min_edge_length=1, dbname=None, attribute=None ):
    """ Build a graph from a shapefile

        :param path: Path of the shapefile
        :param snap_distance: The minimun snap distance
        :param min_edge_length: The minimun edge length
        :param dbname: The database name (optional)
        :param attribute: 
    """
    builder = Builder.from_shapefile( path, dbname )
    builder.build_graph(snap_distance, min_edge_length, attribute)
        

def build_graph_():
    """ Run 'build_graph' from command line
    """
    import argparse
    from time import time
    from .logger import setup_log_handler

    version = "{} {}".format(Builder.description, Builder.version)
    parser = argparse.ArgumentParser(description=version)
    parser.add_argument("shapefile", help="Shapefile path")
    parser.add_argument("--snap-distance"  , nargs='?', type=float, default=0.2, help="Snap distance")
    parser.add_argument("--min-edge-length", nargs='?', type=float, default=4, help="Min edge length")
    parser.add_argument("--attribute", nargs='?', default=None, help="Attribute for building ways")
    parser.add_argument("--dbname", nargs='?', default=None, help="Database name")
    parser.add_argument("--logging", choices=['debug','info','warning','error'], default='info', help="set log level")

    args = parser.parse_args()
    
    setup_log_handler(args.logging, formatstr='%(asctime)s\t%(levelname)s\t%(message)s')
    setup_qgis()
   
    start = time()
    try:
        build_graph(args.shapefile,
                    snap_distance   = args.snap_distance,
                    min_edge_length = args.min_edge_length,
                    dbname = args.dbname,
                    attribute = args.attribute)
    except Exception as e:
        logging.critical("{}".format(e))
        raise
    finally:
        print( "====== Elapsed time: {:.3f} s ======".format(time()-start), file=sys.stderr )

