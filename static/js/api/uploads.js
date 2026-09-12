/**
 * 分片上传 API 封装。
 *
 * 对后端 `/api/v1/files/uploads` 下五个接口的薄封装。分片切分、
 * 并发调度、重试等编排逻辑位于 `uploader.js`，本模块只负责参数
 * 整形与调用 `client.js`。
 */

import {
  deleteRequest,
  getData,
  postJson,
  putBinary,
} from "./client.js";

/** 分片上传接口的 API 路径。 */
const UPLOADS_PATH = "/files/uploads";

/**
 * 初始化分片上传会话。
 *
 * @param {Object} request 初始化请求体。
 * @param {string} request.path 目标文件的沙箱虚拟路径。
 * @param {number} request.size 文件总字节数。
 * @param {number} [request.chunkSize] 分片大小。
 * @param {boolean} [request.overwrite] 目标已存在时是否覆盖。
 * @param {Object|null} [request.checksum] 整体校验信息。
 * @returns {Promise<Object>} 会话信息。
 */
export function initializeUpload(request) {
  return postJson(UPLOADS_PATH, request);
}

/**
 * 查询上传会话状态。
 *
 * @param {string} uploadId 上传会话 ID。
 * @returns {Promise<Object>} 会话状态。
 */
export function getUploadStatus(uploadId) {
  return getData(`${UPLOADS_PATH}/${encodeURIComponent(uploadId)}`);
}

/**
 * 上传单个分片。
 *
 * @param {string} uploadId 上传会话 ID。
 * @param {number} chunkNumber 分片编号，从 0 开始。
 * @param {Blob|ArrayBuffer} content 分片二进制内容。
 * @param {Object} [options] 可选请求头。
 * @param {string} [options.contentMd5] `Content-MD5` 头值。
 * @param {string} [options.chunkSha256] `X-Chunk-SHA256` 头值。
 * @returns {Promise<Object>} 分片上传结果。
 */
export function uploadChunk(uploadId, chunkNumber, content, options = {}) {
  const headers = {};
  if (options.contentMd5) {
    headers["Content-MD5"] = options.contentMd5;
  }
  if (options.chunkSha256) {
    headers["X-Chunk-SHA256"] = options.chunkSha256;
  }
  return putBinary(
    `${UPLOADS_PATH}/${encodeURIComponent(uploadId)}/chunks/${chunkNumber}`,
    content,
    headers
  );
}

/**
 * 完成分片上传。
 *
 * @param {string} uploadId 上传会话 ID。
 * @param {Object} [options] 可选参数。
 * @param {Object|null} [options.checksum] 整体校验信息。
 * @returns {Promise<Object>} 最终文件的元数据。
 */
export function completeUpload(uploadId, options = {}) {
  const body = {};
  if (options.checksum) {
    body.checksum = options.checksum;
  }
  return postJson(
    `${UPLOADS_PATH}/${encodeURIComponent(uploadId)}/complete`,
    body
  );
}

/**
 * 取消分片上传会话。
 *
 * 幂等：会话不存在或已过期时同样返回成功（后端返回 204）。
 *
 * @param {string} uploadId 上传会话 ID。
 * @returns {Promise<null>} 无响应体。
 */
export function cancelUpload(uploadId) {
  return deleteRequest(`${UPLOADS_PATH}/${encodeURIComponent(uploadId)}`);
}
