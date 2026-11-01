/**
 * 上传任务数据模型。
 *
 * 一个任务对应一次用户操作：上传单个小文件、分片上传单个大文件，
 * 或一次上传多个文件 / 文件夹。任务保存进度、速度、冲突与请求控制
 * 器等运行时状态，供调度器与面板读取。
 */

import { getFilename } from "./path-helpers.js";
import { SpeedTracker } from "./speed-tracker.js";
import { TASK_STATUS, TASK_KIND } from "./upload-status.js";

/** 自增任务序号。 */
let nextTaskSequence = 1;

export class UploadTask {
  /**
   * @param {Object} options 构造参数。
   * @param {Array<{file: File, relativePath: string}>} options.entries 上传条目。
   * @param {string} options.targetDirectory 目标目录虚拟路径。
   * @param {string} options.kind 任务类型。
   */
  constructor(options) {
    this.id = `upload-task-${nextTaskSequence}`;
    nextTaskSequence += 1;

    this.kind = options.kind;
    this.entries = options.entries;
    this.targetDirectory = options.targetDirectory;
    this.totalFiles = options.entries.length;
    this.totalBytes = options.entries.reduce(
      (total, entry) => total + entry.file.size,
      0
    );

    this.status = TASK_STATUS.PENDING;
    this.currentIndex = 0;
    this.completedFiles = 0;
    this.completedBytes = 0;
    this.skippedFiles = 0;
    this.skippedBytes = 0;
    this.failedFiles = 0;
    this.failedBytes = 0;
    this.currentBaseBytes = 0;
    this.overwriteCurrentFile = false;
    this.conflict = null;
    this.error = null;
    this.currentPhase = "";

    this.directoriesEnsured = false;
    this.running = false;
    this.resumePending = false;
    this.session = null;

    /** @type {Map<number|string, number>} 正在传输的字节数。 */
    this.inFlightBytes = new Map();
    /** @type {Set<AbortController>} 当前活跃请求的中止控制器。 */
    this.controllers = new Set();
    /** @type {SpeedTracker} */
    this.speedTracker = new SpeedTracker(this.totalBytes);

    this.createdAt = Date.now();
    this.finishedAt = null;

    this.notify = () => {};
    this.onConflict = () => {};
    this.onFinished = () => {};
  }

  /**
   * 当前正在处理的条目。
   *
   * @returns {{file: File, relativePath: string}|null} 当前条目。
   */
  getCurrentEntry() {
    return this.entries[this.currentIndex] || null;
  }

  /**
   * 任务的展示名称。
   *
   * @returns {string} 单文件为文件名；批量上传为文件夹名或文件数量。
   */
  getDisplayName() {
    if (this.kind !== TASK_KIND.BATCH) {
      return getFilename(this.entries[0]?.relativePath || "");
    }
    const firstPath = this.entries[0]?.relativePath || "";
    if (firstPath.includes("/")) {
      const root = firstPath.split("/")[0];
      const sameRoot = this.entries.every((entry) =>
        entry.relativePath.startsWith(`${root}/`)
      );
      if (sameRoot) {
        return `文件夹 ${root}`;
      }
    }
    return `${this.totalFiles} 个文件`;
  }

  /**
   * 当前已上传字节数，包含已完成文件、已确认分片与进行中的请求。
   *
   * @returns {number} 字节数。
   */
  getUploadedBytes() {
    let inFlight = 0;
    for (const bytes of this.inFlightBytes.values()) {
      inFlight += bytes;
    }
    const total = this.completedBytes + this.currentBaseBytes + inFlight;
    return Math.min(this.totalBytes, Math.max(0, total));
  }

  /**
   * 剩余字节数。
   *
   * @returns {number} 字节数。
   */
  getRemainingBytes() {
    const processedBytes =
      this.getUploadedBytes() + this.skippedBytes + this.failedBytes;
    return Math.max(0, this.totalBytes - processedBytes);
  }

  /**
   * 添加上传请求的中止控制器。
   *
   * @param {AbortController} controller 控制器。
   */
  addController(controller) {
    this.controllers.add(controller);
  }

  /**
   * 移除上传请求的中止控制器。
   *
   * @param {AbortController} controller 控制器。
   */
  removeController(controller) {
    this.controllers.delete(controller);
  }

  /**
   * 中止当前所有上传请求。
   */
  abortActiveRequests() {
    for (const controller of this.controllers) {
      controller.abort();
    }
    this.controllers.clear();
  }
}
