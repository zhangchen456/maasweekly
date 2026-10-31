export interface SharedCalculation {v:1;selected:string[];variants:[string,string][];input:number;output:number;fx:number;asOf:string}
export function validCalculation(x:any):x is SharedCalculation {
 const text=(v:any,max:number)=>typeof v==='string'&&v.length<=max;
 return x?.v===1&&Array.isArray(x.selected)&&x.selected.length>=1&&x.selected.length<=5&&x.selected.every((s:any)=>text(s,200))&&new Set(x.selected).size===x.selected.length&&Array.isArray(x.variants)&&x.variants.length===x.selected.length&&x.variants.every((v:any)=>Array.isArray(v)&&v.length===2&&x.selected.includes(v[0])&&text(v[1],1500))&&new Set(x.variants.map((v:any)=>v[0])).size===x.selected.length&&[x.input,x.output].every(n=>typeof n==='number'&&Number.isFinite(n)&&n>=0&&n<=1000000)&&x.input+x.output>0&&typeof x.fx==='number'&&Number.isFinite(x.fx)&&x.fx>=.01&&x.fx<=1000&&text(x.asOf,80);
}
export function readCalculation(hash:string):SharedCalculation|null {
 if(!hash.startsWith('#calc='))return null;
 if(hash.length>16000)throw Error('分享链接过长，请重新生成。');
 try{const x=JSON.parse(decodeURIComponent(hash.slice(6)));if(!validCalculation(x))throw Error();return x;}catch{throw Error('分享参数无效，请重新生成链接。');}
}
export function calculationLink(base:string,value:SharedCalculation){if(!validCalculation(value))throw Error('请先选择模型并填写有效用量。');const u=new URL(base);u.search='';u.hash='calc='+encodeURIComponent(JSON.stringify(value));if(u.href.length>20000)throw Error('分享内容过长，请减少模型数量。');return u.href;}
