from typing import Any

from pydantic import RootModel
from pytauri import Emitter

from ..adapters.adapter import get_app_handle_obj
from ..common.logger import get_logger

logger = get_logger("events")


class _EventPayload(RootModel[dict[str, Any]]):
    pass


def _emit_payload(app_handle, event: str, payload: dict[str, Any] | None) -> None:
    payload_obj = _EventPayload(payload or {})
    Emitter.emit(app_handle, event, payload_obj)


class EventEmitter:
    # 向前端发送事件。若 app handle 尚未就绪则静默丢弃
    # 使用 AppHandle.run_on_main_thread 确保在主线程执行，
    # 避免 pyo3 的 unsendable 检查导致 panic

    _exiting = False

    @classmethod
    def set_exiting(cls, value: bool) -> None:
        cls._exiting = value

    def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        if self._exiting:
            return
        app_handle = get_app_handle_obj()
        if app_handle is None:
            return
        try:
            app_handle.run_on_main_thread(lambda: _emit_payload(app_handle, event, payload))
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning(f"事件发送失败 [{event}]: {e}")

    def emit_direct(self, event: str, payload: dict[str, Any] | None = None) -> None:
        # 直接从主线程发射事件，绕过 run_on_main_thread
        # 仅应在确定当前处于主线程时调用（如 asyncio 事件循环 / drain_progress_events）
        # 在子线程中调用会导致 pyo3 unsendable panic
        if EventEmitter._exiting:
            return
        app_handle = get_app_handle_obj()
        if app_handle is None:
            return
        try:
            _emit_payload(app_handle, event, payload)
        except (RuntimeError, OSError, ValueError) as e:
            logger.warning(f"直接事件发送失败 [{event}]: {e}")


# 模块级单例
_emitter_instance = EventEmitter()

# 门面函数（保持旧接口兼容）
emit = _emitter_instance.emit


def emit_direct(event: str, payload: dict[str, Any] | None = None) -> None:
    _emitter_instance.emit_direct(event, payload)


def emit_plugin_event(event: str, *args: Any, _framework: Any | None = None, **kwargs: Any) -> list[Any]:
    # 向插件系统发送事件（不经过前端 Tauri）
    if _framework is None:
        from ..common.state import AppState

        state = AppState()
        _framework = getattr(state, "plugin_framework", None)
    if _framework is None:
        return []
    try:
        return _framework._event_registry.emit(event, *args, **kwargs)
    except (RuntimeError, AttributeError, TypeError, ValueError) as e:
        logger.warning(f"emit_plugin_event 失败 [{event}]: {e}")
        return []
