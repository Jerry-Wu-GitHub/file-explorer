/**
 * 上传条目收集。
 *
 * 将文件选择器与拖拽数据转换为统一的
 * `{ file, relativePath }` 条目列表，支持递归展开文件夹。
 */

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
 * 递归收集拖拽数据中的所有文件。
 *
 * 优先使用 `DataTransferItem.webkitGetAsEntry()` 以支持目录；
 * 不可用时退化为只处理顶层文件。
 *
 * @param {DataTransfer} dataTransfer 拖拽数据。
 * @returns {Promise<Array<{file: File, relativePath: string}>>} 条目列表。
 */
export async function collectDroppedEntries(dataTransfer) {
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
 * 判断拖拽事件是否携带文件。
 *
 * @param {DragEvent} event 拖拽事件。
 * @returns {boolean} 是否携带文件。
 */
export function hasFilePayload(event) {
  const dataTransfer = event.dataTransfer;
  if (!dataTransfer) {
    return false;
  }
  return Array.from(dataTransfer.types || []).includes("Files");
}
