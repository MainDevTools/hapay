/* Стрічка каталогу: чіпи, картки, пагінація, бічна колонка (S19).
   Історію ціни показує окрема сторінка /product/{id} — шторку прибрано,
   щоб та сама логіка не жила у двох місцях. */
/* <button aria-pressed>, а не <div onclick>: чіп — це перемикач фільтра, і з клавіатури
   до нього треба потрапляти Tab-ом, а читач екрана мусить казати, увімкнений він чи ні. */
/* Чіп «Лише знижки» — окремий зріз, а не badge: сервер розрізняє «є знижка взагалі»
   (only_discounts) і «знижка з таким вердиктом» (badge). Тримати це одним параметром
   означало б вигадати п'ятий стан бейджа, якого в БД немає. */
function renderChips(){
  const c = document.getElementById('chips'); c.innerHTML='';
  BADGES.forEach(b=>{
    const on = b.k==='sale' ? (onlyDiscounts && !badge) : (b.k===badge && !onlyDiscounts);
    const chip=el(`<button type="button" class="chip ${on?'on':''}" aria-pressed="${on}">${b.label}</button>`);
    chip.onclick=()=>{
      if (b.k==='sale'){ onlyDiscounts=true; badge=''; }
      else { badge=b.k; onlyDiscounts=false; }
      page=0;
      renderChips(); syncUrl(); load();
    };
    c.appendChild(chip); });
}

function card(d){
  const off = pct(d);
  const bt = BADGE_TEXT[d.badge_state];   // undefined = мітки нема (як у застосунку)
  const href = '/product/' + d.store_product_id;
  // Гліф за розділом рахує сервер; на биту картинку падаємо в ТОЙ САМИЙ гліф, а не
  // в загальний значок «немає фото» — інакше плитка стрибала б між двома виглядами.
  const gk = d.glyph || 'box';
  const ph = phHtml(gk);
  const c = el(`<div class="card">
    <div class="thumb">
      ${d.image_url?`<img src="${esc(d.image_url)}" loading="lazy" alt="${esc(d.title)}" onerror="this.outerHTML=phHtml('${gk}')">`:ph}
      ${off?`<span class="off">−${off}%</span>`:''}
    </div>
    <div class="body">
      <a class="title" href="${href}">${esc(d.title)}</a>
      <div class="meta"><b>${esc(d.store||'')}</b>${d.variant_note?' · '+esc(d.variant_note):''}</div>
      ${bt?`<span class="badge"><span class="dot"></span>${bt}</span>`:''}
    </div>
    <div class="pricebox">
      <div class="prices">
        <span class="now">${grn(d.current_kop)}</span>
        ${d.old_declared_kop?`<span class="old">${grn(d.old_declared_kop)}</span>`:''}
        ${sparkMini(d.spark, 30)}
      </div>
      ${d.offers_n>1?`<div class="offers">Всі пропозиції (${d.offers_n})</div>`:''}
      <a class="buy" href="${href}">Порівняти ціни</a>
      ${cmpButton(d.store_product_id)}
    </div></div>`);
  // Клік по картці веде на СТОРІНКУ товару, а не у крамницю: там історія ціни,
  // усі пропозиції й провенанс — тобто те, заради чого людина сюди прийшла.
  // ⚠ Назва тепер СПРАВЖНЄ посилання: до цього картка була <div onclick>, тобто на
  // товар не було способу перейти ні з клавіатури, ні читачем екрана, ні краулером.
  // Клік по всій картці лишився для миші, але вкладені посилання й кнопка мусять
  // спиняти сплиття — інакше перехід спрацював би двічі.
  c.querySelectorAll('a').forEach(a => a.addEventListener('click', e=>e.stopPropagation()));
  cmpBind(c);
  c.onclick=()=>{ location.href = href; };
  return c;
}

function skeleton(n){
  const list=document.getElementById('list'); list.innerHTML='';
  for(let i=0;i<n;i++) list.appendChild(el(
    `<div class="skel"><div class="s-img sk"></div><div class="s-body">
      <div class="sk l-title"></div><div class="sk l-meta"></div>
      <div class="sk l-price"></div>
      <div class="sk l-badge"></div></div></div>`));
}
function setMore(show){ document.getElementById('morewrap').hidden = !show; }

