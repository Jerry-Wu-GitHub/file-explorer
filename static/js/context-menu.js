/**
 * 右键上下文菜单。
 *
 * 提供空白区域菜单与条目菜单。菜单内容根据上下文动态构建，
 * 展示后点击外部或按 Escape 关闭。菜单操作通过 `onAction` 回调
 * 交由 `main.js` 协调。
 *
 * 子菜单在当前菜单内展开，避免嵌套定位的复杂性；通过「排序方式」
 * 与「新建」两个入口触发。
 */

/** 回调集合，由 `initializeContextMenu` 注入。 */
let callbacks = {
  onAction: () => {},
  hasClipboard: () => false,
  getSelectedEntries: () => [],
};

/** 是否已初始化。 */
let initialized = false;

/** 当前展示的菜单元素。 */
let activeMenu = null;

/**
 * 关闭当前菜单。
 */
export function closeContextMenu() {
  if (activeMenu) {
    activeMenu.remove();
    activeMenu = null;
  }
}

/**
 * 判断节点是否位于菜单内部。
 *
 * @param {Node} node 目标节点。
 * @returns {boolean} 是否在菜单内。
 */
function isInsideMenu(node) {
  return activeMenu !== null && activeMenu.contains(node);
}

/**
 * 将菜单定位到视口内指定坐标。
 *
 * 若菜单右侧或底部超出视口，会自动向左/向上平移。
 *
 * @param {HTMLElement} menu 菜单元素。
 * @param {number} clientX 鼠标 X 坐标。
 * @param {number} clientY 鼠标 Y 坐标。
 */
function positionMenu(menu, clientX, clientY) {
  menu.style.position = "fixed";
  menu.style.left = "0px";
  menu.style.top = "0px";
  menu.style.visibility = "hidden";
  document.body.appendChild(menu);

  const rect = menu.getBoundingClientRect();
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;

  let left = clientX;
  let top = clientY;
  if (left + rect.width > viewportWidth - 8) {
    left = Math.max(8, viewportWidth - rect.width - 8);
  }
  if (top + rect.height > viewportHeight - 8) {
    top = Math.max(8, viewportHeight - rect.height - 8);
  }

  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.visibility = "";
}

/**
 * 构建菜单项 DOM。
 *
 * @param {Object} item 菜单项描述。
 * @param {Object} context 打开菜单时的上下文。
 * @returns {HTMLElement} 菜单项元素。
 */
function buildMenuItem(item, context) {
  if (item.type === "separator") {
    const separator = document.createElement("div");
    separator.className = "menu-separator";
    return separator;
  }

  if (item.type === "submenu") {
    return buildSubmenu(item, context);
  }

  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("role", "menuitem");
  if (item.action) {
    button.dataset.menuAction = item.action;
  }
  if (item.sortField) {
    button.dataset.sortField = item.sortField;
  }
  if (item.sortDirection) {
    button.dataset.sortDirection = item.sortDirection;
  }
  if (item.danger) {
    button.classList.add("danger");
  }
  if (item.disabled) {
    button.disabled = true;
  }
  button.textContent = item.label;
  return button;
}

/**
 * 构建子菜单。
 *
 * @param {Object} item 子菜单描述。
 * @param {Object} context 打开菜单时的上下文。
 * @returns {HTMLElement} 子菜单容器。
 */
function buildSubmenu(item, context) {
  const wrapper = document.createElement("div");
  wrapper.className = "context-menu__submenu-wrapper";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "context-menu__submenu-trigger";
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");
  trigger.textContent = item.label;

  const caret = document.createElement("span");
  caret.className = "caret";
  caret.textContent = "\u25B8";
  trigger.appendChild(caret);

  const submenu = document.createElement("div");
  submenu.className = "context-menu__submenu";
  submenu.setAttribute("role", "menu");
  submenu.hidden = true;
  for (const child of item.items) {
    submenu.appendChild(buildMenuItem(child, context));
  }

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const willExpand = submenu.hidden;
    submenu.hidden = !willExpand;
    trigger.setAttribute("aria-expanded", String(willExpand));
  });

  wrapper.append(trigger, submenu);
  return wrapper;
}

/**
 * 构建菜单根元素。
 *
 * @param {Object[]} items 菜单项列表。
 * @param {Object} context 打开菜单时的上下文。
 * @returns {HTMLElement} 菜单元素。
 */
