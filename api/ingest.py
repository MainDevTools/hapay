"""Distributed ingest (S10): довірені колектори шлють зібране на сервер.

Навіщо: наш ДЦ-IP (Hetzner) отримує 403 від Rozetka/Allo/Foxtrot/Moyo/... Довірені
колектори (оператор + друзі) збирають зі СВОЇХ резидентних мереж, зі згодою, і шлють
сюди. Це НЕ botnet: збирають ВЛАСНИКИ проекту, не несвідомі клієнти (§7.4/§7.7).

Два тверді правила (без них ingest = дірка в єдиному активі — базі):
  1. Автентифікація per-колектор — лише відомі bearer-токени (`INGEST_TOKENS`). Свій
     токен на кожного → витік одного відкликається окремо.
  2. Сервер ВАЛІДУЄ кожен елемент, не вірить на слово. Довіра до людини ≠ довіра до
     кожного байта (телефон можна зламати; база — єдиний актив). URL мусить бути на
     домені крамниці, ціна — у розумному діапазоні, назва — не порожня.
"""
from __future__ import annotations

import dataclasses
import hmac
import os
import re
from urllib.parse import urlsplit

from adapters.allo import HUB as ALLO_HUB, AlloAdapter
from adapters.base import RawItem, canon_ref
from adapters.brain import BrainAdapter
from adapters.citrus import CitrusAdapter
from adapters.comfy import ComfyAdapter
from adapters.eldorado import EldoradoAdapter
from adapters.epicentr import EpicentrAdapter
from adapters.foxtrot import FoxtrotAdapter
from adapters.ktc import KtcAdapter
from adapters.moyo import MoyoAdapter
from adapters.rozetka import RozetkaAdapter
from adapters.telemart import TelemartAdapter
from adapters.vencon import VenconAdapter
from db.store import load_categories, persist_items, upsert_source

# ── Сервер — АВТОРИТЕТ, хто може бути джерелом і які хости валідні ────────────────
# Колектор не може «вигадати» джерело: лише ці назви приймаються, і URL кожного
# елемента мусить бути на дозволеному хості (проти інʼєкції чужих/фішинг-URL).
INGEST_SOURCES: dict[str, dict] = {
    "Foxtrot":  {"base_url": "https://www.foxtrot.com.ua", "hosts": ("foxtrot.com.ua",)},
    "Moyo":     {"base_url": "https://www.moyo.ua",        "hosts": ("moyo.ua",)},
    "Eldorado": {"base_url": "https://eldorado.ua",        "hosts": ("eldorado.ua",)},
    "Rozetka":  {"base_url": "https://rozetka.com.ua",     "hosts": ("rozetka.com.ua",)},
    "Allo":     {"base_url": "https://allo.ua",            "hosts": ("allo.ua",)},
    "Comfy":    {"base_url": "https://comfy.ua",           "hosts": ("comfy.ua",)},
    # Citrus переїхав на citrus.ua (перевірено 2026-07-21: ctrs.com.ua віддає редирект
    # туди, og:site_name однаковий). Поки редирект живий, адаптер будує адреси від
    # старого BASE і все працює. Але щойно редирект приберуть, товари поїдуть з нового
    # хоста — і серверна перевірка відкинула б їх УСІ з «url не на домені Citrus».
    # Виглядало б як загадкове обнуління крамниці. Обидва хости — власність Цитруса,
    # тож це не послаблення перевірки, а визнання факту переїзду.
    "Citrus":   {"base_url": "https://www.ctrs.com.ua",
                 "hosts": ("ctrs.com.ua", "citrus.ua")},
    "Brain":    {"base_url": "https://brain.com.ua",       "hosts": ("brain.com.ua",)},
    "KTC":      {"base_url": "https://ktc.ua",             "hosts": ("ktc.ua",)},
    # Епіцентр роздає фото з cdn.27.ua — 27.ua ними поглинута (перевірено: 27.ua віддає
    # сторінку Епіцентру). Хост картинок у hosts НЕ додаємо: там лише фото, а перевірка
    # хостів стереже URL ТОВАРУ.
    "Epicentr": {"base_url": "https://epicentrk.ua",       "hosts": ("epicentrk.ua",)},
    "Vencon":   {"base_url": "https://vencon.ua",          "hosts": ("vencon.ua",)},
    "Telemart": {"base_url": "https://telemart.ua",        "hosts": ("telemart.ua",)},
}

