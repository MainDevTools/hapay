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

    /// УСІ товари (не лише знижки) — повний прайс-агрегатор. onlyDiscounts=true → лише знижкові.
    public async Task<List<Discount>> ProductsAsync(
        string? category = null, string? q = null, string sort = "discount", int page = 0,
        int? priceMinKop = null, int? priceMaxKop = null, bool onlyDiscounts = false,
        CancellationToken ct = default)
    {
        var url = $"{Base}/api/products?sort={Uri.EscapeDataString(sort)}&page={page}";
        if (!string.IsNullOrWhiteSpace(category)) url += $"&category={Uri.EscapeDataString(category)}";
        if (!string.IsNullOrWhiteSpace(q)) url += $"&q={Uri.EscapeDataString(q.Trim())}";
        if (priceMinKop is int lo) url += $"&price_min={lo}";
        if (priceMaxKop is int hi) url += $"&price_max={hi}";
        if (onlyDiscounts) url += "&only_discounts=1";
        return await _http.GetFromJsonAsync<List<Discount>>(url, _json, ct) ?? new();
    }

    public async Task<List<Category>> CategoriesAsync(CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<Category>>($"{Base}/api/categories", _json, ct) ?? new();

    public async Task<List<HistoryPoint>> HistoryAsync(int storeProductId, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<HistoryPoint>>(
            $"{Base}/api/product/{storeProductId}/history", _json, ct) ?? new();

    /// «Де купити» (T15): той самий товар (mpn) у всіх крамницях, від найдешевшої.
    public async Task<List<Offer>> OffersAsync(int storeProductId, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<Offer>>(
            $"{Base}/api/product/{storeProductId}/offers", _json, ct) ?? new();

    // ── auth (S11) ────────────────────────────────────────────────────────────────
    public Task<AuthResult> RegisterAsync(string email, string password, CancellationToken ct = default) =>
        PostAuthAsync("/api/auth/register", email, password, ct);

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

    // ── «Стежити за ціною» ────────────────────────────────────────────────────────
    /// Додати товар у відстеження. Ціну на момент додавання фіксує СЕРВЕР — тут її
    /// свідомо не передаємо (клієнт не має диктувати, від чого рахувати економію).
    public async Task WatchAsync(int storeProductId, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/me/watchlist",
            new { kind = "store_product", ref_id = storeProductId }, ct);
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
