import type {APIRoute} from 'astro';
import {sitemapResponse} from '../lib/runtime-sitemap';
export const GET:APIRoute=({params})=>sitemapResponse(params.shard);