# ── Серверний парсинг пересланого HTML (S11 етап 3) ───────────────────────────────
# Застосунок = «тупий фетчер»: тягне HTML зі своєї резидентної мережі й шле сюди, а
# ВСЯ екстракція — тут, на сервері. Плюс: зміна селекторів/крамниці не вимагає оновлення
# застосунку в сторах. Лише джерела з РОБОЧИМ серверним адаптером; host-політика — з
# INGEST_SOURCES вище. `hub` → дворівневий discovery (сервер робить discover, не застосунок).
HTML_SOURCES: dict[str, dict] = {
    # `category` — джерело-рівневий дефолт: hub-лендинги відкриваються динамічно,
    # їх не пре-тегувати поіменно, але весь Allo-хаб — смартфони.
    # Allo (розвідка 2026-07-21): доти збирали ЛИШЕ хаб акцій — 10 рекламних лендингів
    # («товар дня», «збирай комбо») по жменьці позицій, звідси 49 товарів на все джерело
    # при 1848 у Rozetka. Джерело було справне (11 задач, усі ok, нуль збоїв) — ми просто
    # просили не те. Тепер додано категорійні лістинги; хаб лишаємо, він дає акційні
    # позиції, яких у категоріях може не бути.
    #
    # URL узято з ЖИВОЇ навігації Allo (меню рендериться на клієнті, тож curl його не
    # бачить — читав через браузер). Вгадування коштувало чотирьох 404 поспіль:
    # /ua/mobile/, /ua/smartfony/, /ua/noutbuki/, /ua/products/televizory/ — усі дохлі.
    # Форма лістинга — `/ua/products/<slug>/`, крім телевізорів (старіша `/ua/televizory/`).
    #
    # Пагінація — `?p=N`, і це ВАЖЛИВО: звичне `?page=N` віддає 200 і рівно ті самі 60
    # товарів (перетин зі стор.1 = 60), тобто мовчки дублювало б першу сторінку. Перевірено
    # фактом на всіх трьох категоріях: стор. 2 і 10 → по 60 позицій, перетин з 1-ю ≈ 0.
    "Allo": {"adapter": AlloAdapter(), "hub": ALLO_HUB, "max_pages": 20,
             "category": "smartfony",
             "page_tpl": "{base}?p={n}", "pages": 5, "urls": (
                 ("https://allo.ua/ua/products/mobile/klass-kommunikator_smartfon/", "smartfony"),
                 ("https://allo.ua/ua/products/notebooks/", "noutbuky"),
                 ("https://allo.ua/ua/televizory/", "tv"),
                 ("https://allo.ua/ua/products/internet-planshety/", "planshety", 3),
                 ("https://allo.ua/ua/naushniki/", "audio", 3),
                 ("https://allo.ua/ua/smart-chasy/", "smart-hodynnyky", 3),
                 ("https://allo.ua/ua/holodilniki/", "pobut-tehnika", 3),
                 ("https://allo.ua/ua/stiralnye-mashiny/", "pobut-tehnika", 1),
                 ("https://allo.ua/ua/otdel-no-stojaschie-posudomoechnye-mashiny/", "pobut-tehnika", 1),
                 ("https://allo.ua/ua/igrovye-pristavki/", "konsoli", 2),
                 ("https://allo.ua/ua/universalnye-mobilnye-batarei/", "aksesuary", 1),
                 ("https://allo.ua/ua/products/pylesosy/", "pylososy", 3),
                 ("https://allo.ua/ua/roboty-pylesosy/", "pylososy", 1),
                 ("https://allo.ua/ua/sushil-nye-mashiny/", "pobut-tehnika", 1),
                 ("https://allo.ua/ua/monitory/", "monitory", 3),
                 ("https://allo.ua/ua/products/kondicionery/", "kondycionery", 3),
                 ("https://allo.ua/ua/wi-fi-routery/", "routery", 3),
                 ("https://allo.ua/ua/mul-tipechi/", "multypechi", 3),
                 ("https://allo.ua/ua/products/vodonagrevateli/", "boylery", 3),
             )},
    # Foxtrot/Moyo (2026-07-19): лістинги категорій SSR-лять картки з MPN у назвах —
    # база T15-матчингу. З ДЦ — 403, тому лише через колектора (резидентний IP).
    # Категорії = смартфони (перетин з Allo за MPN доведено розвідкою); сервер —
    # авторитет над списком: додати категорію = дописати URL тут.
    # Ноутбуки/ТВ (розвідка 2026-07-20): URL узято з НАВІГАЦІЇ крамниць (не вгадано —
    # вгадані лістинги раніше давали 404) і перевірено ПАРСИНГОМ адаптера, не лише 200.
    # `page_tpl`/`pages` — пагінація (розвідка 2026-07-20). Схеми взято з навігації
    # крамниць і перевірено фактом: сторінка 2 віддає ІНШІ товари, перетин з 1-ю = 0.
    # Глибина 10 теж була перевірена: стор. 8/10/12 віддають повні набори без повторів 1-ї.
    # KTC — 7: далі його лістинги віддають порожньо (сенсу слати запит немає).
    #
    # ГЛИБИНА 10 → 5 (2026-07-21). Дефолт зрізано, і це свідомий обмін, а не економія
    # «про всяк випадок». Бюджет черги скінченний: колектор дає ~20 задач/год ≈ 480/добу,
    # рівний розклад 720 хв тримає ~384. Глибокі сторінки з'їдали 47% усього бюджету на
    # три категорії (ноутбуки 51.5 запусків/добу, ТВ 51.5, смартфони 46) — і саме вони
    # дають найгірший приріст: хвіст лістинга це рідкісні позиції, яких у сусідніх
    # крамницях немає, тобто НУЛЬ порівнянь. А порівняння — єдина причина, чому «Хапай»
    # існує. Ті самі запуски, віддані новим категоріям, дають товари, що перетинаються.
    # Ціна рішення чесна: три найбільші категорії з часом зменшаться приблизно вдвічі.
    # Відкотити — одне число. Дефолт стосується лише лістингів БЕЗ власної глибини;
    # у нових категорій вона задана поштучно третім елементом запису.
    #
    # ЄМНІСТЬ ЧЕРГИ (заміряно 2026-07-21): періодичність розведено за глибиною
    # (qtasks.repeat_for_page). Додавати лістинги можна, але кожні +3 сторінки це ще
    # ~3 запуски на добу — рахуй перед тим, як дописати рядок.
    "Foxtrot": {"adapter": FoxtrotAdapter(), "page_tpl": "{base}?page={n}", "pages": 5, "urls": (
        ("https://www.foxtrot.com.ua/uk/shop/mobilnye_telefony.html", "smartfony"),
        ("https://www.foxtrot.com.ua/uk/shop/noutbuki.html", "noutbuky"),        # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/led_televizory.html", "tv"),        # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/planshety.html", "planshety", 3),    # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/naushniki.html", "audio", 3),        # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/smart_chasi.html", "smart-hodynnyky", 3),
        ("https://www.foxtrot.com.ua/uk/shop/holodilniki.html", "pobut-tehnika", 3),
        ("https://www.foxtrot.com.ua/uk/shop/stiralki.html", "pobut-tehnika", 1),   # 42
        ("https://www.foxtrot.com.ua/uk/shop/igrovye_pristavki.html", "konsoli", 2),# 9
        ("https://www.foxtrot.com.ua/uk/shop/mikrovolnovki.html", "mikrohvylovky", 3),
        ("https://www.foxtrot.com.ua/uk/shop/pylesosy.html", "pylososy", 3),
        ("https://www.foxtrot.com.ua/uk/shop/cofevarki.html", "kavomashyny", 3),
        ("https://www.foxtrot.com.ua/uk/shop/mobilnye_telefony_telefon.html", "knopkovi-telefony", 3),
        ("https://www.foxtrot.com.ua/uk/shop/roboti_pilesosi.html", "pylososy", 1),
        ("https://www.foxtrot.com.ua/uk/shop/drymachine.html", "pobut-tehnika", 1),
        ("https://www.foxtrot.com.ua/uk/shop/gk-monitory.html", "monitory", 3),
        ("https://www.foxtrot.com.ua/uk/shop/kondicyonery.html", "kondycionery", 3),
        ("https://www.foxtrot.com.ua/uk/shop/marshrutizatory.html", "routery", 3),
        ("https://www.foxtrot.com.ua/uk/shop/multivarki_multipech.html", "multypechi", 3),
        ("https://www.foxtrot.com.ua/uk/shop/blendery.html", "blendery", 3),
        ("https://www.foxtrot.com.ua/uk/shop/bojlery.html", "boylery", 3),
    )},
    "Moyo": {"adapter": MoyoAdapter(), "page_tpl": "{base}?page={n}", "pages": 5, "urls": (
        ("https://www.moyo.ua/ua/telecommunication/smart/", "smartfony"),
        ("https://www.moyo.ua/ua/comp-and-periphery/notebooks/", "noutbuky"),    # 24 товари
        ("https://www.moyo.ua/ua/foto_video/tv_audio/lcd_tv/", "tv"),            # 24 товари
        ("https://www.moyo.ua/ua/tablet_el_knigi/tablet/", "planshety", 3),       # 24 товари
        ("https://www.moyo.ua/ua/acsessor/ipod_headphones/", "audio", 3),         # 24 товари
        ("https://www.moyo.ua/ua/gadgets/smart_chasy/", "smart-hodynnyky", 3),
        ("https://www.moyo.ua/ua/bt/kbt/holodilniky/", "pobut-tehnika", 3),
        ("https://www.moyo.ua/ua/bt/kbt/stiralnie-mashiny/", "pobut-tehnika", 1),    # 24
        ("https://www.moyo.ua/ua/bt/kbt/posudomoechnie-mashi/", "pobut-tehnika", 1), # 24
        ("https://www.moyo.ua/ua/foto_video/photo_video/cameras/", "foto", 3),       # 24
        ("https://www.moyo.ua/ua/game_zone/game_console/", "konsoli", 2),            # 24
        ("https://www.moyo.ua/ua/acsessor/acum/accu_univers/", "aksesuary", 1),      # 24
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/microvolnovie-pechi/", "mikrohvylovky", 3),
        ("https://www.moyo.ua/ua/bt/mbt/pylesosy/", "pylososy", 3),
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/kofevarki/", "kavomashyny", 3),
        ("https://www.moyo.ua/ua/telecommunication/cell_phones/", "knopkovi-telefony", 3),
        ("https://www.moyo.ua/ua/bt/mbt/robot_pyle_i_chist/", "pylososy", 1),
        ("https://www.moyo.ua/ua/bt/kbt/sushilnie-mashini/", "pobut-tehnika", 1),
        ("https://www.moyo.ua/ua/comp-and-periphery/noutebook_pc/monitors/", "monitory", 3),
        ("https://www.moyo.ua/ua/bt/klimaticheskaya-tekh/kondicionery/", "kondycionery", 3),
        ("https://www.moyo.ua/ua/comp-and-periphery/network_equip/routers/", "routery", 3),
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/multypechi/", "multypechi", 3),
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/blendery/", "blendery", 3),
        ("https://www.moyo.ua/ua/bt/klimaticheskaya-tekh/vodonagrevately/boylery/", "boylery", 3),
    )},
    # Comfy (розвідка 2026-07-19): SSR-лістинг, 50 карток, MPN у назвах — перетин із
    # Allo/Foxtrot/Moyo (напр. SM-A376BLVGEUC) → групи «Де купити» ширшають.
    # Comfy → render (2026-07-20): почав віддавати анти-бот заглушку («Pardon Our
    # Interruption», 6 КБ, challenge) на ВСІ прості GET — навіть на смартфон-лістинг,
    # який доти працював. У СПРАВЖНЬОМУ браузері блоку немає (перевірено): сторінки
    # віддають по 50 карток, і всі 50 читаються нашими ж селекторами (product-tile-catalog
    # + .product-tile-title/.product-tile-price__current) — адаптер міняти не довелось.
    # Тому телефон рендерить Comfy у WebView, як Brain. Рендер ~1.9-2.4 МБ — під _MAX_HTML (5 МБ).
    "Comfy": {"adapter": ComfyAdapter(), "mode": "render",
              "page_tpl": "{base}?p={n}", "pages": 5, "urls": (
        ("https://comfy.ua/smartfon/", "smartfony"),
        ("https://comfy.ua/notebook/", "noutbuky"),                              # 50 карток
        ("https://comfy.ua/flat-tvs/", "tv"),                                    # 50 карток
        ("https://comfy.ua/plane-table-computer/", "planshety", 3),              # 50 карток
        ("https://comfy.ua/nayshniki/", "audio", 3),                             # 50 карток
        ("https://comfy.ua/smart-watches/", "smart-hodynnyky", 3),               # 50 карток
        ("https://comfy.ua/refrigerator/", "pobut-tehnika", 3),                  # 50 карток
        ("https://comfy.ua/wash-machines/", "pobut-tehnika", 1),                 # 50 карток
    )},
    # Rozetka (розвідка 2026-07-19): найбільший маркетплейс, Angular-SSR 60 карток;
    # масові перетини MPN (SM-S942BZKGEUC = Foxtrot S26, SM-A576BZVDEUC = Moyo/Allo A57).
    "Rozetka": {"adapter": RozetkaAdapter(), "page_tpl": "{base}page={n}/", "pages": 5, "urls": (
        ("https://rozetka.com.ua/ua/mobile-phones/c80003/", "smartfony"),
        ("https://rozetka.com.ua/ua/notebooks/c80004/", "noutbuky"),             # 60 товарів
        ("https://rozetka.com.ua/ua/all-tv/c80037/", "tv"),                      # 60 товарів
        ("https://rozetka.com.ua/ua/tablets/c130309/", "planshety", 3),           # 60 товарів
        ("https://rozetka.com.ua/ua/headphones/c80027/", "audio", 3),             # 60 товарів
        ("https://rozetka.com.ua/ua/smartwatch/c651392/", "smart-hodynnyky", 3),  # 60 товарів
        ("https://rozetka.com.ua/ua/holodilniki/c80125/", "pobut-tehnika", 3),    # 60 товарів
        ("https://rozetka.com.ua/ua/washing_machines/c80124/", "pobut-tehnika", 1),# 60 товарів
        ("https://rozetka.com.ua/ua/photo/c80001/", "foto", 3),                    # 69 товарів
        ("https://rozetka.com.ua/ua/consoles/c80020/", "konsoli", 2),              # 68 товарів
        # Аксесуари — глибина 1 (2026-07-21, за замiром на живій базі): лише 5% товарів
        # категорії потрапляють у групи «де купити» (11 із 235) проти 62% у ТВ і 52% у
        # ноутбуках. Павербанки продають під довільними назвами без артикулів, тож
        # зіставити їх між крамницями нічим. Глибокі сторінки тут — витрачений бюджет.
        ("https://rozetka.com.ua/ua/poverbanki-i-zaryadnie-stantsii/c4674582/", "aksesuary", 1),
    )},
    # Citrus (розвідка 2026-07-19): Next.js SSR, 47 карток, хешовані класи (префіксні
    # селектори); SM-S948BZKGEUC перетинається з Comfy → більше груп.
    "Citrus": {"adapter": CitrusAdapter(), "page_tpl": "{base}?page={n}", "pages": 5, "urls": (
        ("https://www.ctrs.com.ua/smartfony/", "smartfony"),
        ("https://www.ctrs.com.ua/noutbuki-i-ultrabuki/", "noutbuky"),           # 47 товарів
        ("https://www.ctrs.com.ua/televizory/", "tv"),                           # 47 товарів
        ("https://www.ctrs.com.ua/planshety/", "planshety", 3),                  # 47 товарів
        ("https://www.ctrs.com.ua/naushniki/", "audio", 3),                      # 47 товарів
        ("https://www.ctrs.com.ua/smart-chasy/", "smart-hodynnyky", 3),          # 47 товарів
        ("https://www.ctrs.com.ua/holodilniki/", "pobut-tehnika", 3),            # 47 товарів
        ("https://www.ctrs.com.ua/stiralnye-mashiny/", "pobut-tehnika", 1),      # 47 товарів
        ("https://www.ctrs.com.ua/posudomoechnye-mashiny/", "pobut-tehnika", 1), # 47 товарів
        ("https://www.ctrs.com.ua/cameras/", "foto", 3),                        # 35 товарів
        ("https://www.ctrs.com.ua/igrovye-pristavki/", "konsoli", 2),           # 47 товарів
        ("https://www.ctrs.com.ua/portativnye-batarei/", "aksesuary", 1),       # 47 товарів
        ("https://www.ctrs.com.ua/mikrovolnovki/", "mikrohvylovky", 3),        # 47 товарів
        ("https://www.ctrs.com.ua/pylesosy/", "pylososy", 3),                  # 47 товарів
        ("https://www.ctrs.com.ua/kofemashiny/", "kavomashyny", 3),            # 47 товарів
        ("https://www.ctrs.com.ua/mobilnye-telefony/", "knopkovi-telefony", 3),# 47 товарів
        # Третя хвиля (2026-07-21). УВАГА щодо Citrus: у навігації частина посилань має
        # префікс `/actions/z-ucinkoyu/…` (розділ УЦІНКИ) або місто `/khmelnytskyy/…`.
        # Брати їх не можна: перший — вітрина уцінених, тобто інший стан товару (той самий
        # фільтр, що ми виключаємо з порівнянь), другий прив'язує лістинг до одного міста.
        # Тут — чисті категорійні адреси, кожна перевірена парсингом.
        ("https://www.ctrs.com.ua/roboty-uborshhiki/", "pylososy", 1),         # 47 товарів
        ("https://www.ctrs.com.ua/sushilnye-mashiny/", "pobut-tehnika", 1),    # 42 товари
        ("https://www.ctrs.com.ua/monitory/", "monitory", 3),                  # 47 товарів
        ("https://www.ctrs.com.ua/kondicionery/", "kondycionery", 3),          # 47 товарів
        ("https://www.ctrs.com.ua/wi-fi-routery/", "routery", 3),              # 47 товарів
        ("https://www.ctrs.com.ua/blendery/", "blendery", 3),                  # 47 товарів
    )},
    # Brain (розвідка 2026-07-19): SPA — ціни лише після JS → mode="render" (телефон
    # рендерить у WebView). Дані з data-атрибутів; A07 SM-A075FZKGSEK перетин із Moyo/Rozetka.
    # Пагінація Є, але лише для адрес форми `/ukr/category/…` (перевірено 2026-07-20:
    # `Televizory-c1098/page=10/` → 24 товари з цінами, пейджер аж до 34 сторінок;
    # `Noutbuky-c1191/page=2/` → 24 ІНШІ товари, перетин із 1-ю нульовий).
    # Раніше я помилково записав Brain як «нескінченний скрол без пагінації» — насправді
    # 404 давала стара форма адреси `Smartfoni_zvyazok-c297/page=2/`, а не сайт узагалі.
    # Смартфонний запис — це ДЕПАРТАМЕНТ (15 товарів), він не пагінується → глибина 1.
    "Brain": {"adapter": BrainAdapter(), "mode": "render",
              "page_tpl": "{base}page={n}/", "pages": 5, "urls": (
        ("https://brain.com.ua/ukr/Smartfoni_zvyazok-c297/", "smartfony", 1),    # департамент
        ("https://brain.com.ua/ukr/category/Noutbuky-c1191/", "noutbuky"),       # 24/стор.
        ("https://brain.com.ua/ukr/category/Televizory-c1098/", "tv"),           # 24/стор., 34 стор.
        ("https://brain.com.ua/ukr/category/Planshety-c1192/", "planshety", 3),   # 24/стор.
        ("https://brain.com.ua/ukr/category/Navushnyky_ta_garnitury-c1365-157/", "audio", 3),
        ("https://brain.com.ua/ukr/category/Rozumni_godynnyky_ta_braslety-c7852/", "smart-hodynnyky", 3),
        ("https://brain.com.ua/ukr/category/Holodilniki-c897/", "pobut-tehnika", 3),
    )},
    # Eldorado (розвідка 2026-07-20, у справжньому браузері): SPA + ЛІНИВІ ціни — без
    # прокрутки сторінка віддає товари з НУЛЕМ цін, тому лише mode="render" і лише з
    # новим скрол-рендерером. URL узято з навігації (вгаданий /smartfony/c1050/ → сторінка
    # помилки). Перевірено парсингом: смартфони 32 картки / 11 із цінами (решта «Продано»
    # чи «Незабаром» — їх адаптер пропускає), ноутбуки 40/32, ТВ 40/40.
    # ⚠ БЕЗ пагінації (виправлено 2026-07-20, після заміру): `rel=next` тут Є і вказує на
    # `page=2/`, АЛЕ пряме завантаження цієї адреси віддає ПЕРШУ сторінку — пагінація
    # клієнтська. Доведено звіркою артикулів: page=1 і page=2 → однакові SKU (identical),
    # page=8 — теж перші 40. Тобто попередній `pages: 5` збирав ОДНУ сторінку пʼять разів
    # (звідси лише ~9 унікальних товарів). Моя помилка: для інших крамниць я перевіряв
    # «сторінка 2 дає ІНШІ товари», а тут задовольнився наявністю rel=next.
    # Глибші сторінки потребують кліку по пейджеру у WebView — як і Brain, окрема робота.
    "Eldorado": {"adapter": EldoradoAdapter(), "mode": "render", "urls": (
        ("https://eldorado.ua/uk/smartphones/c1038946/", "smartfony"),
        ("https://eldorado.ua/uk/notebooks/c1039096/", "noutbuky"),
        ("https://eldorado.ua/uk/led/c1038962/", "tv"),
        ("https://eldorado.ua/uk/tablet_pc/c1039006/", "planshety"),             # 40 карток
        ("https://eldorado.ua/uk/headphones/c1038998/", "audio"),                # 40 карток
        ("https://eldorado.ua/uk/smart_chasi/c1197093/", "smart-hodynnyky"),     # 13 карток
        ("https://eldorado.ua/uk/holodilniki/c1061560/", "pobut-tehnika"),       # 40 карток
    )},
    # KTC (розвідка 2026-07-19): SSR-лістинг /smartphone/, 48 карток, 54 SM-коди —
    # S26/A07 перетини з рештою → більше груп «Де купити».
    # Епіцентр (розвідка 2026-07-21) — десята крамниця й найширша: покриває 19 із 20
    # наших полиць, від смартфонів до бойлерів. Національна мережа, тож перетини за
    # артикулом мають бути щільні.
    #
    # Екстракція — РОЗМІТКОЮ schema.org, перший тир порядку (§8.4), а не класами:
    # класи хешовані Nuxt-ом (`_Al-5uY1o`) і міняються з кожним білдом їхнього фронту.
    # Звірено незалежно: ціни всіх 60 карток збіглися з JSON-LD ItemList до копійки.
    #
    # Пагінація — `?PAGEN_1=N` (Bitrix), і це знову перевірено ФАКТОМ: `?page=2` і `?p=2`
    # віддають 200 і рівно ті самі 60 товарів (перетин зі стор.1 = 60), тобто мовчки
    # дублювали б першу сторінку — та сама пастка, що вже коштувала нам Allo.
    # `?PAGEN_1=2/3/5` → по 60 позицій, перетин із першою нульовий.
    #
    # Адреси взято з ЇХНЬОЇ Ж МАПИ САЙТУ (sitemap section_000.xml, 3765 розділів), не
    # вгадано, і кожна перевірена парсингом адаптера — по 60 товарів. Перевірка окупилась
    # одразу: `/mobilnyye-telefony/` виглядає як лістинг смартфонів, а віддає НУЛЬ позицій
    # (це хаб); справжній — `/smartfony-i-mobilnye-telefony/`.
    #
    # ⚠ Заміряно при розвідці: Епіцентр оголошує знижку майже на все — кондиціонери
    # 60 з 60, блендери 60 з 60, холодильники 58 з 60, ТВ 57 з 60. Саме такі вітрини
    # 30-денна формула (§5) і має перевіряти; для детектора це найцінніша крамниця.
    "Epicentr": {"adapter": EpicentrAdapter(), "page_tpl": "{base}?PAGEN_1={n}",
                 "pages": 3, "urls": (
        ("https://epicentrk.ua/ua/shop/smartfony-i-mobilnye-telefony/", "smartfony"),
        ("https://epicentrk.ua/ua/shop/noutbuki/", "noutbuky"),
        ("https://epicentrk.ua/ua/shop/televizory/", "tv"),
        ("https://epicentrk.ua/ua/shop/planshety/", "planshety"),
        ("https://epicentrk.ua/ua/shop/naushniki/", "audio"),
        ("https://epicentrk.ua/ua/shop/smart-chasy-i-fitnes-braslety/", "smart-hodynnyky"),
        ("https://epicentrk.ua/ua/shop/kholodilniki/", "pobut-tehnika"),
        ("https://epicentrk.ua/ua/shop/stiralnye-mashiny/", "pobut-tehnika", 1),
        ("https://epicentrk.ua/ua/shop/posudomoechnye-mashiny/", "pobut-tehnika", 1),
        ("https://epicentrk.ua/ua/shop/sushilnye-mashiny/", "pobut-tehnika", 1),
        ("https://epicentrk.ua/ua/shop/monitory/", "monitory"),
        ("https://epicentrk.ua/ua/shop/konditsionery/", "kondycionery"),
        ("https://epicentrk.ua/ua/shop/marshrutizatory-i-wi-fi-routery/", "routery"),
        ("https://epicentrk.ua/ua/shop/pylesosy/", "pylososy"),
        ("https://epicentrk.ua/ua/shop/roboty-pylesosy/", "pylososy", 1),
        ("https://epicentrk.ua/ua/shop/mikrovolnovye-pechi/", "mikrohvylovky"),
        ("https://epicentrk.ua/ua/shop/kofevarki/", "kavomashyny"),
        ("https://epicentrk.ua/ua/shop/multivarki/", "multypechi"),
        ("https://epicentrk.ua/ua/shop/blendery/", "blendery"),
        ("https://epicentrk.ua/ua/shop/vodonagrevateli/", "boylery"),
        ("https://epicentrk.ua/ua/shop/igrovye-pristavki-i-konsoli/", "konsoli", 2),
        ("https://epicentrk.ua/ua/shop/fotoapparaty/", "foto", 2),
        ("https://epicentrk.ua/ua/shop/knopochnye-telefony/", "knopkovi-telefony", 2),
    )},
    # Венкон (розвідка 2026-07-21) — одинадцята крамниця, вузька й прицільна: техніка
    # для дому й сантехніка, без смартфонів і ТВ. Взято не заради обсягу, а заради
    # ЧОТИРЬОХ полиць третьої хвилі — кондиціонери, бойлери, блендери, мультипечі, —
    # де в нас лише по три крамниці. Венкон стає четвертою саме там.
    #
    # Цінність підтверджена ДО написання конфіга: із 302 артикулів, зібраних з усіх
    # одинадцяти лістингів, 118 (39%) уже є в нашому каталозі, а частина — у групах
    # на п'ять крамниць (LG F2Y2NS3WE: Allo, Citrus, Comfy, Foxtrot, Rozetka).
    #
    # Пагінація `?page=N` перевірена фактом на кожній категорії окремо, не на одній:
    # сторінки 2/3/4 віддають різні товари, перетин із першою нульовий — навіть у
    # малих розділах на 27 позицій. Тому глибина 3 всюди чесна, а не «про запас».
    #
    # ⚠ Крамниця розмічає schema.org НЕ ВСІ розділи (див. шапку adapters/vencon.py):
    # кондиціонери, бойлери, блендери й сушильні мають ті самі картки без жодного
    # itemprop. Адаптер читає обидві розкладки; якби він умів лише мікродані, ці
    # чотири розділи мовчки давали б нуль — тобто саме те, заради чого крамницю брали.
    "Vencon": {"adapter": VenconAdapter(), "page_tpl": "{base}?page={n}",
               "pages": 3, "urls": (
        ("https://vencon.ua/catalog/pylesosy", "pylososy"),                    # 47/стор.
        ("https://vencon.ua/catalog/mikrovolnovye-pechi", "mikrohvylovky"),    # 47/стор.
        ("https://vencon.ua/catalog/multivarki", "multypechi"),                # 47/стор.
        ("https://vencon.ua/catalog/blendery", "blendery"),                    # 27/стор.
        ("https://vencon.ua/catalog/bojlery", "boylery"),                      # 27/стор.
        ("https://vencon.ua/catalog/protochnye-vodonagrevateli", "boylery", 2),
        ("https://vencon.ua/catalog/kondicionery-split-sistemy", "kondycionery"),
        ("https://vencon.ua/catalog/monoblochnye-kondicionery", "kondycionery", 2),
        ("https://vencon.ua/catalog/stiralnye-mashiny", "pobut-tehnika"),      # 47/стор.
        ("https://vencon.ua/catalog/posudomoechnye-mashiny", "pobut-tehnika", 2),
        ("https://vencon.ua/catalog/sushilnye-mashiny", "pobut-tehnika", 2),
    )},
    # Telemart (розвідка 2026-07-21) — дванадцята крамниця. Розмітки schema.org тут
    # НЕМАЄ зовсім, тож екстракція йде нижнім тиром порядку (§8.4) — по класах. Це
    # свідомий компроміс: клас-селектори крихкі, але крамниця того варта.
    #
    # Заміряно ДО написання конфіга: 195 артикулів із семи лістингів, 125 (64%) уже в
    # нашому каталозі — найвищий перетин з усіх доданих (Епіцентр 71% на одній
    # сторінці, Венкон 39%). Частина позицій одразу входить у групи на дев'ять
    # крамниць, тобто Telemart робить десяту.
    #
    # Окремо цінне: КОНСОЛІ. У нас ця полиця мертва — 7% товарів з артикулом, нуль
    # груп (див. T17). Telemart називає консолі з кодами моделей, 64% з артикулом.
    # Не вилікує полицю, але дасть перші справжні порівняння.
    #
    # ⚠ `/graphic-tablets/` НЕ беремо, хоч слово «планшети» спокушає: це графічні
    # планшети для малювання, інший товар. Сплутати легко, а наслідок — хибні групи.
    #
    # Пагінація `?page=N` перевірена фактом: стор.2 → 48 інших карток, перетин нульовий.
    "Telemart": {"adapter": TelemartAdapter(), "page_tpl": "{base}?page={n}",
                 "pages": 3, "urls": (
        ("https://telemart.ua/tv/", "tv"),                        # 48/стор., 79% з артикулом
        ("https://telemart.ua/laptops/", "noutbuky"),             # 48/стор., 97%
        ("https://telemart.ua/monitors/", "monitory"),            # 48/стор., 75%
        ("https://telemart.ua/earphones/", "audio"),              # 48/стор., 58%
        ("https://telemart.ua/wi-fi-routers/", "routery"),        # 48/стор., 39%
        ("https://telemart.ua/consoles/", "konsoli", 2),          # 17 товарів, 64%
        ("https://telemart.ua/iphone/", "smartfony", 2),          # 22 товари, 100%
    )},
    "KTC": {"adapter": KtcAdapter(), "page_tpl": "{base}?page={n}", "pages": 5, "urls": (
        ("https://ktc.ua/smartphone/", "smartfony"),
        ("https://ktc.ua/notebook/", "noutbuky"),                                # 48 товарів
        ("https://ktc.ua/tv/", "tv"),                                            # 48 товарів
        ("https://ktc.ua/headphones/", "audio", 3),                              # 48 товарів
    )},
}
# режим збору per-source: 'fetch' (plain GET) | 'render' (WebView — SPA-крамниці).
COLLECT_MODE = {name: cfg.get("mode", "fetch") for name, cfg in HTML_SOURCES.items()}


