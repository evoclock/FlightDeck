"""Locked layout CSS for the ten slots, ported from crew-tracker. Nuthatch palette; banner keeps its natural aspect.

BASE is the crew-tracker stylesheet verbatim. EXTRA only adds rules for `metrics.generic` and for top-row slots set to
`empty` (the .top.no-* modifiers). Neither may give `.banner` / `.banner img` a fixed height, max-height,
aspect-ratio or object-fit:cover; tests/test_layout_banner.py enforces that.
"""

BASE = """
:root{--ink:#173d3b;--ink2:#2c4a47;--sub:#526965;--line:#173d3b2e;--rule:#173d3b1f;--bg:#edf0e8;--card:#f7f8f3;--band:#153c3b;--focus:#daaa65;
--sage:#79c39e;--rust:#e77843;--peach:#ee9b69;--mustard:#ceb05e;--slate:#617082;--mauve:#76536b;--olive:#6e7354;--teal:#3f6f70;--ochre:#a77c2e;--forest:#52705f;--clay:#9c5f45;color-scheme:light;--gap:28px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink2);font-family:'Geist Sans',ui-sans-serif,system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:18px;line-height:1.65;font-variant-numeric:tabular-nums;font-feature-settings:'tnum' 1}
.wrap{padding:28px 40px 36px;max-width:2200px;margin:0 auto}
[hidden]{display:none!important}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.top{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;margin:0 0 var(--gap);align-items:start}
.banner{margin:0;display:block;line-height:0;overflow:hidden;border:0;border-radius:3px;background:var(--card);width:100%}
.banner img{display:block;width:100%;height:auto;object-fit:unset;border:0;border-radius:0}
.activity{background:var(--card);border:1px solid var(--line);border-radius:3px;padding:10px 14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.activity h2{font-size:17px;font-weight:500;color:var(--ink);margin:0;letter-spacing:-.01em}
.a-tab{width:100%;border-collapse:collapse;flex:1 1 auto}
.a-tab thead th{font-size:14px;font-weight:500;color:var(--sub);text-align:right;padding:0 0 4px 12px;white-space:nowrap}
.a-tab tbody th{font-size:15.5px;font-weight:400;color:var(--sub);text-align:left;white-space:nowrap;border-left:3px solid var(--sage);padding:2px 0 2px 10px}
.ac[data-k=prs_opened] th{border-left-color:var(--mustard)}.ac[data-k=prs_merged] th{border-left-color:var(--teal)}
.a-tab tbody tr + tr > *{border-top:1px solid var(--rule)}
.av{font-size:26px;font-weight:500;color:var(--ink);line-height:1.15;text-align:right;padding:2px 0 2px 12px}
.a-foot{display:flex;flex-direction:column;gap:1px}
.a-meta,.anote{margin:0;font-size:13px;color:var(--sub);line-height:1.35}
.spark{background:var(--card);border:1px solid var(--line);border-radius:3px;padding:10px 14px;display:flex;flex-direction:column;gap:6px;min-width:0;height:auto;align-self:start;overflow:visible}
.sp-head{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px}
.spark h2{font-size:17px;font-weight:500;color:var(--ink);margin:0;letter-spacing:-.01em}
.online{display:inline-flex;align-items:center;gap:8px;font-size:15.5px;font-weight:500;color:var(--forest);border:1px solid color-mix(in srgb,var(--sage) 60%,transparent);border-radius:999px;padding:1px 12px}
.online.none{color:var(--sub);border-color:var(--line)}.online.none .sdot{background:#c9d2c5}
.csum{margin:0 0 0 auto;font-size:15.5px;color:var(--sub)}
.sp-body{display:flex;flex-direction:column;gap:6px;min-width:0}
.trends{display:flex;flex-direction:column;gap:4px;margin:2px 0 4px}
.tr-head{display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px}
.trends h3{font-size:16px;font-weight:500;color:var(--ink);margin:0;text-transform:none;letter-spacing:0}
.tr-pill{font-size:15px;color:var(--ink);background:color-mix(in srgb,var(--sage) 22%,transparent);border-radius:999px;padding:0 12px}
.tr-win{margin-left:auto;font-size:15px;color:var(--sub);border:1px solid var(--line);border-radius:3px;padding:0 10px}
.tr-plot{display:grid;grid-template-columns:auto minmax(0,1fr);grid-template-rows:88px auto;gap:2px 8px}
.tr-y{position:relative;min-width:3.2em;font-size:14px;color:var(--sub);line-height:1;text-align:right}
.tr-y span{position:absolute;right:0;transform:translateY(-50%)}
.tr-area{position:relative;height:88px;border-left:1px solid var(--line);border-bottom:1px solid var(--line)}
.tr-svg{display:block;width:100%;height:100%;overflow:visible}
.tg{stroke:var(--rule);stroke-width:1;vector-effect:non-scaling-stroke}
.tl{fill:none;stroke-width:2;stroke-linejoin:round;vector-effect:non-scaling-stroke}
.td{fill:none;stroke-width:6;stroke-linecap:round;vector-effect:non-scaling-stroke}
.tr-empty{position:absolute;inset:0;margin:0;display:flex;align-items:center;justify-content:center;font-size:14px;color:var(--sub);text-align:center;padding:0 12px}
.tr-x{display:flex;justify-content:space-between;font-size:14px;line-height:1.3;color:var(--sub)}
.tr-legend{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:15px;line-height:1.4;color:var(--ink);margin-top:4px}
.tk{display:inline-flex;align-items:center;gap:8px;font-weight:500}.tk i{width:14px;height:14px;border-radius:3px;display:inline-block;flex:none}.tk-l{width:24px;height:6px;overflow:visible}.tk-l line{stroke-width:3}
.sdot{width:10px;height:10px;border-radius:50%;background:var(--sage);flex:none}
.nodes{display:flex;flex-direction:column}
.nrow{display:grid;grid-template-columns:minmax(min-content,1fr) repeat(2,minmax(0,1.3fr)) repeat(2,minmax(0,.7fr));gap:4px 10px;align-items:start;padding:6px 0;border-top:1px solid var(--rule)}
.nn{display:flex;flex-direction:column;min-width:0}
.nname{display:inline-flex;align-items:center;gap:8px;font-size:18px;font-weight:500;color:var(--ink);white-space:nowrap}
.nsub{font-size:15.5px;color:var(--sub)}
.s-stale .sdot{background:var(--mustard)}.s-offline .sdot{background:var(--rust)}.s-never .sdot{background:#c9d2c5}
.s-offline .nsub{color:var(--clay)}
.s-never .m,.s-offline .m{display:none}
.m{display:flex;flex-direction:column;gap:3px;min-width:0}
.ml{font-size:12px;color:var(--sub)}
.mv{font-size:17px;font-weight:500;color:var(--ink);line-height:1.1;white-space:nowrap}
.mx{font-size:15.5px;color:var(--sub);white-space:nowrap}.mx:empty{display:none}
.s-stale .mv{color:var(--sub)}
.bar{display:block;height:6px;border-radius:3px;background:var(--rule);overflow:hidden}
.bar i{display:block;height:100%;background:var(--teal)}.m[data-k=gpu] .bar i{background:var(--teal)}
header{display:flex;flex-wrap:wrap;align-items:center;gap:14px 24px;padding-bottom:22px;margin-bottom:var(--gap);border-bottom:1px solid var(--line)}
h1{font-size:34px;line-height:1.1;font-weight:500;color:var(--ink);margin:0;letter-spacing:-.02em}
.updated{font-size:16px;color:var(--sub);border:1px solid var(--line);border-radius:3px;padding:4px 12px}
.tools{margin-left:auto;display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.tools button{font:inherit;font-size:16px;font-weight:500;color:var(--ink);background:none;border:1px solid var(--line);border-radius:3px;padding:8px 16px;cursor:pointer}
.tools button:hover{border-color:var(--ink)}
button:focus-visible,a:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
.grid{display:grid;gap:var(--gap);grid-template-columns:minmax(0,1fr);align-items:start}
.pane.closed{align-self:start}
.pane{background:var(--card);border:1px solid var(--line);border-radius:3px;display:flex;flex-direction:column;min-width:0;overflow:hidden}
.ph{all:unset;box-sizing:border-box;display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;flex:none;width:100%;padding:18px 28px;cursor:pointer;border-bottom:1px solid var(--line)}
.ph:hover .pt{text-decoration:underline;text-underline-offset:5px;text-decoration-thickness:1px}
.ph:focus-visible{outline:3px solid var(--focus);outline-offset:-3px}
.pt{white-space:nowrap;font-size:22px;font-weight:500;color:var(--ink);letter-spacing:-.01em}
.chev{width:11px;height:11px;border-right:2px solid var(--ink);border-bottom:2px solid var(--ink);transform:rotate(45deg);margin:0 4px 5px 2px;transition:transform .15s;flex:none}
.pane.closed .chev{transform:rotate(-45deg);margin-bottom:0}
.badge{margin-left:auto;font-size:15.5px;font-weight:500;color:var(--sub);border:1px solid var(--line);border-radius:999px;padding:2px 12px;white-space:nowrap}
.badge.hot{color:var(--clay);border-color:color-mix(in srgb,var(--rust) 50%,transparent)}
.pb{padding:10px 30px 24px;overflow-y:auto;overscroll-behavior:contain;flex:1;min-height:0}
.pane.closed .pb{display:none}
.pane.closed .ph{border-bottom:0}
h3{font-size:15.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--forest);font-weight:500;margin:16px 0 4px}
a{color:var(--teal);text-decoration:none;border-bottom:1px solid rgba(63,111,112,.3);word-break:break-word}
a:hover{border-bottom-color:var(--teal)}
.muted{color:var(--sub)}
.strong{color:var(--ink);font-weight:500}
.dec{display:flex;flex-direction:column;gap:10px;border-left:3px solid var(--rust);padding:14px 0 14px 22px;margin:16px 0}
.dec.settled{border-left-color:var(--sage)}
.dec p{margin:0}
.pill{align-self:flex-start;font-size:15px;letter-spacing:.08em;text-transform:uppercase;font-weight:500;padding:1px 12px;border-radius:999px;border:1px solid var(--rust);color:var(--clay)}
.dec.settled .pill{border-color:var(--sage);color:var(--forest)}
ul{list-style:none;margin:0;padding:0}
.steps li{display:flex;gap:16px;align-items:flex-start;padding:16px 0;border-bottom:1px solid var(--rule)}
.steps li:last-child{border-bottom:0}
.hit{flex:none;display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;margin:-6px 0 -6px -10px;cursor:pointer}
.tick{appearance:none;-webkit-appearance:none;width:24px;height:24px;margin:0;border:2px solid var(--sub);border-radius:3px;background:#fff;cursor:pointer;display:grid;place-content:center}
.tick:checked{background:var(--sage);border-color:var(--sage)}
.tick:checked::after{content:"";width:6px;height:12px;border:solid #fff;border-width:0 3px 3px 0;transform:translateY(-1px) rotate(45deg)}
.tick:disabled{cursor:default}
.tick:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
.txt{flex:1;min-width:0;color:var(--ink)}
.steps .done .txt,.ticked .txt{color:var(--sub)}
.steps .done .t,.ticked .t{text-decoration:line-through;text-decoration-thickness:1.5px}
.when{margin-left:8px;color:var(--forest);font-weight:500}
.when:empty{display:none}
.tickrow{display:flex;gap:16px;align-items:flex-start}
.respond{display:flex;flex-direction:column;gap:8px}
.choice{display:flex;flex-wrap:wrap;gap:8px}
.act{font:inherit;font-size:16px;font-weight:500;min-height:44px;min-width:44px;display:inline-flex;align-items:center;gap:8px;padding:0 16px;border:1px solid var(--line);border-radius:3px;background:var(--card);color:var(--ink);cursor:pointer}
.act svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.act:hover{border-color:var(--ink)}
.acc[aria-pressed=true]{background:var(--forest);border-color:var(--forest);color:#fff}
.rej[aria-pressed=true]{background:var(--clay);border-color:var(--clay);color:#fff}
.alt summary{display:inline-flex;align-items:center;min-height:44px;cursor:pointer;color:var(--teal);font-size:16px;font-weight:500}
.alt summary:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.alt textarea{display:block;width:100%;font:inherit;font-size:17px;color:var(--ink);background:#fff;border:1px solid var(--line);border-radius:3px;padding:10px 12px;margin:4px 0 8px;resize:vertical;min-height:88px}
.alt textarea:focus-visible{outline:3px solid var(--focus);outline-offset:1px}
.send{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.resp{margin:0;display:flex;flex-wrap:wrap;align-items:center;gap:0 10px;font-size:16px}
.rs{font-weight:600}
.r-accepted .rs{color:var(--forest)}.r-rejected .rs{color:var(--clay)}.r-comment .rs{color:var(--teal)}
.rc{flex-basis:100%;color:var(--ink2);white-space:pre-wrap}
.undo{font:inherit;font-size:16px;min-height:44px;padding:0 10px;background:none;border:0;color:var(--teal);text-decoration:underline;text-underline-offset:4px;cursor:pointer}
.dec.r-accepted{border-left-color:var(--forest)}.dec.r-rejected{border-left-color:var(--clay)}.dec.r-comment{border-left-color:var(--teal)}
.sync{font-size:15.5px;align-self:center}
#export textarea{width:100%;font:15px/1.5 ui-monospace,'SF Mono',Menlo,monospace;color:var(--ink);border:1px solid var(--line);border-radius:3px;padding:10px;margin-top:10px}
.meta{font-size:15.5px;color:var(--sub);margin-top:2px}
.steps .todo .meta{color:var(--ochre)}
.meta.blocks{color:var(--clay);font-weight:500}
.list .item{padding:18px 0;border-bottom:1px solid var(--rule)}
.list .item:last-child{border-bottom:0}
.tags,.srow{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;margin-top:6px}
.srow{margin-top:0}
.now{margin:6px 0 4px}
.tag{display:inline-block;white-space:nowrap;font-size:15.5px;font-weight:500;color:var(--c);padding:1px 11px 1px 10px;border:1px solid color-mix(in srgb,var(--c) 35%,transparent);border-radius:999px;background:color-mix(in srgb,var(--c) 7%,#fff)}
.tag::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--c);margin-right:7px;vertical-align:2px}
.st{font-size:15.5px;display:inline-flex;align-items:center;gap:8px;color:var(--ink2)}
.st::before{content:"";width:9px;height:9px;border-radius:50%;flex:none}
.st.ok::before{background:var(--sage)}
.st.wait::before{background:var(--mustard)}
.st.later::before{background:var(--peach)}
.st.you{color:var(--clay)}
.st.you::before{background:var(--rust)}
.st.none{color:var(--sub)}
.st.none::before{background:#c9d2c5}
.note{font-size:15.5px;color:var(--sub);margin:12px 0 0}
.settled .muted{/* prose_html handles lists */}
.prose-list{margin:0;padding:0 0 0 1.15em;list-style:disc}
.prose-list li{margin:0.15em 0;padding:0;line-height:1.35}
.dec-head{display:grid;gap:4px;margin-bottom:10px}
.dec-title{font-size:1.05rem}
.dec .rec,.dec .why{margin:8px 0 0;font-size:.92rem}
.dec.settled .respond{display:none}
.dec-body .prose-list{font-size:inherit;color:inherit}
.muted .prose-list{color:inherit}
ul.settled > li{display:grid;grid-template-columns:64px 1fr;gap:18px;padding:16px 0;border-bottom:1px solid var(--rule)}
ul.settled > li:last-child{border-bottom:0}
.time{color:var(--olive);font-size:16px;font-weight:500;padding-top:2px}
/* Priorities */
.pri{padding:16px 0;border-bottom:1px solid var(--rule)}.pri:last-child{border-bottom:0}
.plist{list-style:none;margin:8px 0 0;padding:0;counter-reset:pi}
.pi{display:grid;grid-template-columns:78px minmax(0,1fr);gap:12px;align-items:baseline;padding:5px 0 5px 12px;border-left:3px solid transparent}
.pm{font-size:13.5px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--sub)}
.p-done .t{color:var(--sub);text-decoration:line-through;text-decoration-thickness:1.5px}.p-done .pm{color:var(--forest)}
.p-current{border-left-color:var(--mustard);background:color-mix(in srgb,var(--mustard) 12%,transparent)}.p-current .t{color:var(--ink);font-weight:500}.p-current .pm{color:var(--ochre)}
.p-blocked .t,.p-blocked .pm{color:var(--clay)}.p-blocked{border-left-color:color-mix(in srgb,var(--rust) 60%,transparent)}
.p-next .t{color:var(--ink2)}
/* Architecture */
.arch-head{display:flex;flex-wrap:wrap;align-items:center;gap:12px 24px;padding:8px 0 14px;border-bottom:1px solid var(--rule)}
.tabs{display:flex;flex-wrap:wrap;gap:6px}
.tabs button{font:inherit;font-size:16px;color:var(--sub);background:none;border:1px solid var(--line);border-radius:20px;padding:6px 14px;cursor:pointer}
.tabs button:hover{color:var(--ink);border-color:var(--ink)}
.tabs button[aria-selected=true]{background:var(--ink);border-color:var(--ink);color:var(--bg)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;margin-left:auto;font-size:15.5px;color:var(--sub)}
.lg b{font-weight:500;color:var(--ink)}
.arch-sum{margin:14px 0 2px;color:var(--ink)}
.arch-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 20px;margin:2px 0 10px}
.arch-meta{margin:0;font-size:15.5px;color:var(--sub)}
.arch-meta a{margin-left:4px}
.views{display:inline-flex;margin-left:auto;border:1px solid var(--line);border-radius:3px;overflow:hidden}
.vt{font:inherit;font-size:16px;font-weight:500;min-height:44px;min-width:44px;padding:0 18px;border:0;background:none;color:var(--sub);cursor:pointer}
.vt+.vt{border-left:1px solid var(--line)}
.vt:hover{color:var(--ink)}
.vt[aria-pressed=true]{background:var(--ink);color:var(--bg)}
.vt:focus-visible{outline:3px solid var(--focus);outline-offset:-3px}
.bb-frame iframe{display:block;width:100%;height:min(82vh,900px);border:1px solid var(--line);border-radius:3px;background:#fbf9f6}
#architecture{height:auto}
#architecture .pb{max-height:none}
dialog{border:1px solid var(--line);border-radius:3px;background:var(--card);color:var(--ink2);padding:0;width:min(560px,calc(100vw - 32px));box-shadow:0 18px 50px #173d3b33}
dialog::backdrop{background:#0e1b1a59}
.pop{padding:24px 28px 26px}
.pop h2{font-size:26px;font-weight:500;color:var(--ink);margin:0 0 10px;letter-spacing:-.01em;padding-right:44px}
.pop p{margin:10px 0 0}
.pop .x{position:absolute;top:14px;right:14px;font:inherit;font-size:24px;line-height:1;width:40px;height:40px;background:none;border:1px solid var(--line);border-radius:3px;color:var(--ink);cursor:pointer}
footer{margin-top:var(--gap);font-size:15.5px;color:var(--sub);display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;vertical-align:-1px;margin-right:2px}
@media (min-width:1100px){
 .wrap{padding:30px 56px 44px}
 .top{grid-template-columns:minmax(0,40fr) minmax(0,60fr);grid-template-rows:auto 1fr;grid-template-areas:"banner spark" "act spark";align-items:stretch;gap:14px}
 .banner{grid-area:banner;align-self:start}
 .spark{grid-area:spark;align-self:stretch}
 .activity{grid-area:act}
 .sp-body,.trends,.tr-plot{flex:1 1 auto}
 .tr-plot{grid-template-rows:minmax(88px,1fr) auto}
 .tr-area{height:auto}
 .tr-svg{position:absolute;inset:0}
 .nrow{grid-template-columns:13em minmax(0,1.2fr) minmax(0,1.5fr) minmax(0,.6fr) minmax(0,.6fr);padding:4px 0}
 .nsub{font-size:14px}
 .nrow + .nrow .ml{display:none}
 .grid{grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch}
 .pane{height:clamp(420px,70vh,760px)}
 .pane.closed{height:auto}
 #architecture{grid-column:1/-1}
}
@media (min-width:1700px){
 .top{grid-template-columns:minmax(0,40.3fr) minmax(0,44.7fr) minmax(0,15fr);grid-template-rows:auto;grid-template-areas:"banner spark act"}
}
@media (max-width:700px){.legend{margin-left:0}.views{margin-left:0}.bb-frame iframe{height:min(78vh,760px)}.nrow{grid-template-columns:minmax(0,.75fr) minmax(0,1.7fr) minmax(0,.75fr) minmax(0,.75fr);gap:4px 10px;padding:8px 0}.nn{grid-column:1/-1}.spark{padding:12px 16px}.tr-area{height:120px}.tr-plot{grid-template-rows:120px auto}.tr-x span:nth-child(2n){visibility:hidden}.mv{font-size:19px}.ml{font-size:15px}.mx{font-size:14px}.csum{display:none}}
@media (max-width:640px){.wrap{padding:16px 16px 24px}h1{font-size:29px}header{gap:10px 12px;padding-bottom:14px;margin-bottom:18px}.top{gap:14px;margin-bottom:18px}.tools{margin-left:0;width:100%;flex-wrap:nowrap;gap:8px}.tools button{flex:1;min-height:44px;padding:6px 8px}.sync{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}.long{display:none}.ph{padding:14px 16px}.pb{padding:6px 16px 16px;max-height:70vh}.pt{font-size:20px}.pop{padding:20px}}
"""

