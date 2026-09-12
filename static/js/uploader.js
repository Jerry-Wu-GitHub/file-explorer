/**
 * 上传编排模块。
 *
 * 支持三种入口：
 *
 * - 工具栏「上传」按钮 → 选择文件或文件夹；
 * - 拖拽文件 / 文件夹到页面；
 * - 隐藏的 `<input type="file">` 与 `<input webkitdirectory>`。
 *
 * 上传策略：
 *
 * - 文件大小小于阈值时使用 `POST /files/upload` 小文件接口；
 * - 大于等于阈值时使用分片上传（初始化 → 并发上传分片 → 完成）；
 * - 文件夹会被递归展开，上传时保留相对目录结构；
 * - 遇到 `FILE_EXISTS` 冲突时询问一次，用户可选择全部覆盖或全部跳过。
 *
 * 模块不直接刷新列表；通过 `initializeUploader({ onRefresh })` 注入。
 */

import {
  createFolder,
  uploadSmallFile as uploadSmallFileApi,
} from "./api/files.js";
import {
  cancelUpload,
  completeUpload,
  initializeUpload,
  uploadChunk,
} from "./api/uploads.js";
import {
  CHUNKED_UPLOAD_THRESHOLD,
  DEFAULT_CHUNK_SIZE,
  MAX_CHUNKS,
  MAX_CONCURRENT_CHUNK_UPLOADS,
} from "./config.js";
import { getState } from "./state.js";
import { showError, showInfo, showSuccess, showToast } from "./toast.js";

/** 上传完成后调用的刷新回调。由 `main.js` 注入。 */
let refreshCallback = () => {};

/** 是否已初始化。 */
let initialized = false;

/**
 * 内部使用的「跳过」异常，用于在批量上传中标记被用户主动跳过的文件。
 */
class SkipError extends Error {
  /**
   * @param {string} filename 被跳过的文件名。
   */
  constructor(filename) {
    super(`已跳过：${filename}`);
    this.name = "SkipError";
  }
}

/**
 * 从相对路径中提取目录部分。
 *
 * @param {string} relativePath 相对路径。
 * @returns {string} 目录部分，无目录时返回空串。
 */
function getDirectoryPart(relativePath) {
  const index = relativePath.lastIndexOf("/");
  return index >= 0 ? relativePath.substring(0, index) : "";
}

/**
 * 从相对路径中提取文件名。
 *
 * @param {string} relativePath 相对路径。
 * @returns {string} 文件名。
 */
function getFilename(relativePath) {
  const index = relativePath.lastIndexOf("/");
  return index >= 0 ? relativePath.substring(index + 1) : relativePath;
}

/**
 * 拼接沙箱虚拟路径。
 *
 * @param {string} directory 目录路径。
 * @param {string} name 条目名称或相对路径。
 * @returns {string} 完整虚拟路径。
 */
function joinVirtualPath(directory, name) {
  if (!directory || directory === "/") {
    return `/${name}`;
  }
  return `${directory.replace(/\/+$/, "")}/${name}`;
}

/**
 * 根据文件大小选择分片大小。
 *
 * 默认使用 `DEFAULT_CHUNK_SIZE`（16 MiB）。仅当固定分片会导致
 * 分片数超过后端允许的 `MAX_CHUNKS` 时，才按上限反推更大的分片
 * 大小，避免初始化请求被后端拒绝。
 *
 * @param {number} fileSize 文件总字节数。
 * @returns {number} 分片大小。
 */
function pickChunkSize(fileSize) {
  if (fileSize <= DEFAULT_CHUNK_SIZE * MAX_CHUNKS) {
    return DEFAULT_CHUNK_SIZE;
  }
  return Math.ceil(fileSize / MAX_CHUNKS);
}

/**
 * 并发执行任务列表。
 *
 * @template T
 * @param {T[]} items 任务输入。
 * @param {(item: T) => Promise<void>} worker 任务函数。
 * @param {number} concurrency 并发上限。
 * @returns {Promise<void>} 全部完成后 resolve。
 */
async function runConcurrent(items, worker, concurrency) {
  const limit = Math.min(concurrency, items.length);
  if (limit === 0) {
    return;
  }

  let nextIndex = 0;
  let firstError = null;
  let aborted = false;

  async function runWorker() {
    while (!aborted) {
      const index = nextIndex;
      nextIndex += 1;
      if (index >= items.length) {
        return;
      }
      try {
        await worker(items[index]);
      } catch (error) {
        if (!firstError) {
          firstError = error;
          aborted = true;
        }
        return;
      }
    }
  }

  const workers = [];
  for (let index = 0; index < limit; index += 1) {
    workers.push(runWorker());
  }
  await Promise.all(workers);

  if (firstError) {
    throw firstError;
  }
}

