# -*- coding: UTF-8 -*-

from MorpheoAlgorithmProvider import MorpheoAlgorithmProvider
from processing.core.Processing import Processing

class Gui:

    def __init__(self, iface):
        self.iface = iface

        import os, sys
        cmd_folder = os.path.dirname(__file__)
        if cmd_folder not in sys.path:
            sys.path.insert(0, cmd_folder)

    def initGui(self):
        self.morpheoAlgoProvider = MorpheoAlgorithmProvider()
        Processing.addProvider(self.morpheoAlgoProvider, True)

    def unload(self):
        Processing.removeProvider(self.morpheoAlgoProvider)