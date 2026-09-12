/**
 * 文件预览模态框。
 *
 * 双击条目时由 `main.js` 调用 `openPreview`：
 *
 * - 目录：交由调用方通过路由导航；
 * - 图片：在模态框中展示；
 * - 文本：在读取大小允许的前提下展示；
 * - 其他：触发浏览器下载。
 *
 * 读取内容通过 `buildContentDownloadUrl` 直接访问后端内容接口，
 * 避免将大文件读入 JS 内存。
 */

import { buildContentDownloadUrl } from "./api/files.js";
import {
  IMAGE_MIME_PREFIX,
  TEXT_MIME_PREFIXES,
  TEXT_PREVIEW_MAX_BYTES,
} from "./config.js";
import { formatSize, formatTimestamp } from "./format.js";
import { showError } from "./toast.js";

/** 是否已初始化。 */
let initialized = false;

/**
 * 判断 MIME 是否为图片类型。
 *
 * @param {string} mimeType MIME 类型。
 * @returns {boolean} 是否为图片。
 */
export function isImageMime(mimeType) {
  return (
    typeof mimeType === "string" &&
    mimeType.startsWith(IMAGE_MIME_PREFIX)
  );
}

/**
 * 判断 MIME 是否为可预览的文本类型。
 *
 * @param {string} mimeType MIME 类型。
 * @returns {boolean} 是否为文本。
 */
export function isTextMime(mimeType) {
  if (typeof mimeType !== "string") {
    return false;
  }
  return TEXT_MIME_PREFIXES.some((prefix) => mimeType.startsWith(prefix));
}

/**
 * 触发浏览器下载。
 *
 * 通过创建隐藏的 `<a download>` 元素触发，避免使用 `window.open`
 * 导致的空白标签页。
 *
 * @param {string} path 文件的沙箱虚拟路径。
 */
export function triggerDownload(path) {
  const url = buildContentDownloadUrl(path);
  const link = document.createElement("a");
  link.href = url;
  link.download = "";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

/**
 * 获取预览模态框的元素集合。
 *
 * @returns {{modal: HTMLElement, title: HTMLElement, body: HTMLElement}|null}
 *   元素集合；任一缺失时返回 `null`。
 */
function getModalElements() {
  const modal = document.getElementById("preview-modal");
  const title = document.getElementById("preview-title");
  const body = document.getElementById("preview-body");
  if (!modal || !title || !body) {
    return null;
  }
  return { modal, title, body };
}

/**
 * 打开预览模态框。
 *
 * @param {string} title 标题。
 * @param {HTMLElement} content 内容元素。
 */
function openModal(title, content) {
  const elements = getModalElements();
  if (!elements) {
    return;
  }
  elements.title.textContent = title;
  elements.body.replaceChildren(content);
  elements.modal.classList.remove("hidden");
}

/**
 * 关闭预览模态框。
 */
export function closePreview() {
  const elements = getModalElements();
  if (!elements) {
    return;
  }
  elements.modal.classList.add("hidden");
  elements.body.replaceChildren();
}

/**
 * 构造加载中占位。
 *
 * @returns {HTMLElement} 占位元素。
 */
function buildLoadingIndicator() {
  const element = document.createElement("div");
  element.style.color = "var(--fg-muted)";
  element.style.textAlign = "center";
  element.textContent = "加载中…";
  return element;
}

/**
 * 展示文本预览。
 *
 * @param {Object} entry 条目元数据。
 * @returns {Promise<void>} 无返回值。
 */
async function showTextPreview(entry) {
  openModal(entry.name, buildLoadingIndicator());
  const url = buildContentDownloadUrl(entry.path);
  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const text = await response.text();
    const pre = document.createElement("pre");
    pre.textContent = text;
    const elements = getModalElements();
    if (elements) {
      elements.body.replaceChildren(pre);
    }
  } catch (error) {
    closePreview();
    showError(error);
  }
}

/**
 * 展示图片预览。
 *
 * @param {Object} entry 条目元数据。
 */
function showImagePreview(entry) {
  const url = buildContentDownloadUrl(entry.path);
  const container = document.createElement("div");
  container.style.textAlign = "center";

  const image = document.createElement("img");
  image.src = url;
  image.alt = entry.name;
  image.addEventListener("error", () => {
    closePreview();
    showError("图片加载失败");
  });

  const caption = document.createElement("div");
  caption.style.marginTop = "8px";
  caption.style.color = "var(--fg-muted)";
  caption.style.fontSize = "12px";
  caption.textContent = `${formatSize(entry.size)} · ${formatTimestamp(
    entry.modifiedAt
  )}`;

  container.append(image, caption);
  openModal(entry.name, container);
}

/**
 * 打开条目预览。
 *
 * 若条目为目录或不可预览的类型，调用方可通过返回值判断是否已处理。
 *
 * @param {Object} entry 条目元数据。
 * @returns {boolean} 是否已处理（`false` 表示调用方需自行处理，例如导航）。
 */
export function openPreview(entry) {
  if (!entry || entry.type === "directory") {
    return false;
  }

  if (entry.type !== "file") {
    triggerDownload(entry.path);
    return true;
  }

  const mimeType = entry.mimeType || "";
  if (isImageMime(mimeType)) {
    showImagePreview(entry);
    return true;
  }

  if (isTextMime(mimeType) && entry.size <= TEXT_PREVIEW_MAX_BYTES) {
    showTextPreview(entry);
    return true;
  }

  triggerDownload(entry.path);
  return true;
}

/**
 * 初始化预览模块。
 *
 * 绑定关闭按钮、遮罩点击关闭与 Escape 键关闭。应在 `main.js` 中
 * 调用一次。
 */
export function initializePreview() {
  if (initialized) {
    return;
  }
  initialized = true;

  document
    .getElementById("preview-close-button")
    ?.addEventListener("click", closePreview);

  document
    .getElementById("preview-modal")
    ?.addEventListener("click", (event) => {
      if (event.target.id === "preview-modal") {
        closePreview();
      }
    });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closePreview();
    }
  });
}
