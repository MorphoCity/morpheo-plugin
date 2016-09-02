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


Run command line
----------------



