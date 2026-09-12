/**
 * 用户操作协调层。
 *
 * 把工具栏、右键菜单、键盘快捷键共享的「新建 / 重命名 / 删除 /
 * 复制 / 剪切 / 粘贴 / 下载 / 压缩下载 / 分享」操作集中在一处，
 * 避免 `main.js` 膨胀，也避免多个入口重复实现业务编排。
 *
 * 本模块：
 *
 * - 只依赖 `state.js`、`api/files.js`、`toast.js`；
 * - 通过 `setOperationsRefreshCallback` 注入刷新回调，操作成功后
 *   由调用方决定如何重新加载列表；
 * - 交互式问答默认使用 `window.prompt` 与 `window.confirm`，调用
 *   方可通过 `setDialogAdapter` 替换为自定义对话框。
 */

import {
  buildContentDownloadUrl,
  buildZipDownloadUrl,
  copyEntry,
  createFile,
  createFolder,
  deleteEntry,
  renameEntry,
} from "./api/files.js";
import { clearClipboard, getState, setClipboard, setSelection } from "./state.js";
import { showError, showSuccess } from "./toast.js";

/** 操作完成后调用的刷新回调。默认为空，由 `main.js` 注入。 */
let refreshCallback = () => {};

/** 对话框适配器。默认使用浏览器原生 prompt / confirm。 */
let dialogAdapter = {
  prompt: (message, defaultValue = "") =>
    window.prompt(message, defaultValue),
  confirm: (message) => window.confirm(message),
};

/**
 * 设置操作成功后的刷新回调。
 *
 * @param {() => void} callback 刷新函数。
 */
export function setOperationsRefreshCallback(callback) {
  refreshCallback = typeof callback === "function" ? callback : () => {};
}

/**
 * 替换默认的对话框适配器。
 *
 * @param {Object} adapter 适配器对象。
 * @param {(message: string, defaultValue?: string) => string|null} adapter.prompt 输入对话框。
 * @param {(message: string) => boolean} adapter.confirm 确认对话框。
 */
export function setDialogAdapter(adapter) {
  if (!adapter) {
    return;
  }
  dialogAdapter = { ...dialogAdapter, ...adapter };
}

/**
 * 拼接目录路径与条目名。
 *
 * @param {string} directory 目录虚拟路径。
 * @param {string} name 条目名称。
 * @returns {string} 拼接后的虚拟路径。
 */
function joinVirtualPath(directory, name) {
  if (!directory || directory === "/") {
    return `/${name}`;
  }
  return `${directory.replace(/\/+$/, "")}/${name}`;
}

/**
 * 从虚拟路径中提取末段名称。
 *
 * @param {string} path 虚拟路径。
 * @returns {string} 名称。
 */
function getBaseName(path) {
  const segments = path.split("/").filter(Boolean);
  return segments.length > 0 ? segments[segments.length - 1] : path;
}

/**
 * 按路径查询当前已加载的条目。
 *
 * @param {string} path 条目路径。
 * @returns {Object|null} 条目元数据。
 */
function findEntry(path) {
  const state = getState();
  return state.entries.find((entry) => entry.path === path) || null;
}

/* ---------------------------------------------------------------------------
 * 新建
 * ------------------------------------------------------------------------ */

/**
 * 通用新建流程。
 *
 * @param {"folder"|"file"|"symlink"} kind 新建类型。
 */
async function createEntry(kind) {
  const label =
    kind === "folder" ? "文件夹" : kind === "file" ? "文件" : "符号链接";

  if (kind === "symlink") {
    showError("新建符号链接功能暂未开放");
    return;
  }

  const name = dialogAdapter.prompt(`新建${label}名称：`);
  if (name === null) {
    return;
  }
  const trimmedName = name.trim();
  if (!trimmedName) {
    showError("名称不能为空");
    return;
  }
  if (trimmedName.includes("/")) {
    showError("名称不能包含斜杠");
    return;
  }

  const targetPath = joinVirtualPath(getState().currentPath, trimmedName);
  try {
    if (kind === "folder") {
      await createFolder(targetPath);
    } else {
      await createFile(targetPath);
    }
    showSuccess(`已创建${label}：${trimmedName}`);
    refreshCallback();
  } catch (error) {
    showError(error);
  }
}

/**
 * 弹出新建文件夹对话框并创建。
 */
export function promptCreateFolder() {
  return createEntry("folder");
}

/**
 * 弹出新建文件对话框并创建。
 */
export function promptCreateFile() {
  return createEntry("file");
}

/**
 * 弹出新建符号链接对话框（暂未开放）。
 */
export function promptCreateSymlink() {
  return createEntry("symlink");
}

/* ---------------------------------------------------------------------------
 * 重命名
 * ------------------------------------------------------------------------ */

/**
 * 对当前唯一选中项执行重命名。
 */
export async function promptRename() {
  const selected = getState().selectedPaths;
  if (selected.length !== 1) {
    showError("请选择单个条目进行重命名");
    return;
  }
  const targetPath = selected[0];
  const entry = findEntry(targetPath);
  if (!entry) {
    showError("未找到选中的条目");
    return;
  }

  const newName = dialogAdapter.prompt("重命名为：", entry.name);
  if (newName === null) {
    return;
  }
  const trimmedName = newName.trim();
  if (!trimmedName || trimmedName === entry.name) {
    return;
  }
  if (trimmedName.includes("/")) {
    showError("名称不能包含斜杠");
    return;
  }

  try {
    await renameEntry(targetPath, trimmedName);
    showSuccess(`已重命名为：${trimmedName}`);
    refreshCallback();
  } catch (error) {
    showError(error);
  }
}

