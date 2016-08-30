# -*- encoding=utf=8 -*-
""" Tools for computing horizon

    An horizon is the computation of topolgical distance against
    a number of selected features the  'mesh-structure')
""" 

from __future__ import print_function

import logging

from .mesh import features_from_attributes, features_from_geometry
from .algorithms import multiple_sources_shortest_path_length
from .sql import connect_database, SQL
 
import numpy as np


def horizon_from_attribute( conn, G,  attribute, percentile, output=None ):
    """ Compute horizon from a percentile of a numerical attributs
    """
    features = features_from_attributes(conn.cursor(), 'ways', attribute, percentile,
                                        fid_column="WAY_ID")

    # Compute all shortest path lengths
    lengths = multiple_sources_shortest_path_length(G, features)

    data = lengths.values()
    if output is not None:
        np.savetxt(output, (lengths.keys(), data), fmt='%d', 
                header="ways,attribute=%s,percentile=%s" % (attribute, percentile))

    return data

 
def horizon_from_geometry( conn, G,  wkbgeom, within=False, output=None ):
    """ Compute horizon from features selected from a geometry
    """
    features = features_from_geometry(conn.cursor(), 'ways', wkbgeom, within=within)
    return horizon_from_feature_list(G, features, output) 


def horizon_from_feature_list( G,  features, output=None ):
    """ Compute horizon from features selected from a geometry
    """
    # Compute all shortest path lengths
    lengths = multiple_sources_shortest_path_length(G, features)

    data = lengths.values()
    if output is not None:
        np.savetxt(output, (lengths.keys(), data), fmt='%d', header="ways, user mesh")

    return data


def plot_histogram( data, path,  bins=10, color='blue', size=None ):
    """ Generate an histogram plot and save it as png image 

        :param path: path to save image to
        :param numbins: number of bins in the histogram
        :param color: color of histogram
        :param size:  tuple, size (width, height) of the image in pixels
        :param dpi:
    """
    import matplotlib.pyplot as plt

    if size is not None:
        dpi=96.0
        figsize=(size[0]/dpi, size[1]/dpi)
    else:
       figsize=None
       dpi=None

    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax  = fig.add_subplot(111)
    ax.hist(data, bins, color=color)
    fig.savefig(path)
    plt.close()