async function load(reset=true, pageToLoad=null){
  const list=document.getElementById('list');
  if(reset){ page=0; skeleton(6); }
  if(pageToLoad===null) pageToLoad = page;
  try{
    /* ⚠ /api/products, а НЕ /api/discounts (S34). Заміряно 2026-07-29: у базі
       59 445 товарів, знижку має 28 504 — тобто стрічка сайту показувала 48%
       бази, а решта 30 941 товару була недосяжна взагалі: ані категорією, ані
       пошуком, ані фільтром ціни. При цьому їхні сторінки працювали й лежали в
       sitemap — з пошуковика зайти можна, з нашої ж головної ні.
       Знижковий зріз нікуди не подівся: він тепер чіп, а не єдиний режим. */
    const p=new URLSearchParams({sort,page:pageToLoad});
    if(badge)p.set('badge',badge);
    if(onlyDiscounts)p.set('only_discounts','1');
    if(cat)p.set('category',cat); if(query)p.set('q',query);
    if(!cat && SECT)p.set('section',SECT);
    if(PRICE.min!=null)p.set('price_min',PRICE.min);          // копійки (інв. A)
    if(PRICE.max!=null)p.set('price_max',PRICE.max);
    const data=await api('/api/products?'+p.toString());
    if(reset) list.innerHTML='';
    if(!data.length){
      if(reset){
        const s = query
          ? stateBox('search', 'Нічого не знайдено',
                     'Спробуйте коротший запит або перевірте написання.')
          : stateBox('tag', 'Поки порожньо',
                     'Колектор ще накопичує товари цієї категорії.');
        list.innerHTML = s.html; s.bind(list);
      }
      setMore(false); return;
    }
    /* Сервер міг підмінити точний пошук на схожий (S35). Мовчазна підміна — це
       відповідь на питання, якого не ставили, тож кажемо прямо. */
    if (reset && data[0] && data[0].fuzzy){
      list.appendChild(el(`<div class="note"><p>Точного збігу за запитом
        «${esc(query)}» немає. Показуємо <b>схоже за назвою</b> —
        можливо, у запиті одруківка.</p></div>`));
    }
    data.forEach(d=>list.appendChild(card(d)));
    // Схожий пошук віддає ОДНУ сторінку: пагінація по схожості означала б, що
    // друга сторінка ще менш схожа — тобто просто випадкові товари.
    setMore(data.length===50 && !(data[0] && data[0].fuzzy));
  }catch(e){
    // Помилка більше не глухий кут: та сама дія доступна кнопкою (S35).
    if(reset) showError(list, e, () => load(true, pageToLoad));
    setMore(false);
  }
}
function loadMore(){ page++; syncUrl(); load(false); }

/* ── стан стрічки переживає перехід у товар (S35) ─────────────────────────────────
   Заміряно на живому: після двох «Показати ще» в категорії було 150 карток і
   прокрутка 4000; повернення з товару давало 50 карток і прокрутку 414. Тобто сто
   карток і все місце в списку зникали — у каталозі з 59 445 товарів це найдорожчий
   дефект зручності з усіх.

   Сторінка живе в АДРЕСІ (?p=), прокрутка — в sessionStorage під ключем адреси:
   адресу можна переслати, а позиція в списку — річ особиста й тимчасова, їй в
   URL робити нічого. */
const SCROLL_KEY = () => 'sc:' + location.pathname + location.search;

function rememberScroll(){
  try { sessionStorage.setItem(SCROLL_KEY(), String(Math.round(window.scrollY))); }
  catch(e){}
}
// pagehide, а не beforeunload: у Safari/iOS другий не спрацьовує при переході назад,
// і саме там кеш «назад-вперед» найактивніший.
window.addEventListener('pagehide', rememberScroll);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') rememberScroll();
});

/* ⚠ Ціль беремо АРГУМЕНТОМ, а не з `page`: load(true, …) скидає page у нуль
   (це його робота — почати стрічку заново), тож на момент виклику відновлювати
   було б уже нічого. Спіймано одразу після написання, але клас помилки той самий,
   що ловить нас регулярно: стан, який читають ПІСЛЯ того, як його обнулили. */
async function restoreFeed(target){
  // Сторінки вантажимо ПОСЛІДОВНО, від нульової: клієнт не вміє просити «перші N*50»
  // одним запитом, а вигадувати для цього окремий ендпойнт заради двох додаткових
  // звернень — дорожче, ніж вони коштують.
  for (let i = 1; i <= target; i++) await load(false, i);
  page = target;
  const y = parseInt(sessionStorage.getItem(SCROLL_KEY()) || '0', 10);
  if (y > 0) window.scrollTo({top: y, behavior: 'instant'});
}