/**
 * 递归收集拖拽数据中的所有文件。
 *
 * 优先使用 `DataTransferItem.webkitGetAsEntry()` 以支持目录；
 * 不可用时退化为只处理顶层文件。
 *
 * @param {DataTransfer} dataTransfer 拖拽数据。
 * @returns {Promise<Array<{file: File, relativePath: string}>>} 条目列表。
 */
async function collectDroppedEntries(dataTransfer) {
  const items = dataTransfer.items;
  const results = [];

  if (items && items.length > 0) {
    const entries = [];
    for (const item of items) {
      if (item.kind !== "file") {
        continue;
      }
      const fileSystemEntry =
        typeof item.webkitGetAsEntry === "function"
          ? item.webkitGetAsEntry()
          : null;
      if (fileSystemEntry) {
        entries.push(fileSystemEntry);
        continue;
      }
      const file = item.getAsFile();
      if (file) {
        results.push({ file, relativePath: file.name });
      }
    }
    for (const entry of entries) {
      const collected = await collectFileSystemEntry(entry, "");
      results.push(...collected);
    }
    return results;
  }

  const files = Array.from(dataTransfer.files || []);
  for (const file of files) {
    results.push({ file, relativePath: file.name });
  }
  return results;
}

/**
 * 递归遍历 `FileSystemEntry`。
 *
 * @param {FileSystemEntry} entry 条目。
 * @param {string} pathPrefix 路径前缀（不含当前条目名）。
 * @returns {Promise<Array<{file: File, relativePath: string}>>} 条目列表。
 */
async function collectFileSystemEntry(entry, pathPrefix) {
  if (entry.isFile) {
    const file = await new Promise((resolve, reject) => {
      entry.file(resolve, reject);
    });
    return [{ file, relativePath: pathPrefix + file.name }];
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    const children = await readAllDirectoryEntries(reader);
    const results = [];
    const childPrefix = `${pathPrefix}${entry.name}/`;
    for (const child of children) {
      const subResults = await collectFileSystemEntry(child, childPrefix);
      results.push(...subResults);
    }
    return results;
  }
  return [];
}

/**
 * 读取目录条目的所有子项。
 *
 * `readEntries` 每次最多返回 100 项，需要反复调用直到返回空数组。
 *
 * @param {FileSystemDirectoryReader} reader 目录读取器。
 * @returns {Promise<FileSystemEntry[]>} 子项列表。
 */
