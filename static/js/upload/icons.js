/**
 * 上传面板图标。
 *
 * 使用内联 SVG 绘制暂停、终止与继续图标，颜色继承按钮前景色。
 */

/** SVG 命名空间。 */
const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

/** 图标内容定义。 */
const ICON_CONTENT = {
  pause:
    '<rect x="7" y="6.5" width="3.6" height="11" rx="1"></rect>' +
    '<rect x="13.4" y="6.5" width="3.6" height="11" rx="1"></rect>',
  stop:
    '<path d="M7 7l10 10" stroke="currentColor" stroke-width="2.4" ' +
    'stroke-linecap="round"></path>' +
    '<path d="M17 7L7 17" stroke="currentColor" stroke-width="2.4" ' +
    'stroke-linecap="round"></path>',
  play: '<path d="M8 6.3l9.4 5.7L8 17.7z"></path>',
};

/**
 * 创建指定图标。
 *
 * @param {"pause"|"stop"|"play"} name 图标名称。
 * @returns {SVGElement} SVG 元素。
 */
export function createUploadIcon(name) {
  const svg = document.createElementNS(SVG_NAMESPACE, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.classList.add("upload-action-icon");
  svg.innerHTML = ICON_CONTENT[name] || "";
  return svg;
}
