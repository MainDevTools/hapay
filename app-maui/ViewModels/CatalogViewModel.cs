using System.Collections.ObjectModel;
using System.Linq;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

/// Плитка банерної каруселі: категорія + кольори тла/тексту (стиль E-Katalog).
public record BannerTile(Category Cat, Color Bg, Color Fg);

/// Сторінка каруселі — четвірка плиток 2×2.
public class BannerPage : List<BannerTile> { }

/// Картка «Популярних розділів»: фото + назва + лінки топ-категорій.
public record SectionCard(string Title, string? ImageUrl, List<Category> Cats)
{
    public bool HasImage => !string.IsNullOrEmpty(ImageUrl);
}

// Головна = сітка-каталог (E-Katalog, §17): категорії зі знижками, згруповані в розділи.
// Тап по плитці → HomePage зі стрічкою тієї категорії. Порожні категорії сервер не віддає.
public partial class CatalogViewModel : ObservableObject
{
    private readonly ApiService _api;
    private readonly AuthService _auth;
    private readonly IPriceWatchScheduler _watchScheduler;

    public ObservableCollection<CategoryGroup> Groups { get; } = new();

    /// «Популярні моделі» (§17): товари, які продають найбільше крамниць — «від X ₴».
    public ObservableCollection<Discount> Popular { get; } = new();

    /// «Нещодавно переглянуті» — локальна історія відкритих карток (повернутись до
    /// порівняння без повторного пошуку).
    public ObservableCollection<Discount> Recent { get; } = new();

    /// Банерна карусель (E-Katalog): сторінки 2×2 з топ-категорій із фото.
    public ObservableCollection<BannerPage> BannerPages { get; } = new();

    /// «Популярні розділи»: картки з фото + лінками топ-категорій розділу.
    public ObservableCollection<SectionCard> PopularSections { get; } = new();

    [ObservableProperty] private bool _isRefreshing;
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private bool _showEmpty;
    [ObservableProperty] private bool _hasPopular;
    [ObservableProperty] private bool _hasBanners;
    [ObservableProperty] private bool _hasPopularSections;
    [ObservableProperty] private bool _hasRecent;

    private readonly List<Category> _allCats = new();
    private readonly RecentProducts _recent;
    private bool _ready;

    public CatalogViewModel(ApiService api, AuthService auth, IPriceWatchScheduler watchScheduler,
                            RecentProducts recent)
    {
        _api = api;
        _auth = auth;
        _watchScheduler = watchScheduler;
        _recent = recent;
    }

    /// «Нещодавно переглянуті» — оновлюються при КОЖНОМУ поверненні на головну
    /// (без guard: щойно переглянуте має з'явитись одразу).
    public void RefreshLocal()
    {
        Recent.Clear();
        foreach (var d in _recent.Load()) Recent.Add(d);
        HasRecent = Recent.Count > 0;
    }

    /// Фейк-поле пошуку → повний екран пошуку.
    [RelayCommand]
    private async Task OpenSearch() => await Shell.Current.GoToAsync(nameof(SearchPage));

    public async Task InitializeAsync()
    {
        if (_ready) return;
        await _auth.LoadAsync();   // підняти токен до першого запиту (як у HomeVM)
        if (_auth.IsLoggedIn)
            _watchScheduler.EnsureIfEnabled();   // відновити перевірку цін після перезапуску
        await LoadAsync();
        _ready = true;
    }

    [RelayCommand]
    private async Task Refresh()
    {
        IsRefreshing = true;
        await LoadAsync(fresh: true);   // явний жест оновлення — повз кеш
        IsRefreshing = false;
    }

    private async Task LoadAsync(bool fresh = false)
    {
        ErrorMessage = null;
        // обидва запити СТАРТУЮТЬ одразу (послідовність давала подвійну затримку)
        var catsTask = _api.CategoriesAsync(fresh);
        var popTask = _api.ProductsAsync(sort: "popular", onlyDiscounts: true);
        try
        {
            var cats = await catsTask;
            Groups.Clear();
            _allCats.Clear();
            // сервер уже сортує за розділом, тоді за к-стю → GroupBy зберігає цей порядок
            foreach (var g in cats.Where(c => !string.IsNullOrEmpty(c.Slug))
                                  .GroupBy(c => c.Section))
                Groups.Add(new CategoryGroup(g.Key, g));
            _allCats.AddRange(cats.Where(c => !string.IsNullOrEmpty(c.Slug)));
            BuildShowcase();
            ShowEmpty = Groups.Count == 0;
        }
        catch (Exception e)
        {
            ErrorMessage = e.Message;
            ShowEmpty = Groups.Count == 0;
        }

        try
        {
            var pop = await popTask;
            Popular.Clear();
            foreach (var p in pop.Take(12)) Popular.Add(p);
            HasPopular = Popular.Count > 0;
        }
        catch
        {
            HasPopular = Popular.Count > 0;   // блок — бонус; збій не ламає каталог
        }
    }

