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

from adapters.addua import AdduaAdapter
from adapters.allo import HUB as ALLO_HUB, AlloAdapter
from adapters.apteka911 import Apteka911Adapter
from adapters.base import RawItem, canon_ref
from adapters.brain import BrainAdapter
from adapters.citrus import CitrusAdapter
from adapters.comfy import ComfyAdapter
from adapters.eldorado import EldoradoAdapter
from adapters.epicentr import EpicentrAdapter
from adapters.foxtrot import FoxtrotAdapter
from adapters.ktc import KtcAdapter
from adapters.moyo import MoyoAdapter
from adapters.podorozhnyk import PodorozhnykAdapter
from adapters.rozetka import RozetkaAdapter
from adapters.telemart import TelemartAdapter
from adapters.vencon import VenconAdapter
from db.store import load_categories, persist_items, upsert_source
from matching import normalize_gtin

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
    # Подорожник — перша аптека. Фото на i.podorozhnyk.com; у hosts НЕ додаємо (там лише
    # фото, перевірка стереже URL ТОВАРУ, а він на podorozhnyk.ua).
    "Podorozhnyk": {"base_url": "https://podorozhnyk.ua",  "hosts": ("podorozhnyk.ua",)},
    "AddUa":     {"base_url": "https://www.add.ua",        "hosts": ("add.ua",)},
    # Аптека 911 — третя аптека. Фото на власному CDN; у hosts НЕ додаємо (перевірка
    # стереже URL ТОВАРУ, а він на apteka911.ua).
    "Apteka911": {"base_url": "https://apteka911.ua",      "hosts": ("apteka911.ua",)},
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
                 ("https://allo.ua/ua/klaviatury/", "klaviatury", 2),   # слабкий матчер
                 ("https://allo.ua/ua/videokarty/", "videokarty", 2),   # MPN 43/60 (72%)
                 ("https://allo.ua/ua/ssd-nakopiteli/", "ssd", 2),   # MPN 60/60 (100%)
                 ("https://allo.ua/ua/processory/", "procesory", 2),   # MPN 31/60
                 ("https://allo.ua/ua/operativnaja-pamjat/", "ram", 2),   # MPN 45/60
                 ("https://allo.ua/ua/materinskie-platy/", "materynski-platy", 2),   # MPN 17/60 (слабкий)
                 ("https://allo.ua/ua/bloki-pitanija/", "bzh", 2),   # MPN 32/60
                 ("https://allo.ua/ua/korpusa/", "korpusy", 2),   # MPN 31/60 (слабкий)
                 ("https://allo.ua/ua/sistemy-ohlazhdenija/", "kulery", 2),   # MPN 19/60
                 ("https://allo.ua/ua/televizory/", "tv"),
                 ("https://allo.ua/ua/products/internet-planshety/", "planshety", 3),
                 ("https://allo.ua/ua/naushniki/", "audio", 3),
                 ("https://allo.ua/ua/smart-chasy/", "smart-hodynnyky", 3),
                 ("https://allo.ua/ua/holodilniki/", "pobut-tehnika", 3),
                 ("https://allo.ua/ua/elektrochajniki/", "elektrochaynyky", 2),   # MPN 40/60
                 ("https://allo.ua/ua/feny/", "feny", 2),
                 ("https://allo.ua/ua/elektrobritvy/", "brytvy", 2),
                 ("https://allo.ua/ua/trimmery/", "trymery", 2),   # персональні (не садові)
                 ("https://allo.ua/ua/epiljatory/", "epilyatory", 2),
                 ("https://allo.ua/ua/stajlery-i-nabory-dlja-ukladki/", "ukladka-volossya", 2),  # без фенів
                 ("https://allo.ua/ua/jelektricheskie-zubnye-schetki/", "zubni-shchitky", 2),
                 ("https://allo.ua/ua/shurupoverty/", "shurupoverty", 2),
                 ("https://allo.ua/ua/perforatory/", "perforatory", 2),
                 ("https://allo.ua/ua/bolgarki/", "bolharky", 2),
                 ("https://allo.ua/ua/jelektrolobziki/", "lobzyky", 2),
                 ("https://allo.ua/ua/diskovye-pily/", "pyly-dyskovi", 2),
                 ("https://allo.ua/ua/svarochnye-invertory/", "zvaryuvalni", 2),
                 ("https://allo.ua/ua/shlifmashiny/", "shlifmashyny", 2),
                 ("https://allo.ua/ua/kompressory/", "kompresory", 2),
                 ("https://allo.ua/ua/nabory-instrumentov/", "nabory-instrumentu", 2),
                 ("https://allo.ua/ua/trimmery-i-motokosy/", "motokosy", 2),
                 ("https://allo.ua/ua/gazonokosilki/", "gazonokosarky", 2),
                 ("https://allo.ua/ua/cepnye-pily/", "pyly-lancjugovi", 2),
                 ("https://allo.ua/ua/sadovye-pylesosy/", "povitroduvky", 2),
                 ("https://allo.ua/ua/motobloki/", "kultyvatory", 2),
                 ("https://allo.ua/ua/kustorezy/", "kushchorizy", 2),
                 ("https://allo.ua/ua/opryskivateli/", "obpryskuvachi", 2),
                 ("https://allo.ua/ua/nasosy/", "nasosy", 2),
                 ("https://allo.ua/ua/videoregistratory/", "videoreyestratory", 2),
                 ("https://allo.ua/ua/avtomagnitoly/", "avtomagnitoly", 2),
                 ("https://allo.ua/ua/avtokompressory/", "avtokompresory", 2),
                 ("https://allo.ua/ua/avtopylesosy/", "avtopylososy", 2),
                 ("https://allo.ua/ua/portativnye-holodil-niki/", "avtoholodylnyky", 2),
                 ("https://allo.ua/ua/uvlazhniteli-vozduha/", "zvolozhuvachi", 2),
                 ("https://allo.ua/ua/ochistiteli-vozduha/", "ochyshchuvachi", 2),
                 ("https://allo.ua/ua/osushiteli-vozduha/", "osushuvachi", 2),
                 ("https://allo.ua/ua/meteostancii/", "meteostantsii", 2),
                 ("https://allo.ua/ua/begovye-dorozhki/", "begovi-dorizhky", 2),
                 ("https://allo.ua/ua/velotrenazhery/", "velotrenazhery", 2),
                 ("https://allo.ua/ua/jelektrosamokaty/", "elektrosamokaty", 2),
                 ("https://allo.ua/ua/detskie-koljaski/", "kolyasky", 2),
                 ("https://allo.ua/ua/detskie-avtokresla/", "avtokrisla", 2),
                 ("https://allo.ua/ua/molokootsosy/", "molokovidsmoktuvachi", 2),
                 ("https://allo.ua/ua/sterilizatory/", "sterylizatory", 2),
                 ("https://allo.ua/ua/jekshn-kamery/", "ekshn-kamery", 2),
                 ("https://allo.ua/ua/kvadrokoptery/", "drony", 2),
                 ("https://allo.ua/ua/usb-flash-drive/", "usb-fleshky", 2),
                 ("https://allo.ua/ua/vneshnie-hdd/", "zovnishni-hdd", 2),
                 ("https://allo.ua/ua/tostery/", "tostery", 2),   # MPN 36/60
                 ("https://allo.ua/ua/products/utugi/", "prasky", 2),
                 ("https://allo.ua/ua/products/masorubki/", "myasorubky", 2),
                 ("https://allo.ua/ua/products/sokovyzh/", "sokovyzhymalky", 2),
                 ("https://allo.ua/ua/miksery/", "miksery", 2),
                 ("https://allo.ua/ua/stiralnye-mashiny/", "pobut-tehnika", 1),
                 ("https://allo.ua/ua/otdel-no-stojaschie-posudomoechnye-mashiny/", "pobut-tehnika", 1),
                 ("https://allo.ua/ua/vytjazhki/", "vytyazhky", 2),   # Allo пише «vytjazhki» через j
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
        ("https://www.foxtrot.com.ua/uk/shop/klaviatury.html", "klaviatury", 2),  # MPN 21/42 (слабкий)
        ("https://www.foxtrot.com.ua/uk/shop/kompyuternue_myshy.html", "myshi", 2),  # MPN 16/42 (слабкий)
        ("https://www.foxtrot.com.ua/uk/shop/web-kamery.html", "veb-kamery", 2),  # MPN 17/42
        ("https://www.foxtrot.com.ua/uk/shop/istochniki_besbereboyinogo_pitaniya.html", "dbzh", 2),  # MPN 29/42
        ("https://www.foxtrot.com.ua/uk/shop/kovriki_dlya_myshki.html", "kylymky", 2),  # MPN 17/42 (слабкий)
        ("https://www.foxtrot.com.ua/uk/shop/videokarti.html", "videokarty", 2), # 42/стор., MPN 33
        ("https://www.foxtrot.com.ua/uk/shop/zhestkie_diski_ssd_tverdotelnye.html", "ssd", 2),  # MPN 42/42
        ("https://www.foxtrot.com.ua/uk/shop/processori.html", "procesory", 2),  # MPN 40/40
        ("https://www.foxtrot.com.ua/uk/shop/moduli_pamiati.html", "ram", 2),  # MPN 42/42
        ("https://www.foxtrot.com.ua/uk/shop/materinskie_plati.html", "materynski-platy", 2),  # MPN 9/42 (слабкий)
        ("https://www.foxtrot.com.ua/uk/shop/bloki_pytania.html", "bzh", 2),  # MPN 28/42
        ("https://www.foxtrot.com.ua/uk/shop/korpusi_komputernie.html", "korpusy", 2),  # MPN 11/42 (слабкий)
        ("https://www.foxtrot.com.ua/uk/shop/ventiliatori_dlia_korpusa_kulery-dlya-proczessora.html", "kulery", 2),  # MPN 29/42
        ("https://www.foxtrot.com.ua/uk/shop/led_televizory.html", "tv"),        # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/planshety.html", "planshety", 3),    # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/naushniki.html", "audio", 3),        # 42 товари
        ("https://www.foxtrot.com.ua/uk/shop/smart_chasi.html", "smart-hodynnyky", 3),
        ("https://www.foxtrot.com.ua/uk/shop/holodilniki.html", "pobut-tehnika", 3),
        ("https://www.foxtrot.com.ua/uk/shop/stiralki.html", "pobut-tehnika", 1),   # 42
        ("https://www.foxtrot.com.ua/uk/shop/igrovye_pristavki.html", "konsoli", 2),# 9
        ("https://www.foxtrot.com.ua/uk/shop/mikrovolnovki.html", "mikrohvylovky", 3),
        ("https://www.foxtrot.com.ua/uk/shop/elektrochayniki.html", "elektrochaynyky", 2),  # MPN 33/42
        ("https://www.foxtrot.com.ua/uk/shop/feny.html", "feny", 2),  # MPN 36/42
        ("https://www.foxtrot.com.ua/uk/shop/elektrobritvy.html", "brytvy", 2),
        ("https://www.foxtrot.com.ua/uk/shop/trimmery_trymmer.html", "trymery", 2),  # MPN 28/42
        ("https://www.foxtrot.com.ua/uk/shop/epilyatory.html", "epilyatory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/plojki.html", "ukladka-volossya", 2),
        ("https://www.foxtrot.com.ua/uk/shop/zubnye_schetki_elektricheskaya-zybnaya-shhetka.html", "zubni-shchitky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/shurupoverti.html", "shurupoverty", 2),
        ("https://www.foxtrot.com.ua/uk/shop/puncher.html", "perforatory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/grinders_uglovye-bolgarki.html", "bolharky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/electro_lobz.html", "lobzyky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/saw.html", "pyly-dyskovi", 2),
        ("https://www.foxtrot.com.ua/uk/shop/welding_svarochnye-apparaty.html", "zvaryuvalni", 2),
        ("https://www.foxtrot.com.ua/uk/shop/shurupoverti_gajkoverty-elektricheskie.html", "haikoverty", 2),
        ("https://www.foxtrot.com.ua/uk/shop/grinders_lentochnye.html", "shlifmashyny", 2),
        ("https://www.foxtrot.com.ua/uk/shop/compressors.html", "kompresory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/generators.html", "generatory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/carwasher.html", "myyky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/metric_lazernii-nivelir.html", "vymiryuvalni", 2),
        ("https://www.foxtrot.com.ua/uk/shop/solyariy.html", "nabory-instrumentu", 2),  # legacy-слаг наборів
        ("https://www.foxtrot.com.ua/uk/shop/trimeri.html", "motokosy", 2),  # садові (не персональні)
        ("https://www.foxtrot.com.ua/uk/shop/gazonokosilki.html", "gazonokosarky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/cepnie_pili.html", "pyly-lancjugovi", 2),
        ("https://www.foxtrot.com.ua/uk/shop/garden_misc_sadovye-pylesosy.html", "povitroduvky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/kultivator.html", "kultyvatory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/kustorezi.html", "kushchorizy", 2),
        ("https://www.foxtrot.com.ua/uk/shop/opriskivatel.html", "obpryskuvachi", 2),
        ("https://www.foxtrot.com.ua/uk/shop/electro_pump.html", "nasosy", 2),
        ("https://www.foxtrot.com.ua/uk/shop/videoreg.html", "videoreyestratory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/avtomagnitoly.html", "avtomagnitoly", 2),
        ("https://www.foxtrot.com.ua/uk/shop/avto_aksessuary_avtomobilnye-kompressory.html", "avtokompresory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/pylesosy_avto.html", "avtopylososy", 2),
        ("https://www.foxtrot.com.ua/uk/shop/avto_xolodilniki_avtoholodilnik.html", "avtoholodylnyky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/uvlagniteli_vozduha.html", "zvolozhuvachi", 2),
        ("https://www.foxtrot.com.ua/uk/shop/ionizatory.html", "ochyshchuvachi", 2),
        ("https://www.foxtrot.com.ua/uk/shop/osushiteli_vozduha.html", "osushuvachi", 2),
        ("https://www.foxtrot.com.ua/uk/shop/ventilyatory.html", "ventylatory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/meteostanchii.html", "meteostantsii", 2),
        ("https://www.foxtrot.com.ua/uk/shop/trenazheriy_i_sportivnoe_oborudovanie_begovaya-dorozhka.html", "begovi-dorizhky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/trenazheriy_i_sportivnoe_oborudovanie_velotrenazher.html", "velotrenazhery", 2),
        ("https://www.foxtrot.com.ua/uk/shop/girobordi_elektrosamokat.html", "elektrosamokaty", 2),
        ("https://www.foxtrot.com.ua/uk/shop/detskie_koliaski.html", "kolyasky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/detskie_kresla.html", "avtokrisla", 2),
        ("https://www.foxtrot.com.ua/uk/shop/tehnika_dlia_kormlenia_podogrevateli-butylochek.html", "sterylizatory", 2),
        ("https://www.foxtrot.com.ua/uk/shop/action_cam.html", "ekshn-kamery", 2),
        ("https://www.foxtrot.com.ua/uk/shop/kvadrokopteri_droni.html", "drony", 2),
        ("https://www.foxtrot.com.ua/uk/shop/karty_pamyati.html", "karty-pamyati", 2),
        ("https://www.foxtrot.com.ua/uk/shop/fleshki.html", "usb-fleshky", 2),
        ("https://www.foxtrot.com.ua/uk/shop/gestkie_diski.html", "zovnishni-hdd", 2),
        ("https://www.foxtrot.com.ua/uk/shop/tostery.html", "tostery", 2),  # MPN 30/42
        ("https://www.foxtrot.com.ua/uk/shop/utugi.html", "prasky", 2),  # MPN 40/42 (+ відпарювачі)
        ("https://www.foxtrot.com.ua/uk/shop/myasorybki.html", "myasorubky", 2),  # MPN 33/42
        ("https://www.foxtrot.com.ua/uk/shop/sokovygymalki.html", "sokovyzhymalky", 2),  # MPN 24/42
        ("https://www.foxtrot.com.ua/uk/shop/miksery.html", "miksery", 2),  # MPN 23/42 (слабший)
        ("https://www.foxtrot.com.ua/uk/shop/pylesosy.html", "pylososy", 3),
        ("https://www.foxtrot.com.ua/uk/shop/cofevarki.html", "kavomashyny", 3),
        ("https://www.foxtrot.com.ua/uk/shop/mobilnye_telefony_telefon.html", "knopkovi-telefony", 3),
        ("https://www.foxtrot.com.ua/uk/shop/roboti_pilesosi.html", "pylososy", 1),
        ("https://www.foxtrot.com.ua/uk/shop/drymachine.html", "pobut-tehnika", 1),
        ("https://www.foxtrot.com.ua/uk/shop/vytyagki.html", "vytyazhky", 2),        # Foxtrot: слаг «vytyagki» через g
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
        ("https://www.moyo.ua/ua/acsessor/acsessor_for_comp/keyboard/", "klaviatury", 2),
        ("https://www.moyo.ua/ua/acsessor/acsessor_for_comp/mouse/", "myshi", 2),
        ("https://www.moyo.ua/ua/comp-and-periphery/kompiyternaj_perefir/webcams/", "veb-kamery", 2),
        ("https://www.moyo.ua/ua/comp-and-periphery/kompiyternaj_perefir/ibp/", "dbzh", 2),  # MPN 21/24
        ("https://www.moyo.ua/ua/acsessor/acsessor_for_comp/mousepad/", "kylymky", 2),
        ("https://www.moyo.ua/ua/comp-and-periphery/periphery-and-compon/videokarty/", "videokarty", 2),  # MPN 15/24
        ("https://www.moyo.ua/ua/comp-and-periphery/inform_carrier/ssd/", "ssd", 2),  # MPN 21/24
        ("https://www.moyo.ua/ua/comp-and-periphery/periphery-and-compon/processory/", "procesory", 2),  # MPN 14/24
        ("https://www.moyo.ua/ua/comp-and-periphery/periphery-and-compon/ddr-dlya-pc/", "ram", 2),  # MPN 24/24
        ("https://www.moyo.ua/ua/comp-and-periphery/periphery-and-compon/materinskie-platy/", "materynski-platy", 2),  # MPN 13/24
        ("https://www.moyo.ua/ua/comp-and-periphery/periphery-and-compon/bloki-pitaniya/", "bzh", 2),  # MPN 22/24
        ("https://www.moyo.ua/ua/comp-and-periphery/periphery-and-compon/korpusa-k-pc/", "korpusy", 2),  # MPN 11/24 (слабкий)
        ("https://www.moyo.ua/ua/comp-and-periphery/periphery-and-compon/kuleri-i-radiatory/naznachenie_dlya_processora/", "kulery", 2),  # MPN 13/24
        ("https://www.moyo.ua/ua/foto_video/tv_audio/lcd_tv/", "tv"),            # 24 товари
        ("https://www.moyo.ua/ua/tablet_el_knigi/tablet/", "planshety", 3),       # 24 товари
        ("https://www.moyo.ua/ua/acsessor/ipod_headphones/", "audio", 3),         # 24 товари
        ("https://www.moyo.ua/ua/gadgets/smart_chasy/", "smart-hodynnyky", 3),
        ("https://www.moyo.ua/ua/bt/kbt/holodilniky/", "pobut-tehnika", 3),
        ("https://www.moyo.ua/ua/bt/kbt/stiralnie-mashiny/", "pobut-tehnika", 1),    # 24
        ("https://www.moyo.ua/ua/bt/kbt/posudomoechnie-mashi/", "pobut-tehnika", 1), # 24
        ("https://www.moyo.ua/ua/bt/vstraivaemaya-tekh/vytyajki/", "vytyazhky", 2),   # Moyo: слаг «vytyajki»; MPN 16/24
        ("https://www.moyo.ua/ua/foto_video/photo_video/cameras/", "foto", 3),       # 24
        ("https://www.moyo.ua/ua/game_zone/game_console/", "konsoli", 2),            # 24
        ("https://www.moyo.ua/ua/acsessor/acum/accu_univers/", "aksesuary", 1),      # 24
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/microvolnovie-pechi/", "mikrohvylovky", 3),
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/electrochayniki/", "elektrochaynyky", 2),  # MPN 17/24
        ("https://www.moyo.ua/ua/bt/tekhnika-lichnogo-po/feni/", "feny", 2),  # MPN 18/24
        ("https://www.moyo.ua/ua/bt/tekhnika-lichnogo-po/elecricheskie-britvi/", "brytvy", 2),
        ("https://www.moyo.ua/ua/bt/tekhnika-lichnogo-po/trimmer/", "trymery", 2),  # MPN 21/24
        ("https://www.moyo.ua/ua/bt/tekhnika-lichnogo-po/epilatory/", "epilyatory", 2),
        ("https://www.moyo.ua/ua/bt/tekhnika-lichnogo-po/schipci-dlya-ukladki/", "ukladka-volossya", 2),
        ("https://www.moyo.ua/ua/bt/tekhnika-lichnogo-po/elertricheskie_zubni/", "zubni-shchitky", 2),
        ("https://www.moyo.ua/ua/instrument/electroinstrument/shurupovertyi/", "shurupoverty", 2),
        ("https://www.moyo.ua/ua/instrument/electroinstrument/perforatoryi/", "perforatory", 2),
        ("https://www.moyo.ua/ua/instrument/electroinstrument/bolgarky/", "bolharky", 2),
        ("https://www.moyo.ua/ua/instrument/electroinstrument/elektrolobziki/", "lobzyky", 2),
        ("https://www.moyo.ua/ua/instrument/electroinstrument/cyrc_pyly/", "pyly-dyskovi", 2),
        ("https://www.moyo.ua/ua/instrument/stacionarnoe_oborudo/svarochnoe_oborudova/", "zvaryuvalni", 2),
        ("https://www.moyo.ua/ua/instrument/electroinstrument/gaykoverty/", "haikoverty", 2),
        ("https://www.moyo.ua/ua/instrument/electroinstrument/shlifmashinyi/", "shlifmashyny", 2),
        ("https://www.moyo.ua/ua/instrument/stacionarnoe_oborudo/kompressoryi/", "kompresory", 2),
        ("https://www.moyo.ua/ua/instrument/stacionarnoe_oborudo/generatoryi/", "generatory", 2),
        ("https://www.moyo.ua/ua/instrument/ruchnoy_instrument/naboryi_ruchnyih_ins/", "nabory-instrumentu", 2),
        ("https://www.moyo.ua/ua/instrument/sadovaya_technika/sadovyie_trimmeryi/", "motokosy", 2),
        ("https://www.moyo.ua/ua/instrument/sadovaya_technika/gazonokosilki/", "gazonokosarky", 2),
        ("https://www.moyo.ua/ua/instrument/sadovaya_technika/vozduhoduvki/", "povitroduvky", 2),
        ("https://www.moyo.ua/ua/instrument/sadovaya_technika/motokultivatoryi/", "kultyvatory", 2),
        ("https://www.moyo.ua/ua/instrument/sadovaya_technika/opryiskivateli/", "obpryskuvachi", 2),
        ("https://www.moyo.ua/ua/bt/klimaticheskaya-tekh/uvlajnitely-vozduha/", "zvolozhuvachi", 2),
        ("https://www.moyo.ua/ua/bt/klimaticheskaya-tekh/ochistiteli_vozduha/", "ochyshchuvachi", 2),
        ("https://www.moyo.ua/ua/bt/klimaticheskaya-tekh/ventylatory/", "ventylatory", 2),
        ("https://www.moyo.ua/ua/bt/klimaticheskaya-tekh/meteostancyi/", "meteostantsii", 2),
        ("https://www.moyo.ua/ua/sport_otdih_turizm/sportivnye-tovary/trenazher/begovye-dorozhki/", "begovi-dorizhky", 2),
        ("https://www.moyo.ua/ua/sport_otdih_turizm/sportivnye-tovary/trenazher/velotrenazhery/", "velotrenazhery", 2),
        ("https://www.moyo.ua/ua/gadgets/elektro_transport/elektrosamokaty/", "elektrosamokaty", 2),
        ("https://www.moyo.ua/ua/comp-and-periphery/inform_carrier/flash_card/", "karty-pamyati", 2),
        ("https://www.moyo.ua/ua/comp-and-periphery/inform_carrier/usb_drive/", "usb-fleshky", 2),
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/tosteri/", "tostery", 2),  # MPN 16/24
        ("https://www.moyo.ua/ua/bt/mbt/utugi/", "prasky", 2),  # MPN 22/24
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/myasorubki/", "myasorubky", 2),  # MPN 22/24
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/sokovijimalki/", "sokovyzhymalky", 2),  # MPN 14/24
        ("https://www.moyo.ua/ua/bt/tekhnika-dlya-kuhni/miksery/", "miksery", 2),  # MPN 15/24
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
        ("https://comfy.ua/ua/keywords/", "klaviatury", 2),   # slug «keywords» (клавіатури!), render
        ("https://comfy.ua/ua/graphics-cards/", "videokarty", 2),   # slug «graphics-cards», render
        ("https://comfy.ua/ua/ssd-nakopitel/", "ssd", 2),   # render
        ("https://comfy.ua/ua/processors/", "procesory", 2),   # render
        ("https://comfy.ua/ua/ddr/", "ram", 2),   # render
        ("https://comfy.ua/ua/motherboard/", "materynski-platy", 2),   # render
        ("https://comfy.ua/ua/power-supplies/", "bzh", 2),   # render
        ("https://comfy.ua/ua/cases-for-pc/", "korpusy", 2),   # render
        ("https://comfy.ua/ua/computer-cooling/", "kulery", 2),   # render
        ("https://comfy.ua/flat-tvs/", "tv"),                                    # 50 карток
        ("https://comfy.ua/plane-table-computer/", "planshety", 3),              # 50 карток
        ("https://comfy.ua/nayshniki/", "audio", 3),                             # 50 карток
        ("https://comfy.ua/smart-watches/", "smart-hodynnyky", 3),               # 50 карток
        ("https://comfy.ua/refrigerator/", "pobut-tehnika", 3),                  # 50 карток
        ("https://comfy.ua/ua/electric-tea-pot/", "elektrochaynyky", 2),   # render
        ("https://comfy.ua/ua/hair-dryer/", "feny", 2),   # render
        ("https://comfy.ua/ua/razor/", "brytvy", 2),   # render
        ("https://comfy.ua/ua/trimmers/", "trymery", 2),   # render
        ("https://comfy.ua/ua/epilator/", "epilyatory", 2),   # render
        ("https://comfy.ua/ua/hair-stylers/", "ukladka-volossya", 2),   # render, без фенів
        ("https://comfy.ua/ua/n-are-of-body-and-person/", "zubni-shchitky", 2),   # render (електрощітки)
        ("https://comfy.ua/ua/screwdrivers/", "shurupoverty", 2),   # render
        ("https://comfy.ua/ua/perforators/", "perforatory", 2),   # render
        ("https://comfy.ua/ua/angle-grinders/", "bolharky", 2),   # render
        ("https://comfy.ua/ua/jigsaws/", "lobzyky", 2),   # render
        ("https://comfy.ua/ua/power-saws-circular/", "pyly-dyskovi", 2),   # render
        ("https://comfy.ua/ua/grinders/", "shlifmashyny", 2),   # render (шліфмашини, не болгарки)
        ("https://comfy.ua/ua/generators/", "generatory", 2),   # render
        ("https://comfy.ua/ua/mini-washing/", "myyky", 2),   # render
        ("https://comfy.ua/ua/measuring-devices/", "vymiryuvalni", 2),   # render (широкі вимірювальні)
        ("https://comfy.ua/ua/tool-sets/", "nabory-instrumentu", 2),   # render
        ("https://comfy.ua/ua/brushcutters/", "motokosy", 2),   # render
        ("https://comfy.ua/ua/lawn-mower/", "gazonokosarky", 2),   # render
        ("https://comfy.ua/ua/chainsaws/", "pyly-lancjugovi", 2),   # render
        ("https://comfy.ua/ua/garden-vacuum-cleaners/", "povitroduvky", 2),   # render
        ("https://comfy.ua/ua/cultivators/", "kultyvatory", 2),   # render
        ("https://comfy.ua/ua/brush-cutters/", "kushchorizy", 2),   # render (кущорізи, з дефісом)
        ("https://comfy.ua/ua/hand-sprayers/", "obpryskuvachi", 2),   # render
        ("https://comfy.ua/ua/pumps/", "nasosy", 2),   # render
        ("https://comfy.ua/ua/videorecorder/", "videoreyestratory", 2),   # render
        ("https://comfy.ua/ua/auto-compressors/", "avtokompresory", 2),   # render
        ("https://comfy.ua/ua/hand-vacuum-cleaners/pylesos__avtomobilnyj/", "avtopylososy", 2),   # render (фасет авто)
        ("https://comfy.ua/ua/auto-refrigerator/", "avtoholodylnyky", 2),   # render
        ("https://comfy.ua/ua/heater/", "obigrivachi", 2),   # render
        ("https://comfy.ua/ua/humidifiers/", "zvolozhuvachi", 2),   # render
        ("https://comfy.ua/ua/air-purifiers/", "ochyshchuvachi", 2),   # render
        ("https://comfy.ua/ua/dehumidifiers/", "osushuvachi", 2),   # render
        ("https://comfy.ua/ua/fan/", "ventylatory", 2),   # render
        ("https://comfy.ua/ua/weather-station-digital-thermometer/", "meteostantsii", 2),   # render
        ("https://comfy.ua/ua/sports-and-recreation/tip_dorozhki__begovaja-dorozhka/", "begovi-dorizhky", 2),   # render (facet)
        ("https://comfy.ua/ua/jelektrosamokaty/", "elektrosamokaty", 2),   # render
        ("https://comfy.ua/ua/baby-strollers/", "kolyasky", 2),   # render
        ("https://comfy.ua/ua/baby-bottle-warmers/", "sterylizatory", 2),   # render (підігрівачі)
        ("https://comfy.ua/ua/jekshen-kamery/", "ekshn-kamery", 2),   # render
        ("https://comfy.ua/ua/drony/", "drony", 2),   # render
        ("https://comfy.ua/ua/memory-cards/", "karty-pamyati", 2),   # render
        ("https://comfy.ua/ua/flesh-and-usb/", "usb-fleshky", 2),   # render
        ("https://comfy.ua/ua/portable-hard-disk/", "zovnishni-hdd", 2),   # render
        ("https://comfy.ua/ua/toaster/", "tostery", 2),   # render
        ("https://comfy.ua/ua/iron/", "prasky", 2),   # render
        ("https://comfy.ua/ua/meat-grinder/", "myasorubky", 2),   # render
        ("https://comfy.ua/ua/juice-extractor/", "sokovyzhymalky", 2),   # render
        ("https://comfy.ua/ua/mixer/", "miksery", 2),   # render
        ("https://comfy.ua/wash-machines/", "pobut-tehnika", 1),                 # 50 карток
        ("https://comfy.ua/ua/n-hood/", "vytyazhky", 2),   # Comfy: слаг «n-hood», /ua/-форма; render (не перевірено локально)
    )},
    # Rozetka (розвідка 2026-07-19): найбільший маркетплейс, Angular-SSR 60 карток;
    # масові перетини MPN (SM-S942BZKGEUC = Foxtrot S26, SM-A576BZVDEUC = Moyo/Allo A57).
    "Rozetka": {"adapter": RozetkaAdapter(), "page_tpl": "{base}page={n}/", "pages": 5, "urls": (
        ("https://rozetka.com.ua/ua/mobile-phones/c80003/", "smartfony"),
        # відеокарти Rozetka — на піддомені hard.rozetka.com.ua (host-політика пропускає)
        ("https://hard.rozetka.com.ua/ua/videocards/c80087/", "videokarty", 2),
        ("https://hard.rozetka.com.ua/ua/ssd/c80109/", "ssd", 2),
        ("https://hard.rozetka.com.ua/ua/processors/c80083/", "procesory", 2),
        ("https://hard.rozetka.com.ua/ua/memory/c80081/", "ram", 2),
        ("https://hard.rozetka.com.ua/ua/motherboards/c80082/", "materynski-platy", 2),
        ("https://hard.rozetka.com.ua/ua/psu/c80086/", "bzh", 2),
        ("https://hard.rozetka.com.ua/ua/cases/c80090/", "korpusy", 2),
        ("https://hard.rozetka.com.ua/ua/coolers/c80099/", "kulery", 2),
        ("https://rozetka.com.ua/ua/notebooks/c80004/", "noutbuky"),             # 60 товарів
        ("https://hard.rozetka.com.ua/ua/keyboards/c80171/", "klaviatury", 2),  # hard-піддомен
        ("https://hard.rozetka.com.ua/ua/mouses/c80172/", "myshi", 2),  # hard-піддомен
        ("https://rozetka.com.ua/ua/web_cameras/c180143/", "veb-kamery", 2),  # головний домен
        ("https://hard.rozetka.com.ua/ua/ups/c80108/", "dbzh", 2),  # hard-піддомен
        ("https://hard.rozetka.com.ua/ua/gaming-surfaces/c80112/", "kylymky", 2),  # hard-піддомен
        ("https://rozetka.com.ua/ua/all-tv/c80037/", "tv"),                      # 60 товарів
        ("https://rozetka.com.ua/ua/tablets/c130309/", "planshety", 3),           # 60 товарів
        ("https://rozetka.com.ua/ua/headphones/c80027/", "audio", 3),             # 60 товарів
        ("https://rozetka.com.ua/ua/smartwatch/c651392/", "smart-hodynnyky", 3),  # 60 товарів
        ("https://rozetka.com.ua/ua/holodilniki/c80125/", "pobut-tehnika", 3),    # 60 товарів
        ("https://bt.rozetka.com.ua/ua/electric_kettles/c80160/", "elektrochaynyky", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/hairdryers/c81227/", "feny", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/men_electric_shavers/c81226/", "brytvy", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/trimmeri/c4660433/", "trymery", 2),  # bt-піддомен, персональні
        ("https://bt.rozetka.com.ua/ua/epilators_female_shavers/c81225/", "epilyatory", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/hairdressing/c81231/", "ukladka-volossya", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/zubnye-schetki-i-irrigatory/c437994/", "zubni-shchitky", 2),  # bt-піддомен
        ("https://rozetka.com.ua/ua/shurupoverty-i-elektrootvertki/c152499/", "shurupoverty", 2),  # головний домен
        ("https://rozetka.com.ua/ua/rock_drills/c153621/", "perforatory", 2),  # головний домен
        ("https://rozetka.com.ua/ua/sanders/c152503/", "bolharky", 2),  # головний домен (шліфмашини/болгарки)
        ("https://rozetka.com.ua/ua/jigsaws/c152505/", "lobzyky", 2),  # головний домен
        ("https://rozetka.com.ua/ua/pily-i-plitkorezy/c152560/", "pyly-dyskovi", 2),  # головний домен
        ("https://rozetka.com.ua/ua/svarochnie-apparati/c4670641/", "zvaryuvalni", 2),  # головний домен
        ("https://rozetka.com.ua/ua/gaykoverti/c4669237/", "haikoverty", 2),  # головний домен
        ("https://rozetka.com.ua/ua/compressors/c162118/", "kompresory", 2),  # головний домен
        ("https://rozetka.com.ua/ua/generators/c152564/", "generatory", 2),  # головний домен
        ("https://rozetka.com.ua/ua/cleaners/c155534/", "myyky", 2),  # головний домен
        ("https://rozetka.com.ua/ua/niveliri/c4672248/", "vymiryuvalni", 2),  # головний домен (рівні)
        ("https://rozetka.com.ua/ua/dalnomeri/c4672183/", "vymiryuvalni", 2),  # головний домен (далекоміри)
        ("https://rozetka.com.ua/ua/tool_kits/c298224/", "nabory-instrumentu", 2),  # головний домен
        ("https://rozetka.com.ua/ua/trimmers/c155089/", "motokosy", 2),  # головний домен (садові)
        ("https://rozetka.com.ua/ua/grass_cutters/c155072/", "gazonokosarky", 2),  # головний домен
        ("https://rozetka.com.ua/ua/chainsaws/c155515/", "pyly-lancjugovi", 2),  # головний домен
        ("https://rozetka.com.ua/ua/blowers/c156363/", "povitroduvky", 2),  # головний домен
        ("https://rozetka.com.ua/ua/kulivatory-i-motobloki/c155824/", "kultyvatory", 2),  # головний домен
        ("https://rozetka.com.ua/ua/kustorezy/c155467/", "kushchorizy", 2),  # головний домен
        ("https://rozetka.com.ua/ua/sprayers/c156378/", "obpryskuvachi", 2),  # головний домен
        ("https://rozetka.com.ua/ua/pumps/c155952/", "nasosy", 2),  # головний домен
        ("https://rozetka.com.ua/ua/snowthrow/c182187/", "snihoprybyrachi", 2),  # головний домен
        ("https://auto.rozetka.com.ua/ua/vdr/c153617/", "videoreyestratory", 2),  # auto-піддомен
        ("https://auto.rozetka.com.ua/ua/mediareceivers/c275389/", "avtomagnitoly", 2),  # auto-піддомен
        ("https://auto.rozetka.com.ua/ua/car_compressors/c278510/", "avtokompresory", 2),  # auto-піддомен
        ("https://auto.rozetka.com.ua/ua/ruchnie-avtomobilnie/c4631263/", "avtopylososy", 2),  # auto-піддомен
        ("https://auto.rozetka.com.ua/ua/avtoholodilniki/c4674624/", "avtoholodylnyky", 2),  # auto-піддомен
        ("https://bt.rozetka.com.ua/ua/heaters/c80192/", "obigrivachi", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/humidifiers/c80130/", "zvolozhuvachi", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/air_cleaners/c80128/", "ochyshchuvachi", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/osushiteli-vozduha/c388104/", "osushuvachi", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/fans/c80186/", "ventylatory", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/miniweather_stations/c80183/", "meteostantsii", 2),  # bt-піддомен
        ("https://rozetka.com.ua/ua/treadmills/c132896/", "begovi-dorizhky", 2),  # головний домен
        ("https://rozetka.com.ua/ua/exrecise_bikes/c133215/", "velotrenazhery", 2),  # головний домен
        ("https://rozetka.com.ua/ua/elektrosamokati/c4657382/", "elektrosamokaty", 2),  # головний домен
        ("https://rozetka.com.ua/ua/detskie-kolyaski/c100389/", "kolyasky", 2),  # головний домен
        ("https://rozetka.com.ua/ua/detskie-avtokresla/c83687/", "avtokrisla", 2),  # головний домен
        ("https://rozetka.com.ua/ua/breast_pumps/c267223/", "molokovidsmoktuvachi", 2),  # головний домен
        ("https://rozetka.com.ua/ua/sterilizatori-i-podogrevateli/c4630405/", "sterylizatory", 2),  # головний домен
        ("https://rozetka.com.ua/ua/ekshn-kameri-i-aksessuari/c4630489/", "ekshn-kamery", 2),  # головний домен
        ("https://rozetka.com.ua/ua/quadrocopters/c1124685/", "drony", 2),  # головний домен
        ("https://rozetka.com.ua/ua/memory-cards/c80044/", "karty-pamyati", 2),  # головний домен
        ("https://rozetka.com.ua/ua/usb-flash-memory/c80045/", "usb-fleshky", 2),  # головний домен
        ("https://hard.rozetka.com.ua/ua/hdd/c80084/", "zovnishni-hdd", 2),  # hard-піддомен
        ("https://bt.rozetka.com.ua/ua/toasters/c80145/", "tostery", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/irons/c80161/", "prasky", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/meat_choppers/c80176/", "myasorubky", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/squeezers/c80153/", "sokovyzhymalky", 2),  # bt-піддомен
        ("https://bt.rozetka.com.ua/ua/mixers/c80156/", "miksery", 2),  # bt-піддомен
        ("https://rozetka.com.ua/ua/washing_machines/c80124/", "pobut-tehnika", 1),# 60 товарів
        # витяжки Rozetka — на піддомені bt.rozetka.com.ua (host-політика пропускає: .rozetka.com.ua)
        ("https://bt.rozetka.com.ua/ua/extractor_fans/c80140/", "vytyazhky", 2),
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
        ("https://www.ctrs.com.ua/vytyazhki/", "vytyazhky", 2),                  # 47 витяжок
        ("https://www.ctrs.com.ua/cameras/", "foto", 3),                        # 35 товарів
        ("https://www.ctrs.com.ua/igrovye-pristavki/", "konsoli", 2),           # 47 товарів
        ("https://www.ctrs.com.ua/portativnye-batarei/", "aksesuary", 1),       # 47 товарів
        ("https://www.ctrs.com.ua/mikrovolnovki/", "mikrohvylovky", 3),        # 47 товарів
        ("https://www.ctrs.com.ua/elektrochayniki/", "elektrochaynyky", 2),    # 47 чайників, 100%
        ("https://www.ctrs.com.ua/tostery/", "tostery", 2),
        ("https://www.ctrs.com.ua/utyugi/", "prasky", 2),
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
        ("https://brain.com.ua/ukr/category/Klaviatury-c1269-67/", "klaviatury", 2),
        ("https://brain.com.ua/ukr/category/Myshky-c1272-68/", "myshi", 2),
        ("https://brain.com.ua/ukr/category/Vebkamery-c1360-153/", "veb-kamery", 2),
        ("https://brain.com.ua/ukr/category/Kylymky-c1040/", "kylymky", 2),
        ("https://brain.com.ua/ukr/category/Videokarty-c1403/", "videokarty", 2),# 24/стор., MPN 18
        ("https://brain.com.ua/ukr/category/SSD_dysky-c1484/", "ssd", 2),
        ("https://brain.com.ua/ukr/category/Procesory-c1097-128/", "procesory", 2),
        ("https://brain.com.ua/ukr/category/Operativna_pamyat-c3130/", "ram", 2),
        ("https://brain.com.ua/ukr/category/Systemni_materynski_platy-c1264-226/", "materynski-platy", 2),
        ("https://brain.com.ua/ukr/category/Bloky_jhyvlennya-c1442-221/", "bzh", 2),
        ("https://brain.com.ua/ukr/category/Korpusy-c1441-271/", "korpusy", 2),
        ("https://brain.com.ua/ukr/category/Kulery_do_procesoriv_termopasta-c1108/", "kulery", 2),
        ("https://brain.com.ua/ukr/category/Televizory-c1098/", "tv"),           # 24/стор., 34 стор.
        ("https://brain.com.ua/ukr/category/Planshety-c1192/", "planshety", 3),   # 24/стор.
        ("https://brain.com.ua/ukr/category/Navushnyky_ta_garnitury-c1365-157/", "audio", 3),
        ("https://brain.com.ua/ukr/category/Rozumni_godynnyky_ta_braslety-c7852/", "smart-hodynnyky", 3),
        ("https://brain.com.ua/ukr/category/Holodilniki-c897/", "pobut-tehnika", 3),
        ("https://brain.com.ua/ukr/category/Kuhonni_vityazhki-c909/", "vytyazhky", 2),
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
        ("https://eldorado.ua/uk/keyboards/c1039113/", "klaviatury"),   # render
        ("https://eldorado.ua/uk/mouse/c1039112/", "myshi"),   # render
        ("https://eldorado.ua/uk/gpu/c1209287/", "videokarty"),   # slug «gpu», render
        ("https://eldorado.ua/uk/1216773/c1216773/", "ssd"),   # slug — числовий id, render
        ("https://eldorado.ua/uk/1209289/c1209289/", "procesory"),   # slug — числовий id, render
        ("https://eldorado.ua/uk/1209288/c1209288/", "ram"),   # slug — числовий id, render
        ("https://eldorado.ua/uk/1209286/c1209286/", "materynski-platy"),   # slug — числовий id, render
        ("https://eldorado.ua/uk/1209290/c1209290/", "bzh"),   # slug — числовий id, render
        ("https://eldorado.ua/uk/1209527/c1209527/", "korpusy"),   # slug — числовий id, render
        ("https://eldorado.ua/uk/1209578/c1209578/", "kulery"),   # slug — числовий id, render
        ("https://eldorado.ua/uk/led/c1038962/", "tv"),
        ("https://eldorado.ua/uk/tablet_pc/c1039006/", "planshety"),             # 40 карток
        ("https://eldorado.ua/uk/headphones/c1038998/", "audio"),                # 40 карток
        ("https://eldorado.ua/uk/smart_chasi/c1197093/", "smart-hodynnyky"),     # 13 карток
        ("https://eldorado.ua/uk/holodilniki/c1061560/", "pobut-tehnika"),       # 40 карток
        ("https://eldorado.ua/uk/kettles/c1039051/", "elektrochaynyky"),   # render
        ("https://eldorado.ua/uk/hair-dryers/c1039072/", "feny"),   # render
        ("https://eldorado.ua/uk/shavers/c1039071/", "brytvy"),   # render
        ("https://eldorado.ua/uk/mens_hair/c1059388/", "trymery"),   # render (машинки+тримери)
        ("https://eldorado.ua/uk/epilators/c1039070/", "epilyatory"),   # render
        ("https://eldorado.ua/uk/hai-traighteners_curling-irons_and_stylers/c1039073/", "ukladka-volossya"),   # render
        ("https://eldorado.ua/uk/1061587/c1061587/", "zubni-shchitky"),   # render
        ("https://eldorado.ua/uk/1284672/c1284672/", "shurupoverty"),   # render
        ("https://eldorado.ua/uk/1284694/c1284694/", "perforatory"),   # render
        ("https://eldorado.ua/uk/1284670/c1284670/", "bolharky"),   # render (шліфмашини/болгарки)
        ("https://eldorado.ua/uk/1284674/c1284674/", "lobzyky"),   # render
        ("https://eldorado.ua/uk/1284680/c1284680/", "pyly-dyskovi"),   # render
        ("https://eldorado.ua/uk/welding_machines/c1285423/", "zvaryuvalni"),   # render
        ("https://eldorado.ua/uk/generators/c1285119/", "generatory"),   # render
        ("https://eldorado.ua/uk/1284692/c1284692/", "myyky"),   # render
        ("https://eldorado.ua/uk/1067831/c1067831/", "videoreyestratory"),   # render
        ("https://eldorado.ua/uk/car_receivers/c1038991/", "avtomagnitoly"),   # render
        ("https://eldorado.ua/uk/kompressor_avtomobilnyj/c1285523/", "avtokompresory"),   # render
        ("https://eldorado.ua/uk/1061580/c1061580/", "avtoholodylnyky"),   # render (переносні)
        ("https://eldorado.ua/uk/node/c1039065/", "obigrivachi"),   # render (широка обігрівачі)
        ("https://eldorado.ua/uk/humidifiers/c1039069/", "zvolozhuvachi"),   # render
        ("https://eldorado.ua/uk/1061573/c1061573/", "ochyshchuvachi"),   # render
        ("https://eldorado.ua/uk/air_dryers/c1284961/", "osushuvachi"),   # render
        ("https://eldorado.ua/uk/fans/c1039067/", "ventylatory"),   # render
        ("https://eldorado.ua/uk/weather-stations/c1039015/", "meteostantsii"),   # render
        ("https://eldorado.ua/uk/1179528/c1179528/", "ekshn-kamery"),   # render
        ("https://eldorado.ua/uk/node/c1225224/", "drony"),   # render
        ("https://eldorado.ua/uk/1039021/c1039021/", "karty-pamyati"),   # render
        ("https://eldorado.ua/uk/1039117/c1039117/", "usb-fleshky"),   # render
        ("https://eldorado.ua/uk/1039116/c1039116/", "zovnishni-hdd"),   # render
        ("https://eldorado.ua/uk/toasters/c1042091/", "tostery"),   # render (+ сендвічниці/вафельниці)
        ("https://eldorado.ua/uk/irons/c1039036/", "prasky"),   # render
        ("https://eldorado.ua/uk/meat-grinder/c1039054/", "myasorubky"),   # render
        ("https://eldorado.ua/uk/juicers/c1039080/", "sokovyzhymalky"),   # render
        ("https://eldorado.ua/uk/mixers/c1039053/", "miksery"),   # render
        ("https://eldorado.ua/uk/hoods/c1039066/", "vytyazhky"),                 # 40 витяжок, MPN 19
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
        ("https://epicentrk.ua/ua/shop/klaviatury/", "klaviatury", 2),
        ("https://epicentrk.ua/ua/shop/kompyuternye-myshki/", "myshi", 2),
        ("https://epicentrk.ua/ua/shop/veb-kamery/", "veb-kamery", 2),
        ("https://epicentrk.ua/ua/shop/istochniki-bespereboynogo-pitaniya/", "dbzh", 2),
        ("https://epicentrk.ua/ua/shop/kovriki-dlya-kompyuternykh-myshek/", "kylymky", 2),
        ("https://epicentrk.ua/ua/shop/videokarty/", "videokarty", 2),   # MPN 51/60 (85%)
        ("https://epicentrk.ua/ua/shop/ssd-diski/", "ssd", 2),   # MPN 58/60 (97%)
        ("https://epicentrk.ua/ua/shop/protsessory/", "procesory", 2),   # MPN 23/60
        ("https://epicentrk.ua/ua/shop/operativnaya-pamyat/", "ram", 2),   # MPN 50/60
        ("https://epicentrk.ua/ua/shop/materinskie-platy/", "materynski-platy", 2),   # MPN 25/60
        ("https://epicentrk.ua/ua/shop/bloki-pitaniya/", "bzh", 2),   # MPN 34/60
        ("https://epicentrk.ua/ua/shop/korpusa-dlya-pk/", "korpusy", 2),   # MPN 27/60 (слабкий)
        ("https://epicentrk.ua/ua/shop/kulery/", "kulery", 2),   # домішка термопасти, переважно кулери
        ("https://epicentrk.ua/ua/shop/televizory/", "tv"),
        ("https://epicentrk.ua/ua/shop/planshety/", "planshety"),
        ("https://epicentrk.ua/ua/shop/naushniki/", "audio"),
        ("https://epicentrk.ua/ua/shop/smart-chasy-i-fitnes-braslety/", "smart-hodynnyky"),
        ("https://epicentrk.ua/ua/shop/kholodilniki/", "pobut-tehnika"),
        ("https://epicentrk.ua/ua/shop/stiralnye-mashiny/", "pobut-tehnika", 1),
        ("https://epicentrk.ua/ua/shop/posudomoechnye-mashiny/", "pobut-tehnika", 1),
        ("https://epicentrk.ua/ua/shop/sushilnye-mashiny/", "pobut-tehnika", 1),
        ("https://epicentrk.ua/ua/shop/vytyazhki/", "vytyazhky", 2),
        ("https://epicentrk.ua/ua/shop/monitory/", "monitory"),
        ("https://epicentrk.ua/ua/shop/konditsionery/", "kondycionery"),
        ("https://epicentrk.ua/ua/shop/marshrutizatory-i-wi-fi-routery/", "routery"),
        ("https://epicentrk.ua/ua/shop/pylesosy/", "pylososy"),
        ("https://epicentrk.ua/ua/shop/roboty-pylesosy/", "pylososy", 1),
        ("https://epicentrk.ua/ua/shop/mikrovolnovye-pechi/", "mikrohvylovky"),
        ("https://epicentrk.ua/ua/shop/elektrochayniki/", "elektrochaynyky", 2),   # MPN 31/60
        ("https://epicentrk.ua/ua/shop/feny/", "feny", 2),   # MPN 42/60
        ("https://epicentrk.ua/ua/shop/elektrobritvy-dlya-muzhchin/", "brytvy", 2),
        ("https://epicentrk.ua/ua/shop/trimmery-dlya-strizhki/", "trymery", 2),
        ("https://epicentrk.ua/ua/shop/epilyatory-i-zhenskie-elektrobritvy/", "epilyatory", 2),
        ("https://epicentrk.ua/ua/shop/pribory-dlya-ukladki-volos/", "ukladka-volossya", 2),
        ("https://epicentrk.ua/ua/shop/elektricheskie-zubnye-shchetki/", "zubni-shchitky", 2),
        ("https://epicentrk.ua/ua/shop/shurupoverty/", "shurupoverty", 2),
        ("https://epicentrk.ua/ua/shop/perforatory/", "perforatory", 2),
        ("https://epicentrk.ua/ua/shop/bolgarki/", "bolharky", 2),
        ("https://epicentrk.ua/ua/shop/elektrolobziki/", "lobzyky", 2),
        ("https://epicentrk.ua/ua/shop/diskovye-pily/", "pyly-dyskovi", 2),
        ("https://epicentrk.ua/ua/shop/invertory-svarochnye/", "zvaryuvalni", 2),
        ("https://epicentrk.ua/ua/shop/gaykoverty/", "haikoverty", 2),
        ("https://epicentrk.ua/ua/shop/shlifovalnye-i-polirovalnye-mashiny/", "shlifmashyny", 2),
        ("https://epicentrk.ua/ua/shop/kompressory/", "kompresory", 2),
        ("https://epicentrk.ua/ua/shop/generatory/", "generatory", 2),
        ("https://epicentrk.ua/ua/shop/moyki-vysokogo-davleniya/", "myyky", 2),
        ("https://epicentrk.ua/ua/shop/niveliry-i-urovni-lazernye/", "vymiryuvalni", 2),
        ("https://epicentrk.ua/ua/shop/dalnomery/", "vymiryuvalni", 2),
        ("https://epicentrk.ua/ua/shop/nabory-instrumentov/", "nabory-instrumentu", 2),
        ("https://epicentrk.ua/ua/shop/motokosy-i-trimmery-sadovye/", "motokosy", 2),
        ("https://epicentrk.ua/ua/shop/gazonokosilki/", "gazonokosarky", 2),
        ("https://epicentrk.ua/ua/shop/benzopily-i-elektropily/", "pyly-lancjugovi", 2),
        ("https://epicentrk.ua/ua/shop/pylesosy-sadovye/", "povitroduvky", 2),
        ("https://epicentrk.ua/ua/shop/kultivatory-i-motobloki/", "kultyvatory", 2),
        ("https://epicentrk.ua/ua/shop/kustorezy/", "kushchorizy", 2),
        ("https://epicentrk.ua/ua/shop/opryskivateli/", "obpryskuvachi", 2),
        ("https://epicentrk.ua/ua/shop/nasosy/", "nasosy", 2),
        ("https://epicentrk.ua/ua/shop/snegouborochnaya-tekhnika-i-inventar/", "snihoprybyrachi", 2),
        ("https://epicentrk.ua/ua/shop/videoregistratory/", "videoreyestratory", 2),
        ("https://epicentrk.ua/ua/shop/avtomagnitoly/", "avtomagnitoly", 2),
        ("https://epicentrk.ua/ua/shop/kompressory-avtomobilnye/", "avtokompresory", 2),
        ("https://epicentrk.ua/ua/shop/avtopylesosy/", "avtopylososy", 2),
        ("https://epicentrk.ua/ua/shop/avtokholodilniki/", "avtoholodylnyky", 2),
        ("https://epicentrk.ua/ua/shop/obogrevateli/", "obigrivachi", 2),
        ("https://epicentrk.ua/ua/shop/uvlazhniteli-vozdukha/", "zvolozhuvachi", 2),
        ("https://epicentrk.ua/ua/shop/ochistiteli-i-moyki-vozdukha/", "ochyshchuvachi", 2),
        ("https://epicentrk.ua/ua/shop/osushiteli-vozdukha/", "osushuvachi", 2),
        ("https://epicentrk.ua/ua/shop/ventilyatory/", "ventylatory", 2),
        ("https://epicentrk.ua/ua/shop/meteostantsii-i-termometry-bytovye/", "meteostantsii", 2),
        ("https://epicentrk.ua/ua/shop/begovye-dorozhki/", "begovi-dorizhky", 2),
        ("https://epicentrk.ua/ua/shop/velotrenazhery/", "velotrenazhery", 2),
        ("https://epicentrk.ua/ua/shop/elektrosamokaty/", "elektrosamokaty", 2),
        ("https://epicentrk.ua/ua/shop/kolyaski/", "kolyasky", 2),
        ("https://epicentrk.ua/ua/shop/avtokresla/", "avtokrisla", 2),
        ("https://epicentrk.ua/ua/shop/molokootsosy/", "molokovidsmoktuvachi", 2),
        ("https://epicentrk.ua/ua/shop/podogrevateli-i-sterilizatory/", "sterylizatory", 2),
        ("https://epicentrk.ua/ua/shop/videokamery-i-ekshn-kamery/", "ekshn-kamery", 2),
        ("https://epicentrk.ua/ua/shop/kvadrokoptery/", "drony", 2),
        ("https://epicentrk.ua/ua/shop/karty-pamyati/", "karty-pamyati", 2),
        ("https://epicentrk.ua/ua/shop/flesh-pamyat-usb/", "usb-fleshky", 2),
        ("https://epicentrk.ua/ua/shop/zhestkie-diski/", "zovnishni-hdd", 2),
        ("https://epicentrk.ua/ua/shop/tostery/", "tostery", 2),   # MPN 41/60
        ("https://epicentrk.ua/ua/shop/utyugi/", "prasky", 2),
        ("https://epicentrk.ua/ua/shop/myasorubki/", "myasorubky", 2),
        ("https://epicentrk.ua/ua/shop/sokovyzhimalki/", "sokovyzhymalky", 2),
        ("https://epicentrk.ua/ua/shop/miksery/", "miksery", 2),
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
        ("https://vencon.ua/ua/catalog/kuhonnye-vytyazhki", "vytyazhky", 2),   # MPN 1/47 — переважно перегляд
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
        ("https://telemart.ua/ua/keyboards/", "klaviatury", 2),   # MPN 26/48
        ("https://telemart.ua/ua/mouse/", "myshi", 2),   # MPN 27/48
        ("https://telemart.ua/ua/web-cam/", "veb-kamery", 2),   # MPN 21/48
        ("https://telemart.ua/ua/ups/", "dbzh", 2),   # MPN 33/48
        ("https://telemart.ua/ua/kovriki/", "kylymky", 2),   # MPN 24/48
        ("https://telemart.ua/ua/videocard/", "videokarty", 2),   # 48/стор., MPN 36
        ("https://telemart.ua/ua/ssd/", "ssd", 2),   # 48/стор., MPN 45 (94%)
        ("https://telemart.ua/ua/processor/", "procesory", 2),   # 48/стор., MPN 27
        ("https://telemart.ua/ua/ram/", "ram", 2),   # 48/стор., MPN 48 (100%)
        ("https://telemart.ua/ua/motherboard/", "materynski-platy", 2),   # MPN 6/48 (слабкий)
        ("https://telemart.ua/ua/powersuply/", "bzh", 2),   # MPN 40/48 (83%)
        ("https://telemart.ua/ua/case/", "korpusy", 2),   # MPN 25/48 (слабкий)
        ("https://telemart.ua/ua/sistemy-oxlazhdenija/", "kulery", 2),   # MPN 24/48
        ("https://telemart.ua/monitors/", "monitory"),            # 48/стор., 75%
        ("https://telemart.ua/earphones/", "audio"),              # 48/стор., 58%
        ("https://telemart.ua/wi-fi-routers/", "routery"),        # 48/стор., 39%
        ("https://telemart.ua/consoles/", "konsoli", 2),          # 17 товарів, 64%
        ("https://telemart.ua/iphone/", "smartfony", 2),          # 22 товари, 100%
    )},
    # Подорожник (розвідка 2026-07-22) — ПЕРША аптека, тринадцяте джерело. Аптечний
    # домен вирішив T17: на відміну від електроніки, тут є GTIN (штрихкод) на кожному
    # товарі, тож матчинг надійний. Але одна аптека груп «Де купити» не дає — цінність
    # зараз у GTIN-каталозі, порівняння зійдуться з другою аптекою.
    #
    # Екстракція — з ВБУДОВАНОГО JSON-стану сторінки (adapters/podorozhnyk.py), не CSS і
    # не рендер: plain-GET віддає повний стан із name/price/gtins/status/restrictions.
    #
    # ЛИШЕ НЕРЕЦЕПТУРНІ розділи (рішення власника про юр-безпечну форму): звичайні
    # споживчі товари, юридично як електроніка. Рецептурне адаптер відкидає окремо
    # (restrictions.prescription) — навіть якщо трапиться в цих розділах (замір знайшов
    # 1 у косметиці).
    #
    # Пагінація `/<cat>/page-N/` перевірена фактом: стор.2 і 3 віддають інші товари,
    # перетин зі стор.1 нульовий. Глибина 3 — каталог закладається, поглибимо з 2-ю аптекою.
    "Podorozhnyk": {"adapter": PodorozhnykAdapter(), "page_tpl": "{base}page-{n}/",
                    "pages": 3, "urls": (
        ("https://podorozhnyk.ua/vitamini-ta-dobavki/", "vitaminy"),          # ~5829, 100% GTIN
        ("https://podorozhnyk.ua/tovari-dlya-ditej/", "dytyache"),            # ~5966, 93%
        ("https://podorozhnyk.ua/osobista-gigiyena/", "gigiyena"),            # ~5694, 98%
        ("https://podorozhnyk.ua/krasa-ta-doglyad/", "kosmetyka"),            # ~3206, 98%
        ("https://podorozhnyk.ua/tovari-medichnogo-priznachennya/", "medtovary"),  # ~5132, 100%
    )},
    # add.ua (Аптека Доброго Дня) — ДРУГА аптека, ДВОФАЗНА. Штрихкод (ключ GTIN) тут лише
    # на сторінці товару, не в лістингу, тож збираємо як хаб: лістинг discover-ить URL
    # товарів → кожен телефон дотягує (рендер) → extract парсить штрихкод. Cloudflare
    # → mode=render (телефон проходить у WebView як людина; перевірено на живому).
    #
    # ПРИЦІЛ — БРЕНД, не розділ. Урок 2026-07-22: дефолтний лістинг `/ua/kosmetika/`
    # відсортований за брендом і весь Babaria — а в Babaria НЕМАЄ штрихкодів (перевірено
    # на першому ж зібраному товарі) і немає перетину з Подорожником. Штрихкоди й перетин
    # мають саме преміум-дерма бренди. La Roche-Posay: 60 товарів, усі зі штрихкодом
    # (напр. 3337875944960), усі є і в Подорожника. Тому цілимо в БРЕНДОВУ адресу.
    #
    # ВІДКРИТТЯ — через SITEMAP (T20, 2026-07-22), замість render-лістинга бренду:
    # sitemap-product_ua.xml — статичний XML (5.1 МБ, 41 387 товарів), який add.ua сама
    # публікує в robots.txt для краулерів. Телефон тягне його plain GET-ом раз на 2 доби
    # (lease перевизначає mode на fetch — WebView для XML і не потрібен, і шкідливий),
    # сервер фільтрує `la-roche` → 186 карток La Roche (проти ~60 на брендлистингу — 3×
    # ширше, і БЕЗ рендера на фазі відкриття).
    #
    # Економіка: 186 карток × render не влазять у щоденний повтор (~96 задач/добу/крамницю),
    # тому sitemap-нащадки йдуть із repeat 2880 (2 доби): 186/2=93/добу ≈ здатність.
    # `discover_re` лишається: якщо колись знову інджестимо лістинг — він і досі працює.
    # ⚠ include_re МУСИТЬ бути специфічним: замір із `rosh` ловив «поро́шки» (porosh-ok).
    "AddUa": {"adapter": AdduaAdapter(), "mode": "render", "category": "kosmetyka",
              "discover_re": r"/$",
              "sitemap": {"url": "https://www.add.ua/sitemap-product_ua.xml",
                          "include_re": r"la-roche", "max": 200}},
    # Аптека 911 — третя аптека, mode=fetch (БЕЗ рендера, на відміну від add.ua: сайт
    # віддає повний SSR-HTML plain-GET'ом). Двофазна, як add.ua: штрихкод лише на картці.
    # `discover_re` = `^(?!.*-p\d)`: товари — `…-p<id>`, лістинги (бренд/категорія/`/page=N`)
    # цього не мають → лістинг discover-ить, товар extract-иться. Помилка розрізнення
    # безпечна: extract лістинга → [], discover картки → [] (обидва порожні, не падають).
    # Seed — бренд La Roche (56 товарів): заміряно 2026-07-22, ~47% штрихкодів уже в каталозі
    # (Podorozhnyk+AddUa) → крос-аптечні трійки. Vichy/інші — 0 перетину, тому не сіємо.
    # max_pages=80: усі 56 товарів бренду на 1 сторінці (пагінація не потрібна), із запасом.
    "Apteka911": {"adapter": Apteka911Adapter(), "mode": "fetch", "category": "kosmetyka",
                  "discover_re": r"^(?!.*-p\d)", "max_pages": 80, "urls": (
        ("https://apteka911.ua/ua/shop/brands/la-roche", "kosmetyka"),
    )},
    "KTC": {"adapter": KtcAdapter(), "page_tpl": "{base}?page={n}", "pages": 5, "urls": (
        ("https://ktc.ua/smartphone/", "smartfony"),
        ("https://ktc.ua/notebook/", "noutbuky"),                                # 48 товарів
        ("https://ktc.ua/keyboard/", "klaviatury", 2),                           # MPN 20/48
        ("https://ktc.ua/mouse/", "myshi", 2),                                   # MPN 14/48
        ("https://ktc.ua/ups/", "dbzh", 2),
        ("https://ktc.ua/videocard/", "videokarty", 2),                          # 48/стор., MPN 38
        ("https://ktc.ua/ssd/", "ssd", 2),                                       # 48/стор., MPN 43 (90%)
        ("https://ktc.ua/cpu/", "procesory", 2),                                 # 48/стор., MPN 37 (77%)
        ("https://ktc.ua/ram/", "ram", 2),                                       # 48/стор., MPN 48 (100%)
        ("https://ktc.ua/motherboard/", "materynski-platy", 2),                  # MPN 9/48 (слабкий)
        ("https://ktc.ua/power_supply/", "bzh", 2),                              # MPN 41/48 (85%)
        ("https://ktc.ua/case/", "korpusy", 2),                                  # MPN 29/48 (слабкий)
        ("https://ktc.ua/cpu_cooling/", "kulery", 2),                            # MPN 25/48
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


_SM_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)


def sitemap_locs(xml: str, include_re: str | None, hosts: tuple[str, ...],
                 cap: int) -> list[str]:
    """URL зі sitemap-urlset → відфільтровані товарні URL (T20, sitemap-відкриття).

    Правово найчистіший канал відкриття: sitemap крамниця публікує в robots.txt САМЕ
    для авто-краулерів (вет 2026-07-22). Парсимо регексом, не XML-парсером: <loc> —
    єдине, що нам треба, а регекс байдужий до неймспейсів/битих атрибутів.

    `include_re` — звуження до полиці, що перетинається з каталогом (add.ua: `la-roche`).
    ⚠ Патерн МУСИТЬ бути специфічним: перший замір із `rosh` зловив 1003 «товари», з
    яких 817 — «поро́шки» (porosh-ok). Хости — та сама політика, що й у validate_item:
    чужий хост у sitemap (навмисний чи ні) не має збити збір на сторонній сайт."""
    inc = re.compile(include_re) if include_re else None
    out: list[str] = []
    seen: set[str] = set()
    for loc in _SM_LOC.findall(xml):
        u = loc.strip()
        if inc and not inc.search(u):
            continue
        if not _host_ok(u, hosts):
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= cap:
            break
    return out


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

    # gtins — штрихкоди (аптеки/медтовари). Довіряй, але ПЕРЕВІРЯЙ: сервер не бере код на
    # слово, а проганяє через normalize_gtin (контрольна цифра + відсів обмеженого обігу),
    # інакше зіпсований чи внутрішньомагазинний код створив би хибну групу. Лишаємо ЛИШЕ
    # валідні; стелю к-сті тримаємо проти роздування payload.
    # tuple ТЕЖ: HTML-шлях подає елемент як dataclasses.asdict(RawItem), де поле-tuple
    # лишається tuple — не list. Перевіряти лише list означало губити ВСІ штрихкоди на
    # реальному шляху збору (adapter→asdict→validate_item); JSON-шлях це маскував.
    raw_gtins = raw.get("gtins")
    gtins: tuple[str, ...] = ()
    if isinstance(raw_gtins, (list, tuple)):
        gtins = tuple(str(g) for g in raw_gtins[:20]
                      if isinstance(g, (str, int)) and normalize_gtin(g))

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
        gtins=gtins,
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
        if cfg.get("sitemap"):                          # sitemap — завжди plain GET (XML)
            out.append({"source": name, "url": cfg["sitemap"]["url"],
                        "kind": "sitemap", "mode": "fetch"})
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

    # фаза 1: лістинг/хаб → URL для збору (discover робить СЕРВЕР, не застосунок).
    # Два способи розпізнати сторінку-джерело посилань:
    #  · `hub` — ЄДИНИЙ URL хаба акцій (Allo);
    #  · `discover_re` — регекс на лістинг-URL (add.ua): КОЖЕН лістинг категорії
    #    discover-ить свої товари, бо штрихкод там лише на сторінці товару. Регекс
    #    відрізняє лістинг (`/ua/<cat>/`) від товару (`/ua/<slug>.html`).
    # фаза 0: sitemap-відкриття (T20) — статичний XML замість render-лістинга: телефон
    # тягне його plain GET-ом (lease перевизначає mode на fetch), сервер фільтрує до
    # полиці include_re і кладе картки в чергу. Маршрут — ПЕРЕД discover_re: sitemap-URL
    # не мусить підходити під регекс лістингів.
    sm = cfg.get("sitemap")
    if sm and canon_ref(url) == canon_ref(sm["url"]):
        locs = sitemap_locs(html, sm.get("include_re"), hosts, sm.get("max", 500))
        return {"source": source, "kind": "sitemap", "discovered": locs,
                "accepted": 0, "rejected": 0, "status": "ok"}

    is_hub = cfg.get("hub") and canon_ref(url) == canon_ref(cfg["hub"])
    dre = cfg.get("discover_re")
    if is_hub or (dre and re.search(dre, url)):
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
