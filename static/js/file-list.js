/**
 * 文件列表渲染与交互。
 *
 * 负责：
 *
 * - 根据状态快照渲染文件网格；
 * - 处理单击、Ctrl 单击、双击、右键；
 * - 处理空白区域的点击与右键；
 * - 为条目附加 `data-path` / `data-type` 供其他模块查询。
 *
 * 不直接修改状态，而是通过回调交由 `main.js` 协调；不处理框选
 * （由 `selection.js` 负责），不处理上下文菜单的展示
 * （由 `context-menu.js` 负责）。
 */

import { formatSize } from "./format.js";
import { isSelected } from "./state.js";

/** 交互回调，由 `initializeFileList` 注入。 */
let callbacks = {
  onOpen: () => {},
  onEntryContextMenu: () => {},
  onBlankContextMenu: () => {},
  onBlankClick: () => {},
};

/** 是否已初始化。 */
let initialized = false;

/** 图标映射：扩展名到字符图标。 */
const ICON_IMAGE_EXTENSIONS = [
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".webp",
  ".svg",
  ".bmp",
  ".ico",
  ".avif",
];

/** 视频扩展名。 */
const ICON_VIDEO_EXTENSIONS = [
  ".mp4",
  ".webm",
  ".mkv",
  ".mov",
  ".avi",
  ".m4v",
];

/** 音频扩展名。 */
const ICON_AUDIO_EXTENSIONS = [
  ".mp3",
  ".wav",
  ".flac",
  ".ogg",
  ".m4a",
  ".aac",
];

/** 压缩包扩展名。 */
const ICON_ARCHIVE_EXTENSIONS = [
  ".zip",
  ".tar",
  ".gz",
  ".bz2",
  ".7z",
  ".rar",
  ".xz",
];

/** 代码扩展名。 */
const ICON_CODE_EXTENSIONS = [
  ".js",
  ".mjs",
  ".cjs",
  ".ts",
  ".tsx",
  ".jsx",
  ".py",
  ".rb",
  ".go",
  ".rs",
  ".java",
  ".kt",
  ".c",
  ".cpp",
  ".h",
  ".hpp",
  ".cs",
  ".php",
  ".swift",
  ".css",
  ".scss",
  ".html",
  ".htm",
  ".xml",
  ".json",
  ".yaml",
  ".yml",
  ".toml",
  ".sh",
  ".bash",
  ".zsh",
];

/** 文本扩展名。 */
const ICON_TEXT_EXTENSIONS = [
  ".txt",
  ".md",
  ".markdown",
  ".log",
  ".csv",
  ".tsv",
];

/**
 * 从条目名称中提取扩展名。
 *
 * @param {string} name 条目名称。
 * @returns {string} 小写扩展名（含点），无扩展名时返回空字符串。
 */
function extractExtension(name) {
  const index = name.lastIndexOf(".");
  if (index <= 0 || index === name.length - 1) {
    return "";
  }
  return name.slice(index).toLowerCase();
}

/**
 * 根据条目返回用于展示的图标字符。
 *
 * @param {Object} entry 条目元数据。
 * @returns {string} 图标字符。
 */
export function getEntryIcon(entry) {
  if (entry.type === "directory") {
    return "📁";
  }
  if (entry.type === "link") {
    return "🔗";
  }
  if (entry.type !== "file") {
    return "◆";
  }
  const extension = extractExtension(entry.name);
  if (ICON_IMAGE_EXTENSIONS.includes(extension)) {
    return "🖼";
  }
  if (ICON_VIDEO_EXTENSIONS.includes(extension)) {
    return "🎬";
  }
  if (ICON_AUDIO_EXTENSIONS.includes(extension)) {
    return "🎵";
  }
  if (ICON_ARCHIVE_EXTENSIONS.includes(extension)) {
    return "📦";
  }
  if (extension === ".pdf") {
    return "📕";
  }
  if (ICON_CODE_EXTENSIONS.includes(extension)) {
    return "⌨";
  }
  if (ICON_TEXT_EXTENSIONS.includes(extension)) {
    return "📄";
  }
  return "📄";
}

