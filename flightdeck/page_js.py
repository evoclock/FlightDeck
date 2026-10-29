"""Page script ported from crew-tracker: collapsible panes, architecture tabs/views, decision and step responses,
cluster staleness + trends redraw. Every outside link opens in a new tab. localStorage keys live under `flightdeck.*`. __STALE_MIN__ is filled by render."""

JS = """
(function(){function ext(a){if(a.protocol.indexOf('http')!==0||a.origin===location.origin)return;a.target='_blank';a.rel='noopener noreferrer'}
[].forEach.call(document.querySelectorAll('a[href]'),ext);document.addEventListener('click',function(ev){var a=ev.target.closest&&ev.target.closest('a[href]');if(a)ext(a)},true);})();
(function(){var K='flightdeck.collapsed.v1',s={};try{s=JSON.parse(localStorage.getItem(K)||'{}')}catch(_){}
var ps=[].slice.call(document.querySelectorAll('.pane'));
function set(p,c){p.classList.toggle('closed',c);p.querySelector('.ph').setAttribute('aria-expanded',String(!c));}
function save(){var o={};ps.forEach(function(p){o[p.id]=p.classList.contains('closed')});try{localStorage.setItem(K,JSON.stringify(o))}catch(_){}}
ps.forEach(function(p){set(p,p.id in s?s[p.id]:p.dataset.default==='closed');p.querySelector('.ph').addEventListener('click',function(){set(p,!p.classList.contains('closed'));save()})});
document.getElementById('xa').onclick=function(){ps.forEach(function(p){set(p,false)});save()};
document.getElementById('ca').onclick=function(){ps.forEach(function(p){set(p,true)});save()};})();
(function(){var T='flightdeck.archTab.v1',V='flightdeck.archView.v1',tabs=[].slice.call(document.querySelectorAll('[role=tab]'));if(!tabs.length)return;
var views={};try{views=JSON.parse(localStorage.getItem(V)||'{}')||{}}catch(_){views={}}
var bf=document.getElementById('bb-font'),fonts=bf?JSON.parse(bf.textContent):'',LBL={iso:'isometric',flat:'regular'};
// Each view is bowerbird's own page in a sandboxed frame (scripts, popups and downloads only), built on first use.
function frame(pid,v){var box=document.querySelector('.bb-frame[data-p="'+pid+'"]');if(!box)return;
var f=box.querySelector('iframe[data-view="'+v+'"]');
if(!f){var src=document.getElementById('bb-'+pid+'-'+v);if(!src)return;f=document.createElement('iframe');f.dataset.view=v;f.title=box.dataset.name+' architecture, '+LBL[v]+' view';
f.setAttribute('sandbox','allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads');f.setAttribute('allow','fullscreen');
f.srcdoc=JSON.parse(src.textContent).replace('<!--flightdeck-fonts-->','<style>'+fonts+'</style>');box.appendChild(f)}
[].forEach.call(box.querySelectorAll('iframe'),function(x){x.hidden=x!==f})}
function view(pid,v,save){if(!LBL[v])v='iso';var p=document.getElementById('arch-'+pid);
[].forEach.call(p.querySelectorAll('.vt'),function(b){b.setAttribute('aria-pressed',String(b.dataset.view===v))});frame(pid,v);
if(save){views[pid]=v;try{localStorage.setItem(V,JSON.stringify(views))}catch(_){}}}
function pid(t){return t.getAttribute('aria-controls').slice(5)}
function pick(t,focus){tabs.forEach(function(b){var on=b===t;b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;document.getElementById(b.getAttribute('aria-controls')).hidden=!on});if(focus)t.focus();try{localStorage.setItem(T,t.id)}catch(_){}view(pid(t),views[pid(t)])}
tabs.forEach(function(b,i){b.addEventListener('click',function(){pick(b)});b.addEventListener('keydown',function(ev){var j={ArrowRight:i+1,ArrowLeft:i-1,Home:0,End:tabs.length-1}[ev.key];if(j===undefined)return;ev.preventDefault();pick(tabs[(j+tabs.length)%tabs.length],true)})});
[].forEach.call(document.querySelectorAll('.vt'),function(b){b.addEventListener('click',function(){view(b.closest('.tabpanel').id.slice(5),b.dataset.view,true)})});
var saved=null;try{saved=document.getElementById(localStorage.getItem(T))}catch(_){}
if(saved&&tabs.indexOf(saved)>0)pick(saved);else view(pid(tabs[0]),views[pid(tabs[0])]);
window.flightdeckArchView=function(p){var b=document.querySelector('#arch-'+p+' .vt[aria-pressed=true]');return b&&b.dataset.view};})();
(function(){var K='flightdeck.responses.v1',R={};try{R=JSON.parse(localStorage.getItem(K)||'{}')||{}}catch(_){R={}}
var LAB={accepted:'Accepted',rejected:'Rejected',comment:'Alternative sent'},sy=document.getElementById('sync'),t=null,web=/^https?:$/.test(location.protocol);
function esc(s){var d=document.createElement('div');d.textContent=String(s);return d.innerHTML}
function hm(ts){var d=new Date(ts);return ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)}
function list(){return Object.keys(R).sort().map(function(k){return R[k]})}
window.flightdeckResponses=list;
function paint(id){var el=document.querySelector('[data-id="'+CSS.escape(id)+'"]'),r=R[id];if(!el)return;
if(el.dataset.kind==='decision'){el.classList.remove('r-accepted','r-rejected','r-comment');if(r)el.classList.add('r-'+r.value);
[].forEach.call(el.querySelectorAll('[aria-pressed]'),function(b){b.setAttribute('aria-pressed',String(!!r&&r.value===b.dataset.act))});
var p=el.querySelector('.resp');p.hidden=!r;p.innerHTML=r?'<span class="rs">'+LAB[r.value]+' at '+hm(r.timestamp)+'</span><button type="button" class="undo">Undo</button>'+(r.comment?'<span class="rc">'+esc(r.comment)+'</span>':''):'';}
else{var cb=el.querySelector('.tick');if(cb.disabled)return;cb.checked=!!r;el.classList.toggle('ticked',!!r);el.querySelector('.when').textContent=r?'Done '+hm(r.timestamp):''}}
function sync(){if(!web)return;clearTimeout(t);t=setTimeout(function(){fetch('/api/responses',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify({responses:list()})})
.then(function(r){sy.textContent=r.ok?'Responses synced':'Responses saved in this browser'}).catch(function(){sy.textContent='Responses saved in this browser'})},600)}
function put(id,type,value,comment){if(value)R[id]={id:id,type:type,value:value,comment:comment||'',timestamp:new Date().toISOString()};else delete R[id];
try{localStorage.setItem(K,JSON.stringify(R))}catch(_){}paint(id);sync()}
Object.keys(R).forEach(paint);
document.addEventListener('click',function(ev){var b=ev.target.closest&&ev.target.closest('.act,.undo');if(!b)return;var el=b.closest('[data-kind=decision]');if(!el)return;var id=el.dataset.id;
if(b.classList.contains('undo')){put(id);el.querySelector('.acc').focus();return}
if(b.dataset.act==='comment'){var ta=el.querySelector('textarea'),v=ta.value.trim();if(!v){ta.focus();return}put(id,'decision','comment',v);ta.value='';el.querySelector('details').open=false;el.querySelector('.undo').focus();return}
put(id,'decision',R[id]&&R[id].value===b.dataset.act?null:b.dataset.act)});
document.addEventListener('change',function(ev){var cb=ev.target;if(!cb.classList||!cb.classList.contains('tick'))return;var el=cb.closest('[data-id]');put(el.dataset.id,el.dataset.kind,cb.checked?'done':null)});
var ex=document.getElementById('export');ex.querySelector('.x').addEventListener('click',function(){ex.close()});
document.getElementById('ex').onclick=function(){var txt=JSON.stringify({exported:new Date().toISOString(),responses:list()},null,2),n=list().length;
function show(){ex.querySelector('textarea').value=txt;ex.showModal();ex.querySelector('textarea').select()}
if(navigator.clipboard&&navigator.clipboard.writeText&&window.isSecureContext)navigator.clipboard.writeText(txt).then(function(){sy.textContent='Copied '+n+' response'+(n===1?'':'s')},show);else show()};})();
(function(){var MIN=__STALE_MIN__,LBL={online:'Online',stale:'Stale, over '+MIN+' min',offline:'Offline',never:'No reading yet'};
function hm(ts){var d=new Date(ts);return ('0'+d.getHours()).slice(-2)+':'+('0'+d.getMinutes()).slice(-2)}
function state(n,now){if(n.status==='offline')return'offline';if(n.status!=='online'||!n.read_at)return'never';return (now||Date.now())-Date.parse(n.read_at)>MIN*60000?'stale':'online'}
function mark(row,n,now){var st=state(n,now);row.className='nrow s-'+st;if(st==='stale')row.querySelector('.nsub').textContent=LBL.stale+' · read '+hm(n.read_at);return st}
function gb(b){return Math.round(b/1e9)+' GB'}
function fill(row,n){var mp=n.mem_used_bytes!=null&&n.mem_total_bytes?Math.round(100*n.mem_used_bytes/n.mem_total_bytes):null,
v={gpu:[n.gpu_util_pct==null?'n/a':Math.round(n.gpu_util_pct)+'%',n.gpu_util_pct,''],mem:[mp==null?'n/a':mp+'%',mp,mp==null?'':gb(n.mem_used_bytes)+' of '+gb(n.mem_total_bytes)],
temp:[n.temp_c==null?'n/a':Math.round(n.temp_c)+'°C',null,''],power:[n.power_w==null?'n/a':Math.round(n.power_w)+' W',null,'']};
Object.keys(v).forEach(function(k){var m=row.querySelector('[data-k='+k+']');m.querySelector('.mv').textContent=v[k][0];var b=m.querySelector('.bar');b.hidden=v[k][1]==null;b.firstChild.style.width=Math.max(0,Math.min(100,v[k][1]||0))+'%';m.querySelector('.mx').textContent=v[k][2]});
row.dataset.readAt=n.read_at||'';row.dataset.status=n.status||'never';row.querySelector('.nsub').textContent=n.status==='offline'?'Offline'+(n.error?': '+n.error:''):(n.read_at?'Read '+hm(n.read_at):LBL.never)}
function rows(){return [].slice.call(document.querySelectorAll('.nrow'))}
function count(){var on=rows().filter(function(r){return r.classList.contains('s-online')}).length,c=document.querySelector('.spark .online');if(!c)return;c.lastChild.textContent=on+' online';c.classList.toggle('none',!on)}
function check(){var now=clock();rows().forEach(function(r){mark(r,{status:r.dataset.status,read_at:r.dataset.readAt},now)});count()}
var TD=document.getElementById('trends-data'),TR=TD?JSON.parse(TD.textContent):null,TPAL=TR&&TR.palette||['teal'],TDASH=TR&&TR.dash||[''],SVGNS=TD?document.querySelector('#trends svg').namespaceURI:'';
function clock(){if(!TR||!TR.sample)return Date.now();var t=0;(TR.history||[]).forEach(function(h){var p=Date.parse(h.at);if(p>t)t=p});rows().forEach(function(r){var p=Date.parse(r.dataset.readAt||'');if(p>t)t=p});return t||Date.now()}
function draw(){if(!TR)return;var g=document.querySelector('#trends .tr-lines');if(!g)return;var now=clock(),H=TR.history||[],C=TR.colors||{},names=Object.keys(C),any=false;
H.forEach(function(h){Object.keys(h.gpu||{}).forEach(function(k){if(!(k in C)){C[k]='var(--'+TPAL[names.length%TPAL.length]+')';names.push(k)}})});
while(g.firstChild)g.removeChild(g.firstChild);
names.forEach(function(k,ni){var d=[],prev=null,dots=[],dash=TDASH[ni%TDASH.length];H.forEach(function(h){var v=(h.gpu||{})[k];if(v==null)return;var m=(now-Date.parse(h.at))/60000;if(m<0||m>60)return;
v=Math.max(0,Math.min(100,v));var x=(600*(60-m)/60).toFixed(1),y=(100-v).toFixed(1);d.push((prev!=null&&prev-m<=16?'L':'M')+x+','+y);prev=m;dots.push([x,y,k+' '+Math.round(v)+'% at '+hm(h.at)])});
if(!d.length)return;any=true;var p=document.createElementNS(SVGNS,'path');p.setAttribute('class','tl');p.setAttribute('data-node',k);p.setAttribute('stroke',C[k]);if(dash)p.setAttribute('stroke-dasharray',dash);p.setAttribute('d',d.join(' '));g.appendChild(p);
dots.forEach(function(t){var q=document.createElementNS(SVGNS,'path'),ti=document.createElementNS(SVGNS,'title');q.setAttribute('class','td');q.setAttribute('stroke',C[k]);q.setAttribute('d','M'+t[0]+','+t[1]+'h0');ti.textContent=t[2];q.appendChild(ti);g.appendChild(q)})});
document.querySelector('#trends .tr-empty').hidden=any;
var lg=document.querySelector('#trends .tr-legend');if(lg&&lg.children.length!==names.length){lg.textContent='';names.forEach(function(k,ni){var s=document.createElement('span'),v=document.createElementNS(SVGNS,'svg'),l=document.createElementNS(SVGNS,'line'),dash=TDASH[ni%TDASH.length];s.className='tk';var sq=document.createElement('i');sq.style.background=C[k];s.appendChild(sq);v.setAttribute('class','tk-l');v.setAttribute('viewBox','0 0 24 6');v.setAttribute('aria-hidden','true');[['x1',0],['x2',24],['y1',3],['y2',3],['stroke',C[k]]].forEach(function(a){l.setAttribute(a[0],a[1])});if(dash)l.setAttribute('stroke-dasharray',dash);v.appendChild(l);s.appendChild(v);s.appendChild(document.createTextNode(k));lg.appendChild(s)})}}
check();draw();setInterval(function(){check();draw()},60000);
if(/^https?:$/.test(location.protocol)&&!(TR&&TR.sample)){var poll=function(){fetch('/api/spark',{credentials:'same-origin'}).then(function(r){return r.ok?r.json():null}).then(function(s){if(!s||!s.nodes)return;
s.nodes.forEach(function(n){var row=document.querySelector('.nrow[data-node="'+CSS.escape(n.name)+'"]');if(row&&n.read_at&&(!row.dataset.readAt||Date.parse(n.read_at)>Date.parse(row.dataset.readAt)))fill(row,n)});
if(TR&&Array.isArray(s.history)){var last=function(a){return a.length?Date.parse(a[a.length-1].at):0};if(last(s.history)>=last(TR.history||[]))TR.history=s.history;draw()}check()}).catch(function(){})};poll();setInterval(poll,60000)}})();
"""
