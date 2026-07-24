using System.Collections.ObjectModel;
using System.Linq;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

public record SortOption(string Label, string Key);
public record PriceOption(string Label, int? MinKop, int? MaxKop);   // межі — копійки (інв. A), null = без межі

// IQueryAttributable — HomePage тепер пушиться з каталогу з категорією/пошуком (§17).
public partial class HomeViewModel : ObservableObject, IQueryAttributable
{
    private readonly ApiService _api;
    private readonly AuthService _auth;

    public ObservableCollection<Discount> Items { get; } = new();
    public ObservableCollection<Category> Categories { get; } = new();

    /// Розділи → категорії для листа вибору (замість плоского пікера на 171 рядок).
    public ObservableCollection<CategoryGroup> SheetGroups { get; } = new();

    /// Сусідні категорії того ж розділу — стрибок «Ноутбуки → Процесори» одним тапом.
    public ObservableCollection<Category> Neighbors { get; } = new();

    public IReadOnlyList<SortOption> SortOptions { get; } = new List<SortOption>
    {
        // підписи короткі: пікери тепер по третині ширини (компактна панель фільтрів)
        new("За знижкою", "discount"),
        new("Де дешевше", "cheaper"),   // той самий товар дешевший в іншій крамниці
        new("Дешевші", "cheap"),
        new("Дорожчі", "expensive"),
        new("Найновіші", "new"),
    };

    // глобальний фолбек — коли категорія не обрана або без цінових меж (замало даних)
    private static readonly IReadOnlyList<PriceOption> _globalPrices = new List<PriceOption>
    {
        new("Будь-яка", null, null),   // «ціна» зайве — пікер і так підписаний; довше різалось
        new("до 500 ₴", null, 50_000),
        new("500–2 000 ₴", 50_000, 200_000),
        new("2 000–10 000 ₴", 200_000, 1_000_000),
        new("10 000–30 000 ₴", 1_000_000, 3_000_000),
        new("від 30 000 ₴", 3_000_000, null),
    };

    /// Діапазони ціни — ДИНАМІЧНІ від терцілей обраної категорії (§17-nav): «до 500 ₴»
    /// у ноутбуках було декоративним. Перебудовуються при зміні категорії.
    public ObservableCollection<PriceOption> PriceOptions { get; } = new(_globalPrices);

    [ObservableProperty] private Category? _selectedCategory;
    [ObservableProperty] private SortOption? _selectedSort;
    [ObservableProperty] private PriceOption? _selectedPrice;
    [ObservableProperty] private string _searchText = "";
    [ObservableProperty] private bool _isCategorySheetOpen;
    [ObservableProperty] private bool _hasNeighbors;
    [ObservableProperty] private string _selectedCategoryLabel = "Усі категорії";
    [ObservableProperty] private bool _isLoading;
    [ObservableProperty] private bool _isRefreshing;
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private bool _showEmpty;
    [ObservableProperty] private string _pageTitle = "Хапай";   // = назва категорії (пуш із каталогу)

    private string? _pendingCategory;   // slug із каталогу — обрати після завантаження категорій
    private string? _pendingQuery;      // пошук із каталогу

    private bool _searchWidened;        // пошук вийшов за межі обраної категорії

    [ObservableProperty] private string? _searchNote;   // пояснення, чому видача ширша

    /// Режим пошуку: інші правила видачі, ніж при гортанні (див. FetchAsync).
    public bool IsSearching => !string.IsNullOrWhiteSpace(SearchText);

    private int _gen;          // покоління запиту: зміна фільтра інвалідує in-flight відповіді
    private int _page;
    private bool _more = true;
    private bool _ready;       // до першого завантаження ігноруємо property-changed (щоб не дублювати)
    private CancellationTokenSource? _searchCts;

    private readonly ICollectScheduler _scheduler;

    public HomeViewModel(ApiService api, AuthService auth, ICollectScheduler scheduler)
    {
        _api = api;
        _auth = auth;
        _scheduler = scheduler;
    }

    // прийшли з каталогу (§17): категорія / пошук / заголовок сторінки
    public void ApplyQueryAttributes(IDictionary<string, object> query)
    {
        if (query.TryGetValue("Category", out var cat) && cat is string s && s.Length > 0)
            _pendingCategory = s;
        if (query.TryGetValue("Query", out var q) && q is string qs && qs.Length > 0)
            _pendingQuery = qs;
        if (query.TryGetValue("Title", out var t) && t is string ts && ts.Length > 0)
            PageTitle = ts;
    }

