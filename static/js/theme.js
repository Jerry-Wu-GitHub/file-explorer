/**
 * 主题与强调色管理。
 *
 * 主题保存在 `localStorage`，并写入 `<html data-theme="...">`。
 * 强调色通过覆盖 `--accent` CSS 变量生效。首次加载时若未保存过
 * 主题，使用配置中的默认值（跟随系统）。
 */

import {
  DEFAULT_ACCENT_COLOR,
  DEFAULT_THEME,
  STORAGE_KEY_ACCENT_COLOR,
  STORAGE_KEY_THEME,
  SUPPORTED_THEMES,
  THEME_SYSTEM,
} from "./config.js";

/** 系统暗色偏好媒体查询，用于监听系统主题变化。 */
const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

/**
 * 从本地存储读取主题；值不合法时回退到默认值。
 *
 * @returns {string} 主题标识。
 */
export function readStoredTheme() {
  const stored = window.localStorage.getItem(STORAGE_KEY_THEME);
  if (stored && SUPPORTED_THEMES.includes(stored)) {
    return stored;
  }
  return DEFAULT_THEME;
}

/**
 * 从本地存储读取强调色；空值时回退到默认强调色。
 *
 * @returns {string} 十六进制颜色字符串。
 */
export function readStoredAccentColor() {
  const stored = window.localStorage.getItem(STORAGE_KEY_ACCENT_COLOR);
  if (stored && stored.trim() !== "") {
    return stored.trim();
  }
  return DEFAULT_ACCENT_COLOR;
}

/**
 * 判断当前系统是否偏好暗色。
 *
 * @returns {boolean} 系统是否处于暗色偏好。
 */
export function systemPrefersDark() {
  return window.matchMedia(DARK_MEDIA_QUERY).matches;
}

/**
 * 将主题写入 `<html data-theme="...">`。
 *
 * @param {string} theme 主题标识。
 */
export function applyTheme(theme) {
  const target = SUPPORTED_THEMES.includes(theme) ? theme : DEFAULT_THEME;
  document.documentElement.dataset.theme = target;
}

/**
 * 将强调色写入 `--accent` CSS 变量。
 *
 * @param {string} accentColor 十六进制颜色字符串。
 */
export function applyAccentColor(accentColor) {
  document.documentElement.style.setProperty("--accent", accentColor);
}

/**
 * 设置主题并持久化到本地存储。
 *
 * @param {string} theme 主题标识。
 */
export function setTheme(theme) {
  const target = SUPPORTED_THEMES.includes(theme) ? theme : DEFAULT_THEME;
  window.localStorage.setItem(STORAGE_KEY_THEME, target);
  applyTheme(target);
}

/**
 * 设置强调色并持久化到本地存储。
 *
 * @param {string} accentColor 十六进制颜色字符串。
 */
export function setAccentColor(accentColor) {
  const target = accentColor && accentColor.trim() !== ""
    ? accentColor.trim()
    : DEFAULT_ACCENT_COLOR;
  window.localStorage.setItem(STORAGE_KEY_ACCENT_COLOR, target);
  applyAccentColor(target);
}

/**
 * 初始化主题与强调色。
 *
 * 从本地存储读取并应用到文档；若当前主题为「跟随系统」，还会
 * 监听系统主题变化以便实时切换。
 */
export function initializeTheme() {
  const theme = readStoredTheme();
  const accentColor = readStoredAccentColor();
  applyTheme(theme);
  applyAccentColor(accentColor);

  const mediaQuery = window.matchMedia(DARK_MEDIA_QUERY);
  mediaQuery.addEventListener("change", handleSystemThemeChange);
}

/**
 * 系统主题变化时的回调。
 *
 * 仅当用户选择「跟随系统」时才需要响应，因为 `data-theme="system"`
 * 下的 CSS 变量已由媒体查询驱动；此回调用于同步 JS 侧的副作用
 * （例如重新计算依赖颜色的部分）。
 */
export function handleSystemThemeChange() {
  if (readStoredTheme() === THEME_SYSTEM) {
    applyTheme(THEME_SYSTEM);
  }
}

/**
 * 返回当前应当生效的主题（用于需要根据主题分叉的逻辑）。
 *
 * @returns {string} 实际生效的 `light` 或 `dark`。
 */
export function resolveEffectiveTheme() {
  const stored = readStoredTheme();
  if (stored === THEME_SYSTEM) {
    return systemPrefersDark() ? "dark" : "light";
  }
  return stored;
}