/* ---------------------------------------------------------------------------
 * 删除
 * ------------------------------------------------------------------------ */

/**
 * 删除选中条目。
 *
 * 多选时逐个删除，遇错不中断，最后汇总成功与失败数量。
 */
export async function promptDelete() {
  const selected = getState().selectedPaths;
  if (selected.length === 0) {
    return;
  }
  const message =
    selected.length === 1
      ? `确定删除「${getBaseName(selected[0])}」吗？`
      : `确定删除选中的 ${selected.length} 个条目吗？`;
  if (!dialogAdapter.confirm(message)) {
    return;
  }

  let succeeded = 0;
  let failed = 0;
  for (const path of selected) {
    const entry = findEntry(path);
    const recursive = entry ? entry.type === "directory" : true;
    try {
      await deleteEntry(path, { recursive });
      succeeded += 1;
    } catch (error) {
      failed += 1;
      console.error("删除失败：", path, error);
    }
  }

  if (failed === 0) {
    showSuccess(`已删除 ${succeeded} 个条目`);
  } else if (succeeded === 0) {
    showError(`删除失败：${failed} 个条目`);
  } else {
    showError(`部分删除成功：成功 ${succeeded} 个，失败 ${failed} 个`);
  }
  setSelection([]);
  refreshCallback();
}

/* ---------------------------------------------------------------------------
 * 复制 / 剪切 / 粘贴
 * ------------------------------------------------------------------------ */

/**
 * 将选中路径写入剪贴板，模式为复制。
 */
export function copySelection() {
  const selected = getState().selectedPaths;
  if (selected.length === 0) {
    return;
  }
  setClipboard("copy", selected);
  showSuccess(`已复制 ${selected.length} 个条目`);
}

/**
 * 将选中路径写入剪贴板，模式为剪切。
 */
export function cutSelection() {
  const selected = getState().selectedPaths;
  if (selected.length === 0) {
    return;
  }
  setClipboard("cut", selected);
  showSuccess(`已剪切 ${selected.length} 个条目`);
}

/**
 * 将剪贴板内容粘贴到当前目录。
 *
 * 剪切模式在复制成功后删除源路径；全部成功时清空剪贴板。
 */
export async function pasteClipboard() {
  const clipboard = getState().clipboard;
  if (!clipboard || clipboard.paths.length === 0) {
    showError("剪贴板为空");
    return;
  }

  const targetDirectory = getState().currentPath;
  let succeeded = 0;
  let failed = 0;

  for (const sourcePath of clipboard.paths) {
    const name = getBaseName(sourcePath);
    const destination = joinVirtualPath(targetDirectory, name);
    if (sourcePath === destination) {
      failed += 1;
      continue;
    }
    try {
      await copyEntry(sourcePath, destination, { overwrite: false });
      if (clipboard.mode === "cut") {
        await deleteEntry(sourcePath, { recursive: true });
      }
      succeeded += 1;
    } catch (error) {
      failed += 1;
      console.error("粘贴失败：", sourcePath, error);
    }
  }

  if (clipboard.mode === "cut" && succeeded > 0) {
    clearClipboard();
  }
  if (failed === 0) {
    showSuccess(`已粘贴 ${succeeded} 个条目`);
  } else if (succeeded === 0) {
    showError(`粘贴失败：${failed} 个条目`);
  } else {
    showError(`部分粘贴成功：成功 ${succeeded} 个，失败 ${failed} 个`);
  }
  refreshCallback();
}

/* ---------------------------------------------------------------------------
 * 下载 / 压缩下载 / 分享
 * ------------------------------------------------------------------------ */

/**
 * 下载当前选中的每个条目。
 *
 * 浏览器对多个并发下载有节流限制；此处按顺序打开新标签。
 */
export function downloadSelection() {
  const selected = getState().selectedPaths;
  if (selected.length === 0) {
    return;
  }
  for (const path of selected) {
    const url = buildContentDownloadUrl(path);
    window.open(url, "_blank");
  }
}

/**
 * 将当前选中条目打包为 ZIP 下载。
 */
export function downloadSelectionZip() {
  const selected = getState().selectedPaths;
  if (selected.length === 0) {
    return;
  }
  const url = buildZipDownloadUrl(selected);
  window.open(url, "_blank");
}

/**
 * 复制当前唯一选中条目的下载链接到剪贴板。
 *
 * 剪贴板不可用时退化为 `window.prompt`。
 */
export async function shareSelection() {
  const selected = getState().selectedPaths;
  if (selected.length !== 1) {
    showError("请选择单个条目进行分享");
    return;
  }
  const relativeUrl = buildContentDownloadUrl(selected[0]);
  const absoluteUrl = new URL(relativeUrl, window.location.origin).href;
  try {
    await navigator.clipboard.writeText(absoluteUrl);
    showSuccess("下载链接已复制到剪贴板");
  } catch (error) {
    dialogAdapter.prompt("请手动复制下载链接：", absoluteUrl);
  }
}