def _url_cat(entry):
    """url-запис — рядок, (url, slug) або (url, slug, pages). → (url, slug|None, pages|None).

    Третій елемент — ГЛИБИНА саме цього лістинга; перекриває `pages` джерела. Потрібен,
    бо в межах однієї крамниці лістинги пагінуються по-різному: у Brain адреси форми
    `/ukr/category/…` дають `page=N/`, а старий департамент `Smartfoni_zvyazok-c297` — ні.
    """
    if isinstance(entry, str):
        return entry, None, None
    if len(entry) == 2:
        return entry[0], entry[1], None
    return entry[0], entry[1], entry[2]


def source_listings(cfg) -> list[tuple[str, str | None, int]]:
    """Усі лістинг-URL джерела з категоріями й НОМЕРОМ сторінки, включно з пагінацією.

    Сторінки 2..N будуються за схемою самої крамниці (`page_tpl`), перевіреною фактом:
    сторінка 2 має віддавати ІНШІ товари (розвідка 2026-07-20 — перетин з 1-ю усюди 0).
    Категорія успадковується від першої сторінки, тож окремо її ніде реєструвати не треба.
    Джерело без `page_tpl` (SPA-крамниці на кшталт Brain) лишається з однією сторінкою.

    Номер сторінки потрібен черзі: глибина визначає, як часто сторінку перезбирати
    (qtasks.repeat_for_page). Перші сторінки — де з'являються знижки; хвіст майже
    не рухається, і збирати його так само часто — марна трата єдиної пропускної
    здатності (заміряно 2026-07-21: ~480 запусків на добу при 496 потрібних для
    рівного циклу 2×/добу — тобто впритул до стелі; розведення знижує потребу до ~293).
    """
    out: list[tuple[str, str | None, int]] = []
    tpl, pages = cfg.get("page_tpl"), cfg.get("pages", 1)
    for entry in cfg.get("urls", ()):
        u, c, own = _url_cat(entry)
        out.append((u, c, 1))
        depth = own if own is not None else pages     # поштучна глибина > джерельної
        if tpl and depth > 1:
            out += [(tpl.format(base=u, n=n), c, n) for n in range(2, depth + 1)]
    return out


