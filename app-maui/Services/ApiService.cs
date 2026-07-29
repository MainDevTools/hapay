using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Hapay.Models;

namespace Hapay.Services;

/// Кинуто на 401 від захищеного ендпоінта (токен протермінований/недійсний).
public class UnauthorizedException : Exception { }

/// Клієнт read-API «Хапай». Один base-URL — легко змінити хост, не чіпаючи екрани.
public class ApiService
{
    // Прод. Для локального бекенду з емулятора Android: "http://10.0.2.2:8080".
    private const string Base = "https://hapay.today";

    private readonly HttpClient _http;
    private static readonly JsonSerializerOptions _json = new() { PropertyNameCaseInsensitive = true };

    public ApiService()
    {
        // 60 с, а не 20: /api/ingest/html вивантажує сирий HTML сторінки, і після того,
        // як рендерер почав прокручувати сторінки до кінця (2026-07-20), тіло виросло
        // до кількох МБ — на повільному Wi-Fi 20 с не вистачало б. Читальні запити
        // однаково відповідають за частки секунди, тож більший таймаут їм не шкодить.
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
    }

    /// JWT для захищених ендпоінтів (/api/me*). null → анонім (публічні ендпоінти працюють).
    public void SetToken(string? token) =>
        _http.DefaultRequestHeaders.Authorization =
            string.IsNullOrEmpty(token) ? null : new AuthenticationHeaderValue("Bearer", token);

    public async Task<List<Discount>> DiscountsAsync(
        string? category = null, string? q = null, string sort = "discount", int page = 0,
        int? priceMinKop = null, int? priceMaxKop = null, CancellationToken ct = default)
    {
        var url = $"{Base}/api/discounts?sort={Uri.EscapeDataString(sort)}&page={page}";
        if (!string.IsNullOrWhiteSpace(category)) url += $"&category={Uri.EscapeDataString(category)}";
        if (!string.IsNullOrWhiteSpace(q)) url += $"&q={Uri.EscapeDataString(q.Trim())}";
        if (priceMinKop is int lo) url += $"&price_min={lo}";        // копійки (інв. A)
        if (priceMaxKop is int hi) url += $"&price_max={hi}";
        return await _http.GetFromJsonAsync<List<Discount>>(url, _json, ct) ?? new();
    }

    // ── доказовість і моделі (S34) ──────────────────────────────────────────────
    // Три публічні ендпоінти, які доти читав лише сайт. Без них найсильніше
    // твердження продукту («не переписуємо історію, ось доказ») вимагало вийти
    // з застосунку в браузер.

