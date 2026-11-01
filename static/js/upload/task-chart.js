/**
 * 上传任务速度曲线。
 *
 * 使用内联 SVG 绘制从任务开始到当前的瞬时上传速度，暂停阶段会落到
 * 0，从而形成直观的速度变化轨迹。
 */

import { formatSpeed } from "../format.js";

const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
const CHART_WIDTH = 260;
const CHART_HEIGHT = 52;
const HORIZONTAL_PADDING = 2;
const VERTICAL_PADDING = 4;

/**
 * 将采样点映射为 SVG 坐标。
 *
 * @param {Array<{seconds: number, speed: number}>} samples 采样点。
 * @param {number} duration 总时长（秒）。
 * @param {number} maxSpeed 最大速度（字节/秒）。
 * @returns {Array<{x: number, y: number}>} 坐标点。
 */
function buildPoints(samples, duration, maxSpeed) {
  const usableWidth = CHART_WIDTH - HORIZONTAL_PADDING * 2;
  const usableHeight = CHART_HEIGHT - VERTICAL_PADDING * 2;
  return samples.map((sample) => ({
    x: HORIZONTAL_PADDING + (sample.seconds / duration) * usableWidth,
    y:
      CHART_HEIGHT -
      VERTICAL_PADDING -
      (sample.speed / maxSpeed) * usableHeight,
  }));
}

/**
 * 构造面积路径。
 *
 * @param {Array<{x: number, y: number}>} points 坐标点。
 * @returns {string} SVG path 的 d 属性。
 */
function buildAreaPath(points) {
  if (points.length === 0) {
    return "";
  }
  const first = points[0];
  const last = points[points.length - 1];
  const line = points
    .map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`)
    .join(" ");
  const bottom = CHART_HEIGHT - VERTICAL_PADDING;
  return (
    `M ${first.x.toFixed(2)} ${bottom} L ${line.replace(
      /,/g,
      " "
    )} L ${last.x.toFixed(2)} ${bottom} Z`
  );
}

/**
 * 构造折线路径。
 *
 * @param {Array<{x: number, y: number}>} points 坐标点。
 * @returns {string} SVG path 的 d 属性。
 */
function buildLinePath(points) {
  return points
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(
          2
        )}`
    )
    .join(" ");
}

/**
 * 创建速度曲线元素。
 *
 * @param {Array<{seconds: number, speed: number}>} samples 速度采样点。
 * @returns {HTMLElement} 图表容器。
 */
export function renderSpeedChart(samples) {
  const container = document.createElement("div");
  container.className = "upload-task__chart";

  const label = document.createElement("div");
  label.className = "upload-task__chart-label";
  const peakSpeed = samples.reduce(
    (peak, sample) => Math.max(peak, sample.speed),
    0
  );
  label.textContent = `上传速度曲线 · 峰值 ${formatSpeed(peakSpeed)}`;
  container.appendChild(label);

  const svg = document.createElementNS(SVG_NAMESPACE, "svg");
  svg.setAttribute("viewBox", `0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.classList.add("upload-task__chart-svg");
  container.appendChild(svg);

  if (samples.length < 2) {
    const placeholder = document.createElement("div");
    placeholder.className = "upload-task__chart-empty";
    placeholder.textContent = "正在采集速度数据…";
    container.appendChild(placeholder);
    return container;
  }

  const duration = Math.max(samples[samples.length - 1].seconds, 1);
  const maxSpeed = Math.max(peakSpeed, 1);
  const points = buildPoints(samples, duration, maxSpeed);

  const area = document.createElementNS(SVG_NAMESPACE, "path");
  area.setAttribute("d", buildAreaPath(points));
  area.classList.add("upload-task__chart-area");

  const line = document.createElementNS(SVG_NAMESPACE, "path");
  line.setAttribute("d", buildLinePath(points));
  line.classList.add("upload-task__chart-line");

  svg.append(area, line);
  return container;
}