    // Палітра банерів — ЛИШЕ пастелі з темним текстом тієї ж гами: наші фото — це
    // hotlink-продуктівки на білому тлі, на насичених кольорах вони виглядали
    // «наліпками»; на пастелі біле тло фото зливається з плиткою.
    private static readonly (string Bg, string Fg)[] _tileColors =
    {
        ("#EAF1FA", "#1F3A5F"), ("#FDECEA", "#7A2E25"), ("#EAF6EE", "#1F5F3A"),
        ("#FFF4E2", "#7A5222"), ("#F1ECFA", "#46307A"), ("#EAF7F9", "#1F5F6E"),
    };

    /// Банери (топ-категорії з фото, ≤2 на розділ — розмаїття) + «Популярні розділи»
    /// (топ-6 за сумою знижок, у картці — лінки топ-8 категорій). Усе з /api/categories.
    private void BuildShowcase()
    {
        BannerPages.Clear();
        var perSection = new Dictionary<string, int>();
        var banners = new List<Category>();
        foreach (var c in _allCats.Where(c => c.HasImage).OrderByDescending(c => c.N))
        {
            perSection.TryGetValue(c.Section, out var k);
            if (k >= 2) continue;
            perSection[c.Section] = k + 1;
            banners.Add(c);
            if (banners.Count == 8) break;
        }
        for (var i = 0; i + 4 <= banners.Count; i += 4)   // лише повні четвірки — 2×2
        {
            var page = new BannerPage();
            for (var j = 0; j < 4; j++)
            {
                // глобальний індекс: сусідні сторінки не повторюють ту саму четвірку кольорів
                var (bg, fg) = _tileColors[(i + j) % _tileColors.Length];
                page.Add(new BannerTile(banners[i + j], Color.FromArgb(bg), Color.FromArgb(fg)));
            }
            BannerPages.Add(page);
        }
        HasBanners = BannerPages.Count > 0;

        PopularSections.Clear();
        foreach (var g in Groups.OrderByDescending(g => g.Sum(c => c.N)).Take(6))
            PopularSections.Add(new SectionCard(
                g.Title,
                g.FirstOrDefault(c => c.HasImage)?.ImageUrl,
                g.OrderByDescending(c => c.N).Take(8).ToList()));
        HasPopularSections = PopularSections.Count > 0;
    }

    [RelayCommand]
    private async Task OpenProduct(Discount? d)
    {
        if (d is null) return;
        await Shell.Current.GoToAsync(nameof(DetailPage),
            new Dictionary<string, object> { ["Discount"] = d });
    }

    /// Виміряні зниження (S28) — окремий екран, бо це інше твердження, ніж «знижки»:
    /// там оголошення крамниць, тут різниця між двома нашими вимірами.
    [RelayCommand]
    private async Task OpenDrops() => await Shell.Current.GoToAsync(nameof(DropsPage));

    [RelayCommand]
    private async Task OpenStores() => await Shell.Current.GoToAsync(nameof(StoresPage));

    [RelayCommand]
    private async Task OpenCategory(Category? c)
    {
        if (c is null) return;
        await Shell.Current.GoToAsync(nameof(HomePage),
            new Dictionary<string, object> { ["Category"] = c.Slug, ["Title"] = c.Name });
    }

    /// «Весь каталог →»: повний дворівневий каталог; вибір ПУШИТЬ стрічку категорії
    /// (Flow=push — бо повертатись нема куди: каталог-таб не приймає категорію).
    [RelayCommand]
    private async Task OpenAllCatalog() => await Shell.Current.GoToAsync(
        nameof(CategoryPickerPage), new Dictionary<string, object> { ["Flow"] = "push" });

    [RelayCommand]
    private async Task Account()
    {
        var route = _auth.IsLoggedIn ? nameof(ProfilePage) : nameof(LoginPage);
        await Shell.Current.GoToAsync(route);
    }
}
