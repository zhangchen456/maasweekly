import { SITE_CANONICAL } from '../config/public-access';

export function GET() {
  return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${SITE_CANONICAL}/sitemap.xml\n`, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
}
