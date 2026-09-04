import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

// 周报 collection
const weeklyReports = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/weekly' }),
  schema: z.object({
    title: z.string(),
    date: z.string(),
    period: z.string().optional(),
  }),
});

// 信源 collection (从 JSON 生成)
const platforms = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/platforms' }),
  schema: z.object({
    name: z.string(),
    name_en: z.string(),
    region: z.string(),
    vendor: z.string(),
    official_site: z.string(),
    sources: z.object({
      model_list: z.string().nullable(),
      pricing: z.string().nullable(),
      changelog: z.string().nullable(),
      api_docs: z.string().nullable(),
      github: z.string().nullable(),
      blog: z.string().nullable(),
      model_marketplace: z.string().nullable(),
    }),
    notes: z.string(),
  }),
});

// 周报结构化数据 (extract-structured.py 生成)
const weeklyStructured = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/weekly-structured' }),
  schema: z.object({
    date: z.string(),
    period: z.string().optional(),
    headline: z.array(z.any()).default([]),
    platforms: z.array(z.any()).default([]),
    summary_table: z.any().nullable(),
    trends: z.array(z.any()).default([]),
    watchpoints: z.any().nullable(),
    event_index: z.array(z.any()).default([]),
  }),
});

export const collections = { weekly: weeklyReports, platforms, weeklyStructured };
