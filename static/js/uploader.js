/**
 * 上传入口模块。
 *
 * 支持三种入口：
 *
 * - 工具栏「上传」按钮 → 选择文件或文件夹；
 * - 拖拽文件 / 文件夹到页面；
 * - 隐藏的 `<input type="file">` 与 `<input webkitdirectory>`。
 *
 * 每次用户操作都会创建一个上传任务，交由上传任务管理器执行。
 * 任务进度、暂停、继续、终止与冲突处理由上传面板呈现。
 */

import { getState } from "./state.js";
import { showError } from "./toast.js";
import { buildEntriesFromFileList, collectDroppedEntries, hasFilePayload } from "./upload/entry-collector.js";
import { initializeUploadPanel } from "./upload/upload-panel.js";
import { configureUploadManager, createUploadTask } from "./upload/upload-manager.js";

/** 是否已初始化。 */
let initialized = false;

/**
 * 创建上传任务。
 *
 * @param {Array<{file: File, relativePath: string}>} entries 条目列表。
 * @param {string} targetDirectory 目标目录。
 * @returns {void} 无返回值。
 */
export function uploadEntries(entries, targetDirectory) {
  if (!entries || entries.length === 0) {
    return;
  }
  createUploadTask(entries, targetDirectory);
}

/**
 * 打开文件选择器。
 */
export function openFilePicker() {
  document.getElementById("file-input")?.click();
}

/**
 * 打开文件夹选择器。
 */
export function openFolderPicker() {
  document.getElementById("folder-input")?.click();
}

/**
 * 处理文件输入框的变更。
 *
 * 注意：必须先构建条目快照，再重置 `input.value`；重置 value 会
 * 清空 `FileList`，若顺序颠倒会拿到空数组，导致不发起任何上传。
 *
 * @param {Event} event 变更事件。
 */
function handleFileInputChange(event) {
  const entries = buildEntriesFromFileList(event.target.files, false);
  event.target.value = "";
  uploadEntries(entries, getState().currentPath);
}

/**
 * 处理文件夹输入框的变更。
 *
 * 顺序同 :func:`handleFileInputChange`。
 *
 * @param {Event} event 变更事件。
 */
function handleFolderInputChange(event) {
  const entries = buildEntriesFromFileList(event.target.files, true);
  event.target.value = "";
  uploadEntries(entries, getState().currentPath);
}

/**
 * 拖拽上传控制器。
 */
class DragDropUploader {
  constructor() {
    this.dragDepth = 0;
    this.overlay = document.getElementById("drop-overlay");
    this.handleDragEnter = this.handleDragEnter.bind(this);
    this.handleDragOver = this.handleDragOver.bind(this);
    this.handleDragLeave = this.handleDragLeave.bind(this);
    this.handleDrop = this.handleDrop.bind(this);
  }

  /**
   * 安装拖拽监听。
   */
  install() {
    document.addEventListener("dragenter", this.handleDragEnter);
    document.addEventListener("dragover", this.handleDragOver);
    document.addEventListener("dragleave", this.handleDragLeave);
    document.addEventListener("drop", this.handleDrop);
  }

  /**
   * 设置遮罩可见性。
   *
   * @param {boolean} visible 是否可见。
   */
  setOverlayVisible(visible) {
    if (!this.overlay) {
      return;
    }
    this.overlay.classList.toggle("hidden", !visible);
  }

  /**
   * 处理拖入。
   *
   * @param {DragEvent} event 拖拽事件。
   */
  handleDragEnter(event) {
    if (!hasFilePayload(event)) {
      return;
    }
    event.preventDefault();
    this.dragDepth += 1;
    if (this.dragDepth === 1) {
      this.setOverlayVisible(true);
    }
  }

  /**
   * 处理拖拽悬停。
   *
   * @param {DragEvent} event 拖拽事件。
   */
  handleDragOver(event) {
    if (!hasFilePayload(event)) {
      return;
    }
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
  }

  /**
   * 处理拖离。
   *
   * @param {DragEvent} event 拖拽事件。
   */
  handleDragLeave(event) {
    if (!hasFilePayload(event)) {
      return;
    }
    this.dragDepth = Math.max(0, this.dragDepth - 1);
    if (this.dragDepth === 0) {
      this.setOverlayVisible(false);
    }
  }

  /**
   * 处理放置。
   *
   * @param {DragEvent} event 拖拽事件。
   * @returns {Promise<void>} 处理完成后 resolve。
   */
  async handleDrop(event) {
    if (!hasFilePayload(event)) {
      return;
    }
    event.preventDefault();
    this.dragDepth = 0;
    this.setOverlayVisible(false);
    try {
      const entries = await collectDroppedEntries(event.dataTransfer);
      uploadEntries(entries, getState().currentPath);
    } catch (error) {
      console.error("处理拖拽上传失败：", error);
      showError("处理拖拽文件失败");
    }
  }
}

/**
 * 初始化上传模块。
 *
 * 应在 `main.js` 中调用一次。
 *
 * @param {Object} [options] 配置。
 * @param {() => void} [options.onRefresh] 上传成功后的刷新回调。
 */
export function initializeUploader(options = {}) {
  if (initialized) {
    return;
  }
  initialized = true;

  configureUploadManager({ onRefresh: options.onRefresh || (() => {}) });
  initializeUploadPanel();

  document
    .getElementById("file-input")
    ?.addEventListener("change", handleFileInputChange);
  document
    .getElementById("folder-input")
    ?.addEventListener("change", handleFolderInputChange);

  new DragDropUploader().install();
}