/**
 * 生成条目详情文本。
 *
 * 目录与符号链接展示类型，普通文件展示大小。
 *
 * @param {Object} entry 条目元数据。
 * @returns {string} 详情文本。
 */
function buildEntryDetail(entry) {
  if (entry.type === "directory") {
    return "文件夹";
  }
  if (entry.type === "link") {
    return "符号链接";
  }
  return formatSize(entry.size || 0);
}

/**
 * 为单个条目创建 DOM 元素。
 *
 * @param {Object} entry 条目元数据。
 * @param {boolean} selected 是否处于选中状态。
 * @returns {HTMLElement} 条目元素。
 */
export function createEntryElement(entry, selected) {
  const element = document.createElement("div");
  element.className = "file-item";
  element.dataset.path = entry.path;
  element.dataset.type = entry.type;
  element.dataset.name = entry.name;
  if (entry.type === "directory") {
    element.classList.add("directory");
  } else if (entry.type === "link") {
    element.classList.add("link");
  }
  if (entry.isHidden) {
    element.classList.add("hidden-item");
  }
  if (selected) {
    element.classList.add("selected");
  }
  element.title = entry.path;

  const icon = document.createElement("span");
  icon.className = "file-icon";
  icon.textContent = getEntryIcon(entry);

  const name = document.createElement("div");
  name.className = "file-name";
  name.textContent = entry.name;

  const detail = document.createElement("div");
  detail.className = "file-detail";
  detail.textContent = buildEntryDetail(entry);

  element.append(icon, name, detail);
  return element;
}

/**
 * 由条目列表生成签名，用于快速判断是否需要重建 DOM。
 *
 * 使用条目路径拼接，路径在同一目录下唯一，能稳定反映条目集合
 * 是否发生变化。
 *
 * @param {Object[]} entries 条目列表。
 * @returns {string} 签名。
 */
function buildEntriesSignature(entries) {
  return entries.map((entry) => entry.path).join("\n");
}

/**
 * 只更新已渲染条目的选中状态，不重建 DOM。
 *
 * @param {HTMLElement} grid 网格容器。
 * @param {string[]} selectedPaths 选中路径集合。
 */
function updateSelectionClasses(grid, selectedPaths) {
  const selectedSet = new Set(selectedPaths);
  for (const element of grid.querySelectorAll(".file-item")) {
    element.classList.toggle(
      "selected",
      selectedSet.has(element.dataset.path)
    );
  }
}

/**
 * 渲染文件列表。
 *
 * 若条目集合与上一次渲染相同，仅更新选中态，避免重建 DOM 影响
 * 双击、右键等依赖同一目标元素的交互。目录切换、刷新、搜索等
 * 会变更条目集合，仍走完整重建路径。
 *
 * @param {Object} state 状态快照。
 */
export function renderFileList(state) {
  const grid = document.getElementById("file-grid");
  if (!grid) {
    return;
  }

  if (state.loading) {
    grid.replaceChildren(buildPlaceholder("加载中…"));
    grid.dataset.entriesSignature = "";
    return;
  }

  if (state.error) {
    grid.replaceChildren(
      buildPlaceholder(`加载失败：${state.error.message || "未知错误"}`)
    );
    grid.dataset.entriesSignature = "";
    return;
  }

  if (!state.entries || state.entries.length === 0) {
    grid.replaceChildren(buildPlaceholder("此文件夹为空"));
    grid.dataset.entriesSignature = "";
    return;
  }

  const signature = buildEntriesSignature(state.entries);
  if (grid.dataset.entriesSignature === signature) {
    updateSelectionClasses(grid, state.selectedPaths);
    return;
  }

  grid.dataset.entriesSignature = signature;
  const selectedSet = new Set(state.selectedPaths);
  const fragment = document.createDocumentFragment();
  for (const entry of state.entries) {
    fragment.appendChild(
      createEntryElement(entry, selectedSet.has(entry.path))
    );
  }
  grid.replaceChildren(fragment);
}

