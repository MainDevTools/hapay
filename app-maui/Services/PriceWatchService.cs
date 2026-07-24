namespace Hapay.Services;

/// Показ локального сповіщення. Платформозалежна частина винесена сюди, щоб решта
/// логіки (кого й коли сповіщати) жила в одному місці й була однаковою скрізь.
public interface IPriceNotifier
{
    bool IsSupported { get; }
    void ShowDrops(IReadOnlyList<Models.PriceDrop> drops);
    /// Нові знижки у відстежуваних категоріях (уже згруповано сервером по категорії).
    void ShowCategoryNews(IReadOnlyList<Models.CategoryNews> news);
}

public class NoopPriceNotifier : IPriceNotifier
{
    public bool IsSupported => false;
    public void ShowDrops(IReadOnlyList<Models.PriceDrop> drops) { }
    public void ShowCategoryNews(IReadOnlyList<Models.CategoryNews> news) { }
}

/// Одна перевірка зниження цін: спитати сервер → показати сповіщення → підтвердити показ.
///
/// Свідомо ОДИН метод на два виклики — фоновий воркер і кнопка «перевірити зараз».
/// Якби кнопка мала власну копію логіки, вона перевіряла б не те, що працює у фоні,
/// і толку з такої перевірки не було б.
public class PriceWatchService
{
    private readonly ApiService _api;
    private readonly AuthService _auth;
    private readonly IPriceNotifier _notifier;

    public PriceWatchService(ApiService api, AuthService auth, IPriceNotifier notifier)
    {
        _api = api;
        _auth = auth;
        _notifier = notifier;
    }

    /// Повертає к-сть подешевшалих товарів (0 — нема про що сповіщати).
    /// Ack робимо ЛИШЕ після показу: інакше зниження «зникло б» непоміченим.
    public async Task<int> CheckAsync(CancellationToken ct = default)
    {
        await _auth.LoadAsync();                 // токен із SecureStorage (працює і без UI)
        if (!_auth.IsLoggedIn) return 0;

        var shown = 0;
        var drops = await _api.DropsAsync(ct);
        if (drops.Count > 0)
        {
            _notifier.ShowDrops(drops);
            await _api.AckDropsAsync(drops.Select(d => d.WatchlistId), ct);
            shown += drops.Count;
        }

        // категорійні новини — окреме сповіщення (згруповане сервером по категорії);
        // збій тут не має глушити цінові, тому свій try
        try
        {
            var news = await _api.CategoryNewsAsync(ct);
            if (news.Count > 0)
            {
                _notifier.ShowCategoryNews(news);
                await _api.AckCategoryNewsAsync(news.Select(n => n.WatchlistId), ct);
                shown += news.Count;
            }
        }
        catch (UnauthorizedException) { /* токен здох — цінові вже відпрацювали */ }
        return shown;
    }
}