# (source, url) → категорія: категорія береться з ЛІСТИНГА, який зібрали (надійно),
# а не вгадується з product-URL. Hub-лендинги (Allo) тут відсутні → падають на categorize().
URL_CATEGORY: dict[tuple[str, str], str] = {}
for _name, _cfg in HTML_SOURCES.items():
    for _u, _c, _p in source_listings(_cfg):
        if _c:
            URL_CATEGORY[(_name, _u)] = _c

PRICE_MIN_KOP = 100                 # 1 грн — нижче майже напевно помилка парсингу
PRICE_MAX_KOP = 100_000_000         # 1 000 000 грн — стеля здорового глузду
_MAX_TITLE = 300
_MAX_REF = 500
_MAX_URL = 600
# 12 МБ на сторінку — стеля проти роздування (звичайні лендинги ~сотні КБ).
# Підняли з 5 МБ 2026-07-20: рендерер тепер ПРОКРУЧУЄ сторінку до стабілізації DOM,
# тож нескінченні стрічки (Brain) віддають помітно більший HTML, ніж перший екран.
_MAX_HTML = 12_000_000


def load_tokens() -> dict[str, str]:
    """token → label з env `INGEST_TOKENS` (формат: `label:token,label2:token2`).

    Токен генерувати `openssl rand -hex 32`; класти в /etc/hapay/hapay.env, НЕ в git.
    """
    raw = os.environ.get("INGEST_TOKENS", "").strip()
    out: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        label, tok = pair.split(":", 1)
        label, tok = label.strip(), tok.strip()
        if label and tok:
            out[tok] = label
    return out


