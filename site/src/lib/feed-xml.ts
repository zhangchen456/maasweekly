/**
 * feed-xml.ts：XML 原语层——清洗、转义、截断（Task 05 M2，T11）。
 *
 * XML 1.0 只允许 #x9 #xA #xD 与 #x20-#xD7FF/#xE000-#xFFFD/#x10000-#x10FFFF；
 * 控制字符必须剥离（第三方库不做此清洗，是自写生成器的主因）。
 * 不使用 CDATA 节——全部实体转义，']]>' 天然安全。
 */

/** XML 1.0 合法字符判定（含代理区外的 astral 由 JS 字符串按码点处理）。 */
function isLegalXmlChar(cp: number): boolean {
  return cp === 0x9 || cp === 0xA || cp === 0xD
    || (cp >= 0x20 && cp <= 0xD7FF)
    || (cp >= 0xE000 && cp <= 0xFFFD)
    || (cp >= 0x10000 && cp <= 0x10FFFF);
}

/**
 * 剥离 XML 非法字符、规范换行、两端 trim、按码点截断加省略号。
 * maxCodePoints 是合同常量（title 200 / description 600，见 rss-v1.md）。
 */
export function sanitizeXmlText(input: string, maxCodePoints: number): string {
  const cps = Array.from(input)
    .map((ch) => ch.codePointAt(0)!)
    .filter(isLegalXmlChar);
  let out = String.fromCodePoint(...cps);
  out = out.replace(/\r\n?/g, '\n').trim();
  const outCps = Array.from(out);
  if (outCps.length > maxCodePoints) {
    out = `${outCps.slice(0, maxCodePoints).join('')}…`;
  }
  return out;
}

/** XML 实体转义（文本与属性通用；无 CDATA 节）。 */
export function escapeXml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
