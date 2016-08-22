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
          'linux' :'/usr/lib/python2.7/dist-packages/qgis',
        }.get(platform))

    if qgis_pythonpath is not None:
        sys.path.append(qgis_pythonpath)

    qgis_home = os.environ.get('QGIS_HOME',{
            'darwin':'/Applications/QGIS.app/Contents/MacOS',
            'linux' :'/usr/',
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


def build_ways( args ):
    """ Build all : graph, places and ways 
    """
    shapefile = args.shapefile
    output    = args.output or 'morpheo_'+os.path.splitext(os.path.basename(shapefile))[0] 
    dbname    = args.dbname or output

    if args.P or args.W:
        builder = Builder.from_database( dbname )
    else:
        builder = Builder.from_shapefile( shapefile, dbname )
    
        # Compute graph
        builder.build_graph(args.snap_distance, args.min_edge_length, args.way_attribute,
                            output=output)

    if args.G: return

    if not args.W:
        # Compute places
        builder.build_places(buffer_size=args.buffer,
                             places=args.input_places,
                             output=output)

    if args.P: return

    # Compute ways
    kwargs = dict(classes=args.classes, rtopo=args.rtopo)
    if args.attributes:
        kwargs.update(attributes=True,
                      orthogonality = args.orthogonality,
                      betweenness   = args.betweenness,
                      closeness     = args.closeness,
                      stress        = args.stress)

    if args.way_attribute is not None:
        builder_build_ways_from_attribute(output=args.output, **kwargs)
    else:
        builder.build_ways(threshold=args.threshold/180.0 * pi,
                           output=output, **kwargs)


def compute_way_attributes( args ):
    """ Compute way attributes
    """
    builder = Builder.from_database( args.dbname )
    builder.compute_way_attributes(
            orthogonality = args.orthogonality,
            betweenness   = args.betweenness,
            closeness     = args.closeness,
            stress        = args.stress,
            rtopo         = args.rtopo,
            output        = args.output)


def compute_structural_diff( args ):
    """ Compute structural diff
    """
    from builder.structdiff import structural_diff

    output = args.output or "morpheo-diff-{}-{}".format(
                os.path.basename(args.initial),
                os.path.basename(args.final))

    structural_diff( args.initial, args.final,
                     output=output, 
                     buffersize=args.tolerance)



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

    # Ways builder command
    ways_cmd = sub.add_parser('ways', description="Build ways and compute attributes on ways")
    ways_cmd.add_argument("shapefile", help="Shapefile path")
    ways_cmd.add_argument("--dbname" , default=None, help="Database name")
    ways_cmd.add_argument("--output" , default=None, help="Output project")

    group = ways_cmd.add_mutually_exclusive_group()
    group.add_argument("-G", action='store_true', default=False, help="Compute only viary graph")
    group.add_argument("-P", action='store_true', default=False, help="Compute only places")
    group.add_argument("-W", action='store_true', default=False, help="Compute only ways")
    
    # Options controlling graph
    ways_cmd.add_argument("--snap-distance"  , metavar='VALUE', type=float, default=0.2, help="Snap distance")
    ways_cmd.add_argument("--min-edge-length", metavar='VALUE', type=float, default=4, help="Min edge length")
    # Options controlling places
    ways_cmd.add_argument("--buffer"         , metavar='VALUE', type=float, default=4 , help="Place Buffer size")
    ways_cmd.add_argument("--input-places"   , metavar='PATH' , default=None, help="Default input polygons for places")
    # Options controlling ways
    ways_cmd.add_argument("--way-attribute"  , metavar='NAME', default=None, help="Attribute for building street ways")
    ways_cmd.add_argument("--threshold"      , metavar='VALUE', type=float, default=30, help="Treshold angle (in degree)")
    ways_cmd.add_argument("--rtopo"          , action='store_true', default=False, help="Compute topological radius")
    ways_cmd.add_argument("--attributes"     , action='store_true', default=False, help="Compute attributes")
    ways_cmd.add_argument("--orthogonality"  , action='store_true', default=False, help="Compute orthogonality (require --attributes)")
    ways_cmd.add_argument("--betweenness"    , action='store_true', default=False, help="Compute betweenness centrality (require --attributes)")
    ways_cmd.add_argument("--closeness"      , action='store_true', default=False, help="Compute closeness centrality (require --attributes)")
    ways_cmd.add_argument("--stress"         , action='store_true', default=False, help="Compute stress centrality (require --attributes)")
    ways_cmd.add_argument("--classes"        , metavar='NUM', default=10, help="Number of classes")
    ways_cmd.set_defaults(func=build_ways)
 
    # Way attributes command
    ways_cmd = sub.add_parser('way_attributes', description="Compute attributes on ways")
    ways_cmd.add_argument("dbname", help="Database")
    ways_cmd.add_argument("--output"       , metavar='PATH' , default=None, help="Output ways shapefile")
    ways_cmd.add_argument("--orthogonality", action='store_true', default=False, help="Compute orthoganality")
    ways_cmd.add_argument("--betweenness"  , action='store_true', default=False, help="Compute betweenness centrality")
    ways_cmd.add_argument("--closeness"    , action='store_true', default=False, help="Compute closeness centrality")
    ways_cmd.add_argument("--stress"       , action='store_true', default=False, help="Compute stress centrality")
    ways_cmd.add_argument("--rtopo"        , action='store_true', default=False, help="Compute topological radius")
    ways_cmd.add_argument("--classes"      , metavar='NUM', default=10, help="Number of classes")
    ways_cmd.set_defaults(func=compute_way_attributes)

    # Compute structural diff
    sdiff_cmd = sub.add_parser('sdiff'  , description="Compute structural difference")
    sdiff_cmd.add_argument("initial"    , metavar='PATH' , help="Path to initial state data")
    sdiff_cmd.add_argument("final"      , metavar='PATH' , help="Path to final state data")
    sdiff_cmd.add_argument("--tolerance", metavar='VALUE', type=float, default=1, help="Tolerance value") 
    sdiff_cmd.add_argument("--output"   , metavar='PATH' , default=None, help="Path to ouptut data")
    sdiff_cmd.set_defaults(func=compute_structural_diff)

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

