# -*- encoding=utf-8 -*-
""" Utilities to manage shapefile layers
"""
import os
import logging

from .errors import FileNotFoundError, InvalidLayerError
from .sql import create_database, connect_database


def open_shapefile( path, name ):
    """ Open a shapefile as a qgis layer
    """
    from qgis.core import QgsVectorLayer

    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError("Shapefile not found: %s" % path)

    layer = QgsVectorLayer(path, name, 'ogr' )
    if not layer.isValid():
        raise InvalidLayerError("Failed to load layer %s" % path)

    return layer


def check_layer(layer, wkbtypes):
    """ Check layer validity
    """
    if wkbtypes and layer.wkbType() not in wkbtypes:
        raise InvalidLayerError("Invalid geometry type for layer {}".format(layer.wkbType()))

    if layer.crs().geographicFlag():
       raise InvalidLayerError("Invalid CRS (lat/long) for layer")


def import_as_layer( dbname, layer, name, forceSinglePartGeometryType=False ):
    """
    """
    if 'OGR2OGR' in os.environ:
        import_shapefile( dbname, layer, name )
    else:
        from qgis.core import QgsDataSourceURI, QgsVectorLayer, QgsVectorLayerImport
        if isinstance(layer, QgsVectorLayer):
            # Create database if it does not exists
            create_database(dbname)
            # Create Spatialite URI
            uri = QgsDataSourceURI()
            uri.setDatabase(dbname)
            uri.setDataSource('', name, 'GEOMETRY')
            options = {}
            options['overwrite'] = True
            options['forceSinglePartGeometryType'] = forceSinglePartGeometryType
            error, errMsg = QgsVectorLayerImport.importLayer(layer, uri.uri(False), 'spatialite', layer.crs(), False, False, options)
            if error != QgsVectorLayerImport.NoError:
                raise IOError(u"Failed to add layer to database '{}': error {}".format(dbname, errMsg))
        else:
            import_shapefile( dbname, layer, name )


def import_shapefile( dbname, path, name, forceSinglePartGeometryType=False ):
    """ Add shapefile as new table in database

        :param dbname: Path of the database
        :param path: Path of the shapefile
        :param name: Name of the table
    """
    if 'OGR2OGR' in os.environ:
        from subprocess import call

        # Append layer to  database
        ogr2ogr = os.environ['OGR2OGR']
        args = [ogr2ogr]
        if not os.path.exists(dbname):
            args.extend(['-f','SQLite','-dsco', 'SPATIALITE=yes'])
        else:
            args.append('-update')
        args.extend([dbname, path, '-nln', name])
        if forceSinglePartGeometryType:
            args.append('-explodecollections')
        rc = call(args)
        if rc != 0:
            raise IOError(u"Failed to add layer to database '{}'".format(dbname))
    else:
        # Import with QGIS API
        from qgis.core import QgsDataSourceURI, QgsVectorLayer, QgsVectorLayerImport
        # Create shapefile QgsVectorLayer
        if not os.path.exists(path):
            raise IOError("Failed to read shapefile '{}'".format(path))
        layer = QgsVectorLayer(path, name, 'ogr')
        if not layer.isValid():
            raise IOError("Shapefile '{}' is not valid".format(path))
        # create spatialite database if does not exist
        create_database(dbname)
        # Create Spatialite URI
        uri = QgsDataSourceURI()
        uri.setDatabase(dbname)
        uri.setDataSource('', name, 'GEOMETRY')
        options = {}
        options['overwrite'] = True
        options['forceSinglePartGeometryType'] = forceSinglePartGeometryType
        error, errMsg = QgsVectorLayerImport.importLayer(layer, uri.uri(False), 'spatialite', layer.crs(), False, False, options)
        if error != QgsVectorLayerImport.NoError:
            raise IOError(u"Failed to add layer to database '{}': error {}".format(dbname, errMsg))
        # Add spatial index
        conn = connect_database(dbname)
        cur  = conn.cursor()
        cur.execute("SELECT CreateSpatialIndex('{table}', 'GEOMETRY')".format(table=name))
        cur.close()
        conn.close()
        del cur
        del conn


def export_shapefile( dbname, table, output ):
    """ Save spatialite table as shapefile

        :param dbname: Database path
        :param table: The table name
        :param output: Output path of the destination folder to store shapefile
    """
    if 'OGR2OGR' in os.environ:
        from subprocess import call
        # Export with ogr2ogr
        ogr2ogr = os.environ['OGR2OGR']
        rc = call([ogr2ogr,'-f','ESRI Shapefile','-overwrite',output,dbname,table,'-nln',
                    "%s_%s" % (table,os.path.basename(output))])
        if rc != 0:
            raise IOError(u"Failed to save '{}:{}' as  '{}'".format(dbname, table, output))
    else:
        # Export with QGIS API
        from qgis.core import QgsDataSourceURI, QgsVectorLayer, QgsVectorFileWriter
        # Create Spatialite URI
        uri = QgsDataSourceURI()
        uri.setDatabase(dbname)
        uri.setDataSource('', table, 'GEOMETRY')
        # Create Spatialite QgsVectorLayer
        dblayer = QgsVectorLayer(uri.uri(), table, 'spatialite')
        # Shapefile path
        shapefile = os.path.join(output, "%s_%s.shp" % (table,os.path.basename(output)))
        # Write Shapefile
        writeError = QgsVectorFileWriter.writeAsVectorFormat(dblayer, shapefile, "UTF8", None, "ESRI Shapefile")
        if writeError != QgsVectorFileWriter.NoError:
            raise IOError(u"Failed to save '{}:{}' as  '{}'".format(dbname, table, output))