    public async Task InitializeAsync()
    {
        if (_ready) return;
        await _auth.LoadAsync();   // підняти збережений токен (SecureStorage) до першого запиту
        _scheduler.EnsureIfEnabled();   // відновити фоновий збір (T16), якщо був увімкнений
        // «Усі категорії» додаємо ДО запиту — щоб пікер не лишився порожнім, якщо мережа впаде
        Categories.Add(new Category { Slug = "", Name = "Усі категорії" });
        try
        {
            var cats = await _api.CategoriesAsync();
            foreach (var c in cats) Categories.Add(c);
        }
        catch { /* категорії необовʼязкові — «Усі» вже є */ }

        // розділи для листа вибору категорії (сервер уже відсортував за розділами)
        foreach (var g in Categories.Where(c => !string.IsNullOrEmpty(c.Slug))
                                    .GroupBy(c => c.Section))
            SheetGroups.Add(new CategoryGroup(g.Key, g));

        // пуш із каталогу → обрати ту категорію; інакше «Усі»
        _selectedCategory = string.IsNullOrEmpty(_pendingCategory)
            ? Categories[0]
            : Categories.FirstOrDefault(c => c.Slug == _pendingCategory) ?? Categories[0];
        if (!string.IsNullOrEmpty(_pendingQuery))
            _searchText = _pendingQuery;         // backing-поле: не тригерити debounce-reload тут
        _selectedSort = SortOptions[0];
        // backing-поля не проходять partial-хуки → залежне будуємо руками
        ApplyCategorySideEffects(_selectedCategory);
        _selectedPrice = PriceOptions[0];    // «Будь-яка ціна»
        OnPropertyChanged(nameof(SelectedCategory));
        OnPropertyChanged(nameof(SelectedSort));
        OnPropertyChanged(nameof(SelectedPrice));
        OnPropertyChanged(nameof(SearchText));

        await ReloadAsync();
        _ready = true;
    }

    // property-changed від пікерів → перезавантаження (після ініціалізації)
    partial void OnSelectedCategoryChanged(Category? value)
    {
        ApplyCategorySideEffects(value);
        if (_ready) _ = ReloadAsync();
    }
    partial void OnSelectedSortChanged(SortOption? value) { if (_ready) _ = ReloadAsync(); }
    partial void OnSelectedPriceChanged(PriceOption? value)
    { if (_ready && !_rebuildingPrices) _ = ReloadAsync(); }

    private bool _rebuildingPrices;   // зміна категорії міняє список цін — без другого reload

    /// Залежне від категорії: підпис кнопки, сусідні чіпи розділу, діапазони ціни.
    private void ApplyCategorySideEffects(Category? c)
    {
        var real = c is not null && !string.IsNullOrEmpty(c.Slug);
        SelectedCategoryLabel = real ? c!.Display : "Усі категорії";
        if (real) PageTitle = c!.Name;

        Neighbors.Clear();
        if (real)
            foreach (var n in Categories.Where(x => !string.IsNullOrEmpty(x.Slug)
                                                    && x.Section == c!.Section
                                                    && x.Slug != c.Slug))
                Neighbors.Add(n);
        HasNeighbors = Neighbors.Count > 0;

        _rebuildingPrices = true;
        try
        {
            PriceOptions.Clear();
            if (real && c!.P33Kop is int lo && c.P66Kop is int hi)
            {
                // межі — «гарні» терцілі реальних цін категорії (сервер): три чесні кошики
                var loTxt = Money.Grn(lo);
                PriceOptions.Add(new("Будь-яка", null, null));
                PriceOptions.Add(new($"до {loTxt}", null, lo));
                PriceOptions.Add(new($"{loTxt.Replace(" ₴", "")}–{Money.Grn(hi)}", lo, hi));
                PriceOptions.Add(new($"від {Money.Grn(hi)}", hi, null));
            }
            else
                foreach (var p in _globalPrices) PriceOptions.Add(p);
            SelectedPrice = PriceOptions[0];   // фільтр ціни скидається разом із категорією
        }
        finally { _rebuildingPrices = false; }
    }

    [RelayCommand] private void OpenCategorySheet() => IsCategorySheetOpen = true;
    [RelayCommand] private void CloseCategorySheet() => IsCategorySheetOpen = false;

    /// Тап по чіпу (лист вибору або сусідні) → перемкнути категорію.
    [RelayCommand]
    private void PickCategory(Category? c)
    {
        IsCategorySheetOpen = false;
        if (c is null) return;
        SelectedCategory = Categories.FirstOrDefault(x => x.Slug == c.Slug) ?? Categories[0];
    }

    /// «Усі категорії» з листа вибору.
    [RelayCommand]
    private void PickAllCategories()
    {
        IsCategorySheetOpen = false;
        SelectedCategory = Categories.FirstOrDefault(x => string.IsNullOrEmpty(x.Slug));
        PageTitle = "Хапай";
    }

    partial void OnSearchTextChanged(string value)
    {
        OnPropertyChanged(nameof(IsSearching));   // підказка про режим пошуку
        _searchCts?.Cancel();
        var cts = new CancellationTokenSource();
        _searchCts = cts;
        _ = DebouncedSearch(cts.Token);
    }

    private async Task DebouncedSearch(CancellationToken token)
    {
        try { await Task.Delay(400, token); }
        catch (TaskCanceledException) { return; }
        if (!token.IsCancellationRequested)
            await MainThread.InvokeOnMainThreadAsync(ReloadAsync);
    }

