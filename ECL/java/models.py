from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path


@dataclass
class JavaInfo:
    path: Path
    version: str
    major_version: int
    java_type: str
    arch: str
    sources: list[str] = field(default_factory=list)

    @cached_property
    def unique_key(self) -> str:
        java_home = self.path.parent.parent
        return f"{java_home.as_posix().lower()}_{self.major_version}"

    def __str__(self) -> str:
        return (
            f"{self.java_type} {self.major_version} ({self.version}), {self.arch}, "
            f"来源:[{','.join(self.sources)}], 路径: {self.path}"
        )
