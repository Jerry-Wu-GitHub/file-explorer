/**
 * 前端入口模块。
 *
 * 负责：
 *
 * - 初始化主题、预览、上传等一次性组件；
 * - 注册所有 UI 模块并连接它们的回调；
 * - 订阅状态变化，统一触发各区域渲染；
 * - 订阅路由变化，触发目录或搜索结果加载。
 *
 * 该模块不包含业务逻辑；业务操作统一委托给 `operations.js`、
 * `explorer.js`、`uploader.js` 等专业模块。
 */

import { getState, subscribe, setSelection, toggleSelection, addToSelection, clearSelection, getSelectedEntries, hasClipboard } from "./state.js";
import { initializeRouter, navigateTo, subscribeToNavigation } from "./router.js";
import { initializeTheme } from "./theme.js";
import { showError, showInfo } from "./toast.js";
import { formatSize } from "./format.js";

import { initializePathBar, renderPathBar, clearSearchInput } from "./path-bar.js";
import { initializeToolbar, renderToolbar } from "./toolbar.js";
import { initializeFileList, renderFileList } from "./file-list.js";
import { initializeContextMenu, showBlankContextMenu, showEntryContextMenu } from "./context-menu.js";
import { initializeSelection } from "./selection.js";
import { initializeKeyboard } from "./keyboard.js";
import { initializePreview, openPreview } from "./preview.js";
import { initializeUploader, openFilePicker, openFolderPicker } from "./uploader.js";

import {
  clearSearch,
  getTotalPages,
  goToNextPage,
  goToPreviousPage,
  loadPath,
  reloadCurrentContext,
  runSearch,
} from "./explorer.js";

import {
  copySelection,
  cutSelection,
  downloadSelection,
  downloadSelectionZip,
  pasteClipboard,
  promptCreateFile,
  promptCreateFolder,
  promptCreateSymlink,
  promptDelete,
  promptRename,
  setOperationsRefreshCallback,
  shareSelection,
} from "./operations.js";

/**
 * 计算状态栏要显示的总条目描述。
 *
 * @param {Object} state 状态快照。
 * @returns {string} 描述字符串。
 */
function buildStatusText(state) {
  const parts = [`${state.pagination.total} 项`];
  if (state.selectedPaths.length > 0) {
    parts.push(`已选中 ${state.selectedPaths.length} 项`);
  }
  if (state.entries.length > 0 && state.pagination.total > state.entries.length) {
    const visibleBytes = state.entries.reduce(
      (total, entry) => total + (entry.size || 0),
      0
    );
    parts.push(`本页 ${formatSize(visibleBytes)}`);
  }
  return parts.join(" · ");
}

/**
 * 渲染状态栏。
 *
 * @param {Object} state 状态快照。
 */
function renderStatusBar(state) {
  const statusText = document.getElementById("status-info");
  if (statusText) {
    statusText.textContent = buildStatusText(state);
  }

  const pageInfo = document.getElementById("page-info");
  const totalPages = getTotalPages();
  if (pageInfo) {
    pageInfo.textContent = `${state.pagination.page} / ${totalPages}`;
  }

  const prevButton = document.getElementById("prev-page-button");
  if (prevButton) {
    prevButton.disabled = state.pagination.page <= 1;
  }
  const nextButton = document.getElementById("next-page-button");
  if (nextButton) {
    nextButton.disabled = state.pagination.page >= totalPages;
  }
}

/**
 * 在浏览器新标签页中打开属性页面。
 *
 * @param {string} path 条目的沙箱虚拟路径。
 */
function openMetadataWindow(path) {
  const parameters = new URLSearchParams();
  parameters.set("path", path);
  window.open(`/metadata?${parameters.toString()}`, "_blank");
}

/**
 * 处理文件列表中的单击。
 *
 * 修饰键语义：
 *
 * - 无修饰键：单选；
 * - Ctrl / Meta：切换选中；
 * - Shift：追加选中。
 *
 * @param {MouseEvent} event 单击事件。
 * @param {string} path 条目路径。
 */
function handleEntryClick(event, path) {
  if (event.ctrlKey || event.metaKey) {
    toggleSelection(path);
    return;
  }
  if (event.shiftKey) {
    addToSelection([path]);
    return;
  }
  setSelection([path]);
}

/**
 * 处理双击条目。
 *
 * 目录导航；文件与链接触发预览或下载。
 *
 * @param {string} path 条目路径。
 */
function handleEntryOpen(path) {
  const state = getState();
  const entry = state.entries.find((item) => item.path === path);
  if (!entry) {
    navigateTo(path);
    return;
  }
  if (entry.type === "directory") {
    navigateTo(path);
    return;
  }
  openPreview(entry);
}

