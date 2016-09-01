# -*- encoding=utf-8 -*-

class MorpheoException(Exception):
    pass

class BuilderError(MorpheoException):
    pass

class FileNotFoundError(BuilderError):
    pass

class DatabaseNotFound(BuilderError):
    pass

class InvalidLayerError(BuilderError):
    pass

class ErrorGraphNotFound(BuilderError):
    pass

