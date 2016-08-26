# -*- encoding=utf-8 -*-

class BuilderError(Exception):
    pass

class FileNotFoundError(BuilderError):
    pass

class DatabaseNotFound(BuilderError):
    pass

class InvalidLayerError(BuilderError):
    pass


