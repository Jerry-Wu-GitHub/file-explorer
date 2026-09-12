/**
 * HTTP 客户端。
 *
 * 统一封装 `fetch`，负责：
 *
 * - 拼接 API 前缀；
 * - 解析统一响应外壳 `ApiResponse` / `ErrorResponse`；
 * - 将后端错误转换为携带 `code` / `message` / `details` 的
 *   `ApiError`；
 * - 提供请求超时。
 *
 * 所有其他 `api/*.js` 模块都应通过本模块发起请求。
 */

import { API_PREFIX, REQUEST_TIMEOUT_MILLISECONDS } from "../config.js";
import { BASE_PATH } from "../base-path.js";

/**
 * 业务错误。
 *
 * 由后端返回的 `ErrorResponse` 或网络层错误构造，保留业务错误码、
 * 提示文案与附加详情。
 */
export class ApiError extends Error {
  /**
   * @param {string} code 业务错误码。
   * @param {string} message 错误提示。
   * @param {Object|null} details 附加详情。
   * @param {number} status HTTP 状态码。
   */
  constructor(code, message, details = null, status = 0) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.details = details;
    this.status = status;
  }
}

/**
 * 拼接完整的请求地址。
 *
 * 先应用从 `<base>` 标签推导出的部署路径前缀，再拼接 API 前缀，
 * 使页面在非根路径部署时请求依然指向正确位置。
 *
 * @param {string} path 相对于 API 前缀的路径，以 `/` 开头。
 * @returns {string} 完整 URL。
 */
export function buildApiUrl(path) {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${BASE_PATH}${API_PREFIX}${normalized}`;
}

/**
 * 将查询参数对象序列化为查询字符串。
 *
 * 值为 `undefined` 或 `null` 的键会被忽略；布尔值序列化为
 * `true` / `false`；数组通过重复键的方式表达。
 *
 * @param {Object} parameters 查询参数。
 * @returns {string} 以 `?` 开头的查询字符串，没有参数时返回空串。
 */
export function buildQueryString(parameters) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (value === undefined || value === null) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        search.append(key, String(item));
      }
      continue;
    }
    search.append(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

/**
 * 解析响应体中的错误结构并抛出 `ApiError`。
 *
 * @param {Response} response 原始响应。
 * @returns {Promise<never>} 始终抛出。
 */
async function throwResponseError(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch (parseError) {
    payload = null;
  }

  if (payload && typeof payload.code === "string") {
    throw new ApiError(
      payload.code,
      payload.message || "请求失败",
      payload.details || null,
      response.status
    );
  }

  throw new ApiError(
    "HTTP_ERROR",
    `请求失败：HTTP ${response.status}`,
    null,
    response.status
  );
}

/**
 * 发送请求并解析为 `ApiResponse.data`。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {RequestInit} options `fetch` 选项。
 * @returns {Promise<*>} 业务数据。
 */
async function requestData(path, options) {
  const url = buildApiUrl(path);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MILLISECONDS
  );

  let response;
  try {
    response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (networkError) {
    window.clearTimeout(timeoutId);
    if (networkError.name === "AbortError") {
      throw new ApiError("TIMEOUT", "请求超时", null, 0);
    }
    throw new ApiError(
      "NETWORK_ERROR",
      networkError.message || "网络请求失败",
      null,
      0
    );
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    await throwResponseError(response);
  }

  if (response.status === 204) {
    return null;
  }

  const payload = await response.json();
  if (!payload || typeof payload !== "object") {
    throw new ApiError("INVALID_RESPONSE", "响应格式不正确", null, response.status);
  }
  return payload.data;
}

/**
 * 发送请求并解析为完整的 `ApiResponse`（含 `data` 与 `meta`）。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {RequestInit} options `fetch` 选项。
 * @returns {Promise<{data: *, meta: Object|null}>} 完整响应外壳。
 */
async function requestEnvelope(path, options) {
  const url = buildApiUrl(path);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    REQUEST_TIMEOUT_MILLISECONDS
  );

  let response;
  try {
    response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (networkError) {
    window.clearTimeout(timeoutId);
    if (networkError.name === "AbortError") {
      throw new ApiError("TIMEOUT", "请求超时", null, 0);
    }
    throw new ApiError(
      "NETWORK_ERROR",
      networkError.message || "网络请求失败",
      null,
      0
    );
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    await throwResponseError(response);
  }

  if (response.status === 204) {
    return { data: null, meta: null };
  }

  const payload = await response.json();
  if (!payload || typeof payload !== "object") {
    throw new ApiError("INVALID_RESPONSE", "响应格式不正确", null, response.status);
  }
  return {
    data: payload.data ?? null,
    meta: payload.meta ?? null,
  };
}

/**
 * 发起 GET 请求。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Object} [parameters] 查询参数。
 * @returns {Promise<*>} 业务数据。
 */
export function getData(path, parameters = {}) {
  const query = buildQueryString(parameters);
  return requestData(`${path}${query}`, { method: "GET" });
}

/**
 * 发起 GET 请求并保留 `meta`。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Object} [parameters] 查询参数。
 * @returns {Promise<{data: *, meta: Object|null}>} 完整响应外壳。
 */
export function getEnvelope(path, parameters = {}) {
  const query = buildQueryString(parameters);
  return requestEnvelope(`${path}${query}`, { method: "GET" });
}

/**
 * 发起 POST 请求，请求体为 JSON。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Object} [body] 请求体。
 * @param {Object} [parameters] 查询参数。
 * @returns {Promise<*>} 业务数据。
 */
export function postJson(path, body = {}, parameters = {}) {
  const query = buildQueryString(parameters);
  return requestData(`${path}${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * 发起 PATCH 请求，请求体为 JSON。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Object} [body] 请求体。
 * @param {Object} [parameters] 查询参数。
 * @returns {Promise<*>} 业务数据。
 */
export function patchJson(path, body = {}, parameters = {}) {
  const query = buildQueryString(parameters);
  return requestData(`${path}${query}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * 发起 DELETE 请求。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Object} [parameters] 查询参数。
 * @returns {Promise<*>} 业务数据或 `null`。
 */
export function deleteRequest(path, parameters = {}) {
  const query = buildQueryString(parameters);
  return requestData(`${path}${query}`, { method: "DELETE" });
}

/**
 * 发起 multipart/form-data 的 POST 请求。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {FormData} formData 表单数据。
 * @param {Object} [parameters] 查询参数。
 * @returns {Promise<*>} 业务数据。
 */
export function postFormData(path, formData, parameters = {}) {
  const query = buildQueryString(parameters);
  return requestData(`${path}${query}`, {
    method: "POST",
    body: formData,
  });
}

/**
 * 发起 PUT 请求，请求体为二进制内容。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Blob|ArrayBuffer} content 请求体。
 * @param {Object} [headers] 附加请求头。
 * @returns {Promise<*>} 业务数据。
 */
export function putBinary(path, content, headers = {}) {
  return requestData(path, {
    method: "PUT",
    headers: {
      "Content-Type": "application/octet-stream",
      ...headers,
    },
    body: content,
  });
}

/**
 * 返回资源的完整下载链接（用于分享、<a download> 等场景）。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Object} [parameters] 查询参数。
 * @returns {string} 完整 URL。
 */
export function buildDownloadUrl(path, parameters = {}) {
  return `${buildApiUrl(path)}${buildQueryString(parameters)}`;
}
