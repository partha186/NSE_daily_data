"""funcdefs — core utilities package for EOD2.

Public API re-exported for convenient imports:

    from funcdefs import Config, Plotter, Plugin, utils, funcdefs
    from funcdefs import loadJson, writeJson, getDataFrame
    from funcdefs import Color
"""

from funcdefs.Config import Config
from funcdefs.utils import (
    loadJson,
    writeJson,
    randomChar,
    getDataFrame,
    getDeliveryLevels,
    getLevels,
    getLevels_v2,
    relativeStrength,
    mansfieldRelativeStrength,
    Color,
    DateEncoder,
)
from funcdefs import funcdefs, utils, Plugin, Plotter, diagnostic

__all__ = [
    "Config",
    "loadJson",
    "writeJson",
    "randomChar",
    "getDataFrame",
    "getDeliveryLevels",
    "getLevels",
    "getLevels_v2",
    "relativeStrength",
    "mansfieldRelativeStrength",
    "Color",
    "DateEncoder",
    "funcdefs",
    "utils",
    "Plugin",
    "Plotter",
    "diagnostic",
]
