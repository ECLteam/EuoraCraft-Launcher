import {
  invoke
} from "./chunk-DKSFAMV2.js";
import "./chunk-G3PMV62Z.js";

// frontend_QML/node_modules/.pnpm/@tauri-apps+plugin-opener@2.5.4/node_modules/@tauri-apps/plugin-opener/dist-js/index.js
async function openUrl(url, openWith) {
  await invoke("plugin:opener|open_url", {
    url,
    with: openWith
  });
}
async function openPath(path, openWith) {
  await invoke("plugin:opener|open_path", {
    path,
    with: openWith
  });
}
async function revealItemInDir(path) {
  const paths = typeof path === "string" ? [path] : path;
  return invoke("plugin:opener|reveal_item_in_dir", { paths });
}
export {
  openPath,
  openUrl,
  revealItemInDir
};
//# sourceMappingURL=@tauri-apps_plugin-opener.js.map