def collector_label(authorization: str | None) -> str | None:
    """Повертає label колектора для валідного `Authorization: Bearer <token>`, інакше None.
    Порівняння — constant-time (hmac.compare_digest) проти timing-атак."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    for known, label in load_tokens().items():
        if hmac.compare_digest(token, known):
            return label
    return None


def _host_ok(url: str, allowed: tuple[str, ...]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == a or host.endswith("." + a) for a in allowed)


def validate_item(source: str, raw: dict) -> tuple[RawItem | None, str | None]:
    """Один елемент від колектора → (RawItem, None) або (None, причина-відмови).

    Сервер НЕ вірить на слово навіть довіреному колектору: усе перевіряється тут.
    """
    hosts = INGEST_SOURCES[source]["hosts"]

    url = raw.get("url")
    if not isinstance(url, str) or not (0 < len(url) <= _MAX_URL):
        return None, "url: порожній/задовгий"
    if urlsplit(url).scheme != "https":
        return None, "url: лише https"
    if not _host_ok(url, hosts):
        return None, f"url не на домені {source} ({hosts})"

    title = raw.get("title")
    if not isinstance(title, str) or not (0 < len(title.strip()) <= _MAX_TITLE):
        return None, "title: порожній/задовгий"

    now = raw.get("price_now_kop")
    if not isinstance(now, int) or isinstance(now, bool) or not (PRICE_MIN_KOP <= now <= PRICE_MAX_KOP):
        return None, f"price_now_kop поза [{PRICE_MIN_KOP},{PRICE_MAX_KOP}]"

    old = raw.get("price_old_kop")
    if old is not None:
        if not isinstance(old, int) or isinstance(old, bool) or not (PRICE_MIN_KOP <= old <= PRICE_MAX_KOP):
            return None, "price_old_kop поза діапазоном"
        if old <= now:
            old = None                                  # «стара» не вища за поточну — не знижка

    ext = raw.get("external_ref")
    if not isinstance(ext, str) or not (0 < len(ext) <= _MAX_REF):
        return None, "external_ref: порожній/задовгий"

    img = raw.get("image_url")
    if img is not None:
        if not isinstance(img, str) or len(img) > _MAX_URL or urlsplit(img).scheme != "https":
            img = None                                  # погане фото не валить елемент — просто нема

    variant = raw.get("variant_note")
    if variant is not None and (not isinstance(variant, str) or len(variant) > 120):
        variant = None

    in_stock = raw.get("in_stock", True)
    if not isinstance(in_stock, bool):
        in_stock = True

    promo = raw.get("promo_until")   # ISO-дата кінця дії ціни; формат перевіряємо, зміст — ні
    if not (isinstance(promo, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", promo)):
        promo = None

    return RawItem(
        external_ref=canon_ref(ext),
        url=url,
        title=title.strip(),
        price_now_kop=now,
        price_old_kop=old,
        in_stock=in_stock,
        image_url=img,
        variant_note=variant,
        promo_until=promo,
    ), None


def ingest_batch(conn, source: str, items: list, category_slug: str | None = None) -> dict:
    """Валідує й персистить батч від колектора. Погані елементи ВІДКИДАЄ (не валить добрі).

    `scan_run` — песимістично 'failed'→'ok' (T13). `source_method='satellite'` фіксує
    провенанс: ці снапшоти прийшли не з нашого прямого збору.
    """
    if source not in INGEST_SOURCES:
        raise ValueError(f"невідоме джерело: {source!r}")
    if not isinstance(items, list):
        raise ValueError("items має бути списком")

    valid: list[RawItem] = []
    seen: set[str] = set()
    rejected: list[str] = []
    for raw in items[:5000]:                            # стеля батчу — проти зловмисного роздування
        if not isinstance(raw, dict):
            rejected.append("не-обʼєкт"); continue
        item, why = validate_item(source, raw)
        if item is None:
            rejected.append(why or "?"); continue
        if item.external_ref in seen:                   # дедуп у межах батчу
            continue
        seen.add(item.external_ref)
        valid.append(item)

    base_url = INGEST_SOURCES[source]["base_url"]
    source_id = upsert_source(conn, source, base_url, adapter_kind="ssr",
                              platform="custom", fetch_tier="A")
    scan_run_id = conn.execute(
        "INSERT INTO scan_run (source_id, surface, status) VALUES (%s,'discovery','failed') "
        "RETURNING scan_run_id", (source_id,)).fetchone()[0]

    categories = load_categories(conn)
    n = persist_items(conn, source_id, valid, categories, source_method="satellite",
                      scan_run_id=scan_run_id, category_slug=category_slug)

    status = "ok" if valid and not rejected else ("partial" if valid else "failed")
    conn.execute("UPDATE scan_run SET finished_at = now(), items_seen = %s, status = %s "
                 "WHERE scan_run_id = %s", (n, status, scan_run_id))

    # унікальні причини відмов (без спаму) — щоб колектор бачив, що відкинуто й чому
    reasons: dict[str, int] = {}
    for r in rejected:
        reasons[r] = reasons.get(r, 0) + 1
    return {"source": source, "accepted": n, "rejected": len(rejected),
            "reasons": reasons, "status": status}


# ── html-ingest: застосунок шле сирий HTML, СЕРВЕР парсить (S11 етап 3) ────────────
def collect_plan() -> list[dict]:
    """Що застосунку-колектору тягнути. Сервер — авторитет (додати крамницю = зміна ТУТ,
    не оновлення застосунку). Для hub-джерел віддаємо хаб; сервер сам зробить discover()
    з присланого HTML і поверне лендинги наступним кроком."""
    out: list[dict] = []
    for name, cfg in HTML_SOURCES.items():
        mode = cfg.get("mode", "fetch")
        if cfg.get("hub"):
            out.append({"source": name, "url": cfg["hub"], "kind": "hub", "mode": mode})
        for u, _c, _p in source_listings(cfg):          # лістинги + їхня пагінація
            out.append({"source": name, "url": u, "kind": "page", "mode": mode})
    return out


def ingest_html(conn, source: str, url: str, html: str) -> dict:
    """Сирий HTML від колектора → СЕРВЕР парсить адаптером → та сама валідація+персист,
    що й /api/ingest (довіра до людини ≠ довіра до кожного байта — усе перевіряється).

    Двофазно для hub-джерел: якщо `url` — хаб, повертаємо discover()-лендинги (accepted=0);
    застосунок дотягне їх наступними викликами (kind='page'). Так уся логіка парсингу
    лишається на сервері — застосунок лише fetch+forward.
    """
    if source not in HTML_SOURCES:
        raise ValueError(f"невідоме html-джерело: {source!r}")
    if source not in INGEST_SOURCES:
        raise ValueError(f"джерело {source!r} без host-політики")
    hosts = INGEST_SOURCES[source]["hosts"]

    if not isinstance(url, str) or not (0 < len(url) <= _MAX_URL):
        raise ValueError("url: порожній/задовгий")
    if urlsplit(url).scheme != "https":
        raise ValueError("url: лише https")
    if not _host_ok(url, hosts):
        raise ValueError(f"url не на домені {source} ({hosts})")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("html: порожній")
    if len(html) > _MAX_HTML:
        raise ValueError(f"html: завеликий (>{_MAX_HTML} байт)")

    cfg = HTML_SOURCES[source]
    adapter = cfg["adapter"]

    # фаза 1: хаб → лендинги (discover робить СЕРВЕР, не застосунок)
    if cfg.get("hub") and canon_ref(url) == canon_ref(cfg["hub"]):
        try:
            landings = adapter.discover(html)[: cfg.get("max_pages", 20)]
        except Exception as e:
            raise ValueError(f"discover: {type(e).__name__}: {e}")
        # лендинги мусять лишатись на домені джерела (не дати збити застосунок на чужий хост)
        landings = [u for u in landings if _host_ok(u, hosts)]
        return {"source": source, "kind": "hub", "discovered": landings,
                "accepted": 0, "rejected": 0, "status": "ok"}

    # фаза 2: сторінка → екстракт → та сама валідація+персист, що й прямий /api/ingest
    try:
        extracted = adapter.extract(html)
    except Exception as e:
        raise ValueError(f"extract: {type(e).__name__}: {e}")
    items = [dataclasses.asdict(it) for it in extracted]
    # категорія — з ЛІСТИНГА, який зібрали (надійно): спершу поіменний тег URL, тоді
    # джерело-рівневий дефолт (hub); нема — persist_items вгадає з URL (categorize).
    category_slug = URL_CATEGORY.get((source, url)) or cfg.get("category")
    result = ingest_batch(conn, source, items, category_slug=category_slug)
    result["kind"] = "page"
    return result
