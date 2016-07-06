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

#
# Morpheo commands
#

def build_graph( args ):
    """ Build a graph from a shapefile
    """
    builder = Builder.from_shapefile( args.shapefile, args.dbname )
    builder.build_graph(args.snap_distance, args.min_edge_length, args.attribute)


def build_ways( args ):
    """ Build ways
    """
    builder = Builder.from_database( args.dbname )
    if args.street:
        builder_build_ways_from_attribute(output=args.output)
    else:
        builder.build_ways( threshold=args.threshold,
                            buffer_size=args.buffer_size,
                            places=args.places,
                            loop_output=args.loop_output,
                            output=args.output)


    
def morpheo_():
    """ Run 'build_graph' from command line
    """
    import argparse
    from time import time
    from .logger import setup_log_handler

    version = "{} {}".format("Morpheo graph builder", Builder.version)
    parser = argparse.ArgumentParser(description=version)
    parser.add_argument("--logging"  , choices=('debug','info','warning','error'), default='info', help="set log level")

    sub = parser.add_subparsers(title='commands', help='type morpheo <command> help')

    # Builder command
    builder_cmd = sub.add_parser('build')
    builder_cmd.add_argument("shapefile", help="Shapefile path")
    builder_cmd.add_argument("--snap-distance"  , metavar='VALUE', type=float, default=0.2, help="Snap distance")
    builder_cmd.add_argument("--min-edge-length", metavar='VALUE', type=float, default=4, help="Min edge length")
    builder_cmd.add_argument("--attribute",       metavar='NAME', default=None, help="Attribute for building street ways")
    builder_cmd.add_argument("--dbname"   , default=None, help="Database name")
    builder_cmd.set_defaults(func=build_graph)

    # Way builder command
    ways_cmd = sub.add_parser('ways')
    ways_cmd.add_argument("dbname", help="Database")
    ways_cmd.add_argument("--street", action='store_true', default=False, help="Compute way using street name")
    ways_cmd.add_argument("--output"      , metavar='PATH' , default=None, help="Output ways shapefile")
    ways_cmd.add_argument("--treshold"    , metavar='VALUE', type=float, default=10, help="Treshold angle")
    ways_cmd.add_argument("--buffer"      , metavar='VALUE', type=float, default=5 , help="Buffer size")
    ways_cmd.add_argument("--places"      , metavar='PATH' , default=None, help="Default input polygons for places")
    ways_cmd.add_argument("--loop-output" , metavar='PATH' , default=None, help="Output polygons shapefile")
    ways_cmd.set_defaults(func=build_ways)

    args = parser.parse_args()
    
    setup_log_handler(args.logging, formatstr='%(asctime)s\t%(levelname)s\t%(message)s')
    setup_qgis()
  
    start = time()
    try:
        args.func(args)
    except Exception as e:
        logging.critical("{}".format(e))
        raise
    finally:
        print( "====== Elapsed time: {:.3f} s ======".format(time()-start), file=sys.stderr )

