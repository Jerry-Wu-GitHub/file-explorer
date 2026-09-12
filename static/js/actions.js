/**
 * 文件操作：剪贴板、新建、删除、重命名、分享、属性、粘贴。
 */

import {
  contentUrl,
  copyPath,
  createFile,
  createFolder,
  deletePath,
  patchMetadata,
} from "./api.js";
import { downloadSelection } from "./preview.js";
import { refreshToolbar, reloadDirectory, selectedPaths, state } from "./state.js";

/** 剪贴板操作类型 */
const ACTION_COPY = "copy";
const ACTION_CUT = "cut";

/**
 * 执行一个命名操作。
 * @param {string} action - 操作名称
 */
export async function executeAction(action) {
  const paths = selectedPaths();

  switch (action) {
    case "cut":
      state.clipboard = { paths, action: ACTION_CUT };
      refreshToolbar();
      break;
    case "copy":
      state.clipboard = { paths, action: ACTION_COPY };
      refreshToolbar();
      break;
    case "paste":
      await pasteClipboard();
      break;
    case "download":
      downloadSelection(paths);
      break;
    case "downloadZip":
      downloadSelection(paths);
      break;
    case "share":
      await shareSingle(paths[0]);
      break;
    case "delete":
      await deleteSelection(paths);
      break;
    case "rename":
      await renameSingle(paths[0]);
      break;
    case "properties":
      openPropertiesWindows(paths);
      break;
    case "folderProperties":
      window.open(`/metadata?path=${encodeURIComponent(state.currentPath)}`, "_blank");
      break;
    case "newFolder":
      await createNewFolder();
      break;
    case "newFile":
      await createNewFile();
      break;
    case "newLink":
      await createNewLink();
      break;
    case "refresh":
      refreshCurrentDirectory();
      break;
    default:
      break;
  }
}

/**
 * 刷新当前目录。
 */
function refreshCurrentDirectory() {
  state.page = 1;
  state.isSearching = false;
  const searchInput = document.getElementById("search-input");
  searchInput.value = "";
  reloadDirectory();
}

/**
 * 粘贴剪贴板内容到当前目录。
 */
async function pasteClipboard() {
  if (state.clipboard === null || state.clipboard.paths.length === 0) {
    return;
  }
  const { paths, action } = state.clipboard;
  try {
    for (const sourcePath of paths) {
      const destination = joinDestinationPath(state.currentPath, sourcePath);
      if (action === ACTION_CUT) {
        await patchMetadata(sourcePath, { path: destination });
      } else {
        await copyPath(sourcePath, destination, false);
      }
    }
    state.clipboard = null;
    refreshToolbar();
    refreshCurrentDirectory();
  } catch (error) {
    alert(`粘贴失败：${error.message}`);
  }
}

/**
 * 计算粘贴目标路径。
 * @param {string} currentPath - 当前目录
 * @param {string} sourcePath - 源路径
 * @returns {string} 目标路径
 */
function joinDestinationPath(currentPath, sourcePath) {
  const name = sourcePath.split("/").filter(Boolean).pop() || "";
  return currentPath === "/" ? `/${name}` : `${currentPath}/${name}`;
}

/**
 * 复制单个条目的下载链接到剪贴板。
 * @param {string} path - 条目路径
 */
async function shareSingle(path) {
  if (!path) {
    return;
  }
  const downloadLink = contentUrl(path);
  try {
    await navigator.clipboard.writeText(downloadLink);
    alert("下载链接已复制到剪贴板");
  } catch (error) {
    window.prompt("复制失败，请手动复制下载链接：", downloadLink);
  }
}

/**
 * 删除选中条目。
 * @param {string[]} paths - 路径列表
 */
async function deleteSelection(paths) {
  if (paths.length === 0) {
    return;
  }
  const hint = paths.length === 1 ? paths[0] : `${paths.length} 个条目`;
  const confirmed = window.confirm(`确定删除 ${hint}？\n文件夹将连同内容一并删除。`);
  if (!confirmed) {
    return;
  }
  try {
    for (const path of paths) {
      const item = state.selection.get(path);
      const isLink = item && item.dataset && item.dataset.type === "link";
      await deletePath(path, true, !isLink);
    }
    refreshCurrentDirectory();
  } catch (error) {
    alert(`删除失败：${error.message}`);
  }
}

/**
 * 重命名单个条目。
 * @param {string} path - 条目路径
 */
async function renameSingle(path) {
  if (!path) {
    return;
  }
  const name = path.split("/").filter(Boolean).pop() || "";
  const newName = window.prompt("输入新名称：", name);
  if (newName === null || newName.trim() === "") {
    return;
  }
  try {
    await patchMetadata(path, { name: newName.trim() });
    refreshCurrentDirectory();
  } catch (error) {
    alert(`重命名失败：${error.message}`);
  }
}

/**
 * 为每个选中条目打开属性窗口。
 * @param {string[]} paths - 路径列表
 */
function openPropertiesWindows(paths) {
  for (const path of paths) {
    window.open(`/metadata?path=${encodeURIComponent(path)}`, "_blank");
  }
}

/**
 * 新建文件夹。
 */
async function createNewFolder() {
  const name = window.prompt("输入文件夹名称：", "新文件夹");
  if (name === null || name.trim() === "") {
    return;
  }
  try {
    await createFolder(joinCurrentPath(state.currentPath, name.trim()));
    refreshCurrentDirectory();
  } catch (error) {
    alert(`新建文件夹失败：${error.message}`);
  }
}

/**
 * 新建文件。
 */
async function createNewFile() {
  const name = window.prompt("输入文件名：", "新文件.txt");
  if (name === null || name.trim() === "") {
    return;
  }
  try {
    await createFile(joinCurrentPath(state.currentPath, name.trim()), null);
    refreshCurrentDirectory();
  } catch (error) {
    alert(`新建文件失败：${error.message}`);
  }
}

/**
 * 新建符号链接。
 */
async function createNewLink() {
  const name = window.prompt("输入链接名称：", "新链接");
  if (name === null || name.trim() === "") {
    return;
  }
  const linkTarget = window.prompt("输入链接目标路径：", "/");
  if (linkTarget === null || linkTarget.trim() === "") {
    return;
  }
  try {
    await createFile(joinCurrentPath(state.currentPath, name.trim()), linkTarget.trim());
    refreshCurrentDirectory();
  } catch (error) {
    alert(`新建符号链接失败：${error.message}`);
  }
}

/**
 * 拼接当前目录下的新路径。
 * @param {string} currentPath - 当前目录
 * @param {string} name - 条目名称
 * @returns {string} 完整虚拟路径
 */
function joinCurrentPath(currentPath, name) {
  return currentPath === "/" ? `/${name}` : `${currentPath}/${name}`;
}