/**
 * 处理上下文菜单的操作派发。
 *
 * @param {string} action 操作标识。
 * @param {Object} data 附加数据（例如排序字段）。
 * @param {Object} context 打开菜单时的上下文。
 */
function handleContextMenuAction(action, data, context) {
  switch (action) {
    case "refresh":
      reloadCurrentContext();
      break;
    case "sort":
      setSortAndReload(data.sortField, data.sortDirection);
      break;
    case "paste":
      pasteClipboard();
      break;
    case "new-folder":
      promptCreateFolder();
      break;
    case "new-file":
      promptCreateFile();
      break;
    case "new-symlink":
      promptCreateSymlink();
      break;
    case "properties-blank":
      openMetadataWindow(getState().currentPath);
      break;
    case "properties-entry":
      if (context && Array.isArray(context.entries)) {
        for (const entry of context.entries) {
          openMetadataWindow(entry.path);
        }
      }
      break;
    case "cut":
      cutSelection();
      break;
    case "copy":
      copySelection();
      break;
    case "download":
      downloadSelection();
      break;
    case "download-zip":
      downloadSelectionZip();
      break;
    case "rename":
      promptRename();
      break;
    case "delete":
      promptDelete();
      break;
    default:
      console.warn("未识别的菜单操作：", action);
  }
}

/**
 * 更新排序并重新加载。
 *
 * @param {string} field 排序字段。
 * @param {string} direction 排序方向。
 */
async function setSortAndReload(field, direction) {
  const { setSort } = await import("./state.js");
  setSort(field, direction);
  await reloadCurrentContext();
}

/**
 * 注册所有 UI 模块。
 */
function initializeUserInterface() {
  initializePreview();
  initializeSelection();

  initializeFileList({
    onEntryClick(event, path) {
      handleEntryClick(event, path);
    },
    onOpen(path) {
      handleEntryOpen(path);
    },
    onEntrySelectForContextMenu(path) {
      setSelection([path]);
    },
    onEntryContextMenu(event) {
      showEntryContextMenu(event, getSelectedEntries());
    },
    onBlankContextMenu(event) {
      showBlankContextMenu(event);
    },
    onBlankClick() {
      clearSelection();
    },
  });

  initializeContextMenu({
    hasClipboard,
    getSelectedEntries,
    onAction: handleContextMenuAction,
  });

  initializeKeyboard({
    onNewFolder: promptCreateFolder,
    onCopy: copySelection,
    onCut: cutSelection,
    onPaste: pasteClipboard,
  });

  initializeToolbar({
    onNewFolder: promptCreateFolder,
    onNewFile: promptCreateFile,
    onNewSymlink: promptCreateSymlink,
    onCut: cutSelection,
    onCopy: copySelection,
    onPaste: pasteClipboard,
    onDownload: downloadSelection,
    onDownloadZip: downloadSelectionZip,
    onUploadFiles: openFilePicker,
    onUploadFolder: openFolderPicker,
    onRename: promptRename,
    onShare: shareSelection,
    onDelete: promptDelete,
    onSort(field, direction) {
      setSortAndReload(field, direction);
    },
    onShowHiddenChange() {
      reloadCurrentContext();
    },
  });

  initializePathBar({
    onRefresh: reloadCurrentContext,
    onSearch: runSearch,
    onSearchClear: clearSearch,
  });

  initializeUploader({
    onRefresh: reloadCurrentContext,
  });
}

/**
 * 注册分页按钮。
 */
function initializePagination() {
  document
    .getElementById("prev-page-button")
    ?.addEventListener("click", () => {
      goToPreviousPage();
    });
  document
    .getElementById("next-page-button")
    ?.addEventListener("click", () => {
      goToNextPage();
    });
}

/**
 * 注册状态订阅：状态变化时统一渲染各区域。
 */
function initializeStateSubscriptions() {
  subscribe((state) => {
    renderFileList(state);
    renderPathBar(state);
    renderToolbar(state);
    renderStatusBar(state);
  });
}

/**
 * 注册路由订阅：路径变化时加载目录。
 */
function initializeNavigationSubscriptions() {
  subscribeToNavigation(async (path) => {
    clearSearchInput();
    try {
      await loadPath(path);
    } catch (error) {
      console.error("加载路径失败：", path, error);
      showError(error);
    }
  });
}

/**
 * 应用启动入口。
 */
async function bootstrap() {
  initializeTheme();
  setOperationsRefreshCallback(reloadCurrentContext);
  initializeUserInterface();
  initializePagination();
  initializeStateSubscriptions();
  initializeNavigationSubscriptions();
  initializeRouter();
}

window.addEventListener("DOMContentLoaded", () => {
  bootstrap().catch((error) => {
    console.error("应用初始化失败：", error);
    showError(error);
  });
});
