/**
 * 上传任务内部错误与判定工具。
 */

/** 内部信号：任务进入暂停或冲突状态，当前执行链应静默退出。 */
export class UploadHaltedError extends Error {
  constructor() {
    super("上传任务已暂停");
    this.name = "UploadHaltedError";
  }
}

/**
 * 判断错误是否来自主动中止。
 *
 * @param {*} error 错误对象。
 * @returns {boolean} 是否为中止错误。
 */
export function isAbortError(error) {
  return (
    error !== null &&
    error !== undefined &&
    (error.code === "ABORTED" ||
      error.name === "AbortError" ||
      error.name === "UploadHaltedError")
  );
}

/**
 * 判断错误是否代表同名文件冲突。
 *
 * @param {*} error 错误对象。
 * @returns {boolean} 是否为文件冲突。
 */
export function isFileConflict(error) {
  return (
    error?.code === "FILE_EXISTS" && !`${error.message}`.includes("目录")
  );
}
