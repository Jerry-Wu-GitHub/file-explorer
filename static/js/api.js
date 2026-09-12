/**
 * 后端 REST API 客户端：统一封装请求与错误处理。
 */

const API_BASE = "/api/v1";

/**
 * API 请求错误，携带 HTTP 状态码与业务错误码。
 */
export class ApiError extends Error {
  /**
   * @param {number} status - HTTP 状态码
   * @param {string} code - 业务错误码
   * @param {string} message - 错误文案
   * @param {object} details - 附加详情
   */
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/**
 * 发起 JSON 请求并统一解析响应。
 * @param {string} path - 接口路径（不含前缀）
 * @param {object} options - fetch 选项
 * @returns {Promise<object>} 响应体 data 字段
 */
async function requestJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options);
  return parseResponse(response);
}

/**
 * 解析响应：成功返回 data 与 meta，失败抛出 ApiError。
 * @param {Response} response - fetch 响应
 * @returns {Promise<object>} { data, meta }
 */
async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = await response.json();
    if (!response.ok) {
      throw new ApiError(response.status, body.code, body.message, body.details);
    }
    return { data: body.data, meta: body.meta };
  }
  if (!response.ok) {
    throw new ApiError(response.status, "HTTP_ERROR", `请求失败: ${response.status}`);
  }
  return { data: null, meta: null };
}

/**
 * 列出目录内容。
 * @param {object} params - 查询参数
 * @returns {Promise<object>} { data, meta }
 */
export function listFiles(params) {
  const query = buildQuery(params);
  return requestJson(`/files${query}`);
}

/**
 * 获取条目元数据。
 * @param {string} path - 虚拟路径
 * @returns {Promise<object>} 条目元数据
 */
export function getMetadata(path) {
  const query = buildQuery({ path });
  return requestJson(`/files/metadata${query}`);
}

/**
 * 生成文件下载地址。
 * @param {string} path - 虚拟路径
 * @returns {string} 下载 URL
 */
export function contentUrl(path) {
  return `${API_BASE}/files/content?path=${encodeURIComponent(path)}`;
}

/**
 * 生成压缩包下载地址。
 * @param {string[]} paths - 路径列表
 * @returns {string} 下载 URL
 */
export function zipUrl(paths) {
  const joined = paths.map(encodeURIComponent).join(",");
  return `${API_BASE}/files/download-zip?paths=${joined}`;
}

/**
 * 上传小文件。
 * @param {string} directory - 目标目录
 * @param {File} file - 文件对象
 * @param {boolean} overwrite - 是否覆盖
 * @returns {Promise<object>} 新条目元数据
 */
export function uploadFile(directory, file, overwrite) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("overwrite", String(overwrite));
  return requestJson(`/files/upload?path=${encodeURIComponent(directory)}`, {
    method: "POST",
    body: formData,
  });
}

/**
 * 创建文件或符号链接。
 * @param {string} path - 目标路径
 * @param {string|null} linkTarget - 符号链接目标（可空）
 * @returns {Promise<object>} 新条目元数据
 */
export function createFile(path, linkTarget) {
  const payload = { path };
  if (linkTarget !== null && linkTarget !== undefined) {
    payload.linkTarget = linkTarget;
  }
  return requestJson("/files", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/**
 * 创建文件夹。
 * @param {string} path - 目标路径
 * @returns {Promise<object>} 新条目元数据
 */
export function createFolder(path) {
  return requestJson("/folders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
}

/**
 * 删除路径。
 * @param {string} path - 目标路径
 * @param {boolean} recursive - 是否递归删除
 * @param {boolean} followLink - 是否跟随符号链接
 * @returns {Promise<void>}
 */
export function deletePath(path, recursive, followLink) {
  const query = buildQuery({ path, recursive, followLink });
  return requestJson(`/files${query}`, { method: "DELETE" });
}

/**
 * 修改元数据。
 * @param {string} path - 目标路径
 * @param {object} fields - 待修改字段
 * @returns {Promise<object>} 更新后的元数据
 */
export function patchMetadata(path, fields) {
  const query = buildQuery({ path });
  return requestJson(`/files${query}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

/**
 * 搜索文件。
 * @param {object} params - 搜索参数
 * @returns {Promise<object>} { data, meta }
 */
export function searchFiles(params) {
  const query = buildQuery(params);
  return requestJson(`/files/search${query}`);
}

/**
 * 复制路径。
 * @param {string} source - 源路径
 * @param {string} destination - 目标路径
 * @param {boolean} overwrite - 是否覆盖
 * @returns {Promise<object>} 副本元数据
 */
export function copyPath(source, destination, overwrite) {
  return requestJson("/files/copy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source, destination, overwrite }),
  });
}

/**
 * 构造查询字符串。
 * @param {object} params - 参数对象
 * @returns {string} 形如 ?a=b&c=d 的查询串
 */
function buildQuery(params) {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const text = searchParams.toString();
  return text ? `?${text}` : "";
}
