# -*- coding: UTF-8 -*-

from MorpheoAlgorithmProvider import MorpheoAlgorithmProvider
from processing.core.Processing import Processing

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic

from qgis.core import *

from matplotlib.pyplot import *

import os

class Gui:

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.dlg = QDialog()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'filter_by_attribute.ui'), self.dlg)
        self.spacer = QSpacerItem(10,10, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.dlg.verticalLayout.addItem(self.spacer)

        self.filter_field = ''
        self.filter_values = set()
    
    def initGui(self):
        self.morpheoAlgoProvider = MorpheoAlgorithmProvider()
        Processing.addProvider(self.morpheoAlgoProvider, True)

        self.actions.append( QAction(
            QIcon(os.path.join(os.path.dirname(__file__),"morpheo.png")),
            u"filter by attribute", self.iface.mainWindow()) )
        self.actions[-1].setWhatsThis("filter by attribute")
        self.actions[-1].triggered.connect(self.filter_by_attribute)
        
        for a in self.actions:
            self.iface.addToolBarIcon(a)

        QgsMapLayerRegistry.instance().layersAdded.connect( self.layerAdded )
    
    def unload(self):
        Processing.removeProvider(self.morpheoAlgoProvider)
        for a in self.actions:
            self.iface.removeToolBarIcon(a)

    def layerAdded(self, layers):
        pass

    def filter_by_attribute(self):
        if not self.iface.activeLayer():
            return

        self.iface.activeLayer().setSubsetString("")
        self.dlg.fieldComboBox.clear()

        self.dlg.fieldComboBox.addItem('') 
        for field in self.iface.activeLayer().pendingFields(): 
            self.dlg.fieldComboBox.addItem(field.name()) 

        self.dlg.fieldComboBox.currentIndexChanged.connect(self.filter_attribute_changed)

        if self.filter_field:
            idx = self.dlg.fieldComboBox.findText(self.filter_field)
            print idx
            self.dlg.fieldComboBox.setCurrentIndex(idx)
        
        if self.dlg.exec_():
            self.update_filter()

        self.dlg.fieldComboBox.currentIndexChanged.disconnect(self.filter_attribute_changed)


    def filter_attribute_changed(self, idx):
        print 'filter by', self.filter_field
        values = set()
        fit = self.iface.activeLayer().getFeatures()
        attribute = self.dlg.fieldComboBox.currentText()
        if attribute != self.filter_field:
            self.filter_values = set()
        self.filter_field = attribute

        if len(attribute): 
            for feature in fit:
                values.add(feature[attribute])

        # clear layout
        layout = self.dlg.verticalLayout
        layout.removeItem(self.spacer)
        for i in reversed(range(layout.count())): 
            layout.itemAt(i).widget().setParent(None)

        for value in values:
            chk = QCheckBox(str(value))
            layout.addWidget(chk)
            #chk.stateChanged.connect(self.update_filter)
            if value not in self.filter_values:
                chk.setCheckState(Qt.Checked)

        layout.addItem(self.spacer)

    def update_filter(self):
        self.filter_values = set()
        for i in range(self.dlg.verticalLayout.count()-1):
            chk = self.dlg.verticalLayout.itemAt(i).widget()
            if not chk.isChecked():
                self.filter_values.add(chk.text())

        self.iface.activeLayer().setSubsetString(
                '"'+self.filter_field+
                '" NOT IN ('+','.join(['"'+str(v)+'"' for v in self.filter_values])+")")



        


