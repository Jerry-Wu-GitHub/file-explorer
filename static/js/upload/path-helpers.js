/**
 * 上传路径辅助函数。
 *
 * 处理批量上传条目中的相对路径，将其转换为沙箱虚拟路径。
 */

/**
 * 从相对路径中提取目录部分。
 *
 * @param {string} relativePath 相对路径。
 * @returns {string} 目录部分，无目录时返回空串。
 */
export function getDirectoryPart(relativePath) {
  const index = relativePath.lastIndexOf("/");
  return index >= 0 ? relativePath.substring(0, index) : "";
}

/**
 * 从相对路径中提取文件名。
 *
 * @param {string} relativePath 相对路径。
 * @returns {string} 文件名。
 */
export function getFilename(relativePath) {
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
export function joinVirtualPath(directory, name) {
  if (!directory || directory === "/") {
    return `/${name}`;
  }
  return `${directory.replace(/\/+$/, "")}/${name}`;
}

/**
 * 计算条目最终所在的目标目录。
 *
 * @param {string} baseDirectory 基础目标目录。
 * @param {string} relativePath 条目相对路径。
 * @returns {string} 目标目录虚拟路径。
 */
export function resolveEntryDirectory(baseDirectory, relativePath) {
  const directoryPart = getDirectoryPart(relativePath);
  return directoryPart
    ? joinVirtualPath(baseDirectory, directoryPart)
    : baseDirectory;
}
