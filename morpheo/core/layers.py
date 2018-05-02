""" Utilities to manage shapefile layers
"""
import os
import logging

from .errors import FileNotFoundError, InvalidLayerError
from .sql import create_database, connect_database


def check_layer(layer, wkbtypes):
    """ Check layer validity
    """
    if wkbtypes and layer.wkbType() not in wkbtypes:
        raise InvalidLayerError("Invalid geometry type for layer {}".format(layer.wkbType()))

    if layer.crs().isGeographic():
       raise InvalidLayerError("Invalid CRS (lat/long) for layer")


def import_vector_layer( dbname, layer, name, forceSinglePartGeometryType=False, feedback=None, context=None):
    from processing.tools.general import run
    logging.info("Importing layer %s as %s", layer.name(), name)
    run('morpheo:importlayer',{
            'INPUT': layer,
            'DBNAME': dbname,
            'NAME' : name,
            'SINGLEPARTGEOMETRY': forceSinglePartGeometryType
        }, feedback=feedback, context=context)


def import_as_layer( dbname, layer, name, forceSinglePartGeometryType=False, feedback=None, context=None ):
    """
    """
    if 'OGR2OGR' in os.environ:
        import_shapefile( dbname, layer, name )
    else:
        from qgis.core import QgsVectorLayer
        if isinstance(layer, QgsVectorLayer):
            import_vector_layer(dbname, layer, name, forceSinglePartGeometryType, feedback=feedback,
                    context=context)
        else:
            import_shapefile( dbname, layer, name )


def import_shapefile( dbname, path, name, forceSinglePartGeometryType=False, feedback=None, context=None ):
    """ Add shapefile as new table in database

        :param dbname: Path of the database
        :param path: Path of the shapefile
        :param name: Name of the table
    """
    if not 'OGR2OGR' in os.environ:
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
            raise IOError("Failed to add layer to database '{}'".format(dbname))
    else:
        # Import with QGIS API
        from qgis.core import QgsVectorLayer
        # Create shapefile QgsVectorLayer
        if not os.path.exists(path):
            raise IOError("Failed to read shapefile '{}'".format(path))
        layer = QgsVectorLayer(path, name, 'ogr')
        if not layer.isValid():
            raise IOError("Shapefile '{}' is not valid".format(path))
        import_vector_layer(dbname, layer, name, forceSinglePartGeometryType, feedback=feedback,
                context=context)
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
            raise IOError("Failed to save '{}:{}' as  '{}'".format(dbname, table, output))
    else:
        # Export with QGIS API
        from qgis.core import QgsDataSourceUri, QgsVectorLayer, QgsVectorFileWriter
        # Create Spatialite URI
        uri = QgsDataSourceUri()
        uri.setDatabase(dbname)
        uri.setDataSource('', table, 'GEOMETRY')
        # Create Spatialite QgsVectorLayer
        dblayer = QgsVectorLayer(uri.uri(), table, 'spatialite')
        # Shapefile path
        shapefile = os.path.join(output, "%s_%s.shp" % (table,os.path.basename(output)))
        # Write Shapefile
        writeError, msg = QgsVectorFileWriter.writeAsVectorFormat(dblayer, shapefile, "utf-8", driverName="ESRI Shapefile")
        if writeError != QgsVectorFileWriter.NoError:
            raise IOError("Failed to save '{} table {}' as '{}': {}".format(dbname, table, output, msg))



