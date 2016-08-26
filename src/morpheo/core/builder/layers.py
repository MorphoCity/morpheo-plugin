# -*- encoding=utf-8 -*-
""" Utilities to manage shapefile layers
"""
import os

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


def import_shapefile( dbname, path, name, wkbtypes):
    """ Add shapefile as new table in database

        :param conn: Connection to database
        :param dbname: Path of the database
        :param path: Path of the shapefile
        :param name: Name of the table
        :param wkbtypes: Required types for geometries
    """
    from subprocess import call

    if wkbtypes is not None:
        layer = open_shapefile(path, name)
        check_layer(layer, wkbtypes)

    # Append layer to  database
    ogr2ogr = os.environ['OGR2OGR']
    args = [ogr2ogr]
    if not os.path.exists(dbname):
        args.extend(['-f','SQLite','-dsco','SPATIALITE=yes'])
    else:
        args.append('-update')
    args.extend([dbname, path, '-nln', name])
    rc = call(args)
    if rc != 0:
        raise IOError("Failed to add layer to database '{}'".format(dbname))


def export_shapefile( dbname, table, output ):
    """ Save spatialite table as shapefile

        :param dbname: Database path
        :param table: The table name
        :param output: Output path of the destination folder to store shapefile
    """
    from subprocess import call
    if 'OGR2OGR' in os.environ:
        # Export with ogr2ogr
        ogr2ogr = os.environ['OGR2OGR']
        rc = call([ogr2ogr,'-f','ESRI Shapefile','-overwrite',output,dbname,table,'-nln',
                    "%s_%s" % (table,os.path.basename(output))])
        if rc != 0:
            raise IOError("Failed to save '{}:{}' as  '{}'".format(dbname, table, output))
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
            raise IOError("Failed to save '{}:{}' as  '{}'".format(dbname, table, output))


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

