/**
 * 属性页视图：展示条目元数据并支持修改部分属性。
 */

import { getMetadata, patchMetadata } from "./api.js";
import { formatFileSize, formatTimestamp, parseQueryParams } from "./utils.js";

/** DOM 元素引用 */
const elements = {};

/** 当前条目路径 */
let currentPath = "/";

/**
 * 初始化属性页。
 */
export async function initMetadata() {
  cacheElements();
  bindEvents();
  const params = parseQueryParams();
  currentPath = params.get("path") || "/";
  elements["metadata-path-label"].textContent = currentPath;
  await loadMetadata();
}

/**
 * 缓存属性页 DOM 元素。
 */
function cacheElements() {
  const ids = [
    "metadata-back-button", "metadata-form", "metadata-path-label",
    "metadata-name", "metadata-path", "metadata-type", "metadata-size",
    "metadata-mime", "metadata-created", "metadata-modified",
    "metadata-accessed", "metadata-permissions", "metadata-hidden",
    "metadata-cancel-button", "metadata-error",
  ];
  for (const id of ids) {
    elements[id] = document.getElementById(id);
  }
}

/**
 * 绑定属性页事件。
 */
function bindEvents() {
  elements["metadata-back-button"].addEventListener("click", goBack);
  elements["metadata-cancel-button"].addEventListener("click", goBack);
  elements["metadata-form"].addEventListener("submit", onSubmit);
}

/**
 * 加载并填充元数据表单。
 */
async function loadMetadata() {
  try {
    const result = await getMetadata(currentPath);
    const entry = result.data;
    elements["metadata-name"].value = entry.name === "/" ? "/" : entry.name;
    elements["metadata-path"].value = entry.path;
    elements["metadata-type"].textContent = entry.type;
    elements["metadata-size"].textContent = formatFileSize(entry.size);
    elements["metadata-mime"].textContent = entry.mimeType || "-";
    elements["metadata-created"].textContent = formatTimestamp(entry.createdAt);
    elements["metadata-modified"].value = String(Math.round(entry.modifiedAt));
    elements["metadata-accessed"].value = String(Math.round(entry.accessedAt));
    elements["metadata-permissions"].value = entry.permissions;
    elements["metadata-hidden"].checked = entry.isHidden;
    hideError();
  } catch (error) {
    showError(`加载失败：${error.message}`);
  }
}

/**
 * 提交修改。
 * @param {Event} event - 提交事件
 */
async function onSubmit(event) {
  event.preventDefault();
  const fields = buildChangedFields();
  if (Object.keys(fields).length === 0) {
    showError("没有需要保存的修改");
    return;
  }
  try {
    await patchMetadata(currentPath, fields);
    showError("保存成功");
    await loadMetadata();
  } catch (error) {
    showError(`保存失败：${error.message}`);
  }
}

/**
 * 收集表单中发生变化（或显式提供）的字段。
 * @returns {object} 待修改字段
 */
function buildChangedFields() {
  const fields = {};
  const nameValue = elements["metadata-name"].value.trim();
  const pathValue = elements["metadata-path"].value.trim();
  const modifiedValue = elements["metadata-modified"].value.trim();
  const accessedValue = elements["metadata-accessed"].value.trim();
  const permissionsValue = elements["metadata-permissions"].value.trim();

  if (nameValue && nameValue !== "/") {
    fields.name = nameValue;
  }
  if (pathValue && pathValue !== currentPath) {
    fields.path = pathValue;
  }
  if (modifiedValue) {
    fields.modifiedAt = parseNumber(modifiedValue);
  }
  if (accessedValue) {
    fields.accessedAt = parseNumber(accessedValue);
  }
  if (permissionsValue) {
    fields.permissions = permissionsValue;
  }
  fields.isHidden = elements["metadata-hidden"].checked;
  return fields;
}

/**
 * 解析输入为数字，非法时返回 undefined。
 * @param {string} text - 输入文本
 * @returns {number|undefined} 解析结果
 */
function parseNumber(text) {
  const value = Number(text);
  return Number.isFinite(value) ? value : undefined;
}

/**
 * 显示错误/提示信息。
 * @param {string} message - 提示文案
 */
function showError(message) {
  const errorElement = elements["metadata-error"];
  errorElement.textContent = message;
  errorElement.classList.remove("hidden");
}

/**
 * 隐藏错误/提示信息。
 */
function hideError() {
  elements["metadata-error"].classList.add("hidden");
}

/**
 * 返回文件浏览器。
 */
function goBack() {
  window.location.href = `/?path=${encodeURIComponent(currentPath)}`;
}
