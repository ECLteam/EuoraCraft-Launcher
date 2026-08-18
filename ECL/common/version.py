"""启动器版本信息。

单一来源：pyproject.toml 的 [tool.euoracraft] 字段（version / version_type）。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT_TOML = Path(__file__).resolve().parents[2] / "pyproject.toml"

with _PYPROJECT_TOML.open("rb") as _f:
    _euoracraft = tomllib.load(_f)["tool"]["euoracraft"]

__version__ = _euoracraft["version"]
__version_type__ = _euoracraft["version_type"]
