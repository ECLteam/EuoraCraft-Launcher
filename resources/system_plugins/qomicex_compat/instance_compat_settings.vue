<template>
  <section class="qomicex-settings settings-section ecl-surface" data-theme-component="settings-section">
    <div class="qomicex-settings__header settings-section__header">QomicEX 实例兼容</div>
    <div class="qomicex-settings__item setting-item">
      <div class="setting-info">
        <div class="setting-label">QomicEX 实例索引</div>
        <div class="setting-desc">留空时自动探测 QOMICEX_HOME 与 LocalAppData；也可手动指定 instances.json。ECL 只读取，不会修改该文件。</div>
      </div>
      <div class="setting-control">
        <input
          class="qomicex-input"
          :value="path"
          :placeholder="'自动探测'"
          @input="onInput"
        />
        <button class="qomicex-btn" type="button" @click="browse">浏览</button>
      </div>
    </div>
    <div class="qomicex-settings__item setting-item">
      <div class="setting-info">
        <div class="setting-label">当前生效索引</div>
        <div class="setting-desc" :class="statusClass">{{ statusText }}</div>
      </div>
      <div class="setting-control">
        <button v-if="canOpen" class="qomicex-btn qomicex-btn--ghost" type="button" @click="openFolder">打开文件夹</button>
      </div>
    </div>
  </section>
</template>

<script>
module.exports = {
  name: 'QomicExInstanceCompatSettings',
  data() {
    return {
      path: '',
      effectivePath: '',
      status: 'loading',
      statusText: '正在探测…',
      _saveTimer: null,
    }
  },
  computed: {
    canOpen() {
      return this.status === 'valid' && !!this.effectivePath
    },
    statusClass() {
      return `qomicex-status qomicex-status--${this.status}`
    },
  },
  mounted() {
    this.init()
  },
  beforeUnmount() {
    if (this._saveTimer) clearTimeout(this._saveTimer)
  },
  methods: {
    async init() {
      const sdk = window.__plugin_sdk__
      if (!sdk) return
      const config = await sdk.api.getLauncherConfig('game')
      const manual = (config && config.success && config.data && config.data.qomicex_instances_path) || ''
      this.path = manual
      await this.resolve()
    },
    async resolve() {
      const sdk = window.__plugin_sdk__
      if (!sdk) return
      this.status = 'loading'
      this.statusText = '正在探测…'
      const res = await sdk.api.callPluginCommand('qomicex-compat:resolve', {
        instances_path: this.path || null,
      })
      if (res && res.success) {
        const data = res.data || {}
        this.effectivePath = data.path || ''
        if (this.effectivePath) {
          if (data.valid) {
            this.status = 'valid'
            this.statusText = `已生效：${this.effectivePath}`
          } else {
            this.status = 'missing'
            this.statusText = `路径无效：${this.effectivePath}`
          }
        } else {
          this.status = 'missing'
          this.statusText = '未找到实例索引，可手动指定'
        }
      } else {
        this.status = 'error'
        this.statusText = '探测失败，请重试'
      }
    },
    onInput(event) {
      this.path = event.target.value
      if (this._saveTimer) clearTimeout(this._saveTimer)
      this._saveTimer = setTimeout(() => this.save(this.path), 400)
    },
    async save(value) {
      const sdk = window.__plugin_sdk__
      if (!sdk) return
      const config = await sdk.api.getLauncherConfig('game')
      const current = config && config.success && config.data ? config.data : {}
      await sdk.api.setLauncherConfig('game', { ...current, qomicex_instances_path: value })
      await this.resolve()
    },
    async browse() {
      const sdk = window.__plugin_sdk__
      if (!sdk) return
      const res = await sdk.api.selectFile()
      const selected = res && res.success && res.data && res.data.path ? res.data.path : ''
      if (!selected) return
      this.path = selected
      await this.save(selected)
    },
    async openFolder() {
      const sdk = window.__plugin_sdk__
      if (!sdk || !this.effectivePath) return
      const folder = this.effectivePath.replace(/[\\/][^\\/]*$/, '')
      await sdk.api.openFolder(folder || this.effectivePath)
    },
  },
}
</script>

<style>
.qomicex-settings.settings-section {
  overflow: hidden;
  margin-bottom: 16px;
}
.qomicex-settings.settings-section:last-child {
  margin-bottom: 0;
}
.qomicex-settings .settings-section__header {
  padding: 13px 16px;
  border-bottom: 1px solid var(--ecl-border);
  color: var(--ecl-text);
  font-size: 13px;
  font-weight: 650;
}
.qomicex-settings__item {
  display: flex;
  min-height: 64px;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ecl-border);
}
.qomicex-settings__item:last-child {
  border-bottom: 0;
}
.qomicex-settings .setting-info {
  flex: 1;
  min-width: 0;
}
.qomicex-settings .setting-label {
  margin-bottom: 2px;
  color: var(--ecl-text);
  font-size: 13px;
  font-weight: 600;
}
.qomicex-settings .setting-desc {
  color: var(--ecl-text-secondary);
  font-size: 11px;
  line-height: 1.5;
}
.qomicex-settings .setting-control {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.qomicex-input {
  width: 260px;
  height: var(--ecl-control-height, 36px);
  padding: 0 12px;
  border: 1px solid var(--ecl-border-strong);
  border-radius: var(--ecl-radius-control, 6px);
  background: var(--ecl-surface-muted, transparent);
  color: var(--ecl-text);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.qomicex-input::placeholder {
  color: var(--ecl-text-tertiary);
}
.qomicex-input:focus {
  border-color: var(--ecl-primary);
  box-shadow: 0 0 0 2px var(--ecl-primary-alpha);
}
.qomicex-btn {
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--ecl-primary);
  border-radius: var(--ecl-radius-control, 6px);
  background: var(--ecl-primary);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
}
.qomicex-btn:hover {
  background: var(--ecl-primary-hover);
  border-color: var(--ecl-primary-hover);
}
.qomicex-btn:active {
  background: var(--ecl-primary-active);
  border-color: var(--ecl-primary-active);
}
.qomicex-btn--ghost {
  border-color: var(--ecl-border-strong);
  background: transparent;
  color: var(--ecl-text);
}
.qomicex-btn--ghost:hover {
  background: var(--ecl-hover);
  border-color: var(--ecl-border-strong);
}
.qomicex-status--valid {
  color: var(--ecl-success, #18a058);
}
.qomicex-status--missing {
  color: var(--ecl-warning, #f0a020);
}
.qomicex-status--error {
  color: var(--ecl-error, #d03050);
}
</style>
