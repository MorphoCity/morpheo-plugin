Install as QGIS plugin
======================

QGIS 2.14+ is required

Copy or extract the morpheo python package  in the .qgis/python/plugins folder of your
home directory.

The plugin will add a 'Morpheo' entry under the Extension menu.


Install as python package
=========================

If installed as standard python package, the morpheo plugin can be used 
as a command line tool

Requirements
------------

While it doesn't need the QGIS interface in this mode, the  QGIS python api still need to be installed
to run the programm.

Morpheo has a dependency with the spatialite python package: the package provided by QGIS has  

QGIS must have the spatialite support enabled and the gdal tools installed (ogr2ogr)

Once installed you should define the QGIS_PYTHONPATH environment value to hold the path to the QGIS python files.

Installation
------------

The morpheo package can be installed like any python package

From the sources, the moprpheo package cam be installed with the command:

.. code-block:: bash
    
    python setup.py


Run as command line
-------------------

Help for any command options is displayed with the following shell command:

.. code-block:: bash

    morpheo <command> --help

Where ``<command>`` is:

    ways
        Compute ways. This commande has many options for controlling output and what's computed.

    way_attributes
        Compute attributes on ways. Compute local attributes and centrality attributes.

    edge_attributes
        Compute attributes on ways. Compute local attributes and centrality attributes.

    sdiff
        Compute structural difference between two sets of edges. Note that set of edges must have been computed
        previously by the ``ways`` command with the ``--rtopo`` option.

    path
        Compute shortest path (weigthed or not) on edges. Topological shortcuts may be defined from attributes on ways or edges.

    mesh 
        Compute a *mesh structure* i,e a set of edges from attributes on ways or edges.  

    horizon 
        Compute a topological horizon from a *mesh structure*

    way_path
        Compute simplest path from the way **line graph** perspective and transpose that path on edges.