/**
 * 构造占位元素。
 *
 * @param {string} text 提示文本。
 * @returns {HTMLElement} 占位元素。
 */
function buildPlaceholder(text) {
  const element = document.createElement("div");
  element.className = "empty-hint";
  element.textContent = text;
  return element;
}

/**
 * 处理条目单击。
 *
 * Ctrl / Meta 单击为切换选中；普通单击为单选；Shift 单击为在
 * 当前选中基础之上追加。
 *
 * @param {MouseEvent} event 单击事件。
 * @param {HTMLElement} entryElement 条目元素。
 */
function handleEntryClick(event, entryElement) {
  const path = entryElement.dataset.path;
  if (!path) {
    return;
  }
  callbacks.onEntryClick(event, path, entryElement);
}

/**
 * 处理容器内的 click 事件。
 *
 * @param {MouseEvent} event 事件对象。
 */
function handleContainerClick(event) {
  const entryElement = event.target.closest(".file-item");
  if (entryElement) {
    handleEntryClick(event, entryElement);
    return;
  }
  callbacks.onBlankClick(event);
}

/**
 * 处理容器内的 dblclick 事件。
 *
 * @param {MouseEvent} event 事件对象。
 */
function handleContainerDoubleClick(event) {
  const entryElement = event.target.closest(".file-item");
  if (!entryElement) {
    return;
  }
  const path = entryElement.dataset.path;
  if (!path) {
    return;
  }
  callbacks.onOpen(path);
}

/**
 * 处理容器内的 contextmenu 事件。
 *
 * @param {MouseEvent} event 事件对象。
 */
function handleContainerContextMenu(event) {
  const entryElement = event.target.closest(".file-item");
  if (entryElement) {
    const path = entryElement.dataset.path;
    if (!path) {
      return;
    }
    if (!isSelected(path)) {
      callbacks.onEntrySelectForContextMenu(path);
    }
    event.preventDefault();
    callbacks.onEntryContextMenu(event, path);
    return;
  }
  event.preventDefault();
  callbacks.onBlankContextMenu(event);
}

/**
 * 初始化文件列表。
 *
 * 应在 `main.js` 中调用一次，并注入交互回调。
 *
 * @param {Object} [options] 回调集合。
 * @param {(event: MouseEvent, path: string, element: HTMLElement) => void} [options.onEntryClick] 条目单击。
 * @param {(path: string) => void} [options.onOpen] 打开条目（双击）。
 * @param {(path: string) => void} [options.onEntrySelectForContextMenu] 右键时若未选中则先选中。
 * @param {(event: MouseEvent, path: string) => void} [options.onEntryContextMenu] 条目右键菜单。
 * @param {(event: MouseEvent) => void} [options.onBlankContextMenu] 空白处右键菜单。
 * @param {(event: MouseEvent) => void} [options.onBlankClick] 空白处单击。
 */
export function initializeFileList(options = {}) {
  if (initialized) {
    return;
  }
  initialized = true;
  callbacks = { ...callbacks, ...options };

  const container = document.getElementById("file-list-container");
  if (!container) {
    console.error("未找到 #file-list-container，文件列表无法初始化");
    return;
  }

  container.addEventListener("click", handleContainerClick);
  container.addEventListener("dblclick", handleContainerDoubleClick);
  container.addEventListener("contextmenu", handleContainerContextMenu);
}

/**
 * 通过路径查询当前渲染的条目元素。
 *
 * @param {string} path 条目路径。
 * @returns {HTMLElement|null} 条目元素。
 */
export function findEntryElement(path) {
  const grid = document.getElementById("file-grid");
  if (!grid) {
    return null;
  }
  const escaped = CSS.escape(path);
  return grid.querySelector(`.file-item[data-path="${escaped}"]`);
}

/**
 * 返回所有当前渲染的条目元素。
 *
 * @returns {HTMLElement[]} 条目元素数组。
 */
export function listEntryElements() {
  const grid = document.getElementById("file-grid");
  if (!grid) {
    return [];
  }
  return Array.from(grid.querySelectorAll(".file-item"));
}
