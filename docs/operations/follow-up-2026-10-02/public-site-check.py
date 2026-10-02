import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup
base='https://daily.maas.click';results=[]
for path in ['/?lang=zh','/robots.txt','/sitemap.xml','/models/','/pricing/','/agent/']:
 r=requests.get(base+path,timeout=30);r.raise_for_status();row={'path':path,'status':r.status_code,'finalUrl':r.url}
 if path=='/?lang=zh':
  soup=BeautifulSoup(r.text,'html.parser');metas=soup.select('meta[name="baidu-site-verification"]')
  assert len(metas)==1 and metas[0].get('content')=='codeva-UXsh2qWgbK'
  canonical=soup.select_one('link[rel="canonical"]');assert canonical and canonical.get('href')==base+'/'
  assert len(soup.select('.market-table'))==1 and len(soup.select('[role="tab"]'))==3
  row.update(baiduMetaCorrect=True,canonical=canonical['href'],singlePriceTable=True)
 elif path=='/robots.txt':assert 'sitemap' in r.text.lower() and 'disallow: /\n' not in r.text.lower()
 elif path=='/sitemap.xml':assert '<urlset' in r.text or '<sitemapindex' in r.text
 results.append(row)
Path('docs/operations/follow-up-2026-10-02/public-site-check.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'publicSiteChecks':len(results),'passed':True}))
