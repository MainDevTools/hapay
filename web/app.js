/* Спільне ядро сайту (S19): хелпери, звернення до API, стан входу, шапка/підвал.
   Логіка стрічки живе в catalog.js, бо потрібна лише каталогу й товару. */
const tg = window.Telegram && window.Telegram.WebApp;

/* ⚠ `tg` ІСНУЄ й у звичайному браузері: скрипт telegram-web-app.js створює
   window.Telegram.WebApp завжди. Перевірка `if (tg)` тому НЕ означає «ми в Telegram»
   (2026-07-26: через неї лендинг перекидало на /catalog, а шапку й підвал зрізало на
   всіх сторінках — у браузері виміряно initData="" і platform="unknown").
   Справжня ознака міні-застосунку — непорожній initData або відома платформа. */
const IN_TG = !!(tg && (tg.initData || (tg.platform && tg.platform !== 'unknown')));
if (IN_TG) { tg.ready(); tg.expand(); }

/* ⚠ МОВА МІТОК — РІШЕННЯ ОПЕРАТОРА 2026-07-26: «звести мову бейджів — сайт під
   застосунок». Рядки скопійовано ДОСЛІВНО з `app-maui/Models/Models.cs` (BadgeText) і
   `Views/HomePage.xaml` (чіпи), щоб дві поверхні не розходились удруге.

   Це ЗАМІЩАЄ попереднє формулювання сайту, яке трималось на T12/§5.4.1: там мітки
   свідомо були ВИМІРАМИ, не вердиктом («↓ Нижче за 30 днів», «≥ Не нижче»), а ✓/⚠
   уникались саме як оцінка. Рішення змінити це — людське й свідоме; CC його не ухвалював
   і не має міняти назад без оператора. Якщо §5.4.1 у спеці ще описує стару мову — її
   треба привести у відповідність (крок оператора, не мій).

   Наслідок, який варто памʼятати: застосунок НЕ показує мітки для `declared` і
   `insufficient_history` (BadgeText → null), а це 23 564 з 23 612 подій. Тобто пігулку
   тепер бачить лише той товар, про який нам справді є що сказати. */
const BADGES = [
  {k:'', label:'Усі'},
  {k:'verified', label:'✓ Підтверджені'},
  {k:'pumped', label:'⚠ Завищена стара ціна'},
];
// Пігулка на картці; null = не кажемо нічого (як у застосунку). Повне твердження з
// provenance дає сторінка товару (§5.4.2).
const BADGE_TEXT = {
  verified:'🛡 знижка перевірена',
  verified_provisional:'🛡 знижка перевірена',
  pumped:'⚠ «стара» ціна завищена',
};
let badge='', sort='verified', cat='', query='', page=0;

// Цілі гривні — без «,00» (так само, як у застосунку: Money.Grn). З копійками —
// два знаки. Інакше «19 999,00 ₴» з'їдає ширину й читається важче за «19 999 ₴».
const grn = k => k==null ? '—'
  : (k/100).toLocaleString('uk-UA', k%100===0
      ? {maximumFractionDigits:0}
      : {minimumFractionDigits:2,maximumFractionDigits:2}) + ' ₴';
