from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DownloadSource(StrEnum):
    OFFICIAL = "official"
    BMCLAPI = "bmclapi"


class LoaderType(StrEnum):
    FABRIC = "fabric"
    FORGE = "forge"
    NEOFORGE = "neoforge"
    QUILT = "quilt"


class WardrobeKind(StrEnum):
    SKIN = "skin"
    CAPE = "cape"


class SkinModel(StrEnum):
    CLASSIC = "classic"
    SLIM = "slim"


class ImagePurpose(StrEnum):
    BACKGROUND = "background"
    SKIN = "skin"
    CAPE = "cape"


class FileSelectionPurpose(StrEnum):
    CRASH_ANALYSIS = "crash-analysis"


class FileSavePurpose(StrEnum):
    CRASH_REPORT = "crash-report"
    LAUNCHER_LOGS = "launcher-logs"


class SettingsQuery(RequestModel):
    section: str | None = None
    sections: list[str] | None = None

    @field_validator("section")
    @classmethod
    def validate_section(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("配置分区名称不能为空")
        return value

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not section for section in value):
            raise ValueError("配置分区名称不能为空")
        return value


class SettingsUpdate(RequestModel):
    section: str = Field(min_length=1)
    data: JsonValue


class GameCatalogRequest(RequestModel):
    filter_type: str | None = None
    classified: bool = False
    source: DownloadSource | None = None


class LoaderCatalogRequest(RequestModel):
    loader: LoaderType
    game_version: str = Field(min_length=1)
    source: DownloadSource | None = None


class GameScanRequest(RequestModel):
    paths: list[Path] | None = None
    force: bool = False

    @field_validator("paths", mode="before")
    @classmethod
    def validate_paths(cls, value):
        if value is not None and any(isinstance(path, str) and "\0" in path for path in value):
            raise ValueError("路径包含非法字符")
        return value


class JavaScanRequest(RequestModel):
    paths: list[Path] | None = None


class GamePathRequest(RequestModel):
    game_path: Path

    @field_validator("game_path", mode="before")
    @classmethod
    def validate_game_path(cls, value):
        if isinstance(value, str) and "\0" in value:
            raise ValueError("路径包含非法字符")
        return value


class GameConfigUpdate(GamePathRequest):
    data: dict[str, JsonValue]


class GameConfigPatch(GamePathRequest):
    patch: dict[str, JsonValue]


class GameUninstallRequest(GamePathRequest):
    version_id: str = Field(min_length=1)


class GameVersionRequest(GamePathRequest):
    version_id: str = Field(min_length=1)


class GameInstanceRequest(RequestModel):
    instance_id: str = Field(min_length=1)


class CrashAnalyzeRequest(GameVersionRequest):
    file_path: Path

    @field_validator("file_path", mode="before")
    @classmethod
    def validate_file_path(cls, value):
        if isinstance(value, str) and (not value.strip() or "\0" in value):
            raise ValueError("崩溃日志路径无效")
        return value


class CrashReportRequest(RequestModel):
    report_id: str = Field(min_length=1, pattern=r"^[a-f0-9]{32}$")


class CrashExportRequest(CrashReportRequest):
    output_path: Path | None = None

    @field_validator("output_path", mode="before")
    @classmethod
    def validate_output_path(cls, value):
        if isinstance(value, str) and (not value.strip() or "\0" in value):
            raise ValueError("导出路径无效")
        return value


class InstallRequest(RequestModel):
    version_id: str = Field(min_length=1)
    version_name: str | None = None
    loader_type: LoaderType | None = None
    loader_version: str | None = None
    game_path: Path
    java_path: Path | None = None
    source: DownloadSource | None = None
    task_id: str | None = None

    @field_validator("game_path", "java_path", mode="before")
    @classmethod
    def validate_paths(cls, value):
        if isinstance(value, str) and "\0" in value:
            raise ValueError("路径包含非法字符")
        return value


class LaunchRequest(RequestModel):
    version_id: str = Field(min_length=1)
    game_path: Path
    java_path: Path | None = None
    source: DownloadSource | None = None
    memory: int = Field(default=4096, ge=256, le=131072)
    width: int = Field(default=854, ge=320, le=16384)
    height: int = Field(default=480, ge=240, le=16384)
    jvm_args: list[str] = Field(default_factory=list)
    game_args: list[str] = Field(default_factory=list)
    version_isolation: bool = False

    @field_validator("game_path", "java_path", mode="before")
    @classmethod
    def validate_paths(cls, value):
        if isinstance(value, str) and "\0" in value:
            raise ValueError("路径包含非法字符")
        return value


