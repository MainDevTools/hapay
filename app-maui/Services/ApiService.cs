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
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(20) };
    }

    /// JWT для захищених ендпоінтів (/api/me*). null → анонім (публічні ендпоінти працюють).
    public void SetToken(string? token) =>
        _http.DefaultRequestHeaders.Authorization =
            string.IsNullOrEmpty(token) ? null : new AuthenticationHeaderValue("Bearer", token);

    public async Task<List<Discount>> DiscountsAsync(
        string? category = null, string? q = null, string sort = "discount", int page = 0,
        CancellationToken ct = default)
    {
        var url = $"{Base}/api/discounts?sort={Uri.EscapeDataString(sort)}&page={page}";
        if (!string.IsNullOrWhiteSpace(category)) url += $"&category={Uri.EscapeDataString(category)}";
        if (!string.IsNullOrWhiteSpace(q)) url += $"&q={Uri.EscapeDataString(q.Trim())}";
        return await _http.GetFromJsonAsync<List<Discount>>(url, _json, ct) ?? new();
    }

    public async Task<List<Category>> CategoriesAsync(CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<Category>>($"{Base}/api/categories", _json, ct) ?? new();

    public async Task<List<HistoryPoint>> HistoryAsync(int storeProductId, CancellationToken ct = default) =>
        await _http.GetFromJsonAsync<List<HistoryPoint>>(
            $"{Base}/api/product/{storeProductId}/history", _json, ct) ?? new();

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

    // ── збір (S11 етап 3): застосунок = «тупий фетчер», парсить сервер ────────────────
    /// Сервер каже, ЩО тягнути (гейт ролі collector). 401 → нема прав/токен застарів.
    public async Task<CollectPlan> GetCollectPlanAsync(CancellationToken ct = default)
    {
        var resp = await _http.GetAsync($"{Base}/api/collect/plan", ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        resp.EnsureSuccessStatusCode();
        return (await resp.Content.ReadFromJsonAsync<CollectPlan>(_json, ct))!;
    }

    /// Пересилаємо СИРИЙ HTML крамниці — сервер парсить. Для hub повертає discovered-лендинги.
    public async Task<IngestHtmlResult> IngestHtmlAsync(string source, string url, string html,
                                                        CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync($"{Base}/api/ingest/html",
                                               new { source, url, html }, ct);
        if (resp.StatusCode == HttpStatusCode.Unauthorized) throw new UnauthorizedException();
        if (!resp.IsSuccessStatusCode) throw new ApiException(await SafeDetail(resp, ct));
        return (await resp.Content.ReadFromJsonAsync<IngestHtmlResult>(_json, ct))!;
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
