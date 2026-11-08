// Worker KV behavior is exercised directly; Python sync tests do not run this route.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../site/api.js'), 'utf8').replace('export default {', 'const exported = {');
const ctx = { Response, URL, Date, JSON, Map, CFG: {team:'team',aud:'aud'}, HDRS:{},
  verify: async () => ({email:'a@example.com'}), deny: () => new Response('', {status:403}), page: {} };
vm.createContext(ctx);
vm.runInContext(source + '\nthis.worker = exported;', ctx);
const kv = new Map();
const env = {FLIGHTDECK_RESPONSES: {get: async k => kv.get(k) ?? null, put: async (k,v) => kv.set(k,v)}};
async function post(route, payload) {
  const req = new Request('https://example.com' + route, {method:'POST',
    headers:{'content-type':'application/json','cf-access-jwt-assertion':'valid'}, body:JSON.stringify(payload)});
  return ctx.worker.fetch(req,env);
}
const row = (id,value,timestamp) => ({id,type:'decision',value,timestamp});

// Why: a browser with an old snapshot must not erase chat answers or resurrect Undo.
test('browser merges by id and tombstone survives stale browser and chat', async () => {
  const key = 'responses/a@example.com';
  kv.set(key,JSON.stringify({responses:[row('other','accepted','2026-10-25T10:00:00Z')]}));
  assert.equal((await post('/api/responses',{responses:[row('mine','accepted','2026-10-25T10:01:00Z')]})).status,200);
  assert.deepEqual(JSON.parse(kv.get(key)).responses.map(r=>r.id),['other','mine']);
  const undo = row('mine','undone','2026-10-25T10:02:00Z');
  await post('/api/responses',{responses:[undo]});
  await post('/api/responses',{responses:[row('mine','accepted','2026-10-25T10:01:00Z')]});
  await post('/api/chat-accept',{id:'mine',value:'accepted',timestamp:'2026-10-25T10:03:00Z'});
  await post('/api/responses',{responses:[row('mine','accepted','2026-10-25T10:04:00Z')]});
  assert.equal(JSON.parse(kv.get(key)).responses.find(r=>r.id==='mine').value,'undone');
  assert.equal(JSON.parse(kv.get(key)).responses.find(r=>r.id==='other').value,'accepted');
});

// Why: a changed KV snapshot must be retried instead of knowingly overwritten.
test('changed snapshot returns conflict rather than overwriting it', async () => {
  const key = 'responses/a@example.com';
  kv.clear();
  let reads = 0;
  const original = env.FLIGHTDECK_RESPONSES.get;
  env.FLIGHTDECK_RESPONSES.get = async k => {
    if (++reads === 2) kv.set(k, JSON.stringify({responses:[row('rival','done','2026-10-25T10:04:00Z')]}));
    return original(k);
  };
  try {
    assert.equal((await post('/api/responses',{responses:[row('mine','accepted','2026-10-25T10:03:00Z')]})).status,409);
    assert.equal(JSON.parse(kv.get(key)).responses[0].id,'rival');
  } finally { env.FLIGHTDECK_RESPONSES.get = original; }
});