    /// Ринковий зріз: скільки заявлених знижок ми змогли перевірити.
    public async Task<MarketIndex?> MarketAsync(int days = 30, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<MarketIndex>($"{Base}/api/market?days={days}", _json, ct);

    /// Печатки спостережень: корінь Меркла кожної доби + ланцюжок.
    public async Task<VerifyInfo?> VerifyChainAsync(CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<VerifyInfo>($"{Base}/api/verify", _json, ct);

    /// Канонічна модель: усі сторінки крамниць під одним артикулом.
    public async Task<ModelCard?> ModelAsync(int productId, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<ModelCard>($"{Base}/api/model/{productId}", _json, ct);

    /// УСІ товари (не лише знижки) — повний прайс-агрегатор. onlyDiscounts=true → лише знижкові.
    public async Task<List<Discount>> ProductsAsync(
        string? category = null, string? q = null, string sort = "discount", int page = 0,
        int? priceMinKop = null, int? priceMaxKop = null, bool onlyDiscounts = false,
        string? badge = null, CancellationToken ct = default)
    {
        var url = $"{Base}/api/products?sort={Uri.EscapeDataString(sort)}&page={page}";
        if (!string.IsNullOrWhiteSpace(category)) url += $"&category={Uri.EscapeDataString(category)}";
        if (!string.IsNullOrWhiteSpace(q)) url += $"&q={Uri.EscapeDataString(q.Trim())}";
        if (priceMinKop is int lo) url += $"&price_min={lo}";
        if (priceMaxKop is int hi) url += $"&price_max={hi}";
        if (onlyDiscounts) url += "&only_discounts=1";
        if (!string.IsNullOrEmpty(badge)) url += $"&badge={Uri.EscapeDataString(badge)}";
        return await _http.GetFromJsonAsync<List<Discount>>(url, _json, ct) ?? new();
    }

    /// Порівняння 2-4 товарів side-by-side (S14): базові факти + таблиця характеристик.
    public async Task<CompareResult?> CompareAsync(IEnumerable<int> ids, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<CompareResult>(
            $"{Base}/api/compare?ids={string.Join(",", ids)}", _json, ct);

    /// Хвилини від останнього успішного збору (чесна свіжість у шапці стрічки).
    public async Task<int?> FreshnessAsync(CancellationToken ct = default)
    {
        var doc = await _http.GetFromJsonAsync<Dictionary<string, int?>>(
            $"{Base}/api/freshness", _json, ct);
        return doc is not null && doc.TryGetValue("minutes", out var m) ? m : null;
    }

    // Кеш категорій (сінглтон-сервіс): каталог, стрічка і «Каталог товарів» тягнули
    // той самий список по колу — кожна навігація коштувала зайвого раунд-тріпа
    // (скарга на затримки 2026-07-24). Каталог міняється повільно; pull-to-refresh
    // проходить повз кеш (fresh: true).
    private List<Category>? _catsCache;
    private DateTime _catsCachedAt;
    private static readonly TimeSpan _catsTtl = TimeSpan.FromMinutes(3);

    public async Task<List<Category>> CategoriesAsync(bool fresh = false, CancellationToken ct = default)
    {
        // повертаємо КОПІЮ: викликачі роблять AddRange/foreach, і хоча зараз ніхто
        // список не мутує, віддати сам кеш-екземпляр — крихко (bug-review 2026-07-25)
        if (!fresh && _catsCache is not null && DateTime.UtcNow - _catsCachedAt < _catsTtl)
            return new List<Category>(_catsCache);
        var cats = await _http.GetFromJsonAsync<List<Category>>($"{Base}/api/categories", _json, ct) ?? new();
        if (cats.Count > 0) { _catsCache = cats; _catsCachedAt = DateTime.UtcNow; }
        return new List<Category>(cats);
    }

    public async Task<List<HistoryPoint>> HistoryAsync(int storeProductId, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<HistoryPoint>>(
            $"{Base}/api/product/{storeProductId}/history", _json, ct) ?? new();

    /// «Де купити» (T15): той самий товар (mpn) у всіх крамницях, від найдешевшої.
    public async Task<List<Offer>> OffersAsync(int storeProductId, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<Offer>>(
            $"{Base}/api/product/{storeProductId}/offers", _json, ct) ?? new();

    /// «Наш вибір» (S9): найвигідніший спосіб купити — прозорий скор зі складниками.
    /// null = нема ≥2 крамниць у наявності (блок не показується).
    public async Task<ChoiceResult?> ChoiceAsync(int storeProductId, CancellationToken ct = default) =>
        (await _http.GetFromJsonAsync<ChoiceEnvelope>(
            $"{Base}/api/product/{storeProductId}/choice", _json, ct))?.Choice;

    /// Крамниці, за якими стежимо (S28). Ті самі числа, що на hapay.today/stores.
    public async Task<List<Store>> StoresAsync(CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<Store>>($"{Base}/api/stores", _json, ct) ?? new();

    public async Task<Store?> StoreAsync(string slug, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<Store>(
            $"{Base}/api/store/{Uri.EscapeDataString(slug)}", _json, ct);

    /// ВИМІРЯНІ зниження цін (S28) — не плутати з `DropsAsync`, який про watchlist.
    /// `order`: fresh (щойно виміряні) або deep (найбільші).
    public async Task<DropsResult?> MeasuredDropsAsync(int days = 1, string order = "fresh",
                                                       CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<DropsResult>(
            $"{Base}/api/drops?days={days}&order={order}", _json, ct);

    /// Самостійне видалення акаунта (вимога Google Play: шлях у застосунку + веб-адреса).
    /// Незворотно; сервер віддає 400 з поясненням, якщо це останній активний адмін.
    public async Task DeleteAccountAsync(CancellationToken ct = default)
    {
        var resp = await _http.DeleteAsync($"{Base}/api/me", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Один товар за id. Потрібен там, де товару в руках НЕМАЄ — глибоке посилання
    /// hapay.today/product/{id} дає лише число, а екран деталей чекає повний Discount.
    public async Task<Discount?> CardAsync(int storeProductId, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<Discount>(
            $"{Base}/api/product/{storeProductId}/card", _json, ct);

    /// Характеристики (S12): пари назва-значення з картки крамниці (одна на групу).
    /// null = ще не зібрано (бекфіл у вільних слотах) — секція не показується.
    public async Task<SpecsResult?> SpecsAsync(int storeProductId, CancellationToken ct = default) =>
        (await _http.GetFromJsonAsync<SpecsEnvelope>(
            $"{Base}/api/product/{storeProductId}/specs", _json, ct))?.Specs;

    // ── auth (S11) ────────────────────────────────────────────────────────────────
    /// Реєстрація НЕ повертає сесію: сервер відповідає однаково на нову й на вже
    /// зареєстровану адресу, тож токен видав би саме те, що ми ховаємо. Людина далі
    /// входить звичайним паролем.
    public async Task RegisterAsync(string email, string password, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/auth/register",
                                               new { email, password }, ct);
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    public Task<AuthResult> LoginAsync(string email, string password, CancellationToken ct = default) =>
        PostAuthAsync("/api/auth/login", email, password, ct);

    private async Task<AuthResult> PostAuthAsync(string path, string email, string password, CancellationToken ct)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}{path}", new { email, password }, ct);
        if (!resp.IsSuccessStatusCode)
        {
            // сервер віддає {"detail": "..."} — показуємо людині зрозуміле
            var detail = await SafeDetail(resp, ct);
            throw new ApiException(detail);
        }
        return (await resp.Content.ReadFromJsonAsync<AuthResult>(_json, ct))!;
    }

    public async Task<UserProfile> MeAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/me", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<UserProfile>(_json, ct))!;
    }

    // ── S13: підтвердження email + скидання пароля ────────────────────────────────
    /// Підтвердити email кодом із листа (потрібен токен акаунта). True — підтверджено.
    public async Task VerifyEmailAsync(string code, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/auth/verify", new { code }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Надіслати новий код підтвердження на email акаунта.
    public async Task ResendVerifyAsync(CancellationToken ct = default)
    {
        var resp = await _http.PostAsync($"{Base}/api/auth/verify/resend", null, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// «Забув пароль»: запросити код на email. Сервер ЗАВЖДИ відповідає 200 (не
    /// розкриває, чи email зареєстрований) — тож тут не розрізняємо існування.
    public async Task RequestResetAsync(string email, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/auth/reset/request", new { email }, ct);
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Змінити пароль за кодом із листа.
    public async Task ConfirmResetAsync(string email, string code, string newPassword,
                                        CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/auth/reset/confirm",
            new { email, code, new_password = newPassword }, ct);
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    // ── «Стежити за ціною» ────────────────────────────────────────────────────────
    /// Додати товар у відстеження. Ціну на момент додавання фіксує СЕРВЕР — тут її
    /// свідомо не передаємо (клієнт не має диктувати, від чого рахувати економію).
    /// `targetKop` (S29): «сповісти, коли ціна впаде до X». null = будь-яке зниження,
    /// тобто стара поведінка — нікого не змушуємо називати число.
    public async Task WatchAsync(int storeProductId, int? targetKop = null,
                                 CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/me/watchlist",
            new { kind = "store_product", ref_id = storeProductId, target_kop = targetKop }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Найнижча ціна за час НАШИХ спостережень (S29). Разом із вікном: клієнт
    /// зобовʼязаний показати `Days`/`Measurements`, інакше твердження не перевірити.
    public async Task<PriceLow?> LowAsync(int storeProductId, CancellationToken ct = default)
    {
        try
        {
            return await _http.GetFromJsonAsync<PriceLow>(
                $"{Base}/api/product/{storeProductId}/low", _json, ct);
        }
        catch (HttpRequestException) { return null; }   // 404 = історії ще немає
    }

    /// Стежити за КАТЕГОРІЄЮ (kind=category, ключ — slug у query_text).
    public async Task WatchCategoryAsync(string slug, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/me/watchlist",
            new { kind = "category", query_text = slug }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Нові знижки у відстежуваних категоріях (згруповано по категорії).
    public async Task<List<CategoryNews>> CategoryNewsAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/me/watchlist/category-news", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<List<CategoryNews>>(_json, ct) ?? new();
    }

    public async Task AckCategoryNewsAsync(IEnumerable<int> watchlistIds, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/me/watchlist/category-news/ack",
            new { watchlist_ids = watchlistIds.ToArray() }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    public async Task<List<WatchItem>> WatchlistAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/me/watchlist", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<List<WatchItem>>(_json, ct) ?? new();
    }

    public async Task UnwatchAsync(int watchlistId, CancellationToken ct = default)
    {
        var resp = await _http.DeleteAsync($"{Base}/api/me/watchlist/{watchlistId}", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Товари з відстеження, що подешевшали від часу останнього сповіщення.
    /// Опитується у фоні; сповіщення показуємо ЛОКАЛЬНО, без сторонніх push-сервісів (§7.7).
    public async Task<List<PriceDrop>> DropsAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/me/watchlist/drops", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<List<PriceDrop>>(_json, ct) ?? new();
    }

    /// Підтвердити показ — інакше про те саме зниження сповіщатимемо щогодини.
    public async Task AckDropsAsync(IEnumerable<int> watchlistIds, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/me/watchlist/drops/ack",
            new { watchlist_ids = watchlistIds.ToArray() }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    // ── збір (S11 етап 3): застосунок = «тупий фетчер», парсить сервер ────────────────
    /// Сервер каже, ЩО тягнути (гейт ролі collector). 401 → нема прав/токен застарів.
    /// Стан збору (гейт колектора). Не кидає на 401 — профіль просто не покаже рядок.
    public async Task<CollectHealth?> GetCollectHealthAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/collect/health", ct);
        if (!resp.IsSuccessStatusCode) return null;
        return await resp.Content.ReadFromJsonAsync<CollectHealth>(_json, ct);
    }

    public async Task<CollectPlan> GetCollectPlanAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/collect/plan", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<CollectPlan>(_json, ct))!;
    }

    /// Пересилаємо СИРИЙ HTML крамниці — сервер парсить. Для hub повертає discovered-лендинги.
    /// taskId (черга T16): сервер закриє задачу сам при успішному інджесті.
    public async Task<IngestHtmlResult> IngestHtmlAsync(string source, string url, string html,
                                                        int? taskId = null, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/ingest/html",
                                               new { source, url, html, task_id = taskId }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
        return (await resp.Content.ReadFromJsonAsync<IngestHtmlResult>(_json, ct))!;
    }

    /// Черга-оренда (T16): забрати ≤limit дозрілих задач (по 1 на крамницю). 401 → нема прав.
    public async Task<List<LeaseTask>> LeaseAsync(int limit = 3, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/collect/lease", new { limit }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<LeaseResponse>(_json, ct))!.Tasks;
    }

    /// Не стягнулось (403/капча/таймаут) → сервер зробить бекоф цій задачі.
    public async Task CollectFailAsync(int taskId, string note, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/collect/fail",
                                               new { task_id = taskId, note }, ct);
        resp.EnsureSuccessStatusCode();
    }

    // ── адмін-панель (S15/S16): гейт на сервері, клієнт лише ховає вхід ──────────────
    public async Task<AdminUsersPage> AdminUsersAsync(string? q = null, string? role = null,
                                                      bool? active = null, int page = 0,
                                                      CancellationToken ct = default)
    {
        var p = new List<string> { $"page={page}" };
        if (!string.IsNullOrWhiteSpace(q)) p.Add($"q={Uri.EscapeDataString(q)}");
        if (!string.IsNullOrWhiteSpace(role)) p.Add($"role={role}");
        if (active is bool a) p.Add($"active={(a ? "true" : "false")}");
        var resp = await _http.GetAsync($"{Base}/api/admin/users?{string.Join("&", p)}", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
        return await resp.Content.ReadFromJsonAsync<AdminUsersPage>(_json, ct) ?? new();
    }

    public async Task<AuditPage> AdminAuditAsync(string? action = null, int page = 0,
                                                 CancellationToken ct = default)
    {
        var p = new List<string> { $"page={page}" };
        if (!string.IsNullOrWhiteSpace(action)) p.Add($"action={action}");
        var resp = await _http.GetAsync($"{Base}/api/admin/audit?{string.Join("&", p)}", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
        return await resp.Content.ReadFromJsonAsync<AuditPage>(_json, ct) ?? new();
    }

    /// Ручне підтвердження email — коли лист не доходить (сервер пише це в аудит).
    public async Task AdminVerifyAsync(long userId, CancellationToken ct = default)
    {
        var resp = await _http.PostAsync($"{Base}/api/admin/users/{userId}/verify", null, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    public async Task AdminSendResetAsync(long userId, CancellationToken ct = default)
    {
        var resp = await _http.PostAsync($"{Base}/api/admin/users/{userId}/send-reset", null, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Видалення акаунта — незворотне, лише admin (сервер відхилить решту).
    public async Task AdminDeleteUserAsync(long userId, CancellationToken ct = default)
    {
        var resp = await _http.DeleteAsync($"{Base}/api/admin/users/{userId}", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    public async Task<AdminMetrics?> AdminMetricsAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/admin/metrics", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
        return await resp.Content.ReadFromJsonAsync<AdminMetrics>(_json, ct);
    }

    /// Змінити роль (лише admin). Відмови сервера («не можна лишити систему без
    /// активного адміна» тощо) приходять текстом у detail → показуємо людині як є.
    public async Task SetUserRoleAsync(long userId, string role, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/admin/users/{userId}/role",
                                               new { role }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    /// Бан/розбан (moderator+). Межа прав приходить 403 із поясненням у detail.
    public async Task SetUserActiveAsync(long userId, bool active, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/admin/users/{userId}/ban",
                                               new { active }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
    }

    private static async Task<string> SafeDetail(HttpResponseMessage resp, CancellationToken ct)
    {
        try
        {
            var doc = await resp.Content.ReadFromJsonAsync<Dictionary<string, string>>(_json, ct);
            if (doc is not null && doc.TryGetValue("detail", out var d) && !string.IsNullOrWhiteSpace(d))
                return d;
        }
        catch { /* тіло не JSON — падаємо на дефолт */ }
        return $"Помилка сервера ({(int)resp.StatusCode})";
    }
}

/// Кинуто, коли сервер повернув осмислену помилку (текст із detail) — показуємо людині.
public class ApiException : Exception
{
    public ApiException(string message) : base(message) { }
}
