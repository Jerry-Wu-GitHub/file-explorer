/**
 * 属性页面入口。
 *
 * 从 URL 的 `?path=` 参数解析目标路径，拉取元数据，渲染表单，
 * 并提交 PATCH 请求修改可编辑字段。
 *
 * 该页面独立于浏览页面，不依赖 `state.js` / `router.js`。
 */

import { getMetadata, updateMetadata } from "./api/files.js";
import { formatSize, formatTimestamp } from "./format.js";
import { initializeTheme } from "./theme.js";
import { showError, showSuccess } from "./toast.js";

/** 从 URL 解析出的目标路径。 */
let targetPath = "/";

/** 最近一次加载的元数据，用于重置与比较。 */
let originalMetadata = null;

/**
 * 从当前 URL 中解析 `path` 参数。
 *
 * @returns {string} 沙箱虚拟路径，缺省为 `/`。
 */
function parseTargetPath() {
  const url = new URL(window.location.href);
  const value = url.searchParams.get("path");
  if (value === null || value === "") {
    return "/";
  }
  return value;
}

/**
 * 按 ID 获取表单元素。
 *
 * @param {string} id 元素 ID。
 * @returns {HTMLElement|null} 元素。
 */
function getElement(id) {
  return document.getElementById(id);
}

/**
 * 更新页面标题与路径标签。
 *
 * @param {Object} metadata 元数据。
 */
function renderHeader(metadata) {
  const pathLabel = getElement("metadata-path-label");
  if (pathLabel) {
    pathLabel.textContent = metadata.path;
  }
  document.title = `${metadata.name} — 属性`;
}

/**
 * 将元数据填充到表单。
 *
 * @param {Object} metadata 元数据。
 */
function fillForm(metadata) {
  const typeLabel =
    metadata.type === "directory"
      ? "文件夹"
      : metadata.type === "link"
      ? "符号链接"
      : metadata.type === "file"
      ? "文件"
      : "其它";

  getElement("metadata-name").value = metadata.name;
  getElement("metadata-path").value = metadata.path;
  getElement("metadata-type").textContent = typeLabel;
  getElement("metadata-size").textContent =
    metadata.type === "file" ? formatSize(metadata.size) : "—";
  getElement("metadata-mime").textContent = metadata.mimeType || "—";
  getElement("metadata-created").textContent = formatTimestamp(
    metadata.createdAt
  );
  getElement("metadata-modified").value = String(metadata.modifiedAt ?? "");
  getElement("metadata-accessed").value = String(metadata.accessedAt ?? "");
  getElement("metadata-permissions").value = metadata.permissions || "";
  getElement("metadata-hidden").checked = Boolean(metadata.isHidden);
}

/**
 * 清空并隐藏错误提示。
 */
function clearError() {
  const errorBox = getElement("metadata-error");
  if (errorBox) {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
  }
}

/**
 * 展示错误提示。
 *
 * @param {*} error 错误对象或字符串。
 */
function showFormError(error) {
  const errorBox = getElement("metadata-error");
  if (!errorBox) {
    return;
  }
  errorBox.classList.remove("hidden");
  if (typeof error === "string") {
    errorBox.textContent = error;
  } else if (error && typeof error.message === "string") {
    errorBox.textContent = error.message;
  } else {
    errorBox.textContent = "未知错误";
  }
}

/**
 * 设置底部状态文本。
 *
 * @param {string} text 文本。
 */
function setStatusText(text) {
  const statusBox = getElement("metadata-status");
  if (statusBox) {
    statusBox.textContent = text;
  }
}

/**
 * 从表单收集待提交的字段。
 *
 * 只有与原始值不同的字段才会被包含，避免触发不必要的写入。
 *
 * @returns {Object} 待提交的补丁对象。
 */
function collectPatch() {
  if (!originalMetadata) {
    return {};
  }
  const patch = {};

  const nameInput = getElement("metadata-name").value.trim();
  const pathInput = getElement("metadata-path").value.trim();
  if (pathInput !== originalMetadata.path && pathInput !== "") {
    patch.path = pathInput;
  } else if (nameInput !== originalMetadata.name && nameInput !== "") {
    patch.name = nameInput;
  }

  const modifiedInput = getElement("metadata-modified").value.trim();
  if (modifiedInput !== "") {
    const modifiedValue = Number(modifiedInput);
    if (Number.isFinite(modifiedValue) && modifiedValue !== originalMetadata.modifiedAt) {
      patch.modifiedAt = modifiedValue;
    }
  }

  const accessedInput = getElement("metadata-accessed").value.trim();
  if (accessedInput !== "") {
    const accessedValue = Number(accessedInput);
    if (Number.isFinite(accessedValue) && accessedValue !== originalMetadata.accessedAt) {
      patch.accessedAt = accessedValue;
    }
  }

  const permissionsValue = getElement("metadata-permissions").value.trim();
  if (
    permissionsValue !== "" &&
    permissionsValue !== originalMetadata.permissions
  ) {
    patch.permissions = permissionsValue;
  }

  const hiddenValue = getElement("metadata-hidden").checked;
  if (hiddenValue !== Boolean(originalMetadata.isHidden)) {
    patch.isHidden = hiddenValue;
  }

  return patch;
}

/**
 * 加载元数据并渲染。
 */
async function loadMetadata() {
  setStatusText("加载中…");
  try {
    const metadata = await getMetadata(targetPath);
    originalMetadata = metadata;
    renderHeader(metadata);
    fillForm(metadata);
    clearError();
    setStatusText("");
  } catch (error) {
    showFormError(error);
    setStatusText("加载失败");
    showError(error);
  }
}

/**
 * 处理表单提交。
 *
 * @param {SubmitEvent} event 提交事件。
 */
async function handleSubmit(event) {
  event.preventDefault();
  if (!originalMetadata) {
    return;
  }
  const patch = collectPatch();
  if (Object.keys(patch).length === 0) {
    setStatusText("没有需要保存的修改");
    return;
  }

  setStatusText("保存中…");
  clearError();
  try {
    const updated = await updateMetadata(targetPath, patch);
    originalMetadata = updated;
    renderHeader(updated);
    fillForm(updated);
    setStatusText("已保存");
    showSuccess("已保存修改");
    if (patch.path) {
      targetPath = updated.path;
      const url = new URL(window.location.href);
      url.searchParams.set("path", updated.path);
      window.history.replaceState({}, "", url.toString());
    }
  } catch (error) {
    showFormError(error);
    setStatusText("保存失败");
    showError(error);
  }
}

/**
 * 处理表单重置：恢复为最近一次加载的元数据。
 *
 * @param {Event} event 点击事件。
 */
function handleReset(event) {
  event.preventDefault();
  if (!originalMetadata) {
    return;
  }
  fillForm(originalMetadata);
  clearError();
  setStatusText("已重置");
}

/**
 * 应用启动入口。
 */
function bootstrap() {
  initializeTheme();
  targetPath = parseTargetPath();
  document.title = "属性";

  const form = getElement("metadata-form");
  form?.addEventListener("submit", handleSubmit);
  getElement("metadata-reset-button")?.addEventListener(
    "click",
    handleReset
  );

  loadMetadata().catch((error) => {
    console.error("属性页面初始化失败：", error);
    showError(error);
  });
}

window.addEventListener("DOMContentLoaded", bootstrap);
