/**
 * 共享 DOM 元素缓存。
 */

/** 元素引用映射 */
export const elements = {};

/**
 * 缓存指定 ID 的 DOM 元素。
 * @param {string[]} ids - 元素 ID 列表
 */
export function cacheElements(ids) {
  for (const id of ids) {
    elements[id] = document.getElementById(id);
  }
}

/**
 * 获取已缓存的 DOM 元素。
 * @param {string} id - 元素 ID
 * @returns {HTMLElement} DOM 元素
 */
export function getElement(id) {
  return elements[id];
}
