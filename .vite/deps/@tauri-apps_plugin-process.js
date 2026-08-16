import {
  invoke
} from "./chunk-DKSFAMV2.js";
import "./chunk-G3PMV62Z.js";

// frontend_QML/node_modules/.pnpm/@tauri-apps+plugin-process@2.3.1/node_modules/@tauri-apps/plugin-process/dist-js/index.js
async function exit(code = 0) {
  await invoke("plugin:process|exit", { code });
}
async function relaunch() {
  await invoke("plugin:process|restart");
}
export {
  exit,
  relaunch
};
//# sourceMappingURL=@tauri-apps_plugin-process.js.map
