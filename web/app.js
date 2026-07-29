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
/* Плейсхолдер фото. Лапки лишались із часів, коли каталог був суто зоо; тепер там
   ноутбуки й тонометри. Значок нейтральний і векторний — емодзі малюються по-різному
   на кожній платформі, а це елемент, який видно на ТРЕТИНІ стрічки: KTC (2405 з 2405)
   і Eldorado (923 з 923) не віддають фото взагалі. */
const PH_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"
  stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/>
  <circle cx="8.5" cy="9.5" r="1.6"/><path d="M21 15.5l-5-5-5 5-3-3-5 5"/></svg>`;
const PH_HTML = `<div class="ph">${PH_SVG}</div>`;

/* ── гліф за розділом (S32) ───────────────────────────────────────────────────────
   Той самий значок «немає картинки» на третині стрічки читався як зламана сторінка.
   Тепер плитка каже хоч щось про товар. Ключ рахує сервер (taxonomy.glyph_key) —
   розділ живе лише там, і два клієнти не мають групувати товари по-різному.
   Вектор, не емодзі: причина та сама, що й у PH_SVG вище. */
const GLYPHS = {
  device:   `<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/>`,
  camera:   `<path d="M4 7h3l1.5-2h7L17 7h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z"/><circle cx="12" cy="12.5" r="3.2"/>`,
  appliance:`<rect x="5" y="3" width="14" height="18" rx="2"/><circle cx="12" cy="14" r="4"/><path d="M8 6.5h2"/>`,
  tool:     `<path d="M15.5 3.5a5 5 0 0 0-6.1 6.6L3.7 15.8a2 2 0 0 0 2.8 2.8l5.7-5.7a5 5 0 0 0 6.6-6.1l-3 3-2.6-.7-.7-2.6 3-3z"/>`,
  car:      `<path d="M3 16h18v-3.2a2 2 0 0 0-.5-1.3L18 8H6l-2.5 3.5A2 2 0 0 0 3 12.8V16z"/><circle cx="7.5" cy="16" r="1.4"/><circle cx="16.5" cy="16" r="1.4"/>`,
  pet:      `<circle cx="8" cy="8" r="1.8"/><circle cx="12" cy="6.5" r="1.8"/><circle cx="16" cy="8" r="1.8"/><path d="M12 11c-3 0-5 2.2-5 4.4 0 1.7 1.3 2.6 2.8 2.6h4.4c1.5 0 2.8-.9 2.8-2.6C17 13.2 15 11 12 11z"/>`,
  health:   `<rect x="3" y="7" width="18" height="12" rx="2.5"/><path d="M12 10.5v5M9.5 13h5"/>`,
  toy:      `<circle cx="7.5" cy="7" r="2.2"/><circle cx="16.5" cy="7" r="2.2"/><circle cx="12" cy="13.5" r="5.6"/>`,
  sport:    `<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c3 4.5 3 12.5 0 17M12 3.5c-3 4.5-3 12.5 0 17"/>`,
  watch:    `<circle cx="12" cy="12" r="4.8"/><path d="M9 7.2 9.5 3h5l.5 4.2M9 16.8 9.5 21h5l.5-4.2"/>`,
  box:      `<path d="M12 3 3.5 7.5v9L12 21l8.5-4.5v-9L12 3z"/><path d="M3.5 7.5 12 12l8.5-4.5M12 12v9"/>`,
};
/* ── значки порожніх станів (S33) ─────────────────────────────────────────────────
   Було 14 місць із емодзі кеглем 40px: 🔍 🏷 ⚖️ 📉 🏪 🧭 ⚠️. Це рівно той аргумент,
   яким емодзі відкинули для плиток товарів (див. PH_SVG) — вони малюються по-різному
   на кожній платформі. Правило застосували до третини стрічки й не застосували до
   сторінок помилок, порожнього пошуку й 404. Тепер той самий вектор. */
