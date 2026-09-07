// Passed to chrome.scripting: keep the function self-contained for serialization.
export function inspectZhihuAuth(): "authenticated" | "login_required" | "verification_required" | "unknown" {
  const path = window.location.pathname.toLowerCase();
  const text = (document.body?.innerText || document.body?.textContent || "").replace(/\s+/g, " ").slice(0, 100_000);
  if (path.startsWith("/signin") || path.startsWith("/account/login")) return "login_required";
  if (
    ["当前请求存在异常", "请完成安全验证", "暂时限制访问", "验证后继续访问"].some(value => text.includes(value))
    || document.querySelector("[class*='Captcha']:not([class*='Login']), [class*='Verification'], iframe[src*='captcha']")
  ) return "verification_required";
  if (document.querySelector(".AppHeader-profile, .AppHeader-userInfo .Avatar, button.AppHeader-profileEntry img.AppHeader-profileAvatar")) return "authenticated";
  if (document.querySelector(".SignFlow, .SignFlowHomepage")) return "login_required";
  return "unknown";
}
