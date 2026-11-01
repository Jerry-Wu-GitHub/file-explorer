/**
 * 带进度回调与中止能力的上传请求。
 *
 * `fetch` 无法暴露上传进度，本模块使用 `XMLHttpRequest` 发送
 * multipart 表单或二进制分片，同时保持与 `client.js` 一致的
 * `ApiResponse` 解析与 `ApiError` 错误结构。
 */

import { REQUEST_TIMEOUT_MILLISECONDS } from "../config.js";
import { ApiError, buildApiUrl, buildQueryString } from "./client.js";

class ProgressRequest {
  /**
   * @param {string} method HTTP 方法。
   * @param {string} path 相对于 API 前缀的路径。
   * @param {FormData|Blob|ArrayBuffer} body 请求体。
   * @param {Object} headers 请求头。
   * @param {Object} parameters 查询参数。
   * @param {Object} options 可选参数。
   * @param {(loaded: number, total: number) => void} [options.onProgress] 进度回调。
   * @param {AbortSignal} [options.signal] 中止信号。
   */
  constructor(method, path, body, headers, parameters, options) {
    this.method = method;
    this.url = `${buildApiUrl(path)}${buildQueryString(parameters)}`;
    this.body = body;
    this.headers = headers;
    this.options = options;
    this.request = null;
    this.resolve = null;
    this.reject = null;
    this.signalAbortHandler = () => this.abort();
  }

  /**
   * 发送请求。
   *
   * @returns {Promise<*>} 后端 `ApiResponse.data`。
   */
  send() {
    return new Promise((resolve, reject) => {
      this.resolve = resolve;
      this.reject = reject;

      const request = new XMLHttpRequest();
      this.request = request;
      request.open(this.method, this.url);
      request.timeout = REQUEST_TIMEOUT_MILLISECONDS;
      for (const [name, value] of Object.entries(this.headers)) {
        if (value !== undefined && value !== null) {
          request.setRequestHeader(name, String(value));
        }
      }

      request.upload?.addEventListener(
        "progress",
        (event) => this.handleUploadProgress(event)
      );
      request.addEventListener("load", () => this.handleLoad());
      request.addEventListener("error", () => this.handleError());
      request.addEventListener("abort", () => this.handleAbort());
      request.addEventListener("timeout", () => this.handleTimeout());

      if (this.options.signal) {
        if (this.options.signal.aborted) {
          this.handleAbort();
          return;
        }
        this.options.signal.addEventListener(
          "abort",
          this.signalAbortHandler,
          { once: true }
        );
      }

      request.send(this.body);
    });
  }

  /**
   * 处理上传进度。
   *
   * @param {ProgressEvent} event 进度事件。
   */
  handleUploadProgress(event) {
    if (typeof this.options.onProgress !== "function") {
      return;
    }
    const total = event.lengthComputable ? event.total : 0;
    this.options.onProgress(event.loaded, total);
  }

  /**
   * 处理请求完成。
   */
  handleLoad() {
    const request = this.request;
    this.cleanup();
    if (!request) {
      return;
    }

    let payload = null;
    try {
      payload = request.responseText ? JSON.parse(request.responseText) : null;
    } catch {
      payload = null;
    }

    if (request.status >= 200 && request.status < 300) {
      if (request.status === 204) {
        this.resolve(null);
        return;
      }
      if (!payload || typeof payload !== "object") {
        this.reject(
          new ApiError(
            "INVALID_RESPONSE",
            "响应格式不正确",
            null,
            request.status
          )
        );
        return;
      }
      this.resolve(payload.data);
      return;
    }

    if (payload && typeof payload.code === "string") {
      this.reject(
        new ApiError(
          payload.code,
          payload.message || "请求失败",
          payload.details || null,
          request.status
        )
      );
      return;
    }

    this.reject(
      new ApiError(
        "HTTP_ERROR",
        `请求失败：HTTP ${request.status}`,
        null,
        request.status
      )
    );
  }

  /**
   * 处理网络错误。
   */
  handleError() {
    this.cleanup();
    this.reject(new ApiError("NETWORK_ERROR", "网络请求失败", null, 0));
  }

  /**
   * 处理主动中止。
   */
  handleAbort() {
    this.cleanup();
    this.reject(new ApiError("ABORTED", "上传请求已中止", null, 0));
  }

  /**
   * 处理超时。
   */
  handleTimeout() {
    this.cleanup();
    this.reject(new ApiError("TIMEOUT", "请求超时", null, 0));
  }

  /**
   * 中止底层请求。
   */
  abort() {
    this.request?.abort();
  }

  /**
   * 清理 signal 监听。
   */
  cleanup() {
    if (this.options.signal) {
      this.options.signal.removeEventListener(
        "abort",
        this.signalAbortHandler
      );
    }
  }
}

/**
 * 使用 multipart/form-data 上传并报告进度。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {FormData} formData 表单数据。
 * @param {Object} parameters 查询参数。
 * @param {Object} [options] 进度与中止选项。
 * @returns {Promise<*>} 业务数据。
 */
export function uploadFormDataWithProgress(
  path,
  formData,
  parameters = {},
  options = {}
) {
  return new ProgressRequest(
    "POST",
    path,
    formData,
    {},
    parameters,
    options
  ).send();
}

/**
 * 使用 PUT 上传二进制内容并报告进度。
 *
 * @param {string} path 相对于 API 前缀的路径。
 * @param {Blob|ArrayBuffer} content 请求体。
 * @param {Object} [headers] 附加请求头。
 * @param {Object} [options] 进度与中止选项。
 * @returns {Promise<*>} 业务数据。
 */
export function uploadBinaryWithProgress(
  path,
  content,
  headers = {},
  options = {}
) {
  return new ProgressRequest(
    "PUT",
    path,
    content,
    { "Content-Type": "application/octet-stream", ...headers },
    {},
    options
  ).send();
}
