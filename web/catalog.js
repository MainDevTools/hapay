/* Стрічка каталогу: чіпи, картки, пагінація, бічна колонка (S19).
   Історію ціни показує окрема сторінка /product/{id} — шторку прибрано,
   щоб та сама логіка не жила у двох місцях. */
function renderChips(){
  const c = document.getElementById('chips'); c.innerHTML='';
  BADGES.forEach(b=>{ const chip=el(`<div class="chip ${b.k===badge?'on':''}">${b.label}</div>`);
    chip.onclick=()=>{ badge=b.k; renderChips(); syncUrl(); load(); }; c.appendChild(chip); });
}

function card(d){
  const off = pct(d);
  const bt = BADGE_TEXT[d.badge_state]||d.badge_state;
  const c = el(`<div class="card">
    <div class="thumb">
      ${d.image_url?`<img src="${esc(d.image_url)}" loading="lazy" alt="${esc(d.title)}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'ph',textContent:'🐾'}))">`:`<div class="ph">🐾</div>`}
      ${off?`<span class="off">−${off}%</span>`:''}
    </div>
    <div class="body">
      <p class="title">${esc(d.title)}</p>
      <div class="meta"><b>${esc(d.store||'')}</b>${d.variant_note?' · '+esc(d.variant_note):''}</div>
      <span class="badge"><span class="dot"></span>${bt}</span>
    </div>
    <div class="pricebox">
      <div class="prices">
        <span class="now">${grn(d.current_kop)}</span>
        ${d.old_declared_kop?`<span class="old">${grn(d.old_declared_kop)}</span>`:''}
      </div>
      ${d.offers_n>1?`<div class="offers">Всі пропозиції (${d.offers_n})</div>`:''}
      <a class="buy" href="/product/${d.store_product_id}">Порівняти ціни</a>
    </div></div>`);
  // Клік по картці веде на СТОРІНКУ товару, а не у крамницю: там історія ціни,
  // усі пропозиції й провенанс — тобто те, заради чого людина сюди прийшла.
  // Кнопка веде туди ж, тож її клік не має спрацьовувати двічі.
  c.querySelector('.buy').addEventListener('click', e=>e.stopPropagation());
  c.onclick=()=>{ location.href = '/product/' + d.store_product_id; };
  return c;
}

function skeleton(n){
  const list=document.getElementById('list'); list.innerHTML='';
  for(let i=0;i<n;i++) list.appendChild(el(
    `<div class="skel"><div class="s-img sk"></div><div class="s-body">
      <div class="sk" style="height:13px;width:80%"></div><div class="sk" style="height:11px;width:45%"></div>
      <div class="sk" style="height:18px;width:55%;margin-top:6px"></div>
      <div class="sk" style="height:20px;width:40%;border-radius:8px"></div></div></div>`));
}
function setMore(show){ document.getElementById('morewrap').hidden = !show; }

async function load(reset=true){
  const list=document.getElementById('list');
  if(reset){ page=0; skeleton(6); }
  try{
    const p=new URLSearchParams({sort,page});
    if(badge)p.set('badge',badge); if(cat)p.set('category',cat); if(query)p.set('q',query);
    if(PRICE.min!=null)p.set('price_min',PRICE.min);          // копійки (інв. A)
    if(PRICE.max!=null)p.set('price_max',PRICE.max);
    const data=await api('/api/discounts?'+p.toString());
    if(reset) list.innerHTML='';
    if(!data.length){
      if(reset) list.innerHTML=`<div class="empty"><div class="ic">${query?'🔍':'🐾'}</div>
        <div class="t">${query?'Нічого не знайдено':'Поки порожньо'}</div>
        <div>${query?'Спробуй іншу назву.':'Колектор ще накопичує знижки.'}</div></div>`;
      setMore(false); return;
    }
    data.forEach(d=>list.appendChild(card(d)));
    setMore(data.length===50);
  }catch(e){
    if(reset) list.innerHTML=`<div class="empty"><div class="ic">⚠️</div><div class="t">Помилка завантаження</div><div>${e.message}</div></div>`;
    setMore(false);
  }
}
function loadMore(){ page++; load(false); }

/* Бічна колонка: 171 категорія в 31 розділі. Плоский список був би стіною, тому
   групуємо за розділом — той самий порядок, що в застосунку (сервер уже віддає
   `section`). На телефоні колонка прихована, категорію обирає select у шапці. */
function renderSide(cats){
  const box=document.getElementById('side'); if(!box) return;
  box.innerHTML='';
  const all=el(`<div class="catlink ${cat===''?'on':''}"><span>Усі категорії</span></div>`);
  all.onclick=()=>{ setCat(''); }; box.appendChild(all);
  const bySect=new Map();
  cats.forEach(c=>{ const s=c.section||'Інше';
    if(!bySect.has(s)) bySect.set(s,[]); bySect.get(s).push(c); });
  for(const [sect,items] of bySect){
    box.appendChild(el(`<div class="sect">${esc(sect)}</div>`));
    items.forEach(c=>{
      const a=el(`<div class="catlink ${cat===c.slug?'on':''}">
        <span>${esc(c.name)}</span><span class="n">${c.n}</span></div>`);
      a.onclick=()=>setCat(c.slug);
      box.appendChild(a);
    });
  }
}

let CATS=[];
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
  if (cat) p.set('c', cat);
  if (badge) p.set('b', badge);
  if (query) p.set('q', query);
  if (PRICE.min != null) p.set('pmin', Math.round(PRICE.min/100));   // в адресі — гривні
  if (PRICE.max != null) p.set('pmax', Math.round(PRICE.max/100));
  const s = p.toString();
  history.replaceState(null, '', s ? '/catalog?' + s : '/catalog');
}

function crumbs(){
  const c = CATS.find(x => x.slug === cat);
  const items = [{href:'/', label:'Головна'}];
  if (c) { items.push({href:'/catalog', label:'Знижки'});
           if (c.section) items.push({href:'/catalog', label:c.section});
           items.push({label:c.name}); }
  else items.push({label:'Знижки'});
  renderCrumbs(items);
}

function setCat(slug){
  cat=slug;
  const sel=document.getElementById('cat'); if(sel) sel.value=slug;   // тримаємо select у синхроні
  renderSide(CATS);
  crumbs(); syncUrl();
  window.scrollTo({top:0,behavior:'smooth'});
  load();
}

function setPrice(lo, hi){
  PRICE.min = lo; PRICE.max = hi;
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
document.getElementById('sort').onchange=e=>{ sort=e.target.value; load(); };
document.getElementById('moreBtn').onclick=loadMore;
let searchT;
const _srch = document.getElementById('search');
if (_srch) {
  _srch.value = query;             // пошук із адреси має бути видно в полі
  _srch.oninput = e => { clearTimeout(searchT);
    searchT = setTimeout(() => { query = e.target.value.trim(); syncUrl(); load(); }, 300); };
}
crumbs(); drawPrice(); renderChips(); loadCats(); load();