/* Бічна колонка: 171 категорія в 31 розділі. Плоский список був би стіною, тому
   групуємо за розділом — той самий порядок, що в застосунку (сервер уже віддає
   `section`). На телефоні колонка прихована, категорію обирає select у шапці. */
/* ⚠ Категорії — СПРАВЖНІ посилання (<a href>), а не <div onclick>. Було: 149 пунктів,
   до яких неможливо дійти Tab-ом, невидимих для читача екрана й для краулера. Тепер
   href робочий (сторінка відкриється й без JS, і в новій вкладці середньою кнопкою),
   а звичайний клік перехоплюємо — стрічка перемальовується без перезавантаження. */
function renderSide(cats){
  const box=document.getElementById('side'); if(!box) return;
  box.innerHTML='';
  const nav = el('<nav aria-label="Категорії"></nav>');
  const mk = (slug, label, n) => {
    const on = cat === slug;
    const a = el(`<a class="catlink ${on?'on':''}" href="/catalog${slug?'?c='+encodeURIComponent(slug):''}"
        ${on?'aria-current="page"':''}><span>${esc(label)}</span>${
        n==null?'':`<span class="n">${n}</span>`}</a>`);
    a.addEventListener('click', e => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;  // «відкрити в новій» лишаємо браузеру
      e.preventDefault(); setCat(slug);
    });
    return a;
  };
  nav.appendChild(mk('', 'Усі категорії', null));
  const bySect=new Map();
  cats.forEach(c=>{ const s=c.section||'Інше';
    if(!bySect.has(s)) bySect.set(s,[]); bySect.get(s).push(c); });
  // Заголовок розділу — ПОСИЛАННЯ на його сторінку, а не мертвий підпис: інакше
  // рівень над категорією видно, але дійти до нього неможливо.
  for(const [sect,items] of bySect){
    const sl = (items[0] && items[0].section_slug) || 'inshe';
    nav.appendChild(el(`<a class="sect" href="/section/${encodeURIComponent(sl)}">${esc(sect)}</a>`));
    items.forEach(c=> nav.appendChild(mk(c.slug, c.name, c.n)));
  }
  box.appendChild(nav);
}

let CATS=[];
// Розділ — ширший за категорію (мапа живе на сервері, taxonomy). Обрана категорія
// його скасовує: тримати обидва означало б показувати перетин, якого людина не просила.
let SECT = (typeof _sect !== 'undefined' ? _sect : '');
// копійки; null = межа не задана. Початкові значення приходять з адреси (розбирає
// інлайн-скрипт catalog.html, який виконується раніше за цей файл).
const PRICE = {
  min: (typeof _pmin !== 'undefined' ? _pmin : null),
  max: (typeof _pmax !== 'undefined' ? _pmax : null),
};

/* Стан фільтрів живе в АДРЕСІ: сторінку можна переслати, і кнопка «назад» повертає
   попередній фільтр, а не той самий список. Порожні значення в адресу не пишемо. */
function syncUrl(){
  const p = new URLSearchParams();
  if (cat) p.set('c', cat); else if (SECT) p.set('s', SECT);
  if (badge) p.set('b', badge); else if (onlyDiscounts) p.set('b', 'sale');
  // ?p= — 1-based, бо це число для людини: «сторінка 3», а не «offset 2».
  if (page > 0) p.set('p', page + 1);
  if (query) p.set('q', query);
  if (PRICE.min != null) p.set('pmin', Math.round(PRICE.min/100));   // в адресі — гривні
  if (PRICE.max != null) p.set('pmax', Math.round(PRICE.max/100));
  const s = p.toString();
  history.replaceState(null, '', s ? '/catalog?' + s : '/catalog');
}

/* Заголовок стрічки + крихти з одного місця: обидва відповідають на «де я»,
   і розійтись вони не мають права. До 2026-07-29 у каталогу не було <h1> зовсім —
   його роль мовчки грав бренд у шапці, тобто кожна сторінка сайту «називалась»
   однаково. */
function feedTitle(label){
  const t = document.getElementById('feedttl');
  if (t) t.textContent = label;
}

function crumbs(){
  const c = CATS.find(x => x.slug === cat);
  const items = [{href:'/', label:'Головна'}];
  if (c) {
    items.push({href:'/catalog', label:'Каталог'});
    // розділ у крихтах — робоче посилання на сам розділ, а не мертвий підпис
    if (c.section) items.push({href:'/catalog?s=' + encodeURIComponent(c.section),
                               label:c.section});
    items.push({label:c.name});
  } else if (SECT) {
    items.push({href:'/catalog', label:'Каталог'});
    items.push({label:SECT});
  } else items.push({label:'Каталог'});
  renderCrumbs(items);
  feedTitle(items[items.length - 1].label);
}

