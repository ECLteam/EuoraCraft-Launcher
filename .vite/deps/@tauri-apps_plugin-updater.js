import {
  Channel,
  Resource,
  invoke
} from "./chunk-DKSFAMV2.js";
import "./chunk-G3PMV62Z.js";

// frontend_QML/node_modules/.pnpm/@tauri-apps+plugin-updater@2.10.1/node_modules/@tauri-apps/plugin-updater/dist-js/index.js
var Update = class extends Resource {
  constructor(metadata) {
    super(metadata.rid);
    this.available = true;
    this.currentVersion = metadata.currentVersion;
    this.version = metadata.version;
    this.date = metadata.date;
    this.body = metadata.body;
    this.rawJson = metadata.rawJson;
  }
  /** Download the updater package */
  async download(onEvent, options) {
    convertToRustHeaders(options);
    const channel = new Channel();
    if (onEvent) {
      channel.onmessage = onEvent;
    }
    const downloadedBytesRid = await invoke("plugin:updater|download", {
      onEvent: channel,
      rid: this.rid,
      ...options
    });
    this.downloadedBytes = new Resource(downloadedBytesRid);
  }
  /** Install downloaded updater package */
  async install() {
    if (!this.downloadedBytes) {
      throw new Error("Update.install called before Update.download");
    }
    await invoke("plugin:updater|install", {
      updateRid: this.rid,
      bytesRid: this.downloadedBytes.rid
    });
    this.downloadedBytes = void 0;
  }
  /** Downloads the updater package and installs it */
  async downloadAndInstall(onEvent, options) {
    convertToRustHeaders(options);
    const channel = new Channel();
    if (onEvent) {
      channel.onmessage = onEvent;
    }
    await invoke("plugin:updater|download_and_install", {
      onEvent: channel,
      rid: this.rid,
      ...options
    });
  }
  async close() {
    await this.downloadedBytes?.close();
    await super.close();
  }
};
async function check(options) {
  convertToRustHeaders(options);
  const metadata = await invoke("plugin:updater|check", {
    ...options
  });
  return metadata ? new Update(metadata) : null;
}
function convertToRustHeaders(options) {
  if (options?.headers) {
    options.headers = Array.from(new Headers(options.headers).entries());
  }
}
export {
  Update,
  check
};
//# sourceMappingURL=@tauri-apps_plugin-updater.js.map
