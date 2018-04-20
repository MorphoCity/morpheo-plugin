# -*- coding: utf-8 -*-

import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QSizePolicy, QMessageBox, QDialog
from qgis.PyQt.QtCore import Qt, QSettings, QByteArray, pyqtSignal

from qgis.utils import iface
from qgis.gui import QgsMessageBar

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'ui', 'morpheo_dialog.ui'))


class MorpheoDialog(QDialog, FORM_CLASS):

    closed = pyqtSignal()

    def __init__(self, parent=None):
        """Constructor."""
        super(MorpheoDialog, self).__init__(parent)
        # Set up the user interface from Designer.
        # After setupUI you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

        self.setWindowFlags(Qt.WindowMinimizeButtonHint |
                            Qt.WindowMaximizeButtonHint |
                            Qt.WindowCloseButtonHint)

        self.settings = QSettings()
        self.restoreGeometry(self.settings.value("/Morpheo/dialog", QByteArray()))

        self.bar = QgsMessageBar()
        self.bar.setSizePolicy( QSizePolicy.Minimum, QSizePolicy.Fixed )
        self.layout().insertWidget(0, self.bar)

    def accept(self):
        pass

    def reject(self):
        self.close()
        self.hide()

    def closeEvent(self, evt):
        self.closed.emit()
        self.settings.setValue("/Morpheo/dialog", self.saveGeometry())
        super(MorpheoDialog, self).closeEvent(evt)