const ICONS = {
  search: `<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>`,
  tag:    `<path d="M12.6 3H4a1 1 0 0 0-1 1v8.6a2 2 0 0 0 .6 1.4l7.4 7.4a2 2 0 0 0 2.8 0l6.6-6.6a2 2 0 0 0 0-2.8L14 3.6a2 2 0 0 0-1.4-.6z"/><circle cx="7.8" cy="7.8" r="1.5"/>`,
  scales: `<path d="M12 4v16M6 8h12M8 20h8"/><path d="M4.5 8 2 14h5L4.5 8zM19.5 8 17 14h5l-2.5-6z"/>`,
  drop:   `<path d="M3 7l6 6 4-4 8 8"/><path d="M15 17h6v-6"/>`,
  store:  `<path d="M4 9h16v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9z"/><path d="M3 9l1.6-4.4A1 1 0 0 1 5.5 4h13a1 1 0 0 1 .9.6L21 9"/><path d="M9.5 20v-6h5v6"/>`,
  compass:`<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2.1 5-5 2.1 2.1-5 5-2.1z"/>`,
  warn:   `<path d="M12 4.5 2.8 20h18.4L12 4.5z"/><path d="M12 10v4.6M12 17.5v.1"/>`,
};
function icon(key){
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
    >${ICONS[key] || ICONS.tag}</svg>`;
}

function phHtml(key){
  return `<div class="ph"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
    >${GLYPHS[key] || GLYPHS.box}</svg></div>`;
}

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

/* ── порівняння товарів (S26) ────────────────────────────────────────────────────
   Сервер уміє /api/compare з S14 (2-4 товари), у застосунку є екран — на сайті не було
   нічого. Вибір тримаємо в localStorage: людина набирає товари, гортаючи каталог, і
   вибір не має зникати від переходу на сторінку товару чи перезавантаження.
   Стеля 4 — не забаганка UI, а межа самого ендпойнта. */
const CMP_MAX = 4;
const COMPARE = {
  get list(){ try { return JSON.parse(localStorage.getItem('hapay_cmp') || '[]')
                      .filter(Number.isInteger).slice(0, CMP_MAX); }
              catch(e){ return []; } },
  has(id){ return this.list.includes(id); },
  set(a){ localStorage.setItem('hapay_cmp', JSON.stringify(a.slice(0, CMP_MAX))); },
  toggle(id){
    const a = this.list, i = a.indexOf(id);
    if (i >= 0) a.splice(i, 1);
    else if (a.length >= CMP_MAX) return false;   // мовчки не додаємо — кажемо смугою
    else a.push(id);
    this.set(a); return true;
  },
  clear(){ localStorage.removeItem('hapay_cmp'); },
};

/* Смуга внизу: скільки обрано + куди перейти. Малюється сама, один раз на сторінку. */
function renderCmpBar(){
  if (IN_TG) return;                 // у Mini App свій хром знизу — не займаємо його
  let bar = document.getElementById('cmpbar');
  if (!bar){
    bar = el(`<div class="cmpbar" id="cmpbar"><span class="n"></span>
      <a href="/compare">Порівняти</a>
      <button type="button" aria-label="Скинути вибір">Скинути</button></div>`);
    document.body.appendChild(bar);
    bar.querySelector('button').onclick = () => {
      COMPARE.clear(); renderCmpBar();
      document.querySelectorAll('.cmp').forEach(b => {
        b.setAttribute('aria-pressed', 'false'); b.textContent = '+ до порівняння'; });
    };
  }
  const n = COMPARE.list.length;
  bar.querySelector('.n').textContent = n >= CMP_MAX
    ? `Обрано ${n} — це максимум`
    : plu(n, 'товар обрано', 'товари обрано', 'товарів обрано');
  // порівнювати можна від двох; поки один — смугу показуємо, але кнопку глушимо
  const go = bar.querySelector('a');
  go.href = '/compare';
  go.style.pointerEvents = n < 2 ? 'none' : '';
  go.style.opacity = n < 2 ? '.45' : '';
  bar.classList.toggle('on', n > 0);
}

/* Кнопка на картці. Повертає готовий рядок розмітки; обробник вішає cmpBind(). */
function cmpButton(id){
  const on = COMPARE.has(id);
  return `<button type="button" class="cmp" data-cmp="${id}" aria-pressed="${on}">` +
         `${on ? '✓ у порівнянні' : '+ до порівняння'}</button>`;
}

function cmpBind(root){
  root.querySelectorAll('[data-cmp]').forEach(b => {
    b.addEventListener('click', e => {
      e.stopPropagation();            // клік по картці веде на товар — тут не веде
      e.preventDefault();
      const id = +b.dataset.cmp;
      if (!COMPARE.toggle(id)) { renderCmpBar(); return; }   // уперлись у стелю
      const on = COMPARE.has(id);
      b.setAttribute('aria-pressed', on);
      b.textContent = on ? '✓ у порівнянні' : '+ до порівняння';
      renderCmpBar();
    });
  });
}

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
  const nav = [['/', 'Головна'], ['/catalog', 'Знижки'], ['/drops', 'Подешевшало']];
  // «Перейти до вмісту» — перше, на що потрапляє Tab: інакше клавіатурі доводиться
  // проходити всю шапку й фільтри перед кожним переглядом стрічки.
  h.innerHTML = `<a class="skip" href="#list">Перейти до вмісту</a><div class="hrow">
    <a class="brand" href="/"><span class="wordmark">Хапай</span><span class="sub">знижки проти історії цін</span></a>
    <nav class="nav">${nav.map(([href,label]) =>
      `<a href="${href}" class="${active===href?'on':''}">${label}</a>`).join('')}</nav>
    ${opts.search ? `<div class="searchwrap">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input id="search" class="search" placeholder="Пошук за назвою…" autocomplete="off"
             aria-label="Пошук за назвою товару"></div>` : ''}
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
  // «Як ми перевіряємо» першим: це головна сторінка довіри, і вона мусить бути
  // досяжна з БУДЬ-ЯКОГО місця сайту, а не лише з головної.
  f.innerHTML = `<a href="/how">Як ми перевіряємо</a><a href="/verify">Перевірити наші записи</a><a href="/stores">Крамниці</a>
    <a href="/privacy">Конфіденційність</a><a href="/terms">Умови</a>
    <a href="/support">Підтримка</a>
    <div style="margin-top:10px">Ціни й назви — публічні дані крамниць; перевірка знижки
      рахується з нашої власної історії спостережень.</div>`;
}


