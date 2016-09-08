# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import QgsMessageBar

from MorpheoDialog import MorpheoDialog
from MorpheoAlgorithmProvider import MorpheoAlgorithmProvider
from MorpheoAlgorithm import add_vector_layer
from processing.core.Processing import Processing
from processing.core.parameters import ParameterTableField
from processing.tools.system import tempFolder

from ..core.errors import BuilderError
from ..core.graph_builder import SpatialiteBuilder
from ..core.structdiff import structural_diff
from ..core import horizon as hrz
from ..core.ways import read_ways_graph
from ..core.sql  import connect_database
from logger import init_log_custom_hooks

Builder = SpatialiteBuilder

import os.path
import locale, time
from math import pi
from datetime import datetime

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

        # Rename OK button to Run
        self.dlg.buttonBox.button(QDialogButtonBox.Ok).setText(self.tr('Run'))

        # connect group toggle
        self.dlg.grpWaysBuilderStreetName.setChecked(False)
        self.dlg.grpWaysBuilderGeomProps.toggled.connect(self.grpWaysBuilderGeomPropsToggled)
        self.dlg.grpWaysBuilderStreetName.toggled.connect(self.grpWaysBuilderStreetNameToggled)

        # Initialize field path selection
        self.connectFileSelectionPanel(self.dlg.letWaysBuilderDirectoryPath, self.dlg.pbnWaysBuilderDirectoryPath, True)
        self.connectFileSelectionPanel(self.dlg.letWayAttributesDBPath, self.dlg.pbnWayAttributesDBPath, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letHorizonDBPath, self.dlg.pbnHorizonDBPath, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDBPath1, self.dlg.pbnStructuralDiffDBPath1, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDBPath2, self.dlg.pbnStructuralDiffDBPath2, False, 'sqlite')
        self.connectFileSelectionPanel(self.dlg.letStructuralDiffDirectoryPath, self.dlg.pbnStructuralDiffDirectoryPath, True)

        # Initialize attribute list
        self.connectComboboxLayerAttribute(self.dlg.cbxWaysBuilderWayAttribute, self.dlg.cbxWaysBuilderInputLayer, ParameterTableField.DATA_TYPE_STRING)
        self.connectComboboxLayerAttribute(self.dlg.cbxHorizonWayAttribute, self.dlg.cbxHorizonWayLayer, ParameterTableField.DATA_TYPE_NUMBER)

        # Connect compute attributes on
        self.dlg.cbxWayAttributesComputeOn.currentIndexChanged.connect(self.cbxWayAttributesComputeOnCurrentIndexChanged)

        # Connect compute
        self.computeRow = 0
        self.dlg.mAlgosListWidget.setCurrentRow(self.computeRow)
        self.dlg.buttonBox.accepted.connect(self.accept)

        # add to processing
        self.morpheoAlgoProvider = MorpheoAlgorithmProvider()
        Processing.addProvider(self.morpheoAlgoProvider, True)

    def grpWaysBuilderGeomPropsToggled(self, toggle):
        self.dlg.grpWaysBuilderStreetName.setChecked(not toggle)

    def grpWaysBuilderStreetNameToggled(self, toggle):
        self.dlg.grpWaysBuilderGeomProps.setChecked(not toggle)

    def cbxWayAttributesComputeOnCurrentIndexChanged(self, idx):
        if self.dlg.cbxWayAttributesComputeOn.currentText() == self.tr('Edges'):
            self.dlg.cbxWayAttributesRtopo.setChecked(False)
            self.dlg.cbxWayAttributesRtopo.setEnabled(False)
        else:
            self.dlg.cbxWayAttributesRtopo.setEnabled(True)

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
                                      folder)
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
        if not layer or not layer.isValid():
            return set()
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

        self.setText(self.tr('Compute ways builder'))
        layerIdx = self.dlg.cbxWaysBuilderInputLayer.currentIndex()
        layerId = self.dlg.cbxWaysBuilderInputLayer.itemData( layerIdx )
        layer = QgsMapLayerRegistry.instance().mapLayer(layerId)
        if not layer:
            self.setError(self.tr('No available layer!'))
            return

        output    = self.dlg.letWaysBuilderDirectoryPath.text() or tempFolder()
        dbname    = self.dlg.letWaysBuilderDBName.text() or 'morpheo_'+layer.name().replace(" ", "_")

        if not os.path.exists(output):
            self.setError(self.tr('Output dir does not exist!'))
            return

        if not os.path.exists(os.path.join(output, dbname)):
            os.mkdir(os.path.join(output, dbname))

        builder = Builder.from_layer( layer, os.path.join(output, dbname) )

        # Compute graph
        builder.build_graph(self.dlg.spxWaysBuilderSnapDist.value(),
                            self.dlg.spxWaysBuilderMinEdgeLength.value(),
                            self.dlg.grpWaysBuilderStreetName.isChecked() and self.dlg.cbxWaysBuilderWayAttribute.currentText() or '',
                            output=os.path.join(output, dbname))

        # Compute places
        placesIdx = self.dlg.cbxWaysBuilderPlacesLayer.currentIndex()
        placesId = self.dlg.cbxWaysBuilderPlacesLayer.itemData(placesIdx)
        places = None
        if placesId :
            places = QgsMapLayerRegistry.instance().mapLayer(placesId)
        builder.build_places(buffer_size=self.dlg.spxWaysBuilderBuffer.value(),
                             places=places,
                             output=os.path.join(output, dbname))

        # Compute ways
        if self.dlg.grpWaysBuilderStreetName.isChecked():
            builder.build_ways_from_attribute(self.dlg.cbxWaysBuilderWayAttribute.currentText(),
                                              output=os.path.join(output, dbname))
        else:
            builder.build_ways(threshold=self.dlg.spxWaysBuilderThreshold.value()/180.0 * pi,
                               output=os.path.join(output, dbname))

        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'places', "%s_%s" % ('places',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'place_edges', "%s_%s" % ('place_edges',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'ways', "%s_%s" % ('ways',dbname))

        self.setText(self.tr('Compute ways builder finished'), withMessageBar=True)


    def computeWayAttributes(self):

        self.setText(self.tr('Compute attributes'))

        dbpath    = self.dlg.letWayAttributesDBPath.text()
        if not os.path.isfile( dbpath ):
            self.setError(self.tr('DB Path does not exist!'))
            return

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')


        builder = Builder.from_database( os.path.join(output, dbname) )
        if self.dlg.cbxWayAttributesComputeOn.currentText() == self.tr('Edges'):
            builder.compute_edge_attributes( os.path.join(output, dbname),
                    orthogonality = self.dlg.cbxWayAttributesOrthogonality.isChecked(),
                    betweenness   = self.dlg.cbxWayAttributesBetweenness.isChecked(),
                    closeness     = self.dlg.cbxWayAttributesCloseness.isChecked(),
                    stress        = self.dlg.cbxWayAttributesStress.isChecked(),
                    classes       = self.dlg.spxWayAttributesClasses.value(),
                    output        = os.path.join(output, dbname))

            # Visualize data
            add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'place_edges', "%s_%s" % ('place_edges',dbname))
        else:
            builder.compute_way_attributes(
                    orthogonality = self.dlg.cbxWayAttributesOrthogonality.isChecked(),
                    betweenness   = self.dlg.cbxWayAttributesBetweenness.isChecked(),
                    closeness     = self.dlg.cbxWayAttributesCloseness.isChecked(),
                    stress        = self.dlg.cbxWayAttributesStress.isChecked(),
                    rtopo         = self.dlg.cbxWayAttributesRtopo.isChecked(),
                    classes       = self.dlg.spxWayAttributesClasses.value(),
                    output        = os.path.join(output, dbname))

            # Visualize data
            add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'places', "%s_%s" % ('places',dbname))
            add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'place_edges', "%s_%s" % ('place_edges',dbname))
            add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'ways', "%s_%s" % ('ways',dbname))

        self.setText(self.tr('Compute attributes finished'), withMessageBar=True)

    def computeHorizon(self):

        self.setText(self.tr('Compute horizon'))

        dbpath    = self.dlg.letHorizonDBPath.text()
        if not os.path.isfile( dbpath ):
            self.setError(self.tr('DB Path does not exist!'))
            return

        output    = os.path.dirname(dbpath)
        dbname    = os.path.basename(dbpath).replace('.sqlite','')

        attribute = self.dlg.cbxHorizonWayAttribute.currentText()
        percentile = self.dlg.spxHorizonPercentile.value()


        conn = connect_database(dbpath)
        G    = read_ways_graph(os.path.join(output, dbname))
        data = hrz.horizon_from_attribute(conn, G, attribute, percentile,
                                          output=os.path.join(output, dbname, '%s_%s_%s.txt' % (attribute, percentile, dbname)))
        hrz.plot_histogram(data, os.path.join(output, dbname, '%s_%s_%s.png' % (attribute, percentile, dbname)),
                           bins=self.dlg.spxHorizonPlotBins.value(),
                           size=(self.dlg.spxHorizonPlotWidth.value(), self.dlg.spxHorizonPlotHeight.value()))

        imgDlg = QDialog(self.dlg)
        imgDlg.setLayout(QVBoxLayout())
        imgDlg.layout().setContentsMargins(0, 0, 0, 0)
        imgLabel = QLabel()
        imgPixmap = QPixmap(os.path.join(output, dbname, '%s_%s_%s.png' % (attribute, percentile, dbname)))
        imgLabel.setPixmap(imgPixmap)
        imgDlg.layout().insertWidget(0, imgLabel)
        imgDlg.show()

    def computeStructuralDiff(self):

        self.setText(self.tr('Compute structural differences'))

        def check_dbpath(path):
            basename = os.path.basename(path)
            shp = os.path.join(path,'place_edges_%s.shp' % basename)
            gpickle = os.path.join(path,'way_graph_%s.gpickle' % basename)
            return os.path.isfile(shp) and os.path.isfile(gpickle)

        dbpath1    = self.dlg.letStructuralDiffDBPath1.text()
        dirname1  = os.path.dirname(dbpath1)
        dbname1   = os.path.basename(dbpath1).replace('.sqlite','')
        if not check_dbpath(os.path.join(dirname1, dbname1)):
            self.setError(self.tr('Initial Morpheo directory is incomplete'))
            return

        dbpath2    = self.dlg.letStructuralDiffDBPath2.text()
        dirname2  = os.path.dirname(dbpath2)
        dbname2   = os.path.basename(dbpath2).replace('.sqlite','')
        if not check_dbpath(os.path.join(dirname2, dbname2)):
            self.setError(self.tr('Final Morpheo directory is incomplete'))
            return


        output    = self.dlg.letStructuralDiffDirectoryPath.text() or tempFolder()
        dbname    = self.dlg.letStructuralDiffDBName.text() or 'morpheo_%s_%s' % (dbname1, dbname2)

        if not os.path.exists(os.path.join(output, dbname)):
            os.mkdir(os.path.join(output, dbname))


        structural_diff( os.path.join(dirname1, dbname1), os.path.join(dirname2, dbname2),
                         output=os.path.join(output, dbname),
                         buffersize=self.dlg.spxStructuralDiffTolerance.value())

        # Visualize data
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'paired_edges', "%s_%s" % ('paired_edges',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'removed_edges', "%s_%s" % ('removed_edges',dbname))
        add_vector_layer( os.path.join(output, dbname)+'.sqlite', 'added_edges', "%s_%s" % ('added_edges',dbname))

        self.setText(self.tr('Compute structural differences'), withMessageBar=True)

    def setInfo(self, msg, error=False):
        if error:
            self.dlg.bar.pushMessage(self.tr("Error"), msg, level=QgsMessageBar.CRITICAL)
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
            self.dlg.bar.pushMessage(self.tr("Info"), text, level=QgsMessageBar.INFO)
        QCoreApplication.processEvents()

    def setWarning(self, text, withMessageBar=False):
        self.dlg.lblProgress.setText(text)
        self.setWarningInfo(text)
        if withMessageBar:
            self.dlg.bar.pushMessage(self.tr("Warning"), text, level=QgsMessageBar.WARNING)
        QCoreApplication.processEvents()

    def setError(self, text):
        self.dlg.lblProgress.setText(text)
        self.setInfo(text, True)
        QCoreApplication.processEvents()

    def init_log_handler(self):

        def on_info(msg):
            # do something with msg
            self.setText(msg)

        def on_warn(msg):
            # do something with msg
            self.setWarning(msg)

        def on_error(msg):
            # do something with msg
            self.setError(msg)

        def on_critical(msg):
            # do something with msg
            self.setError(msg)

        def on_progress(value, msg):
            # de something with value and message
            self.dlg.lblProgress.setText(msg)
            self.setPercentage(value)

        init_log_custom_hooks(on_info=on_info,
                              on_warn=on_warn,
                              on_error=on_error,
                              on_critical=on_critical,
                              on_progress=on_progress)


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
        try:
            if self.computeRow == 0:
                self.computeWaysBuilder()
            elif self.computeRow == 1:
                self.computeWayAttributes()
            elif self.computeRow == 3:
                self.computeHorizon()
            elif self.computeRow == 4:
                self.computeStructuralDiff()
        except Exception, e:
            import traceback
            self.setError(self.tr('Uncaught error, please report it from QGIS logs: %s') % e)
            lines = [self.tr('Uncaught error while compute operation')]
            lines.append(traceback.format_exc())
            msg = '\n'.join([m for m in lines])
            QgsMessageLog.logMessage(msg, "Morpheo", QgsMessageLog.CRITICAL)
        self.finish()
        pass


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        init_log_custom_hooks()

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
        if not self.dlg.isVisible():
            # show the dialog
            self.dlg.show()
            self.init_log_handler()
            # Run the dialog event loop
            result = self.dlg.exec_()
            init_log_custom_hooks()
