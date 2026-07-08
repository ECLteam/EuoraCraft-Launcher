from ECL.common.logger import get_logger
from ECL.plugin.plugin import Plugin

logger = get_logger("mouse_effect")

MOUSE_EFFECT_IFRAME = '<iframe src="/mouse-effect.html" class="mouse-effect-iframe" frameborder="0" style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:99998;"></iframe>'

BRIDGE_SCRIPT = r"""
const sdk = window.__plugin_sdk__
if (!sdk) {
  console.error('[mouse_effect] plugin-sdk 未加载')
} else {
  let bridge = null

  function initBridge() {
    if (bridge) bridge.destroy()
    bridge = sdk.createIframeBridge({
      selector: '.mouse-effect-iframe',
      onConfigUpdate: function(iframe, _config) {
        // 设置变更时由 settings_changed 事件处理
      }
    })
  }

  function updateIframeConfig() {
    // 通过 postMessage 发送配置到 iframe
    const iframes = document.querySelectorAll('.mouse-effect-iframe')
    if (iframes.length === 0) return
    // 配置值由后端 settings 系统管理，iframe 内部通过 postMessage 接收
    // 此处仅确保桥接就绪
  }

  initBridge()

  sdk.listen(sdk.Events.SETTINGS_CHANGED, function(payload) {
    if (payload && payload.plugin === 'mouse_effect') {
      // 延迟等 DOM 更新
      setTimeout(function() {
        initBridge()
      }, 100)
    }
  })
}
"""

SETTINGS_SCHEMA = {
    "enabled": {
        "type": "boolean",
        "label": "启用鼠标特效",
        "description": "开启后鼠标移动时显示粒子拖尾特效",
        "default": True,
    },
    "color": {
        "type": "select",
        "label": "特效颜色",
        "description": "选择粒子特效的颜色",
        "default": "45,175,255",
        "options": [
            {"value": "45,175,255", "label": "蓝色"},
            {"value": "160,100,255", "label": "紫色"},
            {"value": "255,100,180", "label": "粉色"},
            {"value": "80,220,120", "label": "绿色"},
            {"value": "255,160,50", "label": "橙色"},
            {"value": "220,220,240", "label": "白色"},
        ],
    },
    "scale": {
        "type": "number",
        "label": "粒子大小",
        "description": "调整粒子的缩放比例 (0.5 - 3.0)",
        "default": 1.5,
        "min": 0.5,
        "max": 3.0,
        "step": 0.1,
    },
    "opacity": {
        "type": "number",
        "label": "粒子透明度",
        "description": "调整粒子的不透明度 (0.1 - 1.0)",
        "default": 1.0,
        "min": 0.1,
        "max": 1.0,
        "step": 0.05,
    },
    "speed": {
        "type": "number",
        "label": "粒子速度",
        "description": "调整粒子移动的速度 (0.25 - 2.0)",
        "default": 1.0,
        "min": 0.25,
        "max": 2.0,
        "step": 0.05,
    },
}


class MouseEffectPlugin(Plugin):
    def on_load(self):
        self.register_settings(SETTINGS_SCHEMA)
        logger.info("mouse effect plugin loaded")

    def on_enable(self):
        self._inject_effect()

    def on_disable(self):
        self._framework.clear_plugin_slots(self._name)
        logger.info("mouse effect plugin disabled")

    @Plugin.on("plugin:settings_changed")
    def on_settings_changed(self, payload):
        if payload.get("plugin") != self._name:
            return
        self._inject_effect()

    def _inject_effect(self):
        enabled = self.get_setting("enabled", True)
        if not enabled:
            self._framework.clear_plugin_slots(self._name)
            return

        self._framework.clear_plugin_slots(self._name)
        self.inject_html("page-bottom", MOUSE_EFFECT_IFRAME)
        self.inject_typescript(BRIDGE_SCRIPT)
