# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *

from MorpheoDialog import MorpheoDialog
from MorpheoAlgorithmProvider import MorpheoAlgorithmProvider
from MorpheoAlgorithm import add_vector_layer
from processing.core.Processing import Processing
from processing.core.parameters import ParameterTableField
from processing.tools.system import tempFolder

from math import pi
from ..core.errors import BuilderError
from ..core.graph_builder import SpatialiteBuilder
from ..core.structdiff import structural_diff
from ..core import horizon as hrz
from ..core.ways import read_ways_graph
from ..core.sql  import connect_database

Builder = SpatialiteBuilder

import os.path
import locale, time

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

        # Create the dialog (after translation) and keep reference
        self.dlg = MorpheoDialog()

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Morpheo')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'Morpheo')
        self.toolbar.setObjectName(u'Morpheo')

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
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

        # connect group toggle
        self.dlg.grpWaysBuilderStreetName.setChecked(False)
        self.dlg.grpWaysBuilderGeomProps.toggled.connect(self.grpWaysBuilderGeomPropsToggled)
        self.dlg.grpWaysBuilderStreetName.toggled.connect(self.grpWaysBuilderStreetNameToggled)

        # Initialize field path selection
        self.connectFileSelectionPanel(self.dlg.letWaysBuilderDirectoryPath, self.dlg.pbnWaysBuilderDirectoryPath, True)
        self.connectFileSelectionPanel(self.dlg.letWayAttributesDBPath, self.dlg.pbnWayAttributesDBPath, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letHorizonDBPath, self.dlg.pbnHorizonDBPath, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDBPath1, self.dlg.pbnStructuralDiffDBPath1, True)
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDBPath2, self.dlg.pbnStructuralDiffDBPath2, True)
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDirectoryPath, self.dlg.pbnStructuralDiffDirectoryPath, True)

        # Initialize attribute list
        self.connectComboboxLayerAttribute(self.dlg.cbxWaysBuilderWayAttribute, self.dlg.cbxWaysBuilderInputLayer, ParameterTableField.DATA_TYPE_STRING)
        self.connectComboboxLayerAttribute(self.dlg.cbxHorizonWayAttribute, self.dlg.cbxHorizonWayLayer, ParameterTableField.DATA_TYPE_NUMBER)

        # Connect compute
        self.dlg.pbnComputeWaysBuilder.clicked.connect(self.computeWaysBuilder)

        # add to processing
        self.morpheoAlgoProvider = MorpheoAlgorithmProvider()
        Processing.addProvider(self.morpheoAlgoProvider, True)

    def grpWaysBuilderGeomPropsToggled(self, toggle):
        self.dlg.grpWaysBuilderStreetName.setChecked(not toggle)

    def grpWaysBuilderStreetNameToggled(self, toggle):
        self.dlg.grpWaysBuilderGeomProps.setChecked(not toggle)

    def connectFileSelectionPanel(self, leText, btnSelect, isFolder, ext=None):

        def showSelectionDialog():
            #QMessageBox.warning(self.dlg, 'showSelectionDialog', 'showSelectionDialog')
            # Find the file dialog's working directory
            settings = QSettings()
            text = leText.text()
            if os.path.isdir(text):
                path = text
            elif os.path.isdir(os.path.dirname(text)):
                path = os.path.dirname(text)
            elif settings.contains('/Morpheo/LastInputPath'):
                path = settings.value('/Morpheo/LastInputPath')
            else:
                path = ''

            if isFolder:
                folder = QFileDialog.getExistingDirectory(self.dlg,
                                                          self.tr('Select folder'), path)
                if folder:
                    leText.setText(folder)
                    settings.setValue('/Morpheo/LastInputPath',
                                      os.path.dirname(folder))
            else:
                filenames = QFileDialog.getOpenFileNames(self.dlg,
                                                         self.tr('Select file'), path, '*.' + ext)
                if filenames:
                    leText.setText(u';'.join(filenames))
                    settings.setValue('/Morpheo/LastInputPath',
                                      os.path.dirname(filenames[0]))

        btnSelect.clicked.connect(showSelectionDialog)


    def getFields(self, layer, datatype):
        fieldTypes = []
        if datatype == ParameterTableField.DATA_TYPE_STRING:
            fieldTypes = [QVariant.String]
        elif datatype == ParameterTableField.DATA_TYPE_NUMBER:
            fieldTypes = [QVariant.Int, QVariant.Double, QVariant.LongLong,
                          QVariant.UInt, QVariant.ULongLong]

        fieldNames = set()
        for field in layer.pendingFields():
            if not fieldTypes or field.type() in fieldTypes:
                fieldNames.add(unicode(field.name()))
        return sorted(list(fieldNames), cmp=locale.strcoll)

    def connectComboboxLayerAttribute(self, attributeCbx, layerCbx, datatype):

        def updateAttributeCombobox(idx):
            """update"""
            attributeCbx.clear()
            layerId = layerCbx.itemData( idx )
            for fieldName in self.getFields(QgsMapLayerRegistry.instance().mapLayer(layerId), datatype):
                attributeCbx.addItem(fieldName)

        layerCbx.currentIndexChanged.connect(updateAttributeCombobox)

    def populateLayerComboboxes(self):
        """Populate all layer comboboxes"""
        # clear comboboxes
        self.dlg.cbxWaysBuilderInputLayer.clear()
        self.dlg.cbxHorizonWayLayer.clear()
        self.dlg.cbxWaysBuilderPlacesLayer.clear()
        self.dlg.cbxWaysBuilderPlacesLayer.addItem(self.tr('No layer'), '')
        # add items to comboboxes
        layers = QgsProject.instance().layerTreeRoot().findLayers()
        layers = [lay.layer() for lay in layers if lay.layer().type() == QgsMapLayer.VectorLayer]
        for l in layers:
            if l.geometryType() == QGis.Line:
                self.dlg.cbxWaysBuilderInputLayer.addItem(l.name(), l.id())
                self.dlg.cbxHorizonWayLayer.addItem(l.name(), l.id())
            elif l.geometryType() == QGis.Polygon:
                self.dlg.cbxWaysBuilderPlacesLayer.addItem(l.name(), l.id())


    def computeWaysBuilder(self):
        self.dlg.scrollAreaWidgetContents.setEnabled(False)
        self.dlg.pgbComputeWaysBuilder.setMaximum(0)
        self.dlg.pbnComputeWaysBuilder.setEnabled(False)
        self.dlg.scrollAreaWidgetContents.repaint()

        layerIdx = self.dlg.cbxWaysBuilderInputLayer.currentIndex()
        layerId = self.dlg.cbxWaysBuilderInputLayer.itemData( layerIdx )
        layer = QgsMapLayerRegistry.instance().mapLayer(layerId)

        output    = self.dlg.letWaysBuilderDirectoryPath.text() or tempFolder()
        dbname    = self.dlg.letWaysBuilderDBName.text() or 'morpheo_'+layer.name().replace(" ", "_")

        if not os.path.exists(output):
            self.dlg.scrollAreaWidgetContents.setEnabled(True)
            QMessageBox.warning(self.dlg, 'Morpheo warning', self.tr('Output dir does not exist!'))
            return

        if not os.path.exists(os.path.join(output, dbname)):
            os.mkdir(os.path.join(output, dbname))

        builder = Builder.from_layer( layer, os.path.join(output, dbname) )
        time.sleep(1)

        # Compute graph
        builder.build_graph(self.dlg.spxWaysBuilderSnapDist.value(),
                            self.dlg.spxWaysBuilderMinEdgeLength.value(),
                            self.dlg.grpWaysBuilderStreetName.isChecked() and self.dlg.cbxWaysBuilderWayAttribute.currentText() or '',
                            output=os.path.join(output, dbname))
        time.sleep(1)

        # Compute places
        placesIdx = self.dlg.cbxWaysBuilderPlacesLayer.currentIndex()
        placesId = self.dlg.cbxWaysBuilderPlacesLayer.itemData(placesIdx)
        QMessageBox.warning(self.dlg, 'Morpheo warning', 'placesIdx: %s and placesId: "%s"' % (placesIdx, placesId))
        places = None
        if placesId :
            places = QgsMapLayerRegistry.instance().mapLayer(placesId)
        builder.build_places(buffer_size=self.dlg.spxWaysBuilderBuffer.value(),
                             places=places,
                             output=os.path.join(output, dbname),
                             export_graph=True)
        time.sleep(1)

        # Compute ways
        if self.dlg.grpWaysBuilderStreetName.isChecked():
            builder.build_ways_from_attribute(output=os.path.join(output, dbname))
        else:
            builder.build_ways(threshold=self.dlg.spxWaysBuilderThreshold.value()/180.0 * pi,
                           output=os.path.join(output, dbname))

        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'places', "%s_%s" % ('places',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'place_edges', "%s_%s" % ('place_edges',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'ways', "%s_%s" % ('ways',dbname))

        self.dlg.pbnComputeWaysBuilder.setEnabled(True)
        self.dlg.pgbComputeWaysBuilder.setMaximum(100)
        self.dlg.scrollAreaWidgetContents.setEnabled(True)

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
        Processing.removeProvider(self.morpheoAlgoProvider)


    def run(self):
        """Run method that performs all the real work"""
        # populate layer comboboxes
        self.populateLayerComboboxes()
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass
