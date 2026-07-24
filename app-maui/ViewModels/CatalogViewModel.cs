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

    /// Підказки категорій під пошуком: «овер» → Оверлоки (пошук знаходить і КАТЕГОРІЇ,
    /// не лише товари — при 171 категорії згадати точну назву нереально).
    public ObservableCollection<Category> Suggestions { get; } = new();

    /// Банерна карусель (E-Katalog): сторінки 2×2 з топ-категорій із фото.
    public ObservableCollection<BannerPage> BannerPages { get; } = new();

    /// «Популярні розділи»: картки з фото + лінками топ-категорій розділу.
    public ObservableCollection<SectionCard> PopularSections { get; } = new();

    [ObservableProperty] private bool _isRefreshing;
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private bool _showEmpty;
    [ObservableProperty] private bool _hasPopular;
    [ObservableProperty] private bool _hasSuggestions;
    [ObservableProperty] private bool _hasBanners;
    [ObservableProperty] private bool _hasPopularSections;
    [ObservableProperty] private string _searchText = "";

    private readonly List<Category> _allCats = new();
    private bool _ready;

    public CatalogViewModel(ApiService api, AuthService auth, IPriceWatchScheduler watchScheduler)
    {
        _api = api;
        _auth = auth;
        _watchScheduler = watchScheduler;
    }

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
        await LoadAsync();
        IsRefreshing = false;
    }

    private async Task LoadAsync()
    {
        ErrorMessage = null;
        try
        {
            var cats = await _api.CategoriesAsync();
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
            var pop = await _api.ProductsAsync(sort: "popular", onlyDiscounts: true);
            Popular.Clear();
            foreach (var p in pop.Take(12)) Popular.Add(p);
            HasPopular = Popular.Count > 0;
        }
        catch
        {
            HasPopular = Popular.Count > 0;   // блок — бонус; збій не ламає каталог
        }
    }

    // палітра банерів (цикл): два насичені з білим текстом + два пастельні з темним
    private static readonly (string Bg, string Fg)[] _tileColors =
    {
        ("#4A6DA7", "#FFFFFF"), ("#D65B4F", "#FFFFFF"),
        ("#E9EFF6", "#1F2A3A"), ("#F5EADB", "#3A2E1F"),
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
                var (bg, fg) = _tileColors[j % _tileColors.Length];
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

    [RelayCommand]
    private async Task OpenCategory(Category? c)
    {
        if (c is null) return;
        await Shell.Current.GoToAsync(nameof(HomePage),
            new Dictionary<string, object> { ["Category"] = c.Slug, ["Title"] = c.Name });
    }

    [RelayCommand]
    private async Task Search()
    {
        var q = SearchText?.Trim();
        if (string.IsNullOrEmpty(q)) return;
        await Shell.Current.GoToAsync(nameof(HomePage),
            new Dictionary<string, object> { ["Query"] = q, ["Title"] = $"Пошук: {q}" });
    }

    // введення в пошук → підказки категорій за назвою (CurrentCulture: кирилиця)
    partial void OnSearchTextChanged(string value)
    {
        Suggestions.Clear();
        var q = value?.Trim();
        if (!string.IsNullOrEmpty(q) && q.Length >= 2)
            foreach (var c in _allCats.Where(c =>
                         c.Name.Contains(q, StringComparison.CurrentCultureIgnoreCase)).Take(8))
                Suggestions.Add(c);
        HasSuggestions = Suggestions.Count > 0;
    }

    /// Відстеження — з тулбара, а не трьома тапами через профіль.
    /// Не залогінений → спершу вхід: список належить акаунту.
    [RelayCommand]
    private async Task Watchlist() => await Shell.Current.GoToAsync(
        _auth.IsLoggedIn ? nameof(WatchlistPage) : nameof(LoginPage));

    [RelayCommand]
    private async Task Account()
    {
        var route = _auth.IsLoggedIn ? nameof(ProfilePage) : nameof(LoginPage);
        await Shell.Current.GoToAsync(route);
    }
}
