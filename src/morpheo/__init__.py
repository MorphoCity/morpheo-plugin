# -*- coding: UTF-8 -*-

# -----------------------
# Qgis plugin entrypoint
# -----------------------
def classFactory(iface):
    from gui.gui import Cui
    return Gui(iface)

