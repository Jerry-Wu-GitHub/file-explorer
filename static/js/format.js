/**
 * 通用格式化函数。
 *
 * 提供文件大小、时间戳等展示格式化。
 */

/** 大小单位。 */
const SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"];

/**
 * 将字节数格式化为人类可读字符串。
 *
 * @param {number} bytes 字节数。
 * @returns {string} 格式化结果，例如 `1.2 MB`。
 */
export function formatSize(bytes) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  const exponent = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    SIZE_UNITS.length - 1
  );
  const scaled = value / Math.pow(1024, exponent);
  const precision = exponent === 0 ? 0 : 1;
  return `${scaled.toFixed(precision)} ${SIZE_UNITS[exponent]}`;
}

/**
 * 将 Unix 时间戳（秒）格式化为本地日期时间字符串。
 *
 * @param {number} timestamp 秒级时间戳。
 * @returns {string} 本地化时间字符串。
 */
export function formatTimestamp(timestamp) {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) {
    return "—";
  }
  const date = new Date(value * 1000);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  const second = String(date.getSeconds()).padStart(2, "0");
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

/**
 * 将持续时间格式化为紧凑的中文时长。
 *
 * @param {number} seconds 持续秒数。
 * @returns {string} 格式化结果，例如 `2 分 03 秒`。
 */
export function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) {
    return "—";
  }
  const totalSeconds = Math.floor(value);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainSeconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours} 时 ${String(minutes).padStart(2, "0")} 分`;
  }
  if (minutes > 0) {
    return `${minutes} 分 ${String(remainSeconds).padStart(2, "0")} 秒`;
  }
  return `${remainSeconds} 秒`;
}

/**
 * 将每秒字节数格式化为带单位的速度。
 *
 * @param {number} bytesPerSecond 每秒字节数。
 * @returns {string} 格式化结果，例如 `1.2 MB/s`。
 */
export function formatSpeed(bytesPerSecond) {
  const value = Number(bytesPerSecond);
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B/s";
  }
  return `${formatSize(value)}/s`;
}

/**
 * 将百分比格式化为一位小数。
 *
 * @param {number} percent 百分比数值。
 * @returns {string} 格式化结果，例如 `42.3%`。
 */
export function formatPercent(percent) {
  const value = Number(percent);
  if (!Number.isFinite(value) || value <= 0) {
    return "0%";
  }
  const clamped = Math.min(value, 100);
  if (clamped < 0.1) {
    return "<0.1%";
  }
  return `${clamped.toFixed(1)}%`;
}

/**
 * 将剩余秒数格式化为预计剩余时间。
 *
 * @param {number} seconds 预计剩余秒数，非有限值时显示破折号。
 * @returns {string} 格式化结果。
 */
export function formatRemainingTime(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) {
    return "—";
  }
  return formatDuration(value);
}
