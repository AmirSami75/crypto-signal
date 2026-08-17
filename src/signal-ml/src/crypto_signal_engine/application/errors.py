class MlEngineError(Exception):
    """Base class for expected application failures."""


class InvalidInferenceRequest(MlEngineError):
    """The caller supplied invalid or incompatible inference input."""


class ModelUnavailable(MlEngineError):
    """No valid production model can serve inference."""