class WardrobeImportRequest(RequestModel):
    path: Path
    kind: WardrobeKind
    name: str | None = Field(default=None, max_length=80)
    model: SkinModel | None = None

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, value):
        if isinstance(value, str) and (not value.strip() or "\0" in value):
            raise ValueError("纹理路径无效")
        return value

    @model_validator(mode="after")
    def validate_model(self):
        if self.kind == WardrobeKind.CAPE and self.model is not None:
            raise ValueError("披风不能指定手臂模型")
        return self


class WardrobeItemRequest(RequestModel):
    item_id: str = Field(min_length=1)


class WardrobeUpdateRequest(WardrobeItemRequest):
    name: str | None = Field(default=None, max_length=80)
    model: SkinModel | None = None
    favorite: bool | None = None


class WardrobeApplySkinRequest(WardrobeItemRequest):
    account_id: str = Field(min_length=1)


class AccountTextureRequest(RequestModel):
    account_id: str = Field(min_length=1)


class MicrosoftCapeRequest(AccountTextureRequest):
    cape_id: str = Field(min_length=1)


class ImageSelectionRequest(RequestModel):
    purpose: ImagePurpose = ImagePurpose.BACKGROUND


class FileSelectionRequest(RequestModel):
    purpose: FileSelectionPurpose | None = None


class FileSaveRequest(RequestModel):
    purpose: FileSavePurpose


REQUEST_MODELS: dict[str, type[RequestModel]] = {
    "settings_get": SettingsQuery,
    "settings_set": SettingsUpdate,
    "game_versions": GameCatalogRequest,
    "game_loader_versions": LoaderCatalogRequest,
    "game_scan": GameScanRequest,
    "game_java_scan": JavaScanRequest,
    "game_install": InstallRequest,
    "game_launch": LaunchRequest,
    "game_uninstall": GameUninstallRequest,
    "game_config_get": GamePathRequest,
    "game_config_set": GameConfigUpdate,
    "game_config_patch": GameConfigPatch,
    "game_version_stats": GameVersionRequest,
    "game_instance_stop": GameInstanceRequest,
    "game_crash_analyze": CrashAnalyzeRequest,
    "game_crash_output": CrashReportRequest,
    "game_crash_export": CrashExportRequest,
    "wardrobe_import": WardrobeImportRequest,
    "wardrobe_sync_account_skin": AccountTextureRequest,
    "wardrobe_update": WardrobeUpdateRequest,
    "wardrobe_delete": WardrobeItemRequest,
    "wardrobe_texture": WardrobeItemRequest,
    "wardrobe_export": WardrobeItemRequest,
    "wardrobe_apply_skin": WardrobeApplySkinRequest,
    "accounts_texture_urls": AccountTextureRequest,
    "microsoft_reset_skin": AccountTextureRequest,
    "microsoft_set_cape": MicrosoftCapeRequest,
    "microsoft_reset_cape": AccountTextureRequest,
    "select_image": ImageSelectionRequest,
    "select_file": FileSelectionRequest,
    "select_save_file": FileSaveRequest,
}


def request_schemas() -> dict[str, dict]:
    """
    Return JSON Schema documents consumed by the frontend integration task.

    """
    return {command: model.model_json_schema() for command, model in REQUEST_MODELS.items()}


__all__ = [
    "REQUEST_MODELS",
    "AccountTextureRequest",
    "CrashAnalyzeRequest",
    "CrashExportRequest",
    "CrashReportRequest",
    "FileSavePurpose",
    "FileSaveRequest",
    "FileSelectionPurpose",
    "FileSelectionRequest",
    "GameCatalogRequest",
    "GameConfigPatch",
    "GameConfigUpdate",
    "GameInstanceRequest",
    "GamePathRequest",
    "GameScanRequest",
    "GameUninstallRequest",
    "GameVersionRequest",
    "ImagePurpose",
    "ImageSelectionRequest",
    "InstallRequest",
    "JavaScanRequest",
    "LaunchRequest",
    "LoaderCatalogRequest",
    "MicrosoftCapeRequest",
    "SettingsQuery",
    "SettingsUpdate",
    "SkinModel",
    "WardrobeApplySkinRequest",
    "WardrobeImportRequest",
    "WardrobeItemRequest",
    "WardrobeKind",
    "WardrobeUpdateRequest",
    "request_schemas",
]