    [RelayCommand]
    private async Task Refresh()
    {
        IsRefreshing = true;
        await ReloadAsync();
        IsRefreshing = false;
    }

    [RelayCommand]
    private async Task LoadMore()
    {
        if (IsLoading || !_more) return;
        IsLoading = true;
        await FetchAsync(_gen);
    }

    [RelayCommand]
    private async Task GoToDetail(Discount? d)
    {
        if (d is null) return;
        await Shell.Current.GoToAsync(nameof(DetailPage),
            new Dictionary<string, object> { ["Discount"] = d });
    }

    [RelayCommand]
    private async Task Account()
    {
        // залогінений → профіль; ні → екран входу/реєстрації
        var route = _auth.IsLoggedIn ? nameof(ProfilePage) : nameof(LoginPage);
        await Shell.Current.GoToAsync(route);
    }

    /// Стеження з тулбара (як у каталозі). Не залогінений → спершу вхід: список акаунтний.
    [RelayCommand]
    private async Task Watchlist() => await Shell.Current.GoToAsync(
        _auth.IsLoggedIn ? nameof(WatchlistPage) : nameof(LoginPage));

    private async Task ReloadAsync()
    {
        var gen = ++_gen;              // нове покоління → будь-який in-flight запит застарілий
        _page = 0;
        _more = true;
        _searchWidened = false;        // новий запит — знову поважаємо обрану категорію
        SearchNote = null;
        ErrorMessage = null;
        Items.Clear();
        IsLoading = true;
        await FetchAsync(gen);         // НЕ через LoadMore: свіжий reload не блокується IsLoading
    }

    private async Task FetchAsync(int gen)
    {
        try
        {
            var cat = string.IsNullOrEmpty(SelectedCategory?.Slug) ? null : SelectedCategory!.Slug;
            if (_searchWidened) cat = null;          // вже розширили — тримаємось цього й далі

            var batch = await _api.ProductsAsync(
                category: cat,
                q: SearchText,
                sort: SelectedSort?.Key ?? "discount",
                page: _page,
                priceMinKop: SelectedPrice?.MinKop,
                priceMaxKop: SelectedPrice?.MaxKop,
                // Гортаємо — лише знижки (ідентичність «Хапай»). ШУКАЄМО — по всьому
                // каталогу: коли людина ввела назву, вона хоче саме цей товар, а не
                // «нічого не знайдено» через те, що на нього зараз немає знижки.
                // Заміряно 2026-07-21: знижкові — лише 48% зібраного (2673 товари
                // були недосяжні пошуком).
                onlyDiscounts: !IsSearching);
            if (gen != _gen) return;   // фільтр змінився під час запиту → відповідь застаріла

            // Глухий кут: шукали всередині категорії й нічого. Замість «нічого не
            // знайдено» розширюємо пошук на всі категорії й прямо кажемо про це —
            // «ASUS» у «Смартфони» справді порожньо, але 280 ноутбуків у нас є.
            if (batch.Count == 0 && _page == 0 && IsSearching && cat is not null)
            {
                batch = await _api.ProductsAsync(
                    category: null, q: SearchText, sort: SelectedSort?.Key ?? "discount",
                    page: 0, priceMinKop: SelectedPrice?.MinKop,
                    priceMaxKop: SelectedPrice?.MaxKop, onlyDiscounts: false);
                if (gen != _gen) return;
                if (batch.Count > 0)
                {
                    _searchWidened = true;
                    SearchNote = $"У категорії «{SelectedCategory?.Name}» нічого — показуємо з усіх категорій";
                }
            }

            // «Де дешевше» піднімає такі картки нагору, тож якщо навіть ПЕРША не має
            // дешевшої пропозиції — їх нема в усій категорії. Кажемо це прямо: інакше
            // людина гортає список, який на вигляд нічим не відрізняється від звичайного,
            // і думає, що фільтр зламався. У смартфонах це штатний стан (заміряно:
            // розкид ціни там 53 ₴ проти 1 468 ₴ на ноутбуках), а не помилка.
            if (_page == 0 && SelectedSort?.Key == "cheaper" && batch.Count > 0 && !batch[0].HasCheaper)
                SearchNote = string.IsNullOrEmpty(cat)
                    ? "Ціни в крамницях однакові — дешевших пропозицій поруч не знайшли"
                    // «У категорії «X»», а не «У «X»»: назву не відмінити програмно
                    // («Коти · Сухий корм»), тож родове слово бере відмінок на себе
                    : $"У категорії «{SelectedCategory?.Name}» ціни в крамницях однакові — дешевшого поруч нема";

            foreach (var d in batch) Items.Add(d);
            _more = batch.Count >= 50;
            _page++;
            ErrorMessage = null;
        }
        catch (Exception e)
        {
            if (gen != _gen) return;
            ErrorMessage = e.Message;
        }
        finally
        {
            if (gen == _gen)
            {
                IsLoading = false;
                ShowEmpty = Items.Count == 0 && ErrorMessage is null;
            }
        }
    }
}