/* Графік = головне твердження продукту (T12), тому малюємо РІВНО те, що виміряли:
   сходинки (не інтерполяція — вона вигадує ціни, яких не існувало), вісь X за реальними
   датами (щоб прогалини було видно), точки завжди, пунктир там, де вимірів не було. */

/* ── мікрографік у картці стрічки (S32) ──────────────────────────────────────────
   Наша єдина унікальна річ — власна історія цін — доти була невидима, доки людина
   не відкриє товар. 64×20 у рядку переносять її на першу поверхню.

   Це НЕ зменшена копія графіка зі сторінки товару. Там ми показуємо провенанс:
   точки вимірів, пунктир на прогалинах, лінію 30-денної бази. Тут на це немає
   пікселів, і кожна з тих деталей стала б шумом — тому тут лише ФОРМА, а
   твердження лишається на сторінці товару, куди веде картка.

   Що ЗБЕРЕЖЕНО з тієї логіки й чому: сходинки замість інтерполяції (пряма між
   двома вимірами вигадує ціни, яких не було — T12) і вісь X за реальними зсувами
   діб (прогалина лишається прогалиною, а не стискається в рівний крок). */
function sparkMini(pts, days){
  if(!pts || pts.length < 3) return '';       // менше трьох діб — це не лінія, а відрізок
  const W=64, H=20, pad=2, span=Math.max(days-1, 1);
  const ys=pts.map(p=>p[1]);
  const lo=Math.min(...ys), hi=Math.max(...ys);
  const X=d=>(pad+(W-2*pad)*Math.min(Math.max(d,0),span)/span).toFixed(1);
  const Y=v=>(hi===lo ? H/2 : pad+(H-2*pad)*(1-(v-lo)/(hi-lo))).toFixed(1);
  let d=`M${X(pts[0][0])} ${Y(pts[0][1])}`;
  for(let i=1;i<pts.length;i++)
    d+=` L${X(pts[i][0])} ${Y(pts[i-1][1])} L${X(pts[i][0])} ${Y(pts[i][1])}`;
  const label = hi===lo
    ? `Наша ціна не змінювалась: ${grn(lo)}`
    : `Наші виміри: від ${grn(lo)} до ${grn(hi)}`;
  /* Рамка 30-денного вікна. Без неї товар із вимірами лише за пʼять діб малювався
     коротким відрізком посеред порожнечі й читався як випадкова риска, а не як
     графік (побачено на емуляторі застосунку, де та сама логіка). Лінія знизу
     показує, скільки вікна ми ПОКРИЛИ — те саме твердження, що «стежимо N із 30». */
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}"
    ><title>${esc(label)}</title><line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}"
    stroke="currentColor" stroke-width="1" opacity=".28" vector-effect="non-scaling-stroke"/
    ><path d="${d}" fill="none" stroke="currentColor"
    stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"
    vector-effect="non-scaling-stroke"/></svg>`;
}

function sparkline(points, refKop, W, H){
  if(points.length<2) return '<div class="prov">Замало вимірів для графіка — історія ще накопичується.</div>';
  // H передає викликач: на широкій сторінці товару графік 954×158 (6:1) сплющував рух
  // ціни в майже пряму. Значення за замовчуванням — те, що було.
  const DAY=86400000, pad=8; H = H || 158;
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
