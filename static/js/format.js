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
