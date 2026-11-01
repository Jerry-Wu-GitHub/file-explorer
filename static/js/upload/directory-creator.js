/**
 * 上传前的目录准备。
 *
 * 批量上传文件夹时，先按相对路径创建所需目录，再逐文件上传。
 * 目录已存在视为成功，不中断任务。
 */

import { createFolder } from "../api/files.js";
import {
  getDirectoryPart,
  joinVirtualPath,
} from "./path-helpers.js";

/**
 * 收集条目需要的所有相对目录。
 *
 * @param {Array<{relativePath: string}>} entries 条目列表。
 * @returns {string[]} 去重并排序后的相对目录。
 */
function collectRelativeDirectories(entries) {
  const directories = new Set();
  for (const entry of entries) {
    const directoryPart = getDirectoryPart(entry.relativePath);
    if (!directoryPart) {
      continue;
    }
    const parts = directoryPart.split("/");
    let accumulated = "";
    for (const part of parts) {
      accumulated = accumulated ? `${accumulated}/${part}` : part;
      directories.add(accumulated);
    }
  }
  return [...directories].sort();
}

/**
 * 确保批量上传所需目录全部存在。
 *
 * @param {Array<{relativePath: string}>} entries 条目列表。
 * @param {string} baseDirectory 目标基础目录。
 * @returns {Promise<void>} 无返回值。
 */
export async function ensureUploadDirectories(entries, baseDirectory) {
  const relativeDirectories = collectRelativeDirectories(entries);
  for (const relativeDirectory of relativeDirectories) {
    const path = joinVirtualPath(baseDirectory, relativeDirectory);
    try {
      await createFolder(path);
    } catch (error) {
      if (error.code !== "FILE_EXISTS") {
        console.warn(`创建目录失败：${path}`, error);
      }
    }
  }
}
