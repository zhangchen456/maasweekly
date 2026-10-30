import campaigns from '../../../packages/analytics/campaigns.json';
// Tab-session attribution only: no visitor ID, raw URL, search text or cross-site identity.
export const SOURCE_CHANNELS = ['search','social','ai','referral','campaign','unknown'] as const;
type Source = typeof SOURCE_CHANNELS[number];
const KEY='maas-source-session-v1';
function channel(host:string):Source {
 if(/(^|\.)(chatgpt.com|perplexity.ai|claude.ai|gemini.google.com)$/.test(host))return 'ai';
 if(/(^|\.)(google\.[a-z.]+|bing.com|baidu.com|duckduckgo.com)$/.test(host))return 'search';
 if(/(^|\.)(x.com|twitter.com|xiaohongshu.com|weixin.qq.com|bilibili.com|reddit.com)$/.test(host))return 'social';
 return 'referral';
}
export function registrationSource(win:Window=window) {
 try {
  if(win.navigator.doNotTrack==='1'||win.localStorage.getItem('umami.disabled')){win.sessionStorage.removeItem(KEY);return undefined;}
  const now=Date.now(), url=new URL(win.location.href);
  let current:Source|undefined;
  const source=url.searchParams.get('utm_source');
  const internal=win.document.referrer&&new URL(win.document.referrer).origin===url.origin;
  if(source&&!internal){const known:Record<string,Source>={google:'search',bing:'search',baidu:'search',chatgpt:'ai',perplexity:'ai',claude:'ai',wechat:'social',xiaohongshu:'social',x:'social',twitter:'social',bilibili:'social'};current=known[source.toLowerCase()]??(channel(source.toLowerCase())==='referral'?'campaign':channel(source.toLowerCase()));}
  else if(win.document.referrer){const ref=new URL(win.document.referrer);if(['http:','https:'].includes(ref.protocol)&&ref.origin!==url.origin)current=channel(ref.hostname);}
  const raw=JSON.parse(win.sessionStorage.getItem(KEY)??'null');
  const valid=raw&&SOURCE_CHANNELS.includes(raw.first)&&SOURCE_CHANNELS.includes(raw.last)&&Number.isFinite(raw.started)&&raw.started<=now&&now-raw.started<30*60*1000;
  const value=valid?raw:{first:current??'unknown',last:current??'unknown',started:now};
  if(current)value.last=current;
  const campaign=url.searchParams.get('utm_campaign');
  if(!internal && campaign && campaigns.includes(campaign)) {
   if(!value.firstCampaign)value.firstCampaign=campaign;
   value.lastCampaign=campaign;
  }
  // Retain only configured campaign IDs, including when reading old session data.
  for(const key of ['firstCampaign','lastCampaign'])if(!campaigns.includes(value[key]))delete value[key];
  win.sessionStorage.setItem(KEY,JSON.stringify({first:value.first,last:value.last,started:value.started,...(value.firstCampaign?{firstCampaign:value.firstCampaign,lastCampaign:value.lastCampaign}: {})}));
  return {first:value.first as Source,last:value.last as Source,...(value.firstCampaign?{firstCampaign:value.firstCampaign,lastCampaign:value.lastCampaign}: {})};
 }catch{return undefined;}
}
