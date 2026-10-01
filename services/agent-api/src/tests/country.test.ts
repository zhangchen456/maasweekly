import assert from 'node:assert/strict';
import test from 'node:test';
import http, { type IncomingMessage } from 'node:http';
import { countryFor, countryHandler } from '../country.js';
function request(ip: string, peer='127.0.0.1') {
  return {socket:{remoteAddress:peer},headers:{'x-maas-client-ip':ip}} as unknown as IncomingMessage;
}
test('real database country mapping and trusted peer boundary', () => {
  for (const [ip, expected] of [['223.5.5.5','CN'],['8.8.8.8','US'],['1.36.0.1','HK'],['2001:4860:4860::8888','US']]) assert.equal(countryFor(request(ip!)),expected);
  assert.equal(countryFor(request('8.8.8.8','203.0.113.1')),null);
  for (const ip of ['not-ip','8.8.8.8, 223.5.5.5','127.0.0.1','010.001.001.001','']) assert.equal(countryFor(request(ip)),null);
  const req=request('223.5.5.5');req.headers['cf-ipcountry']='US';req.headers['x-forwarded-for']='8.8.8.8';assert.equal(countryFor(req),'CN');
});
test('country endpoint does not cache, leak addresses or accept writes', async () => {
  const server=http.createServer(countryHandler);await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
  try {const port=(server.address() as {port:number}).port;const response=await fetch(`http://127.0.0.1:${port}/_locale/country`,{headers:{'X-Maas-Client-IP':'8.8.8.8'}});assert.equal(response.headers.get('cache-control'),'no-store');assert.deepEqual(await response.json(),{country:'US'});
    const post=await fetch(`http://127.0.0.1:${port}/_locale/country`,{method:'POST'});assert.equal(post.status,405);
  } finally {await new Promise<void>(r=>server.close(()=>r()));}
});
