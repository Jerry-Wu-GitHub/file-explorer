/**
 * 文件系统 API 封装。
 *
 * 对后端 `/api/v1/files`、`/api/v1/folders` 下所有接口的薄封装，
 * 只负责参数整形与调用 `client.js`，不包含业务编排与 UI 逻辑。
 *
 * 所有返回值均为后端 `ApiResponse.data`（或含 `meta` 的完整外壳），
 * 错误统一抛出 `ApiError`。
 */

import {
  buildDownloadUrl,
  deleteRequest,
  getData,
  getEnvelope,
  patchJson,
  postFormData,
  postJson,
} from "./client.js";

/** 文件接口的 API 路径。 */
const FILES_PATH = "/files";

/** 文件夹接口的 API 路径。 */
const FOLDERS_PATH = "/folders";

/**
 * 列出目录内容。
 *
 * @param {string} path 目录的沙箱虚拟路径。
 * @param {Object} [options] 可选查询参数。
 * @param {number} [options.page] 页码，从 1 开始。
 * @param {number} [options.size] 每页数量。
 * @param {string} [options.sort] 排序表达式，例如 `name,asc`。
 * @param {string} [options.type] 过滤类型：`all` / `file` / `directory`。
 * @param {boolean} [options.followLink] 是否跟随符号链接。
 * @returns {Promise<{data: Object[], meta: Object|null}>} 条目列表与分页元数据。
 */
export function listDirectory(path, options = {}) {
  return getEnvelope(FILES_PATH, {
    path,
    page: options.page,
    size: options.size,
    sort: options.sort,
    type: options.type,
    followLink: options.followLink,
  });
}

/**
 * 获取单个条目元数据。
 *
 * @param {string} path 条目的沙箱虚拟路径。
 * @param {Object} [options] 可选查询参数。
 * @param {boolean} [options.followLink] 是否跟随符号链接。
 * @returns {Promise<Object>} 条目元数据。
 */
export function getMetadata(path, options = {}) {
  return getData(`${FILES_PATH}/metadata`, {
    path,
    followLink: options.followLink,
  });
}

/**
 * 构造文件内容下载的完整 URL。
 *
 * 用于 `<a download>` 或 `window.open`，不经过 fetch。
 *
 * @param {string} path 文件的沙箱虚拟路径。
 * @param {Object} [options] 可选查询参数。
 * @param {boolean} [options.followLink] 是否跟随符号链接。
 * @returns {string} 完整下载 URL。
 */
export function buildContentDownloadUrl(path, options = {}) {
  return buildDownloadUrl(`${FILES_PATH}/content`, {
    path,
    followLink: options.followLink,
  });
}

/**
 * 构造压缩包下载的完整 URL。
 *
 * @param {string[]} paths 要打包的沙箱虚拟路径列表。
 * @param {Object} [options] 可选查询参数。
 * @param {boolean} [options.followLink] 是否跟随符号链接。
 * @returns {string} 完整下载 URL。
 */
export function buildZipDownloadUrl(paths, options = {}) {
  return buildDownloadUrl(`${FILES_PATH}/download-zip`, {
    paths: paths.join(","),
    followLink: options.followLink,
  });
}

/**
 * 创建空文件。
 *
 * @param {string} path 目标文件的沙箱虚拟路径。
 * @returns {Promise<Object>} 新文件的元数据。
 */
export function createFile(path) {
  return postJson(FILES_PATH, { path });
}

/**
 * 创建文件夹。
 *
 * @param {string} path 目标文件夹的沙箱虚拟路径。
 * @returns {Promise<Object>} 新文件夹的元数据。
 */
export function createFolder(path) {
  return postJson(FOLDERS_PATH, { path });
}

/**
 * 删除文件、目录或符号链接。
 *
 * @param {string} path 要删除的沙箱虚拟路径。
 * @param {Object} [options] 可选查询参数。
 * @param {boolean} [options.recursive] 目录非空时是否递归删除。
 * @param {boolean} [options.followLink] 是否跟随符号链接。
 * @returns {Promise<null>} 后端返回 204，无响应体。
 */
