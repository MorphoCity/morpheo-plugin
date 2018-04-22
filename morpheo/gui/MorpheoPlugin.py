
from qgis.PyQt.QtCore import (QCoreApplication, QSettings, Qt, QByteArray, QVariant)
from qgis.PyQt.QtWidgets import (QAction, QDialogButtonBox, QFileDialog, QMessageBox)
from qgis.PyQt.QtGui import (QIcon,)
from qgis.core import (
            Qgis,
            QgsWkbTypes,
            QgsMapLayer,
            QgsApplication,
            QgsProject,
            QgsProcessing,
            QgsProcessingContext,
            QgsProcessingFeedback,
            QgsProcessingParameterField,)

from qgis.gui import QgsMessageBar, QgsMapToolEmitPoint

from .MorpheoDialog import MorpheoDialog
from ..processing.MorpheoAlgorithmProvider import MorpheoAlgorithmProvider

from processing.tools.general import run, runAndLoadResults

from ..core.edge_properties import computed_properties
from ..core.sql import connect_database

import os.path
from functools import partial
from math import pi
from datetime import datetime


class ProcessingFeedBack(QgsProcessingFeedback):

    def __init__(self, iface ):
        super().__init__()
        self._iface = iface
        self.progressChanged.connect(self._iface.setPercentage)

    def pushInfo(self, msg):
        self._iface.setText(msg)

    def reportError(self, msg, fatalError=False):
        self._iface.setError(msg)

    def setProgressText(self,text):
        self._iface.dlg.lblProgress.setText(text)




class MorpheoPlugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'morpheo_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # settings
        self.settings = QSettings()

        # Create the dialog (after translation) and keep reference
        self.dlg = MorpheoDialog()

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Morpheo')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'Morpheo')
        self.toolbar.setObjectName(u'Morpheo')


    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        return QCoreApplication.translate('morpheo', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = os.path.join(os.path.dirname(__file__),"..","morpheo.png")
        self.add_action(
            icon_path,
            text=self.tr(u'Morpheo'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # Rename OK button to Run
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).setText(self.tr('Run'))

        # connect group toggle
        self.dlg.grpWaysBuilderStreetName.setChecked(False)
        self.connectMutuallyExclusiveGroup(self.dlg.grpWaysBuilderGeomProps, self.dlg.grpWaysBuilderStreetName)
        self.dlg.grpHorizonGeo.setChecked(False)
        self.connectMutuallyExclusiveGroup(self.dlg.grpHorizonAttribute, self.dlg.grpHorizonGeo)

        # Initialize field path selection
        self.connectFileSelectionPanel(self.dlg.letWaysBuilderDirectoryPath, self.dlg.pbnWaysBuilderDirectoryPath, True)
        self.connectFileSelectionPanel(self.dlg.letWayAttributesDBPath, self.dlg.pbnWayAttributesDBPath, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letPathDBPath, self.dlg.pbnPathDBPath, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letHorizonDBPath, self.dlg.pbnHorizonDBPath, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDBPath1, self.dlg.pbnStructuralDiffDBPath1, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDBPath2, self.dlg.pbnStructuralDiffDBPath2, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDirectoryPath, self.dlg.pbnStructuralDiffDirectoryPath, True)

        # Initialize attribute list
        self.connectComboboxLayerAttribute(self.dlg.cbxWaysBuilderWayAttribute, self.dlg.cbxWaysBuilderInputLayer)
        # connect layer name
        self.dlg.cbxWaysBuilderInputLayer.currentIndexChanged.connect(self.cbxWaysBuilderInputLayerCurrentIndexChanged)

        # Connect db path and properties list
        self.connectDBPathWithAttribute(self.dlg.letHorizonDBPath, self.dlg.cbxHorizonWayAttribute)
        self.connectDBPathWithAttribute(self.dlg.letPathDBPath, self.dlg.cbxPathWayAttribute, self.dlg.cbxPathComputeOn)

        # Connect compute attributes on
        self.dlg.cbxWayAttributesComputeOn.currentIndexChanged.connect(self.cbxWayAttributesComputeOnCurrentIndexChanged)
        # Connect select all attributes
        self.dlg.pbnWayAttributeSelectAll.clicked.connect(self.pbnWayAttributeSelectAllClicked)

        # Deactivate path with attribute
        self.dlg.grpPathAttribute.setChecked(False)
        self.updatePathType()
        self.dlg.grpPathAttribute.toggled.connect(self.updatePathType)
        self.dlg.cbxPathComputeOn.currentIndexChanged.connect(self.updatePathType)

        # Set default value
        if self.settings.contains('/Morpheo/LastInputPath'):
            self.dlg.letWaysBuilderDirectoryPath.setText(self.settings.value('/Morpheo/LastInputPath'))
            self.dlg.letStructuralDiffDirectoryPath.setText(self.settings.value('/Morpheo/LastInputPath'))
        if self.settings.contains('/Morpheo/LastOutputPath'):
            self.synchronizeAllDBPathOnChanged(self.settings.value('/Morpheo/LastOutputPath'))

        # Synchronize DBPath
        self.dlg.letWayAttributesDBPath.textChanged.connect(self.synchronizeAllDBPathOnChanged)
        self.dlg.letPathDBPath.textChanged.connect(self.synchronizeAllDBPathOnChanged)
        self.dlg.letHorizonDBPath.textChanged.connect(self.synchronizeAllDBPathOnChanged)

        # Connect compute
        self.computeRow = 0
        self.dlg.mAlgosListWidget.setCurrentRow(self.computeRow)
        self.dlg.buttonBox.accepted.connect(self.accept)
        self.dlg.closed.connect(self.close)

        # Add to processing
        self.morpheoAlgoProvider = MorpheoAlgorithmProvider()
        QgsApplication.processingRegistry().addProvider(self.morpheoAlgoProvider)

    def cbxWaysBuilderInputLayerCurrentIndexChanged(self, idx):
        layerIdx = self.dlg.cbxWaysBuilderInputLayer.currentIndex()
        layerId = self.dlg.cbxWaysBuilderInputLayer.itemData( layerIdx )
        layer = QgsProject.instance().mapLayer(layerId)
        if layer:
            self.dlg.letWaysBuilderDBName.setText('morpheo_'+layer.name().replace(" ", "_"))
        else:
            self.dlg.letWaysBuilderDBName.setText('')

    def cbxWayAttributesComputeOnCurrentIndexChanged(self, idx):
        if self.dlg.cbxWayAttributesComputeOn.currentText() == self.tr('Edges'):
            self.dlg.cbxWayAttributesRtopo.setChecked(False)
            self.dlg.cbxWayAttributesRtopo.setEnabled(False)
        else:
            self.dlg.cbxWayAttributesRtopo.setEnabled(True)

    def pbnWayAttributeSelectAllClicked(self):
        self.dlg.cbxWayAttributesOrthogonality.setChecked(True)
        if self.dlg.cbxWayAttributesComputeOn.currentText() != self.tr('Edges'):
            self.dlg.cbxWayAttributesRtopo.setChecked(True)
        self.dlg.cbxWayAttributesBetweenness.setChecked(True)
        self.dlg.cbxWayAttributesCloseness.setChecked(True)
        self.dlg.cbxWayAttributesStress.setChecked(True)

    def connectMutuallyExclusiveGroup(self, grp1, grp2):
        def grp1Toggled(toggle):
            grp2.setChecked(not toggle)

        def grp2Toggled(toggle):
            grp1.setChecked(not toggle)

        grp1.toggled.connect(grp1Toggled)
        grp2.toggled.connect(grp2Toggled)

    def connectFileSelectionPanel(self, leText, btnSelect, isFolder, ext=None):

        def showSelectionDialog():
            #QMessageBox.warning(self.dlg, 'showSelectionDialog', 'showSelectionDialog')
            # Find the file dialog's working directory
            text = leText.text()
            if os.path.isdir(text):
                path = text
            elif os.path.isdir(os.path.dirname(text)):
                path = os.path.dirname(text)
            elif self.settings.contains('/Morpheo/LastInputPath'):
                path = self.settings.value('/Morpheo/LastInputPath')
            else:
                path = ''

            if isFolder:
                folder = QFileDialog.getExistingDirectory(self.dlg,
                                                          self.tr('Select folder'), path)
                if folder:
                    leText.setText(folder)
                    self.settings.setValue('/Morpheo/LastInputPath',
                                      folder)
            else:
                filenames = QFileDialog.getOpenFileNames(self.dlg,
                                                         self.tr('Select file'), path, '*.' + ext)
                if filenames:
                    leText.setText(';'.join(filenames))
                    self.settings.setValue('/Morpheo/LastInputPath',
                                      os.path.dirname(filenames[0]))

        btnSelect.clicked.connect(showSelectionDialog)

    def synchronizeAllDBPathOnChanged(self, txt):
        if self.dlg.letWayAttributesDBPath.text() != txt:
            self.dlg.letWayAttributesDBPath.setText(txt)
        if self.dlg.letPathDBPath.text() != txt:
            self.dlg.letPathDBPath.setText(txt)
        if self.dlg.letHorizonDBPath.text() != txt:
            self.dlg.letHorizonDBPath.setText(txt)

        self.settings.setValue('/Morpheo/LastOutputPath', txt)

    def connectDBPathWithAttribute(self, dbpathLet ,attributeCbx, waysCbx=None):

        def updateAttributeCombobox(txt):
            """update"""
            pass
            attributeCbx.clear()
            dbpath = dbpathLet.text()
            conn = connect_database(dbpath)
            use_way = True
            if waysCbx:
                use_way = waysCbx.currentText() == self.tr('Ways')
            for fieldName in computed_properties(conn, use_way):
                attributeCbx.addItem(fieldName)
            
        dbpathLet.textChanged.connect(updateAttributeCombobox)
        if waysCbx:
            waysCbx.currentIndexChanged.connect(updateAttributeCombobox)

    def connectComboboxLayerAttribute(self, attributeCbx, layerCbx):

        def updateAttributeCombobox(idx):
            """update"""
            attributeCbx.clear()
            layerId = layerCbx.itemData( idx )
            if layerId:
                layer = QgsProject.instance().mapLayer(layerId)
                if not layer or not layer.isValid():
                    self.setWarning("Cannot get fields: Invalid layer %s" % layerId)
                    return
                fields = sorted(field.name() for field in layer.fields() if field.type()==QVariant.String)
                for fieldName in fields:
                    attributeCbx.addItem(fieldName)

        layerCbx.currentIndexChanged.connect(updateAttributeCombobox)

    def updatePathType(self):
        self.dlg.cbxPathType.clear()
        use_attribute = self.dlg.grpPathAttribute.isChecked()
        use_way = self.dlg.cbxPathComputeOn.currentText() == self.tr('Ways')
        types = ['Simplest', 'Shortest', 'Azimuth']
        for t in types:
            self.dlg.cbxPathType.addItem(self.tr(t))

    def populateLayerComboboxes(self):
        """Populate all layer comboboxes"""
        # clear comboboxes
        self.dlg.cbxWaysBuilderInputLayer.clear()
        #self.dlg.cbxHorizonWayLayer.clear()
        self.dlg.cbxWaysBuilderPlacesLayer.clear()
        self.dlg.cbxWaysBuilderPlacesLayer.addItem(self.tr('No layer'), '')
        # add items to comboboxes
        layers = QgsProject.instance().layerTreeRoot().findLayers()
        layers = [lay.layer() for lay in layers if lay.layer().type() == QgsMapLayer.VectorLayer]
        for l in layers:
            if l.geometryType() == QgsWkbTypes.LineGeometry:
                self.dlg.cbxWaysBuilderInputLayer.addItem(l.name(), l.id())
                #self.dlg.cbxHorizonWayLayer.addItem(l.name(), l.id())
            elif l.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.dlg.cbxWaysBuilderPlacesLayer.addItem(l.name(), l.id())


    def computeWaysBuilder(self):

        self.setText(self.tr('Compute ways builder'))
        layerIdx = self.dlg.cbxWaysBuilderInputLayer.currentIndex()
        layerId = self.dlg.cbxWaysBuilderInputLayer.itemData( layerIdx )
        layer = QgsProject.instance().mapLayer(layerId)
        if not layer:
            self.setError(self.tr('No available layer!'))
            return

        output = self.dlg.letWaysBuilderDirectoryPath.text() or tempFolder()
        dbname = self.dlg.letWaysBuilderDBName.text() or 'morpheo_'+layer.name().replace(" ", "_")

        parameters = {
            'INPUT_LAYER'    : layer,
            'DIRECTORY'      : output,
            'DBNAME'         : dbname,
            'SNAP_DISTANCE'  : self.dlg.spxWaysBuilderSnapDist.value(),
            'MIN_EDGE_LENGTH': self.dlg.spxWaysBuilderMinEdgeLength.value(),
            'THRESHOLD'      : self.dlg.spxWaysBuilderThreshold.value()/180.0 * pi
        }

        if self.dlg.grpWaysBuilderStreetName.isChecked():
            parameters['WAY_ATTRIBUTE'] = self.dlg.cbxWaysBuilderWayAttribute.currentText()

        # Compute places
        placesIdx = self.dlg.cbxWaysBuilderPlacesLayer.currentIndex()
        placesId = self.dlg.cbxWaysBuilderPlacesLayer.itemData(placesIdx)
        places = None
        if placesId :
            places = QgsProject.instance().mapLayer(placesId)

        parameters['INPUT_PLACES'] = places
        parameters['BUFFER']       = self.dlg.spxWaysBuilderBuffer.value()

        parameters.update(
            OUTPUT_PLACES      = "%s_%s" % ('places',dbname),
            OUTPUT_PLACE_EDGES = "%s_%s" % ('place_edges',dbname),
            OUTPUT_WAYS        = "%s_%s" % ('ways',dbname)
        )

        self.remove_layer(parameters['OUTPUT_PLACES'])
        self.remove_layer(parameters['OUTPUT_PLACE_EDGES'])
        self.remove_layer(parameters['OUTPUT_WAYS'])

        runAndLoadResults('morpheo:ways', parameters, feedback=ProcessingFeedBack(self), context=None)

        self.setText(self.tr('Compute ways builder finished'), withMessageBar=True)
        self.synchronizeAllDBPathOnChanged(os.path.join(output, dbname)+'.sqlite')


    def get_basename( self, dbpath):
        """ Return a layer name for the table' table
        """
        return os.path.basename(dbpath).replace('.sqlite','')


    def remove_layer(self, name):
        """
        """
        project = QgsProject.instance()
        layers = project.mapLayersByName(name)
        if layers:
            # XXX Problem with qgis list type conversion error
            project.removeMapLayers([l.id() for l in layers])


    def computeWayAttributes(self):
        """ Compute attributes on ways or edges
        """
        self.setText(self.tr('Compute attributes'))

        dbpath = self.dlg.letWayAttributesDBPath.text()
        if not os.path.isfile( dbpath ):
            self.setError(self.tr('DB Path does not exist!'))
            return

        basename = self.get_basename(dbpath)

        parameters = {
            'DBPATH': dbpath,
            'ORTHOGONALITY': self.dlg.cbxWayAttributesOrthogonality.isChecked(),
            'BETWEENNESS'  : self.dlg.cbxWayAttributesBetweenness.isChecked(),
            'CLOSENESS'    : self.dlg.cbxWayAttributesCloseness.isChecked(),
            'STRESS'       : self.dlg.cbxWayAttributesStress.isChecked(),
            'CLASSES'      : self.dlg.spxWayAttributesClasses.value(),
        }        

        if self.dlg.cbxWayAttributesComputeOn.currentText() == self.tr('Edges'):
            algorithm = 'morpheo:edge_attributes'
            parameters['OUTPUT_PLACE_EDGES'] = "%s_%s" % ('place_edges',basename)
        else:
            parameters['RTOPO']       = self.dlg.cbxWayAttributesRtopo.isChecked()
            parameters['OUTPUT_WAYS'] = "%s_%s" % ('ways',basename)
            algorithm = 'morpheo:way_attributes'

        run(algorithm, parameters, feedback=ProcessingFeedBack(self), context=None)
        self.setText(self.tr('Compute attributes finished'), withMessageBar=True)


    def computePath(self):
        """ Compute paths on morpheo graph
        """
        self.setText(self.tr('Compute path'))

        dbpath = self.dlg.letPathDBPath.text()
        if not os.path.isfile( dbpath ):
            self.setError(self.tr('DB Path does not exist!'))
            return

        basename = self.get_basename(dbpath)

        # Get the selection on the place layer
        place_layer = QgsProject.instance().mapLayersByName('places_%s' % basename)
        if not place_layer:
            self.setError("No 'places' layer found !")
            return

        place_layer = place_layer[0]
        if place_layer.selectedFeatureCount() != 2:
            QMessageBox.information(self.dlg,
                    self.tr("Message"),
                    self.tr("You must select exactly 2 places in the 'places' layer"))
            return

        fi = place_layer.getSelectedFeatures()  

        path_type = self.dlg.cbxPathType.currentText()
        parameters = {
            'DBPATH'     : dbpath,
            'PLACE_START': next(fi).id(),
            'PLACE_END'  : next(fi).id(),
            'PATH_TYPE'  : str(path_type).lower(),
            'OUTPUT_PATH': "path_%s_%s" % (path_type, basename) 
        }

        if self.dlg.grpPathAttribute.isChecked():
            use_way   = self.dlg.cbxPathComputeOn.currentText() == self.tr('Ways')
            attribute = self.dlg.cbxPathWayAttribute.currentText()
            parameters.update(
                ATTRIBUTE   = attribute,
                PERCENTILE  = self.dlg.spxPathPercentile.value(),
                USE_WAY     = use_way,
                OUTPUT_PATH = "path_{}_{}{}_{}".format(
                    path_type,
                    attribute,
                    '_way' if use_way else '',
                    basename)
            )

        runAndLoadResults('morpheo:path', parameters, feedback=ProcessingFeedBack(self), context=None)
        self.setText(self.tr('Compute path finished'), withMessageBar=True)


    def computeHorizon(self):

        self.setText(self.tr('Compute horizon'))

        dbpath    = self.dlg.letHorizonDBPath.text()
        if not os.path.isfile( dbpath ):
            self.setError(self.tr('DB Path does not exist!'))
            return

        output = os.path.dirname(dbpath)
        dbname = os.path.basename(dbpath).replace('.sqlite','')

        conn = connect_database(dbpath)
        G    = read_ways_graph(os.path.join(output, dbname))

        if self.dlg.grpHorizonAttribute.isChecked():

            attribute = self.dlg.cbxHorizonWayAttribute.currentText()
            percentile = self.dlg.spxHorizonPercentile.value()

            table = 'horizon_%s_%s' % (attribute, percentile)
            hrz.horizon_from_attribute(conn, G, table, attribute, percentile)
        else:
            pt = self.dlg.letHorizonGeoPoint.text()
            if len(pt.split(',')) != 2:
                self.setError(self.tr('Invalid point!'))
                return
            pt = [ float(n) for n in pt.split(',') ]
            radius = self.dlg.spxHorizonGeoRadius.value()
            features = mesh.features_from_point_radius( conn.cursor(), 'ways', pt[0], pt[1], radius, 'WAY_ID' )
            if len(features) == 0:
                self.setError(self.tr('No ways found!'))
                return

            self.add_vector_layer( dbpath, 'ways', "way_selection_%s" % dbname, 
                    'WAY_ID IN ('+','.join(str(i) for i in features)+')')

            table = "horizon_from_selection"
            hrz.horizon_from_way_list(conn, G, table, features)

        conn.commit()
        conn.close()
        self.add_vector_layer( dbpath, table, "%s_%s" % (table,dbname))



    def computeStructuralDiff(self):

        self.setText(self.tr('Compute structural differences'))

        dbpath1  = self.dlg.letStructuralDiffDBPath1.text()
        dbpath2  = self.dlg.letStructuralDiffDBPath2.text()

        dbname1 = self.get_basename(dbpath1)
        dbname2 = self.get_basename(dbpath2)

        output = self.dlg.letStructuralDiffDirectoryPath.text() or tempFolder()
        dbname = self.dlg.letStructuralDiffDBName.text() or 'morpheo_diff_{}_{}'.format(
                                                            os.path.basename(dbname1),
                                                            os.path.basename(dbname2))

        paired_edges  = "%s_%s" % ('paired_edges' , dbname)
        removed_edges = "%s_%s" % ('removed_edges', dbname)
        added_edges   = "%s_%s" % ('added_edges'  , dbname)

        # Remove already computed layers
        for layer_name in (paired_edges, removed_edges, added_edges):
            self.remove_layer(layer_name)

        parameters = {
            'DBPATH1'  : dbpath1,
            'DBPATH2'  : dbpath2,
            'DIRECTORY': output,
            'DBNAME'   : dbname,
            'TOLERANCE': self.dlg.spxStructuralDiffTolerance.value(),
            'OUTPUT_PAIRED_EDGES' : paired_edges,
            'OUTPUT_ADDED_EDGES'  : added_edges,
            'OUTPUT_REMOVED_EDGES': removed_edges
        }
        
        runAndLoadResults('morpheo:structural_diff', parameters, feedback=ProcessingFeedBack(self), context=None)
        self.setText(self.tr('Compute structural differences finished'), withMessageBar=True)

    def setInfo(self, msg, error=False):
        if error:
            self.dlg.bar.pushMessage(self.tr("Error"), msg, level=Qgis.Critical)
            self.dlg.txtLog.append('<span style="color:red"><br>%s<br></span>' % msg)
        else:
            self.dlg.txtLog.append(msg)
        QCoreApplication.processEvents()

    def setWarningInfo(self, msg):
        self.setInfo('<span style="color:orange">%s</span>' % msg)
        QCoreApplication.processEvents()

    def setDebugInfo(self, msg):
        self.setInfo('<span style="color:blue">%s</span>' % msg)
        QCoreApplication.processEvents()

    def setConsoleInfo(self, msg):
        self.setCommand('<span style="color:darkgray">%s</span>' % msg)
        QCoreApplication.processEvents()

    def setPercentage(self, value):
        if self.dlg.progressBar.maximum() == 0:
            self.dlg.progressBar.setMaximum(100)
        self.dlg.progressBar.setValue(value)
        QCoreApplication.processEvents()

    def setText(self, text, withMessageBar=False):
        self.dlg.lblProgress.setText(text)
        self.setInfo(text, False)
        if withMessageBar:
            self.dlg.bar.pushMessage(self.tr("Info"), text, level=Qgis.Info)
        QCoreApplication.processEvents()

    def setWarning(self, text, withMessageBar=False):
        self.dlg.lblProgress.setText(text)
        self.setWarningInfo(text)
        if withMessageBar:
            self.dlg.bar.pushMessage(self.tr("Warning"), text, level=Qgis.Warning)
        QCoreApplication.processEvents()

    def setError(self, text):
        self.dlg.lblProgress.setText(text)
        self.setInfo(text, True)
        QCoreApplication.processEvents()

    def add_vector_layer(self, dbname, table_name, layer_name, clause=''):
        add_vector_layer(dbname, table_name, layer_name, clause)
        self.iface.actionDraw().trigger()
        self.iface.mapCanvas().refresh()


    def start(self):
        self.dlg.mAlgosListWidget.setEnabled(False)
        self.dlg.progressBar.setMaximum(0)
        self.dlg.lblProgress.setText(self.tr('Start'))
        self.dlg.txtLog.append('======== %s %s ========' % (self.tr('Start'), datetime.now()))


    def finish(self):
        self.dlg.progressBar.setValue(0)
        self.dlg.progressBar.setMaximum(100)
        self.dlg.lblProgress.setText(self.tr(''))
        self.dlg.txtLog.append('======== %s %s ========' % (self.tr('Finish'), datetime.now()))
        self.dlg.mAlgosListWidget.setEnabled(True)
        self.dlg.mAlgosListWidget.setCurrentRow(self.computeRow)


    def accept(self):
        self.computeRow = self.dlg.mAlgosListWidget.currentRow()
        self.dlg.mAlgosListWidget.setCurrentRow(5)
        self.start()

        if self.computeRow == 0:
            self.computeWaysBuilder()
        elif self.computeRow == 1:
            self.computeWayAttributes()
        elif self.computeRow == 2:
            self.computePath()
        elif self.computeRow == 3:
            self.computeHorizon()
        elif self.computeRow == 4:
            self.computeStructuralDiff()

        self.finish()


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Morpheo'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar
        # remove from processing
        QgsApplication.processingRegistry().removeProvider(self.morpheoAlgoProvider)

    def close(self):
        QgsProject.instance().layerWasAdded.disconnect(self.populateLayerComboboxes)
        QgsProject.instance().layersWillBeRemoved.disconnect(self.populateLayerComboboxes)

    def run(self):
        """Run method that performs all the real work"""
        if not self.dlg.isVisible():
            # populate layer comboboxes
            self.populateLayerComboboxes()
            # Rename OK button to Run
            self.dlg.buttonBox.button(QDialogButtonBox.Ok).setText(self.tr('Run'))
            QgsProject.instance().layerWasAdded.connect(self.populateLayerComboboxes)
            QgsProject.instance().layersWillBeRemoved.connect(self.populateLayerComboboxes)
            # set the dialog
            if self.settings.contains('/Morpheo/dialog'):
                self.dlg.restoreGeometry(self.settings.value("/Morpheo/dialog", QByteArray()))
            # show the dialog
            self.dlg.show()
        else:
            self.dlg.showNormal()
            self.dlg.raise_()
            self.dlg.activateWindow()

class PointMapTool(QgsMapToolEmitPoint):

    def __init__(self, canvas):
        QgsMapToolEmitPoint.__init__(self, canvas)

        self.canvas = canvas
        self.cursor = Qt.ArrowCursor

    def activate(self):
        self.canvas.setCursor(self.cursor)

    def canvasPressEvent(self, event):
        pnt = self.toMapCoordinates(event.pos())
        self.canvasClicked.emit(pnt, event.button())

