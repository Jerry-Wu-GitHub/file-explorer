/**
 * 应用部署路径前缀。
 *
 * 从 `<base>` 标签中解析当前页面所在的部署路径，供 API 请求、页面
 * 导航与属性窗口等场景统一拼接前缀。若部署在根路径或未提供
 * `<base>` 标签，则返回空字符串，使拼接结果仍以 `/` 为起点。
 *
 * 例如：
 *
 * - 页面在 `http://host/`：返回 `""`；
 * - 页面在 `http://host/files/`：返回 `"/files"`；
 * - 页面在 `http://host/app/sub/`：返回 `"/app/sub"`。
 */

/**
 * 从 `<base>` 标签解析应用部署的路径前缀。
 *
 * 使用 `URL` 对象解析 `<base>` 的 `href` 并提取 `pathname`，随后
 * 去掉末尾斜杠，使前缀与后续路径拼接时不会产生双斜杠。
 *
 * @returns {string} 以 `/` 开头、不以 `/` 结尾的路径前缀；根路径
 *   时返回空字符串。
 */
function resolveBasePath() {
  const baseElement = document.querySelector("base");
  const href = baseElement ? baseElement.href : document.baseURI;
  if (!href) {
    return "";
  }
  try {
    const url = new URL(href, window.location.href);
    const pathname = url.pathname;
    if (pathname.endsWith("/")) {
      return pathname.replace(/\/$/, "");
    }
    return pathname;
  } catch (error) {
    console.error("解析 <base> 标签失败：", error);
    return "";
  }
}

/**
 * 应用的部署路径前缀，不带末尾斜杠。
 */
export const BASE_PATH = resolveBasePath();
