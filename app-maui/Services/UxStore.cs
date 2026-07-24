using System.Text.Json;
using Hapay.Models;

namespace Hapay.Services;

/// «Нещодавно переглянуті» — локально (Preferences), без сервера і без телеметрії
/// (§7.7): список живе лише на пристрої. Останні 10, найновіше першим.
public class RecentProducts
{
    private const string Key = "recent_products_v1";
    private const int Max = 10;
    private static readonly JsonSerializerOptions _json = new() { PropertyNameCaseInsensitive = true };

    public List<Discount> Load()
    {
        try
        {
            var raw = Preferences.Default.Get(Key, "");
            return string.IsNullOrEmpty(raw) ? new()
                 : JsonSerializer.Deserialize<List<Discount>>(raw, _json) ?? new();
        }
        catch { return new(); }   // бита схема після оновлення — просто порожньо
    }

    public void Push(Discount d)
    {
        var list = Load();
        list.RemoveAll(x => x.StoreProductId == d.StoreProductId);
        list.Insert(0, d);
        if (list.Count > Max) list.RemoveRange(Max, list.Count - Max);
        try { Preferences.Default.Set(Key, JsonSerializer.Serialize(list)); } catch { }
    }
}

/// Історія пошукових запитів — локально, останні 10 успішних.
public class SearchHistory
{
    private const string Key = "search_history_v1";
    private const int Max = 10;

    public List<string> Load()
    {
        try
        {
            var raw = Preferences.Default.Get(Key, "");
            return string.IsNullOrEmpty(raw) ? new()
                 : JsonSerializer.Deserialize<List<string>>(raw) ?? new();
        }
        catch { return new(); }
    }

    public void Push(string q)
    {
        q = (q ?? "").Trim();
        if (q.Length < 2) return;
        var list = Load();
        list.RemoveAll(x => string.Equals(x, q, StringComparison.CurrentCultureIgnoreCase));
        list.Insert(0, q);
        if (list.Count > Max) list.RemoveRange(Max, list.Count - Max);
        try { Preferences.Default.Set(Key, JsonSerializer.Serialize(list)); } catch { }
    }
}

/// Кеш-перший старт стрічки: перша сторінка останнього перегляду лежить у файлі
/// кешу — застосунок відкривається з товарами МИТТЄВО, свіже тихо замінює.
/// Ключ = категорія+сорт (без пошуку і цінового фільтра — кешуємо лише «чисті» види).
public class FeedCache
{
    private static string Path => System.IO.Path.Combine(FileSystem.CacheDirectory, "feed_cache_v1.json");
    private static readonly JsonSerializerOptions _json = new() { PropertyNameCaseInsensitive = true };

    private record Entry(string Key, List<Discount> Items);

    public void Save(string key, IEnumerable<Discount> items)
    {
        try
        {
            File.WriteAllText(Path, JsonSerializer.Serialize(new Entry(key, items.Take(50).ToList())));
        }
        catch { /* кеш — бонус */ }
    }

    public List<Discount>? TryLoad(string key)
    {
        try
        {
            if (!File.Exists(Path)) return null;
            var e = JsonSerializer.Deserialize<Entry>(File.ReadAllText(Path), _json);
            return e is not null && e.Key == key && e.Items.Count > 0 ? e.Items : null;
        }
        catch { return null; }
    }
}