EXTRA = """
.metrics .mlist{display:flex;flex-direction:column}
.mrow{display:grid;grid-template-columns:minmax(6em,.8fr) minmax(4em,.4fr) minmax(0,1.6fr) minmax(0,1fr);gap:4px 12px;align-items:center;padding:6px 0;border-top:1px solid var(--rule)}
.mrow .bar i{background:var(--teal)}
.m-at{margin:0;font-size:13px;color:var(--sub);line-height:1.35}
@media (min-width:1100px){
 .top.no-spark{grid-template-columns:minmax(0,40fr) minmax(0,60fr);grid-template-rows:auto;grid-template-areas:"banner act"}
 .top.no-act{grid-template-rows:auto;grid-template-areas:"banner spark"}
 .top.no-banner{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto;grid-template-areas:"spark" "act"}
 .top.no-spark.no-act,.top.no-spark.no-banner,.top.no-act.no-banner{grid-template-columns:minmax(0,1fr);grid-template-rows:auto;grid-template-areas:none}
 .top.no-spark.no-act>*,.top.no-spark.no-banner>*,.top.no-act.no-banner>*{grid-area:auto}
}
@media (min-width:1700px){
 .top.no-spark{grid-template-columns:minmax(0,40.3fr) minmax(0,59.7fr);grid-template-areas:"banner act"}
 .top.no-act{grid-template-columns:minmax(0,40.3fr) minmax(0,59.7fr);grid-template-areas:"banner spark"}
 .top.no-banner{grid-template-columns:minmax(0,75fr) minmax(0,25fr);grid-template-areas:"spark act"}
}
@media (max-width:700px){.mrow{grid-template-columns:minmax(0,1fr) auto;}.mrow .bar,.mrow .mx{grid-column:1/-1}}
"""

CSS = BASE + EXTRA
