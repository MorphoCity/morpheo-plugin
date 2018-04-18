# -*- coding: UTF-8 -*-

# -----------------------
# Qgis plugin entrypoint
# -----------------------

def classFactory(iface):
    import os, sys
    cmd_folder = os.path.join(os.path.dirname(__file__),'gui')
    if cmd_folder not in sys.path:
        sys.path.insert(0, cmd_folder)

    from .gui.MorpheoPlugin import MorpheoPlugin
    return MorpheoPlugin(iface)