async function readAllDirectoryEntries(reader) {
  const all = [];
  while (true) {
    const batch = await new Promise((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (!batch || batch.length === 0) {
      return all;
    }
    all.push(...batch);
  }
}

/**
 * 确保文件夹上传所需的目录链存在。
 *
 * 对同一批次，重复调用不会重复创建。
 *
 * @param {Array<{relativePath: string}>} entries 条目列表。
 * @param {string} baseDirectory 目标基础目录。
 * @returns {Promise<void>} 无返回值。
 */
async function ensureDirectories(entries, baseDirectory) {
  const directorySet = new Set();
  for (const entry of entries) {
    const directoryPart = getDirectoryPart(entry.relativePath);
    if (!directoryPart) {
      continue;
    }
    const parts = directoryPart.split("/");
    let accumulated = "";
    for (const part of parts) {
      accumulated = accumulated ? `${accumulated}/${part}` : part;
      directorySet.add(accumulated);
    }
  }

  const sorted = [...directorySet].sort();
  for (const relativeDir of sorted) {
    const path = joinVirtualPath(baseDirectory, relativeDir);
    try {
      await createFolder(path);
    } catch (error) {
      if (error.code !== "FILE_EXISTS") {
        console.warn(`创建目录失败：${path}`, error);
      }
    }
  }
}

/**
 * 上传单个文件。
 *
 * 根据大小选择小文件或分片接口。
 *
 * @param {File} file 文件内容。
 * @param {string} targetDirectory 目标目录。
 * @param {string} filename 目标文件名。
 * @param {boolean} overwrite 是否覆盖同名文件。
 * @returns {Promise<Object>} 上传后的元数据。
 */
async function uploadSingleFile(file, targetDirectory, filename, overwrite) {
  if (file.size >= CHUNKED_UPLOAD_THRESHOLD) {
    return await uploadChunkedFile(
      file,
      targetDirectory,
      filename,
      overwrite
    );
  }
  return await uploadSmallFileApi(targetDirectory, file, {
    filename,
    overwrite,
  });
}

/**
 * 使用分片上传接口上传大文件。
 *
 * @param {File} file 文件内容。
 * @param {string} targetDirectory 目标目录。
 * @param {string} filename 目标文件名。
 * @param {boolean} overwrite 是否覆盖同名文件。
 * @returns {Promise<Object>} 上传后的元数据。
 */
async function uploadChunkedFile(
  file,
  targetDirectory,
  filename,
  overwrite
) {
  const targetPath = joinVirtualPath(targetDirectory, filename);
  const chunkSize = pickChunkSize(file.size);

  const session = await initializeUpload({
    path: targetPath,
    size: file.size,
    chunkSize,
    overwrite,
  });

  const uploaded = new Set(session.uploadedChunks || []);
  const pending = [];
  for (let index = 0; index < session.totalChunks; index += 1) {
    if (!uploaded.has(index)) {
      pending.push(index);
    }
  }

  try {
    await runConcurrent(
      pending,
      async (chunkNumber) => {
        const start = chunkNumber * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        const blob = file.slice(start, end);
        await uploadChunk(session.uploadId, chunkNumber, blob);
      },
      MAX_CONCURRENT_CHUNK_UPLOADS
    );
  } catch (error) {
    try {
      await cancelUpload(session.uploadId);
    } catch (cancelError) {
      console.warn(`取消上传失败：${session.uploadId}`, cancelError);
    }
    throw error;
  }

  return await completeUpload(session.uploadId);
}

/**
 * 上传单个条目，处理冲突与跳过。
 *
 * @param {{file: File, relativePath: string}} entry 条目。
 * @param {Object} context 批量上传上下文。
 * @returns {Promise<void>} 无返回值。
 */
async function uploadSingleEntry(entry, context) {
  const directoryPart = getDirectoryPart(entry.relativePath);
  const targetDirectory = directoryPart
    ? joinVirtualPath(context.targetDirectory, directoryPart)
    : context.targetDirectory;
  const filename = getFilename(entry.relativePath);

  try {
    await uploadFileWithConflictHandling(
      entry.file,
      targetDirectory,
      filename,
      context
    );
    context.succeeded += 1;
  } catch (error) {
    if (error instanceof SkipError) {
      context.skipped += 1;
      return;
    }
    context.failed += 1;
    console.error(`上传失败：${entry.relativePath}`, error);
  }
}

/**
 * 上传单个文件，遇冲突时按批次策略处理。
 *
 * @param {File} file 文件内容。
 * @param {string} targetDirectory 目标目录。
 * @param {string} filename 目标文件名。
 * @param {Object} context 批量上传上下文。
 * @returns {Promise<Object>} 上传后的元数据。
 */
async function uploadFileWithConflictHandling(
  file,
  targetDirectory,
  filename,
  context
) {
  if (context.skipAllConflicts) {
    throw new SkipError(filename);
  }

  try {
    return await uploadSingleFile(
      file,
      targetDirectory,
      filename,
      context.overwrite
    );
  } catch (error) {
    if (error.code !== "FILE_EXISTS") {
      throw error;
    }
    if (context.conflictResolved) {
      if (context.overwrite) {
        return await uploadSingleFile(
          file,
          targetDirectory,
          filename,
          true
        );
      }
      throw new SkipError(filename);
    }
    context.conflictResolved = true;
    const overwrite = window.confirm(
      `目标位置已存在同名文件「${filename}」。\n\n` +
        "点击「确定」覆盖所有同名文件；点击「取消」跳过所有冲突文件。"
    );
    context.overwrite = overwrite;
    context.skipAllConflicts = !overwrite;
    if (overwrite) {
      return await uploadSingleFile(
        file,
        targetDirectory,
        filename,
        true
      );
    }
    throw new SkipError(filename);
  }
}

/**
 * 构造进度提示。
 *
 * @param {number} total 总文件数。
 * @returns {{update: (message: string) => void, close: () => void}} 进度句柄。
 */
function createProgress(total) {
  const element = showToast(`准备上传 ${total} 个文件…`, {
    type: "info",
    duration: 0,
  });
  return {
    update(message) {
      if (element) {
        element.textContent = message;
      }
    },
    close() {
      element?.click();
    },
  };
}

/**
 * 批量上传入口。
 *
 * @param {Array<{file: File, relativePath: string}>} entries 条目列表。
 * @param {string} targetDirectory 目标目录。
 * @returns {Promise<void>} 无返回值。
 */
export async function uploadEntries(entries, targetDirectory) {
  if (!entries || entries.length === 0) {
    return;
  }

  const context = {
    targetDirectory,
    overwrite: false,
    skipAllConflicts: false,
    conflictResolved: false,
    succeeded: 0,
    failed: 0,
    skipped: 0,
  };

  const progress = createProgress(entries.length);
  try {
    progress.update("正在创建目录…");
    await ensureDirectories(entries, targetDirectory);

    for (let index = 0; index < entries.length; index += 1) {
      const entry = entries[index];
      progress.update(
        `正在上传 ${index + 1}/${entries.length}：${entry.relativePath}`
      );
      await uploadSingleEntry(entry, context);
    }
  } finally {
    progress.close();
  }

  if (context.failed === 0 && context.skipped === 0) {
    showSuccess(`上传完成：${context.succeeded} 个文件`);
  } else {
    const parts = [`成功 ${context.succeeded}`];
    if (context.skipped > 0) {
      parts.push(`跳过 ${context.skipped}`);
    }
    if (context.failed > 0) {
      parts.push(`失败 ${context.failed}`);
    }
    showInfo(`上传结束：${parts.join("，")}`);
  }

  if (context.succeeded > 0) {
    refreshCallback();
  }
}

/**
 * 从文件输入框的 `FileList` 构造条目。
 *
 * @param {FileList} fileList 文件列表。
 * @param {boolean} useRelativePath 是否使用 `webkitRelativePath`。
 * @returns {Array<{file: File, relativePath: string}>} 条目列表。
 */
export function buildEntriesFromFileList(fileList, useRelativePath) {
  const results = [];
  for (const file of Array.from(fileList || [])) {
    const relativePath = useRelativePath
      ? file.webkitRelativePath || file.name
      : file.name;
    results.push({ file, relativePath });
  }
  return results;
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
async function handleFileInputChange(event) {
  const entries = buildEntriesFromFileList(event.target.files, false);
  event.target.value = "";
  await uploadEntries(entries, getState().currentPath);
}

/**
 * 处理文件夹输入框的变更。
 *
 * 顺序同 :func:`handleFileInputChange`。
 *
 * @param {Event} event 变更事件。
 */
async function handleFolderInputChange(event) {
  const entries = buildEntriesFromFileList(event.target.files, true);
  event.target.value = "";
  await uploadEntries(entries, getState().currentPath);
}

/**
 * 判断拖拽事件是否携带文件。
 *
 * @param {DragEvent} event 拖拽事件。
 * @returns {boolean} 是否携带文件。
 */
function hasFilePayload(event) {
  const dataTransfer = event.dataTransfer;
  if (!dataTransfer) {
    return false;
  }
  return Array.from(dataTransfer.types || []).includes("Files");
}

/**
 * 安装拖拽上传监听。
 */
function setupDragAndDrop() {
  const overlay = document.getElementById("drop-overlay");
  let dragDepth = 0;

  document.addEventListener("dragenter", (event) => {
    if (!hasFilePayload(event)) {
      return;
    }
    event.preventDefault();
    dragDepth += 1;
    if (dragDepth === 1 && overlay) {
      overlay.classList.remove("hidden");
    }
  });

  document.addEventListener("dragover", (event) => {
    if (!hasFilePayload(event)) {
      return;
    }
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
  });

  document.addEventListener("dragleave", (event) => {
    if (!hasFilePayload(event)) {
      return;
    }
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0 && overlay) {
      overlay.classList.add("hidden");
    }
  });

  document.addEventListener("drop", async (event) => {
    if (!hasFilePayload(event)) {
      return;
    }
    event.preventDefault();
    dragDepth = 0;
    if (overlay) {
      overlay.classList.add("hidden");
    }
    try {
      const entries = await collectDroppedEntries(event.dataTransfer);
      await uploadEntries(entries, getState().currentPath);
    } catch (error) {
      console.error("处理拖拽上传失败：", error);
      showError("处理拖拽文件失败");
    }
  });
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
  refreshCallback = options.onRefresh || (() => {});

  document
    .getElementById("file-input")
    ?.addEventListener("change", handleFileInputChange);
  document
    .getElementById("folder-input")
    ?.addEventListener("change", handleFolderInputChange);

  setupDragAndDrop();
}
