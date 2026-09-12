/**
 * 前端入口：根据当前路径分派到文件浏览器或属性页视图。
 */

import { initExplorer } from "./explorer.js";
import { initMetadata } from "./metadata.js";

/**
 * 应用启动入口。
 */
function bootstrap() {
  const pathname = window.location.pathname;
  if (pathname === "/metadata") {
    initMetadata();
    return;
  }
  if (pathname === "/" || pathname === "") {
    initExplorer();
    return;
  }
  window.location.href = "/";
}

bootstrap();
