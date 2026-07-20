using System.Net;
using System.Text;

namespace Hapay.Services;

/// Збір «тупим фетчером» (S11 етап 3): застосунок тягне HTML крамниці зі СВОГО
/// (резидентного) IP і пересилає серверу, який парсить. Логіки парсингу тут НЕМАЄ —
/// зміна селекторів/крамниці не потребує оновлення застосунку в сторах.
///
/// Двофазно: сервер віддає план (хаб) → тягнемо хаб → сервер робить discover і повертає
/// лендинги → тягнемо кожен → сервер extract+персист. Доступно лише ролі collector+.
public class CollectorService
{
    private readonly ApiService _api;
    private readonly IWebRenderer _renderer;   // рендер SPA-крамниць (mode=render) — Android WebView
    private readonly HttpClient _store;    // ОКРЕМИЙ клієнт: БЕЗ нашого JWT (не світимо токен крамниці)

    private const int MaxHtml = 5_000_000;                       // = серверна стеля; не вантажимо більше
    private static readonly TimeSpan Polite = TimeSpan.FromSeconds(2);  // §10.2 — пауза між запитами до хоста

    public CollectorService(ApiService api, IWebRenderer renderer)
    {
        _api = api;
        _renderer = renderer;
        var handler = new HttpClientHandler
        {
            AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate,
        };
        _store = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(30) };
        // TryAddWithoutValidation — без ризику FormatException на UA з дужками/комами
        _store.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36");
        _store.DefaultRequestHeaders.TryAddWithoutValidation("Accept-Language", "uk,en;q=0.9");
    }

    public async Task<CollectSummary> RunAsync(IProgress<string> progress, CancellationToken ct = default)
    {
        var plan = await _api.GetCollectPlanAsync(ct);
        int accepted = 0, pages = 0;
        var errors = new List<string>();

        foreach (var t in plan.Targets)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                progress.Report($"{t.Source}: {Short(t.Url)}…");
                var html = await GetHtmlAsync(t.Url, t.Mode, ct);
                var r = await _api.IngestHtmlAsync(t.Source, t.Url, html, ct: ct);
                pages++;
                accepted += r.Accepted;

                // фаза 2: хаб віддав лендинги — тягнемо кожен, сервер їх парсить
                if (r.Kind == "hub" && r.Discovered is { Count: > 0 })
                {
                    var host = HostOf(t.Url);
                    foreach (var landing in r.Discovered)
                    {
                        ct.ThrowIfCancellationRequested();
                        // захист: лендинг мусить бути на тому ж хості, що й ціль (не даємо збити на чужий)
                        if (HostOf(landing) != host)
                        {
                            errors.Add($"чужий хост пропущено: {Short(landing)}");
                            continue;
                        }
                        await Task.Delay(Polite, ct);
                        try
                        {
                            progress.Report($"{t.Source}: {Short(landing)} (зібрано {accepted})…");
                            var lhtml = await FetchAsync(landing, ct);
                            var lr = await _api.IngestHtmlAsync(t.Source, landing, lhtml, ct: ct);
                            pages++;
                            accepted += lr.Accepted;
                        }
                        catch (OperationCanceledException) { throw; }
                        catch (Exception e) { errors.Add($"{Short(landing)}: {e.Message}"); }
                    }
                }
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception e) { errors.Add($"{t.Source}: {e.Message}"); }
        }
        return new CollectSummary(accepted, pages, errors);
    }

    /// Один ФОНОВИЙ прохід по черзі-оренді (T16): lease ≤5 задач (по 1 на крамницю,
    /// сервер сам тримає розліт 15 хв) → fetch → ingest із task_id (закривається сам).
    /// Не стягнулось → collect/fail (бекоф на сервері).
    ///
    /// Чому 5, а не 3: після пагінації (2026-07-20) у черзі 174 задачі; щоб оновити всі
    /// за 12 год, треба ~14.6 оренд/год, а прохід кожні 15 хв × 3 давав лише 12/год —
    /// черга відставала б. 5 за прохід → 20/год, із запасом.
    public async Task<QueuePassSummary> RunQueuePassAsync(CancellationToken ct = default)
    {
        var tasks = await _api.LeaseAsync(5, ct);
        int pages = 0, accepted = 0;
        var errors = new List<string>();
        foreach (var t in tasks)
        {
            ct.ThrowIfCancellationRequested();
            try
            {
                var html = await GetHtmlAsync(t.Url, t.Mode, ct);
                var r = await _api.IngestHtmlAsync(t.Source, t.Url, html, t.TaskId, ct);
                pages++;
                accepted += r.Accepted;
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception e)
            {
                errors.Add($"{t.Source}: {e.Message}");
                try { await _api.CollectFailAsync(t.TaskId, e.Message, ct); } catch { /* бекоф не критичний */ }
            }
        }
        if (pages > 0) CollectPrefs.BumpToday(pages);
        return new QueuePassSummary(pages, accepted, errors);
    }

    /// HTML сторінки за режимом: render (WebView — SPA-крамниці) або fetch (plain GET — SSR).
    private async Task<string> GetHtmlAsync(string url, string mode, CancellationToken ct)
    {
        if (mode == "render")
        {
            if (!_renderer.IsSupported)
                throw new Exception("render недоступний на цій платформі");
            var rendered = await _renderer.RenderHtmlAsync(url, ct);
            return rendered ?? throw new Exception("render повернув порожньо");
        }
        return await FetchAsync(url, ct);
    }

    private async Task<string> FetchAsync(string url, CancellationToken ct)
    {
        using var resp = await _store.GetAsync(url, HttpCompletionOption.ResponseHeadersRead, ct);
        resp.EnsureSuccessStatusCode();
        var bytes = await resp.Content.ReadAsByteArrayAsync(ct);
        if (bytes.Length > MaxHtml) throw new Exception("сторінка завелика");
        return Encoding.UTF8.GetString(bytes);
    }

    private static string HostOf(string url) =>
        Uri.TryCreate(url, UriKind.Absolute, out var u) ? u.Host : "";

    private static string Short(string url)
    {
        var i = url.IndexOf("//", StringComparison.Ordinal);
        var s = i >= 0 ? url[(i + 2)..] : url;
        return s.Length > 44 ? s[..44] + "…" : s;
    }
}

/// Підсумок одного прогону збору.
public record CollectSummary(int Accepted, int Pages, List<string> Errors);

/// Підсумок одного фонового проходу по черзі (T16).
public record QueuePassSummary(int Pages, int Accepted, List<string> Errors);
