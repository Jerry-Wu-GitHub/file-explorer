/**
 * 下拉菜单工具。
 *
 * 提供菜单的显示、隐藏、定位，以及「点击菜单或锚点之外时自动关闭」
 * 的全局行为。`toolbar.js` 与后续的 `context-menu.js` 复用本模块。
 *
 * 使用约定：菜单元素带有 `hidden` 属性表示未展示；锚点按钮可选带
 * `aria-expanded` 属性，本模块会自动维护其值。
 */

/** 当前处于打开状态的菜单条目。 */
const openMenus = new Set();

/**
 * 显示菜单。
 *
 * 先关闭其他所有已打开的菜单，再定位并显示目标菜单。
 *
 * @param {HTMLElement} menu 菜单元素。
 * @param {HTMLElement} anchor 锚点元素（按钮）。
 */
export function showDropdown(menu, anchor) {
  hideAllDropdowns();
  positionDropdown(menu, anchor);
  menu.hidden = false;
  anchor?.setAttribute("aria-expanded", "true");
  openMenus.add({ menu, anchor });
}

/**
 * 隐藏指定菜单。
 *
 * @param {HTMLElement} menu 菜单元素。
 */
export function hideDropdown(menu) {
  menu.hidden = true;
  for (const item of [...openMenus]) {
    if (item.menu === menu) {
      item.anchor?.setAttribute("aria-expanded", "false");
      openMenus.delete(item);
    }
  }
}

/**
 * 关闭所有已打开的菜单。
 */
export function hideAllDropdowns() {
  for (const item of openMenus) {
    item.menu.hidden = true;
    item.anchor?.setAttribute("aria-expanded", "false");
  }
  openMenus.clear();
}

/**
 * 切换菜单的显示状态。
 *
 * @param {HTMLElement} menu 菜单元素。
 * @param {HTMLElement} anchor 锚点元素。
 */
export function toggleDropdown(menu, anchor) {
  if (menu.hidden) {
    showDropdown(menu, anchor);
  } else {
    hideDropdown(menu);
  }
}

/**
 * 将菜单定位到锚点下方。
 *
 * 若菜单右侧超出视口，向左平移避免溢出。
 *
 * @param {HTMLElement} menu 菜单元素。
 * @param {HTMLElement} anchor 锚点元素。
 */
export function positionDropdown(menu, anchor) {
  const anchorRect = anchor.getBoundingClientRect();
  menu.style.left = `${anchorRect.left}px`;
  menu.style.top = `${anchorRect.bottom + 4}px`;
  window.requestAnimationFrame(() => {
    const menuRect = menu.getBoundingClientRect();
    if (menuRect.right > window.innerWidth - 8) {
      const shifted = Math.max(8, window.innerWidth - menuRect.width - 8);
      menu.style.left = `${shifted}px`;
    }
  });
}

document.addEventListener("click", (event) => {
  const target = event.target;
  for (const item of [...openMenus]) {
    if (item.menu.contains(target)) continue;
    if (item.anchor && item.anchor.contains(target)) continue;
    hideDropdown(item.menu);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    hideAllDropdowns();
  }
});
