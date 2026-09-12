/**
 * 文件预览与下载：文本/图片预览模态框，其他类型触发下载。
 */

import { getMetadata, contentUrl, zipUrl } from "./api.js";
import { isImageType, isTextPreviewable } from "./utils.js";

/** 预览模态框 DOM 引用 */
let modalElement = null;
let titleElement = null;
let bodyElement = null;

/**
 * 缓存预览相关 DOM 元素。
 */
function cacheElements() {
  modalElement = document.getElementById("preview-modal");
  titleElement = document.getElementById("preview-title");
  bodyElement = document.getElementById("preview-body");
}

/**
 * 预览或下载指定路径的条目。
 * @param {string} path - 虚拟路径
 */
export async function previewEntry(path) {
  cacheElements();
  try {
    const result = await getMetadata(path);
    const entry = result.data;
    const mimeType = entry.mimeType || "";

    if (isTextPreviewable(mimeType)) {
      await showTextPreview(path, entry.name, mimeType);
      return;
    }
    if (isImageType(mimeType)) {
      showImagePreview(path, entry.name);
      return;
    }
    triggerDownload(path);
  } catch (error) {
    alert(`预览失败：${error.message}`);
  }
}

/**
 * 显示文本文件内容。
 * @param {string} path - 虚拟路径
 * @param {string} name - 文件名
 * @param {string} mimeType - MIME 类型
 */
async function showTextPreview(path, name, mimeType) {
  const response = await fetch(contentUrl(path));
  if (!response.ok) {
    throw new Error(`加载失败: ${response.status}`);
  }
  const text = await response.text();
  const previewText = text.length > 200000 ? text.slice(0, 200000) + "\n…（内容过长，已截断）" : text;
  openModal(name, mimeType);
  const pre = document.createElement("pre");
  pre.textContent = previewText;
  bodyElement.appendChild(pre);
}

/**
 * 显示图片预览。
 * @param {string} path - 虚拟路径
 * @param {string} name - 文件名
 */
function showImagePreview(path, name) {
  openModal(name, "image");
  const image = document.createElement("img");
  image.src = contentUrl(path);
  image.alt = name;
  bodyElement.appendChild(image);
}

/**
 * 打开预览模态框。
 * @param {string} name - 文件名
 * @param {string} detail - 附加说明
 */
function openModal(name, detail) {
  titleElement.textContent = `${name}  (${detail})`;
  bodyElement.innerHTML = "";
  modalElement.classList.remove("hidden");
}

/**
 * 触发单个文件下载。
 * @param {string} path - 虚拟路径
 */
export function triggerDownload(path) {
  window.location.href = contentUrl(path);
}

/**
 * 触发多个条目压缩包下载。
 * @param {string[]} paths - 路径列表
 */
export function triggerZipDownload(paths) {
  window.location.href = zipUrl(paths);
}

/**
 * 下载选中的条目：单个直接下载，多个打包。
 * @param {string[]} paths - 路径列表
 */
export function downloadSelection(paths) {
  if (paths.length === 0) {
    return;
  }
  if (paths.length === 1) {
    triggerDownload(paths[0]);
    return;
  }
  triggerZipDownload(paths);
}
