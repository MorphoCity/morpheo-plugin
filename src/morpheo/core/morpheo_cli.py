# -*- encoding=utf-8 -*-

from __future__ import print_function

import os
import sys
import logging

from math import pi
from builder.errors import BuilderError
from builder.graph_builder import SpatialiteBuilder

Builder = SpatialiteBuilder

qgis_app = None

def setup_qgis():
    """ Setup qgis

        This function is only used when morpheo is
        used as standalone command
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


def check_requirements( stand_alone = True ):
    """ Check that everything is ok to run morpheo
    """
    # Lookup for ogr2ogr
    from distutils.spawn import  find_executable

    ogr2ogr = find_executable('ogr2ogr')
    if ogr2ogr is None:
        raise BuilderError("Gdal/OGR executables not found: morpheo requires ogr2ogr")
    else:
        os.environ.update(OGR2OGR=ogr2ogr)

    # Checkout for networkx
    try:
        import networkx
    except ImportError:
        raise BuilderError("Python Module networkx is required, please update your python environment")
   

#
# Morpheo commands
#

def build_graph( args ):
    """ Build a graph from a shapefile
    """
    builder = Builder.from_shapefile( args.shapefile, args.dbname )
    builder.build_graph(args.snap_distance, args.min_edge_length, args.attribute,
                        output=args.output)


def build_ways( args ):
    """ Build ways
    """
    builder = Builder.from_database( args.dbname )
    if args.attributes:
        kwargs = dict(attributes=True,
                      orthogonality = args.orthogonality,
                      betweenness   = args.betweenness,
                      closeness     = args.closeness,
                      stress        = args.stress)
    else:
        kwargs = {}

    if args.rtopo:
        kwargs.update(rtopo=True)

    if args.street:
        builder_build_ways_from_attribute(output=args.output, **kwargs)
    else:
        builder.build_ways(threshold=args.threshold /180.0 * pi,
                           output=args.output, **kwargs)


def compute_way_attributes( args ):
    """ Compute way attributes
    """
    builder = Builder.from_database( args.dbname )
    builder.compute_way_attributes(
            orthogonality = args.orthogonality,
            betweenness   = args.betweenness,
            closeness     = args.closeness,
            stress        = args.stress,
            rtopo         = args.rtopo)


def build_places( args ):
    """ Build places
    """
    builder = Builder.from_database( args.dbname )
    builder.build_places(buffer_size=args.buffer,
                         places=args.places,
                         output=args.output)

    
def main():
    """ Run 'build_graph' from command line
    """
    import argparse
    from time import time
    from .logger import setup_log_handler

    version = "{} {}".format("Morpheo graph builder", Builder.version)
    parser = argparse.ArgumentParser(description=version)
    parser.add_argument("--logging"  , choices=('debug','info','warning','error'), default='info', help="set log level")

    sub = parser.add_subparsers(title='commands', help='type morpheo <command> --help')

    # Graph Builder command
    builder_cmd = sub.add_parser('graph')
    builder_cmd.add_argument("shapefile", help="Shapefile path")
    builder_cmd.add_argument("--snap-distance"  , metavar='VALUE', type=float, default=0.2, help="Snap distance")
    builder_cmd.add_argument("--min-edge-length", metavar='VALUE', type=float, default=4, help="Min edge length")
    builder_cmd.add_argument("--attribute",       metavar='NAME', default=None, help="Attribute for building street ways")
    builder_cmd.add_argument("--dbname", default=None, help="Database name")
    builder_cmd.add_argument("--output", default=None, help="Output sanitized data")
    builder_cmd.set_defaults(func=build_graph)

    # Places builder command
    places_cmd = sub.add_parser('places')
    places_cmd.add_argument("dbname", help="Database")
    places_cmd.add_argument("--buffer" , metavar='VALUE', type=float, default=4 , help="Buffer size")
    places_cmd.add_argument("--places" , metavar='PATH' , default=None, help="Default input polygons for places")
    places_cmd.add_argument("--output" , metavar='PATH' , default=None, help="Output polygons shapefile")
    places_cmd.set_defaults(func=build_places)

    # Way builder command
    ways_cmd = sub.add_parser('ways')
    ways_cmd.add_argument("dbname", help="Database")
    ways_cmd.add_argument("--street", action='store_true', default=False, help="Compute way using street name")
    ways_cmd.add_argument("--output"    , metavar='PATH' , default=None, help="Output ways shapefile")
    ways_cmd.add_argument("--threshold" , metavar='VALUE', type=float, default=30, help="Treshold angle (in degree)")
    ways_cmd.add_argument("--rtopo"        , action='store_true', default=False, help="Compute topological radius")
    ways_cmd.add_argument("--attributes"   , action='store_true', default=False, help="Compute attributes")
    ways_cmd.add_argument("--orthogonality", action='store_true', default=False, help="Compute orthogonality (require --attributes)")
    ways_cmd.add_argument("--betweenness"  , action='store_true', default=False, help="Compute betweenness centrality (require --attributes)")
    ways_cmd.add_argument("--closeness"    , action='store_true', default=False, help="Compute closeness centrality (require --attributes)")
    ways_cmd.add_argument("--stress"       , action='store_true', default=False, help="Compute stress centrality (require --attributes)")
    ways_cmd.set_defaults(func=build_ways)

    # Way attributes command
    ways_cmd = sub.add_parser('way_attributes')
    ways_cmd.add_argument("dbname", help="Database")
    ways_cmd.add_argument("--orthogonality", action='store_true', default=False, help="Compute orthoganality")
    ways_cmd.add_argument("--betweenness"  , action='store_true', default=False, help="Compute betweenness centrality")
    ways_cmd.add_argument("--closeness"    , action='store_true', default=False, help="Compute closeness centrality")
    ways_cmd.add_argument("--stress"       , action='store_true', default=False, help="Compute stress centrality")
    ways_cmd.add_argument("--rtopo"        , action='store_true', default=False, help="Compute topological radius")
    ways_cmd.set_defaults(func=compute_way_attributes)

    args = parser.parse_args()
    
    setup_log_handler(args.logging, formatstr='%(asctime)s\t%(levelname)s\t%(message)s')
    setup_qgis()
  
    check_requirements(stand_alone=True)

    start = time()
    try:
        args.func(args)
    except Exception as e:
        logging.critical("{}".format(e))
        raise
    finally:
        print( "====== Elapsed time: {:.3f} s ======".format(time()-start), file=sys.stderr )