function setCat(slug){
  cat=slug; page=0;   // новий фільтр — нова стрічка, стара сторінка втрачає сенс
  if (slug) SECT='';        // категорія вужча — розділ більше не тримаємо
  const sel=document.getElementById('cat'); if(sel) sel.value=slug;   // тримаємо select у синхроні
  renderSide(CATS);
  crumbs(); syncUrl();
  window.scrollTo({top:0,behavior:'smooth'});
  load();
}

function setPrice(lo, hi){
  PRICE.min = lo; PRICE.max = hi; page=0;
  drawPrice();          // обидва блоки (бічна колонка + мобільний) перемальовуємо
  syncUrl();
  load();
}
function drawPrice(){
  renderPrice(document.getElementById('pricef'), PRICE, setPrice);
  renderPrice(document.getElementById('pricef-m'), PRICE, setPrice);
}

async function loadCats(){
  try{
    const cats=await api('/api/categories');
    CATS=cats;
    const sel=document.getElementById('cat');
    cats.forEach(c=>{ const o=document.createElement('option'); o.value=c.slug;
      o.textContent=`${c.name} (${c.n})`; sel.appendChild(o); });
    if (sel) sel.value = cat;      // категорія могла прийти з адреси — показуємо її
    renderSide(cats);
    crumbs();                      // назву категорії знаємо лише після завантаження
  }catch(e){}
}
const _sel = document.getElementById('cat');
if (_sel) _sel.onchange = e => { setCat(e.target.value); };
document.getElementById('sort').onchange=e=>{ sort=e.target.value; page=0; syncUrl(); load(); };
document.getElementById('moreBtn').onclick=loadMore;
let searchT;
const _srch = document.getElementById('search');
if (_srch) {
  _srch.value = query;             // пошук із адреси має бути видно в полі
  _srch.oninput = e => { clearTimeout(searchT);
    searchT = setTimeout(() => { query = e.target.value.trim(); page=0; syncUrl();
      drawQueryWatch(); load(); }, 300); };
}
/* ── стеження за ЗАПИТОМ (S29) ────────────────────────────────────────────────────
   Схема дозволяла `kind='query'` з 0001, але жоден клієнт такого не створював. Для
   радара знижок це сильніше за стеження за карткою: ловить і товари, яких ще немає.
   ⚠ ТІЛЬКИ з цільовою ціною — «повідом про будь-яке зниження серед усього, що
   підходить під слово „навушники“» це не сповіщення, а розсилка (сервер теж вимагає). */
function drawQueryWatch(){
  const box = document.getElementById('qwatch');
  if (!box) return;
  if (!query){ box.innerHTML = ''; return; }
  box.className = 'pricef';
  box.innerHTML = `<div class="ttl">Стежити за запитом</div>
    <div class="sub" style="color:var(--muted);font-size:var(--f2);margin-bottom:8px">
      Напишемо, щойно щось за запитом «${esc(query)}» подешевшає до вашої ціни.</div>
    <div class="fields">
      <input class="qt" inputmode="numeric" placeholder="ціна, ₴">
      <button class="go" type="button">Стежити</button>
    </div>
    <div class="qmsg" style="font-size:var(--f2);color:var(--muted);margin-top:8px"></div>`;
  const msg = box.querySelector('.qmsg');
  box.querySelector('.go').onclick = async () => {
    if (!AUTH.in){ gotoLogin(); return; }
    const raw = box.querySelector('.qt').value.replace(/[^\d]/g,'');
    if (!raw){ msg.textContent = 'Вкажіть ціну — без неї це була б розсилка, а не сповіщення.'; return; }
    try{
      await api('/api/me/watchlist', {method:'POST', body: JSON.stringify(
        {kind:'query', query_text: query, target_kop: parseInt(raw,10)*100})});
      msg.textContent = `Стежимо за «${query}» до ${grn(parseInt(raw,10)*100)}.`;
    }catch(e){ msg.textContent = e.message; }
  };
}

crumbs(); drawPrice(); renderChips(); renderCmpBar(); drawQueryWatch(); loadCats();
// page із адреси вже виставлено інлайн-скриптом catalog.html; load(true) завжди
// тягне нульову сторінку, а restoreFeed() доганяє решту й повертає прокрутку.
const _restoreTo = page;              // з адреси; load(true) його обнулить
load(true, 0).then(() => restoreFeed(_restoreTo));
