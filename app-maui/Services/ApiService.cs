using System.Net.Http.Json;
using System.Text.Json;
using Hapay.Models;

namespace Hapay.Services;

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
}