export function deleteEntry(path, options = {}) {
  return deleteRequest(FILES_PATH, {
    path,
    recursive: options.recursive,
    followLink: options.followLink,
  });
}

/**
 * 修改文件或目录的元数据。
 *
 * @param {string} path 目标沙箱虚拟路径。
 * @param {Object} updates 需要修改的字段，只传需要变更的键。
 * @param {Object} [options] 可选查询参数。
 * @param {boolean} [options.followLink] 是否跟随符号链接。
 * @returns {Promise<Object>} 更新后的元数据。
 */
export function updateMetadata(path, updates, options = {}) {
  return patchJson(FILES_PATH, updates, {
    path,
    followLink: options.followLink,
  });
}

/**
 * 重命名条目（仅修改名称，保持所在目录）。
 *
 * @param {string} path 原沙箱虚拟路径。
 * @param {string} newName 新名称。
 * @returns {Promise<Object>} 更新后的元数据。
 */
export function renameEntry(path, newName) {
  return updateMetadata(path, { name: newName });
}

/**
 * 移动条目（相当于移动 + 重命名）。
 *
 * @param {string} path 原沙箱虚拟路径。
 * @param {string} newPath 新沙箱虚拟路径。
 * @returns {Promise<Object>} 更新后的元数据。
 */
export function moveEntry(path, newPath) {
  return updateMetadata(path, { path: newPath });
}

/**
 * 递归搜索文件与目录。
 *
 * @param {Object} [parameters] 查询参数。
 * @param {string} [parameters.q] 文件名关键词。
 * @param {string} [parameters.path] 搜索起始目录。
 * @param {string} [parameters.type] 过滤类型。
 * @param {number} [parameters.minSize] 最小字节数。
 * @param {number} [parameters.maxSize] 最大字节数。
 * @param {string} [parameters.modifiedAfter] ISO 8601 时间。
 * @param {string} [parameters.modifiedBefore] ISO 8601 时间。
 * @param {number} [parameters.page] 页码。
 * @param {number} [parameters.size] 每页数量。
 * @param {boolean} [parameters.followLink] 是否跟随符号链接。
 * @returns {Promise<{data: Object[], meta: Object|null}>} 结果与分页元数据。
 */
export function searchEntries(parameters = {}) {
  return getEnvelope(`${FILES_PATH}/search`, parameters);
}

/**
 * 复制文件或递归复制文件夹。
 *
 * @param {string} source 源沙箱虚拟路径。
 * @param {string} destination 目标沙箱虚拟路径。
 * @param {Object} [options] 可选参数。
 * @param {boolean} [options.overwrite] 目标已存在时是否覆盖。
 * @returns {Promise<Object>} 副本的元数据。
 */
export function copyEntry(source, destination, options = {}) {
  return postJson(`${FILES_PATH}/copy`, {
    source,
    destination,
    overwrite: options.overwrite ?? false,
  });
}

/**
 * 上传小文件到目标目录。
 *
 * @param {string} directoryPath 目标目录的沙箱虚拟路径。
 * @param {File|Blob} file 文件内容。
 * @param {Object} [options] 可选参数。
 * @param {string} [options.filename] 文件名；未提供时使用 `file.name`。
 * @param {boolean} [options.overwrite] 目标已存在时是否覆盖。
 * @returns {Promise<Object>} 新文件的元数据。
 */
export function uploadSmallFile(directoryPath, file, options = {}) {
  const filename = options.filename ?? file.name ?? "upload.bin";
  const formData = new FormData();
  formData.append("file", file, filename);
  formData.append("overwrite", String(options.overwrite ?? false));
  return postFormData(`${FILES_PATH}/upload`, formData, {
    path: directoryPath,
  });
}
