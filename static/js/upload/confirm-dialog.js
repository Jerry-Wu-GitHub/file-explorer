/**
 * 通用确认弹窗。
 *
 * 基于页面中的 `#confirm-modal`，返回用户是否确认的 Promise。
 * 支持 Escape 与点击遮罩取消。
 */

/** @type {((value: boolean) => void)|null} */
let pendingResolver = null;

/** 是否已绑定事件。 */
let initialized = false;

/**
 * 关闭弹窗并返回结果。
 *
 * @param {boolean} result 用户选择。
 */
function closeDialog(result) {
  const modal = document.getElementById("confirm-modal");
  modal?.classList.add("hidden");
  const resolver = pendingResolver;
  pendingResolver = null;
  if (resolver) {
    resolver(result);
  }
}

/**
 * 处理确认按钮点击。
 */
function handleConfirm() {
  closeDialog(true);
}

/**
 * 处理取消按钮点击。
 */
function handleCancel() {
  closeDialog(false);
}

/**
 * 处理键盘事件。
 *
 * @param {KeyboardEvent} event 键盘事件。
 */
function handleKeydown(event) {
  if (event.key === "Escape" && pendingResolver) {
    event.preventDefault();
    closeDialog(false);
  }
}

/**
 * 初始化确认弹窗事件。
 */
export function initializeConfirmDialog() {
  if (initialized) {
    return;
  }
  initialized = true;
  document
    .getElementById("confirm-accept-button")
    ?.addEventListener("click", handleConfirm);
  document
    .getElementById("confirm-cancel-button")
    ?.addEventListener("click", handleCancel);
  document
    .getElementById("confirm-close-button")
    ?.addEventListener("click", handleCancel);
  document
    .getElementById("confirm-modal")
    ?.addEventListener("click", (event) => {
      if (event.target.id === "confirm-modal") {
        handleCancel();
      }
    });
  document.addEventListener("keydown", handleKeydown);
}

/**
 * 展示确认弹窗。
 *
 * @param {Object} options 弹窗内容。
 * @param {string} options.title 标题。
 * @param {string} options.message 说明文字。
 * @param {string} [options.confirmLabel] 确认按钮文案。
 * @param {string} [options.cancelLabel] 取消按钮文案。
 * @param {boolean} [options.danger] 是否使用危险色。
 * @returns {Promise<boolean>} 用户是否确认。
 */
export function showConfirmDialog(options) {
  initializeConfirmDialog();
  if (pendingResolver) {
    closeDialog(false);
  }

  const modal = document.getElementById("confirm-modal");
  const title = document.getElementById("confirm-title");
  const message = document.getElementById("confirm-message");
  const acceptButton = document.getElementById("confirm-accept-button");
  const cancelButton = document.getElementById("confirm-cancel-button");
  if (!modal || !title || !message || !acceptButton || !cancelButton) {
    return Promise.resolve(window.confirm(options.message));
  }

  title.textContent = options.title || "请确认";
  message.textContent = options.message || "";
  acceptButton.textContent = options.confirmLabel || "确定";
  cancelButton.textContent = options.cancelLabel || "取消";
  acceptButton.classList.toggle("danger", Boolean(options.danger));
  modal.classList.remove("hidden");

  return new Promise((resolve) => {
    pendingResolver = resolve;
    acceptButton.focus();
  });
}
