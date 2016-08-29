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
                             output=output,
                             export_graph=args.graph)

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
                           output=output,
                           export_graph=args.graph, **kwargs)


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


def build_edges_graph( args ):
    """ Build and export edges graph  
    """
    output = args.output or args.dbname
    builder = Builder.from_database( args.dbname )
    builder.build_edges_graph(output)
 

def build_ways_graph( args ):
    """ Build and save way line graph
    """
    output  = args.output or args.dbname
    builder = Builder.from_database( args.dbname )
    builder.build_ways_graph(output)


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


def compute_path( args ):
    """ Compute shortest paths
    """
    import builder.itinerary as iti

    path   = args.path           # input path
    output = args.output or path # output path
    dbname = args.dbname or path+'.sqlite'

    if args.path_type=='shortest':
        _path_fun = iti.shortest_path
    elif args.path_type=='simplest':
        _path_fun = iti.simplest_path
    elif args.path_type=='azimuth':
        _path_fun = iti.azimuth_path
    elif args.path_type=='naive-azimuth':
        _path_fun = iti.naive_azimuth_path
    elif args.path=='way-simplest':
        _path_fun = iti.way_simplest

    _path_fun(dbname, path, args.source, args.destination, output=output)


def main():
    """ Run 'build_graph' from command line
    """
    import argparse
    from time import time
    from .logger import setup_log_handler

    def range_type(strval, min=0, max=100):
        val = int(strval)
        if not min <= value <= max:
            raise argparse.ArgumentTypeError('value must be in range %s-%s' % (min,max))
        return val

    version = "{} {}".format("Morpheo graph builder", Builder.version)
    parser = argparse.ArgumentParser(description=version)
    parser.add_argument("--logging"  , choices=('debug','info','warning','error'), default='info', help="set log level")

    sub = parser.add_subparsers(title='commands', help='type morpheo <command> --help')

    # Ways builder command
    ways_cmd = sub.add_parser('ways', description="Build ways and compute attributes on ways")
    ways_cmd.add_argument("shapefile", help="Shapefile path")

    group = ways_cmd.add_mutually_exclusive_group()
    group.add_argument("-G", action='store_true', default=False, help="Compute only viary graph")
    group.add_argument("-P", action='store_true', default=False, help="Compute only places")
    group.add_argument("-W", action='store_true', default=False, help="Compute only ways")
 
    ways_cmd.add_argument("--dbname" , default=None, help="Database name")
    ways_cmd.add_argument("--output" , default=None, help="Output project")

    # Options controlling graph
    ways_cmd.add_argument("--snap-distance"  , metavar='VALUE', type=float, default=0.2, help="Snap distance")
    ways_cmd.add_argument("--min-edge-length", metavar='VALUE', type=float, default=4, help="Min edge length")
    # Options controlling places
    ways_cmd.add_argument("--buffer"         , metavar='VALUE', type=float, default=4 , help="Place Buffer size")
    ways_cmd.add_argument("--input-places"   , metavar='PATH' , default=None, help="Default input polygons for places")
    ways_cmd.add_argument("--graph"          , action='store_true', default=False, help="Export graphes")
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

    # edge graph command
    ways_cmd = sub.add_parser('edges_graph', description="Build edges graph")
    ways_cmd.add_argument("dbname", help="Database")
    ways_cmd.add_argument("--output", metavar='PATH', default=None, help="Output path")
    ways_cmd.set_defaults(func=build_edges_graph)
 
    # way graph command
    ways_cmd = sub.add_parser('ways_graph', description="Build way line graph")
    ways_cmd.add_argument("dbname", help="Database")
    ways_cmd.add_argument("--output", metavar='PATH', default=None, help="Output path")
    ways_cmd.set_defaults(func=build_ways_graph)
 
    # Compute structural diff
    sdiff_cmd = sub.add_parser('sdiff'  , description="Compute structural difference")
    sdiff_cmd.add_argument("initial"    , metavar='PATH' , help="Path to initial state data")
    sdiff_cmd.add_argument("final"      , metavar='PATH' , help="Path to final state data")
    sdiff_cmd.add_argument("--tolerance", metavar='VALUE', type=float, default=1, help="Tolerance value") 
    sdiff_cmd.add_argument("--output"   , metavar='PATH' , default=None, help="Path to ouptut data")
    sdiff_cmd.set_defaults(func=compute_structural_diff)

    # Compute paths
    path_cmd = sub.add_parser('path', description="Compute paths")
    path_cmd.add_argument("path", metavar='PATH', help="Path to morpheo graph data")
    path_cmd.add_argument("--dbname", metavar='PATH', help="Database")
    path_cmd.add_argument("--output", metavar='PATH' , default=None, help="Output destination")
    path_cmd.add_argument("-from","--from", metavar='NUMBER' , type=int, dest='source'     , 
            required=True, help="FID of starting place")
    path_cmd.add_argument("-to"  ,"--to"  , metavar='NUMBER' , type=int, dest='destination', 
            required=True, help="FID of destination place")
    path_cmd.add_argument("-T, --type", choices=[
        'shortest',
        'simplest',
        'azimuth' ,
        'way-simplest',
        'naive-azimuth',
    ], default='shortest', dest="path_type", help="Type of path (default to shortest)")
    path_cmd.add_argument("--mesh-attribute" , metavar='NAME'  , default=None, 
            help="Specify attribute name for mesh structure")
    path_cmd.add_argument("--mesh-percentile", metavar='NUMBER', default=0, type=int, 
            help="The percentile for computing the mesh structure")
    path_cmd.set_defaults(func=compute_path)

    #--------------------------
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