const el = h => { const d=document.createElement('div'); d.innerHTML=h.trim(); return d.firstElementChild; };
const esc = s => (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function pct(d){ if(d.old_declared_kop && d.current_kop < d.old_declared_kop)
  return Math.round((1 - d.current_kop/d.old_declared_kop)*100); return null; }
const plu = (n,a,b,c) => { const m=n%100, k=n%10;
  return n+' '+(m>=11&&m<=14 ? c : k===1 ? a : k>=2&&k<=4 ? b : c); };

/* ── стан входу ──────────────────────────────────────────────────────────────────
   Токен у localStorage (не sessionStorage, як в адмін-панелі): звичайний користувач
   очікує, що сайт памʼятає його між заходами, а прав тут рівно на свій watchlist.
   В адмінці інакше саме тому, що там ціна помилки інша. */
const AUTH = {
  get token(){ return localStorage.getItem('hapay_t') || ''; },
  get email(){ return localStorage.getItem('hapay_e') || ''; },
  get in(){ return !!this.token; },
  set(t, e){ localStorage.setItem('hapay_t', t); localStorage.setItem('hapay_e', e||''); },
  out(){ localStorage.removeItem('hapay_t'); localStorage.removeItem('hapay_e'); },
};

async function api(path, opts){
  const o = Object.assign({headers:{}}, opts||{});
  if (tg && tg.initData) o.headers['X-Init-Data'] = tg.initData;
  if (AUTH.token) o.headers['Authorization'] = 'Bearer ' + AUTH.token;
  if (o.body) o.headers['Content-Type'] = 'application/json';
  const r = await fetch(path, o);
  if (r.status === 401 && AUTH.in) { AUTH.out(); }   // сесія протухла — не тримаємо привида
  if(!r.ok){
    let d = 'Помилка ' + r.status;
    try { const j = await r.json(); if (j.detail) d = j.detail; } catch(e){}
    throw new Error(d);
  }
  return r.status === 204 ? null : r.json();
}

/* ── спільна шапка ───────────────────────────────────────────────────────────────
   Одна розмітка на всі сторінки: бренд → навігація → пошук (лише де треба) → вхід.
   `active` підсвічує поточний розділ. У Telegram Mini App шапку не малюємо: там
   свій хром, а наші посилання вели б із міні-застосунку в браузер. */
function renderHeader(active, opts){
  opts = opts || {};
  const h = document.getElementById('hdr');
  if (!h || IN_TG) { if (h && IN_TG) h.remove(); return; }
  const nav = [['/', 'Головна'], ['/catalog', 'Знижки']];
  h.innerHTML = `<div class="hrow">
    <a class="brand" href="/"><h1>Хапай</h1><span class="sub">знижки проти історії цін</span></a>
    <nav class="nav">${nav.map(([href,label]) =>
      `<a href="${href}" class="${active===href?'on':''}">${label}</a>`).join('')}</nav>
    ${opts.search ? `<div class="searchwrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input id="search" class="search" placeholder="Пошук за назвою…" autocomplete="off"></div>` : ''}
    <div class="hauth">${AUTH.in
      ? `<a href="/me" class="hme" title="${esc(AUTH.email)}">Мій кабінет</a>`
      : `<a href="/login" class="hlogin">Увійти</a>`}</div>
  </div>${opts.controls || ''}`;
}

/* ── хлібні крихти ───────────────────────────────────────────────────────────────
   items = [{href, label}, …]; ОСТАННІЙ елемент — поточна сторінка, без посилання
   (посилання на себе — шум). У Telegram не малюємо: там свій хром і своя навігація. */
function renderCrumbs(items){
  const box = document.getElementById('crumbs');
  if (!box || IN_TG) { if (box) box.hidden = true; return; }
  box.hidden = false;
  box.className = 'crumbs';
  box.setAttribute('aria-label', 'Хлібні крихти');
  box.innerHTML = items.map((it, i) => i === items.length - 1
    ? `<span class="cur">${esc(it.label)}</span>`
    : `<a href="${it.href}">${esc(it.label)}</a><span class="sep">›</span>`).join('');
}

/* ── ціновий фільтр ──────────────────────────────────────────────────────────────
   Малюємо в контейнер (їх два: бічна колонка на десктопі й блок над списком на
   телефоні), тому шукаємо елементи ВСЕРЕДИНІ контейнера, а не за id — інакше два
   однакові id, і на телефоні працював би прихований десктопний. */
function renderPrice(box, state, onApply){
  if (!box) return;
  const g = k => k == null ? '' : Math.round(k / 100);      // копійки → гривні на показ
  box.className = 'pricef';
  box.innerHTML = `<div class="ttl">Ціна</div>
    <div class="fields">
      <input class="pmin" inputmode="numeric" placeholder="від" value="${g(state.min)}">
      <input class="pmax" inputmode="numeric" placeholder="до" value="${g(state.max)}">
      <span class="cur">₴</span>
      <button class="go" type="button">OK</button>
    </div>
    <button class="clr ${state.min != null || state.max != null ? 'on' : ''}">Скинути</button>`;

  const num = s => {
    const v = parseInt(String(s).replace(/[^\d]/g, ''), 10);   // «1 500 грн» → 1500
    return Number.isFinite(v) && v >= 0 ? v * 100 : null;      // гривні → копійки (інв. A)
  };
  const apply = () => {
    let lo = num(box.querySelector('.pmin').value);
    let hi = num(box.querySelector('.pmax').value);
    // переплутані межі — не помилка користувача, а наша: міняємо місцями мовчки
    if (lo != null && hi != null && lo > hi) { const t = lo; lo = hi; hi = t; }
    onApply(lo, hi);
  };
  box.querySelector('.go').onclick = apply;
  box.querySelectorAll('input').forEach(i =>
    i.addEventListener('keydown', e => { if (e.key === 'Enter') apply(); }));
  box.querySelector('.clr').onclick = () => onApply(null, null);
}

function renderFooter(){
  const f = document.getElementById('ftr');
  if (!f || IN_TG) { if (f && IN_TG) f.remove(); return; }
  f.className = 'foot';
  f.innerHTML = `<a href="/privacy">Конфіденційність</a><a href="/terms">Умови</a>
    <a href="/support">Підтримка</a>
    <div style="margin-top:10px">Ціни й назви — публічні дані крамниць; перевірка знижки
      рахується з нашої власної історії спостережень.</div>`;
}


/* Графік = головне твердження продукту (T12), тому малюємо РІВНО те, що виміряли:
   сходинки (не інтерполяція — вона вигадує ціни, яких не існувало), вісь X за реальними
   датами (щоб прогалини було видно), точки завжди, пунктир там, де вимірів не було. */

function sparkline(points, refKop, W){
  if(points.length<2) return '<div class="prov">Замало вимірів для графіка — історія ще накопичується.</div>';
  const DAY=86400000, H=158, pad=8;
  const xs=points.map(p=>Date.parse(p.day)), ys=points.map(p=>p.min_kop);
  const t0=xs[0], tN=xs[xs.length-1], span=Math.max(tN-t0, DAY);
  let minY=Math.min(...ys), maxY=Math.max(...ys);
  if(refKop!=null){ minY=Math.min(minY,refKop); maxY=Math.max(maxY,refKop); }   // база завжди в кадрі
  const X=i=>pad+(W-2*pad)*(xs[i]-t0)/span;
  const sy=v=>maxY===minY?H/2:pad+(H-2*pad)*(1-(v-minY)/(maxY-minY));
  const Y=i=>sy(ys[i]);
  const f=n=>n.toFixed(1);

  let solid='', dashed='', area=`M${f(X(0))} ${H-pad} L${f(X(0))} ${f(Y(0))}`;
  for(let i=1;i<points.length;i++){
    const seg=`M${f(X(i-1))} ${f(Y(i-1))} L${f(X(i))} ${f(Y(i-1))} L${f(X(i))} ${f(Y(i))}`;
    if(xs[i]-xs[i-1] > 1.5*DAY) dashed+=seg+' '; else solid+=seg+' ';   // доба без вимірів → не стверджуємо
    area+=` L${f(X(i))} ${f(Y(i-1))} L${f(X(i))} ${f(Y(i))}`;
  }
  area+=` L${f(X(points.length-1))} ${H-pad} Z`;

  const tRef=Math.max(t0, tN-30*DAY);                        // початок статутного 30-денного вікна
  const xRef=pad+(W-2*pad)*(tRef-t0)/span;
  // база — НЕЙТРАЛЬНА (не зелена): зелень читалась би як вердикт «добре», а видимий шар не оцінює (T12).
  // Плюс --green ≈ --accent, тож зелена база злилася б із лінією ціни.
  const ref = refKop==null ? '' :
    `<line x1="${f(xRef)}" y1="${f(sy(refKop))}" x2="${W-pad}" y2="${f(sy(refKop))}" stroke="var(--muted)"
       stroke-dasharray="3 4" stroke-width="1.5" opacity=".9" vector-effect="non-scaling-stroke"/>` +
    (tRef>t0 ? `<line x1="${f(xRef)}" y1="${pad}" x2="${f(xRef)}" y2="${H-pad}" stroke="var(--line)"
       stroke-dasharray="2 3" stroke-width="1" vector-effect="non-scaling-stroke"/>` : '');

  return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="var(--accent)" stop-opacity=".22"/>
      <stop offset="1" stop-color="var(--accent)" stop-opacity="0"/></linearGradient></defs>
    <path d="${area}" fill="url(#g)"/>
    ${ref}
    <path d="${solid}" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linejoin="round"
      stroke-linecap="round" vector-effect="non-scaling-stroke"/>
    <path d="${dashed}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-dasharray="4 4"
      opacity=".45" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    ${points.map((p,i)=>`<circle cx="${f(X(i))}" cy="${f(Y(i))}" r="${points.length>40?1.6:2.8}" fill="var(--accent)"/>`).join('')}
  </svg>`;
}
