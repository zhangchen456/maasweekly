import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { browserTimeZone, formatTimestamp, nextDigestCheck, startTimeDisplay } from '../public/time-display.js';

const format = (value, timeZone) => formatTimestamp(value, {locale:'en-US', timeZone});
test('timestamps cross calendar boundaries and include the browser offset', () => {
  assert.match(format('2026-10-03T01:15:00Z','Asia/Shanghai'), /10\/03\/2026, 09:15 GMT\+8/);
  assert.match(format('2026-10-03T01:15:00Z','America/Los_Angeles'), /10\/02\/2026, 18:15 GMT-7/);
  assert.match(format('2026-10-03T01:15:00Z','Europe/London'), /10\/03\/2026, 02:15 GMT\+1/);
  assert.match(format('2026-10-03T01:15:00Z','Pacific/Kiritimati'), /10\/03\/2026, 15:15 GMT\+14/);
  assert.equal(format(1790990100000, 'Asia/Shanghai'), format('2026-10-03T01:15:00Z','Asia/Shanghai'));
});
test('dates and timestamps without offsets are never guessed or shifted', () => {
  for (const zone of ['Asia/Shanghai','America/Los_Angeles','Pacific/Kiritimati']) {
    assert.equal(format('2026-10-03',zone),'2026-10-03');
    assert.equal(format('2026-10-03T01:15:00',zone),'2026-10-03T01:15:00 (time zone unspecified)');
  }
  assert.equal(format('2026-10-03T01:15:00Z','Invalid/Zone'),'2026-10-03T01:15:00.000Z');
});
test('next digest check remains fixed in UTC through user daylight saving transitions', () => {
  assert.equal(nextDigestCheck(Date.parse('2026-10-03T01:14:59Z')),'2026-10-03T01:15:00.000Z');
  assert.equal(nextDigestCheck(Date.parse('2026-10-03T01:15:00Z')),'2026-10-04T01:15:00.000Z');
  assert.match(format('2026-07-03T01:15:00Z','America/Los_Angeles'),/18:15 GMT-7/);
  assert.match(format('2026-12-03T01:15:00Z','America/Los_Angeles'),/17:15 GMT-8/);
});
test('static and asynchronously inserted metadata localize while source content stays unchanged', async () => {
  const old = process.env.TZ; process.env.TZ = 'America/Los_Angeles';
  const dom = new JSDOM('<html lang="en"><body><time datetime="2026-10-03T01:15:00Z">raw</time><time id="date" datetime="2026-10-03">2026-10-03</time><p data-time-text>Last success: 2026-10-03T01:15:00Z</p><pre>2026-10-03T01:15:00Z</pre><p>Peak hours 09:00–12:00 Asia/Shanghai</p><span data-browser-timezone></span><time data-digest-next></time></body></html>');
  const stop = startTimeDisplay(dom.window);
  try {
    assert.equal(browserTimeZone(),'America/Los_Angeles');
    assert.match(dom.window.document.querySelector('time').textContent,/10\/02\/2026, 18:15 GMT-7/);
    assert.equal(dom.window.document.getElementById('date').textContent,'2026-10-03');
    assert.match(dom.window.document.querySelector('[data-time-text]').textContent,/Last success: 10\/02\/2026, 18:15 GMT-7/);
    assert.equal(dom.window.document.querySelector('pre').textContent,'2026-10-03T01:15:00Z');
    const dynamic = dom.window.document.createElement('time'); dynamic.dateTime='2026-12-03T01:15:00Z'; dynamic.textContent='raw';
    dom.window.document.body.append(dynamic);
    await new Promise(resolve=>setTimeout(resolve,0));
    assert.match(dynamic.textContent,/12\/02\/2026, 17:15 GMT-8/);
    // Removed mutation nodes may have no parent by observer delivery time.
    const transient = dom.window.document.createTextNode('2026-10-03T01:15:00Z'); dom.window.document.body.append(transient); transient.remove();
    dynamic.dateTime='2026-12-04T01:15:00Z';
    await new Promise(resolve=>setTimeout(resolve,0));
    assert.match(dynamic.textContent,/12\/03\/2026, 17:15 GMT-8/);
  } finally {stop();dom.window.close(); if(old === undefined) delete process.env.TZ; else process.env.TZ=old;}
});