function buildMenu(items, context) {
  const menu = document.createElement("div");
  menu.className = "context-menu";
  menu.setAttribute("role", "menu");
  for (const item of items) {
    menu.appendChild(buildMenuItem(item, context));
  }
  return menu;
}

/**
 * 绑定菜单的点击派发。
 *
 * @param {HTMLElement} menu 菜单元素。
 * @param {Object} context 打开菜单时的上下文。
 */
function attachMenuHandlers(menu, context) {
  menu.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-menu-action]");
    if (!button) {
      return;
    }
    event.stopPropagation();
    const action = button.dataset.menuAction;
    const actionData = { ...button.dataset };
    delete actionData.menuAction;
    closeContextMenu();
    callbacks.onAction(action, actionData, context);
  });
}

/**
 * 构建空白区域菜单项。
 *
 * @returns {Object[]} 菜单项描述数组。
 */
function buildBlankMenuItems() {
  return [
    { action: "refresh", label: "刷新" },
    {
      type: "submenu",
      label: "排序方式",
      items: [
        { sortField: "name", sortDirection: "asc", action: "sort", label: "名称（升序）" },
        { sortField: "name", sortDirection: "desc", action: "sort", label: "名称（降序）" },
        { sortField: "size", sortDirection: "asc", action: "sort", label: "大小（升序）" },
        { sortField: "size", sortDirection: "desc", action: "sort", label: "大小（降序）" },
        { sortField: "modifiedAt", sortDirection: "asc", action: "sort", label: "修改时间（升序）" },
        { sortField: "modifiedAt", sortDirection: "desc", action: "sort", label: "修改时间（降序）" },
      ],
    },
    { action: "paste", label: "粘贴", disabled: !callbacks.hasClipboard() },
    {
      type: "submenu",
      label: "新建",
      items: [
        { action: "new-folder", label: "文件夹" },
        { action: "new-file", label: "文件" },
        { action: "new-symlink", label: "符号链接" },
      ],
    },
    { action: "properties-blank", label: "属性" },
  ];
}

/**
 * 构建条目菜单项。
 *
 * @param {number} count 选中条目数量。
 * @returns {Object[]} 菜单项描述数组。
 */
function buildEntryMenuItems(count) {
  const singleSelection = count === 1;
  return [
    { action: "cut", label: "剪切" },
    { action: "copy", label: "复制" },
    { action: "download", label: "下载" },
    { action: "download-zip", label: "下载压缩包" },
    { type: "separator" },
    { action: "rename", label: "重命名", disabled: !singleSelection },
    { action: "delete", label: "删除", danger: true },
    { type: "separator" },
    { action: "properties-entry", label: "属性" },
  ];
}

/**
 * 展示空白区域右键菜单。
 *
 * @param {MouseEvent} event 右键事件。
 */
export function showBlankContextMenu(event) {
  closeContextMenu();
  const context = { kind: "blank" };
  const menu = buildMenu(buildBlankMenuItems(), context);
  attachMenuHandlers(menu, context);
  positionMenu(menu, event.clientX, event.clientY);
  activeMenu = menu;
}

/**
 * 展示条目右键菜单。
 *
 * @param {MouseEvent} event 右键事件。
 * @param {Object[]} selectedEntries 当前选中的条目。
 */
export function showEntryContextMenu(event, selectedEntries) {
  closeContextMenu();
  const context = { kind: "entry", entries: selectedEntries };
  const menu = buildMenu(
    buildEntryMenuItems(selectedEntries.length),
    context
  );
  attachMenuHandlers(menu, context);
  positionMenu(menu, event.clientX, event.clientY);
  activeMenu = menu;
}

/**
 * 初始化上下文菜单。
 *
 * @param {Object} [options] 回调集合。
 * @param {(action: string, data: Object, context: Object) => void} [options.onAction] 菜单操作处理。
 * @param {() => boolean} [options.hasClipboard] 是否有剪贴板内容。
 * @param {() => Object[]} [options.getSelectedEntries] 获取当前选中条目。
 */
export function initializeContextMenu(options = {}) {
  if (initialized) {
    return;
  }
  initialized = true;
  callbacks = { ...callbacks, ...options };

  document.addEventListener("click", (event) => {
    if (!activeMenu) {
      return;
    }
    if (isInsideMenu(event.target)) {
      return;
    }
    closeContextMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeContextMenu();
    }
  });

  window.addEventListener("blur", () => {
    closeContextMenu();
  });

  document.addEventListener("scroll", () => {
    closeContextMenu();
  }, true);
}
