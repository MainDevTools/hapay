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

/// Чіп сортування (сегменти замість пікера): INPC потрібен для підсвітки обраного.
public partial class SortChip : ObservableObject
{
    public string Label { get; }
    public string Key { get; }
    [ObservableProperty] private bool _isSelected;
    public SortChip(string label, string key) { Label = label; Key = key; }
}

// IQueryAttributable — HomePage тепер пушиться з каталогу з категорією/пошуком (§17).
public partial class HomeViewModel : ObservableObject, IQueryAttributable
{
    private readonly ApiService _api;
    private readonly AuthService _auth;

    public ObservableCollection<Discount> Items { get; } = new();
    public ObservableCollection<Category> Categories { get; } = new();

    /// Сусідні категорії того ж розділу — стрибок «Ноутбуки → Процесори» одним тапом.
    public ObservableCollection<Category> Neighbors { get; } = new();

    public IReadOnlyList<SortOption> SortOptions { get; } = new List<SortOption>
    {
        new("За знижкою", "discount"),
        new("Де дешевше", "cheaper"),   // той самий товар дешевший в іншій крамниці
        new("Дешевші", "cheap"),
        new("Дорожчі", "expensive"),
        new("Найновіші", "new"),
    };

    /// Сорт — сегмент-чіпами (видно всі опції одразу, один тап замість двох у пікері).
    public ObservableCollection<SortChip> SortChips { get; } = new();

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
    [ObservableProperty] private bool _hasNeighbors;
    [ObservableProperty] private string _selectedCategoryLabel = "Усі категорії";
    /// Скелетон-картки замість порожнечі до першої відповіді (сприйнята швидкість).
    [ObservableProperty] private bool _showSkeleton;
    public IReadOnlyList<int> SkeletonRows { get; } = new[] { 0, 1, 2, 3, 4, 5 };

    // розумні порожні стани: кнопки-дії замість глухого «нічого не знайдено»
    [ObservableProperty] private bool _hasPriceFilter;      // «Прибрати фільтр ціни»
    [ObservableProperty] private bool _isCategoryNarrowed;  // «Шукати в усіх категоріях»

    // refId → watchlist_id: серденька на картках знають свій стан і чим видалятись
    private readonly Dictionary<int, int> _watchIds = new();
    // slug категорії → watchlist_id: дзвіночок «Стежити за категорією»
    private readonly Dictionary<string, int> _watchCatIds = new();

    // порівняння (S14): обрані store_product_id, у порядку вибору, макс 4
    private readonly List<int> _compareIds = new();
    [ObservableProperty] private bool _canCompare;         // ≥2 обрано → показати кнопку
    public string CompareButtonText => $"Порівняти ({_compareIds.Count})";

    [ObservableProperty] private bool _isCategoryWatched;
    [ObservableProperty] private string? _freshnessText;   // «Ціни оновлено N хв тому»

    /// «✓ Підтверджені» — лише знижки, що пройшли перевірку 30-денним мінімумом.
    [ObservableProperty] private bool _onlyVerified;

    /// «⚠ Завищена стара ціна» — знижки, де «стару» ціну не підтверджує 30-денний
    /// мінімум. Це те, заради чого «Хапай» і робиться, але доти воно розчинялось у
    /// стрічці серед 23 тисяч просто «заявлених».
    [ObservableProperty] private bool _onlyPumped;

    private bool _pendingCacheSwap;   // кеш на екрані → перший свіжий батч його замінює
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
    private readonly IPriceWatchScheduler _priceWatch;
    private readonly FeedCache _feedCache;
    private readonly SearchHistory _searchHistory;

    public HomeViewModel(ApiService api, AuthService auth, ICollectScheduler scheduler,
                         IPriceWatchScheduler priceWatch, FeedCache feedCache,
                         SearchHistory searchHistory)
    {
        _api = api;
        _auth = auth;
        _scheduler = scheduler;
        _priceWatch = priceWatch;
        _feedCache = feedCache;
        _searchHistory = searchHistory;
        foreach (var s in SortOptions)
            SortChips.Add(new SortChip(s.Label, s.Key));
    }

    /// Ключ кешу стрічки: лише «чисті» види (без пошуку/цінового фільтра/бейджа).
    private string CacheKey => $"{SelectedCategory?.Slug}|{SelectedSort?.Key}";

    private bool IsCleanView => !IsSearching && !OnlyVerified && !OnlyPumped
        && SelectedPrice?.MinKop is null && SelectedPrice?.MaxKop is null;

    // прийшли з каталогу (§17) АБО повернулись із «Каталогу товарів» (вибір через ".."):
    // категорія / пошук / заголовок. Після ініціалізації застосовуємо ОДРАЗУ.
    public void ApplyQueryAttributes(IDictionary<string, object> query)
    {
        if (query.TryGetValue("Category", out var cat) && cat is string s)
        {
            if (_ready)
                SelectedCategory = string.IsNullOrEmpty(s)
                    ? Categories.FirstOrDefault(c => string.IsNullOrEmpty(c.Slug))
                    : Categories.FirstOrDefault(c => c.Slug == s) ?? Categories[0];
            else if (s.Length > 0)
                _pendingCategory = s;
        }
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
        _ = LoadWatchMapAsync();   // серденька на картках; тихо і паралельно до категорій
        _ = LoadFreshnessAsync();  // «Ціни оновлено N хв тому» — теж тихо й паралельно
        // «Усі категорії» додаємо ДО запиту — щоб пікер не лишився порожнім, якщо мережа впаде
        Categories.Add(new Category { Slug = "", Name = "Усі категорії" });
        try
        {
            var cats = await _api.CategoriesAsync();
            foreach (var c in cats) Categories.Add(c);
        }
        catch { /* категорії необовʼязкові — «Усі» вже є */ }

        // пуш із каталогу → обрати ту категорію; без пушу — ОСТАННЯ вжита (людина
        // живе у 2-3 категоріях, щоразу відкривати «Усі» — зайвий тап)
        var wanted = _pendingCategory ?? Preferences.Default.Get("last_category", "");
        _selectedCategory = string.IsNullOrEmpty(wanted)
            ? Categories[0]
            : Categories.FirstOrDefault(c => c.Slug == wanted) ?? Categories[0];
        if (_pendingCategory is null && !string.IsNullOrEmpty(_selectedCategory.Slug))
            PageTitle = _selectedCategory.Name;
        if (!string.IsNullOrEmpty(_pendingQuery))
            _searchText = _pendingQuery;         // backing-поле: не тригерити debounce-reload тут
        var lastSort = Preferences.Default.Get("last_sort", "");
        _selectedSort = SortOptions.FirstOrDefault(s => s.Key == lastSort) ?? SortOptions[0];
        // backing-поля не проходять partial-хуки → залежне будуємо руками
        ApplyCategorySideEffects(_selectedCategory);
        SyncSortChips();
        _selectedPrice = PriceOptions[0];    // «Будь-яка ціна»
        OnPropertyChanged(nameof(SelectedCategory));
        OnPropertyChanged(nameof(SelectedSort));
        OnPropertyChanged(nameof(SelectedPrice));
        OnPropertyChanged(nameof(SearchText));

        // кеш-перший старт: остання перша сторінка цього виду — на екран МИТТЄВО,
        // свіже тихо замінить (ReloadAsync нижче)
        if (string.IsNullOrEmpty(_searchText))
        {
            var cached = _feedCache.TryLoad(CacheKey);
            if (cached is not null)
            {
                foreach (var d in cached)
                {
                    d.IsWatched = _watchIds.ContainsKey(d.StoreProductId);
                    Items.Add(d);
                }
            }
        }

        await ReloadAsync(keepCache: true);
        _ready = true;
    }

    // property-changed від пікерів → перезавантаження (після ініціалізації)
    partial void OnSelectedCategoryChanged(Category? value)
    {
        ApplyCategorySideEffects(value);
        Preferences.Default.Set("last_category", value?.Slug ?? "");   // пам'ять між запусками
        if (_ready) _ = ReloadAsync();
    }
    partial void OnSelectedSortChanged(SortOption? value)
    {
        SyncSortChips();
        Preferences.Default.Set("last_sort", value?.Key ?? "");
        if (_ready) _ = ReloadAsync();
    }
    partial void OnSelectedPriceChanged(PriceOption? value)
    {
        HasPriceFilter = value?.MinKop is not null || value?.MaxKop is not null;
        if (_ready && !_rebuildingPrices) _ = ReloadAsync();
    }

    private void SyncSortChips()
    {
        foreach (var ch in SortChips) ch.IsSelected = ch.Key == SelectedSort?.Key;
    }

    /// Тап по чіпу сортування.
    [RelayCommand]
    private void PickSort(SortChip? ch)
    {
        if (ch is null || ch.Key == SelectedSort?.Key) return;
        SelectedSort = SortOptions.First(s => s.Key == ch.Key);
    }

    // ── розумні порожні стани: дії замість глухого «нічого не знайдено» ──────────
    [RelayCommand]
    private void ClearPriceFilter() { if (PriceOptions.Count > 0) SelectedPrice = PriceOptions[0]; }

    [RelayCommand]
    private void SearchAllCategories() =>
        SelectedCategory = Categories.FirstOrDefault(c => string.IsNullOrEmpty(c.Slug));

    private bool _rebuildingPrices;   // зміна категорії міняє список цін — без другого reload

    /// Залежне від категорії: підпис кнопки, сусідні чіпи розділу, діапазони ціни.
    private void ApplyCategorySideEffects(Category? c)
    {
        var real = c is not null && !string.IsNullOrEmpty(c.Slug);
        SelectedCategoryLabel = real ? c!.Display : "Усі категорії";
        IsCategoryNarrowed = real;
        SyncCategoryWatched();
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

    /// Кнопка категорії → повноекранний «Каталог товарів» (E-Katalog-стиль);
    /// вибір повертається через ".." у ApplyQueryAttributes.
    [RelayCommand]
    private async Task OpenCategoryPicker() =>
        await Shell.Current.GoToAsync(nameof(CategoryPickerPage));

    /// Тап по чіпу сусідньої категорії → перемкнути.
    [RelayCommand]
    private void PickCategory(Category? c)
    {
        if (c is null) return;
        SelectedCategory = Categories.FirstOrDefault(x => x.Slug == c.Slug) ?? Categories[0];
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
            await MainThread.InvokeOnMainThreadAsync(() => ReloadAsync());
    }

    [RelayCommand]
    private async Task Refresh()
    {
        IsRefreshing = true;
        _ = LoadFreshnessAsync();
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

    private async Task ReloadAsync(bool keepCache = false)
    {
        var gen = ++_gen;              // нове покоління → будь-який in-flight запит застарілий
        _page = 0;
        _more = true;
        _searchWidened = false;        // новий запит — знову поважаємо обрану категорію
        SearchNote = null;
        ErrorMessage = null;
        _compareIds.Clear();           // новий вид → чисте порівняння (не при LoadMore)
        CanCompare = false;
        OnPropertyChanged(nameof(CompareButtonText));
        if (keepCache && Items.Count > 0)
        {
            _pendingCacheSwap = true;  // кеш лишається на екрані; свіже його замінить
        }
        else
        {
            _pendingCacheSwap = false;
            Items.Clear();
            ShowSkeleton = true;       // порожнеча до першої відповіді — скелетон-картки
        }
        IsLoading = true;
        await FetchAsync(gen);         // НЕ через LoadMore: свіжий reload не блокується IsLoading
    }

    /// Звірка стеження (серця на картках + дзвіночок категорії). Тихо: збій не ламає стрічку.
    private async Task LoadWatchMapAsync()
    {
        _watchIds.Clear();
        _watchCatIds.Clear();
        if (!_auth.IsLoggedIn) return;
        try
        {
            foreach (var w in await _api.WatchlistAsync())
            {
                if (w.Kind == "store_product" && w.RefId is int rid)
                    _watchIds[rid] = w.WatchlistId;
                if (w.Kind == "category" && !string.IsNullOrEmpty(w.QueryText))
                    _watchCatIds[w.QueryText!] = w.WatchlistId;
            }
            SyncCategoryWatched();
        }
        catch { /* серденька просто лишаться порожніми */ }
    }

    private void SyncCategoryWatched() =>
        IsCategoryWatched = SelectedCategory?.Slug is string s && s.Length > 0
                            && _watchCatIds.ContainsKey(s);

    /// Дзвіночок: стежити за категорією → сповіщення про нові знижки в ній.
    [RelayCommand]
    private async Task ToggleWatchCategory()
    {
        var slug = SelectedCategory?.Slug;
        if (string.IsNullOrEmpty(slug)) return;
        if (!_auth.IsLoggedIn)
        {
            await Shell.Current.GoToAsync(nameof(LoginPage));
            return;
        }
        Haptic.Tap();
        try
        {
            if (_watchCatIds.TryGetValue(slug!, out var wid))
            {
                await _api.UnwatchAsync(wid);
                _watchCatIds.Remove(slug!);
            }
            else
            {
                await _api.WatchCategoryAsync(slug!);
                await LoadWatchMapAsync();
                // дозвіл на сповіщення — саме в момент, коли людина попросила стежити
                await Permissions.RequestAsync<Permissions.PostNotifications>();
                _priceWatch.Enable();
            }
            SyncCategoryWatched();
        }
        catch { /* мережевий збій — стан не змінився */ }
    }

    /// «Ціни оновлено N хв тому» — чесна свіжість (тихо, збій не показуємо).
    private async Task LoadFreshnessAsync()
    {
        try
        {
            var m = await _api.FreshnessAsync();
            FreshnessText = m is null ? null
                : m < 2 ? "Ціни оновлено щойно"
                : m < 60 ? $"Ціни оновлено {m} хв тому"
                : $"Ціни оновлено {m / 60} год тому";
        }
        catch { FreshnessText = null; }
    }

    partial void OnOnlyVerifiedChanged(bool value) { if (_ready) _ = ReloadAsync(); }
    partial void OnOnlyPumpedChanged(bool value) { if (_ready) _ = ReloadAsync(); }

    /// Чіп «✓ Підтверджені». Взаємовиключний із «завищеною» — разом вони дали б
    /// порожню стрічку (жодна подія не буває в обох станах одночасно).
    [RelayCommand]
    private void ToggleVerified()
    {
        if (!OnlyVerified) OnlyPumped = false;
        OnlyVerified = !OnlyVerified;
    }

    /// Чіп «⚠ Завищена стара ціна».
    [RelayCommand]
    private void TogglePumped()
    {
        if (!OnlyPumped) OnlyVerified = false;
        OnlyPumped = !OnlyPumped;
    }

    /// Серденько на картці: додати/зняти стеження одним тапом, без відкриття картки.
    /// Оновлення рядка — заміною елемента (Discount без INPC, патерн IsOurChoice).
    /// Чекбокс «порівняти» на картці: додати/зняти (макс 4). Оновлення рядка — заміною
    /// елемента (Discount без INPC, патерн IsWatched).
    [RelayCommand]
    private void ToggleCompare(Discount? d)
    {
        if (d is null) return;
        if (_compareIds.Contains(d.StoreProductId))
        {
            _compareIds.Remove(d.StoreProductId);
            d.IsCompareSelected = false;
        }
        else
        {
            if (_compareIds.Count >= 4)      // стеля колонок — тихо ігноруємо 5-й
            {
                ErrorMessage = "Порівняти можна до 4 товарів";
                return;
            }
            _compareIds.Add(d.StoreProductId);
            d.IsCompareSelected = true;
            Haptic.Tap();
        }
        var i = Items.IndexOf(d);
        if (i >= 0) Items[i] = d;            // Replace → рядок перечитує CompareGlyph
        CanCompare = _compareIds.Count >= 2;
        OnPropertyChanged(nameof(CompareButtonText));
    }

    [RelayCommand]
    private async Task OpenCompare()
    {
        if (_compareIds.Count < 2) return;
        await Shell.Current.GoToAsync(nameof(ComparePage),
            new Dictionary<string, object> { ["Ids"] = string.Join(",", _compareIds) });
    }

    [RelayCommand]
    private void ClearCompare()
    {
        foreach (var d in Items.ToList())
            if (d.IsCompareSelected) { d.IsCompareSelected = false; var i = Items.IndexOf(d); if (i >= 0) Items[i] = d; }
        _compareIds.Clear();
        CanCompare = false;
        OnPropertyChanged(nameof(CompareButtonText));
    }

    [RelayCommand]
    private async Task ToggleWatch(Discount? d)
    {
        if (d is null) return;
        if (!_auth.IsLoggedIn)
        {
            await Shell.Current.GoToAsync(nameof(LoginPage));   // список належить акаунту
            return;
        }
        Haptic.Tap();
        try
        {
            if (_watchIds.TryGetValue(d.StoreProductId, out var wid))
            {
                await _api.UnwatchAsync(wid);
                _watchIds.Remove(d.StoreProductId);
                d.IsWatched = false;
            }
            else
            {
                await _api.WatchAsync(d.StoreProductId);
                await LoadWatchMapAsync();                      // дістати watchlist_id нового
                d.IsWatched = true;
            }
            var i = Items.IndexOf(d);
            if (i >= 0) Items[i] = d;                           // Replace → рядок перечитується
        }
        catch { /* мережевий збій — стан просто не змінився */ }
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
                onlyDiscounts: !IsSearching,
                badge: OnlyVerified ? "verified" : OnlyPumped ? "pumped" : null);
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

            if (_pendingCacheSwap)
            {
                Items.Clear();          // свіже приїхало — кеш-картки поступаються місцем
                _pendingCacheSwap = false;
            }
            foreach (var d in batch)
            {
                d.IsWatched = _watchIds.ContainsKey(d.StoreProductId);   // серденька
                d.IsCompareSelected = _compareIds.Contains(d.StoreProductId);   // чекбокс порівняння
                Items.Add(d);
            }
            _more = batch.Count >= 50;
            _page++;
            if (_page == 1 && IsCleanView && batch.Count > 0)
                _feedCache.Save(CacheKey, batch);        // перша сторінка «чистого» виду → кеш
            if (_page == 1 && IsSearching && batch.Count > 0)
                _searchHistory.Push(SearchText);         // успішний запит → історія пошуку
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
                ShowSkeleton = false;
                ShowEmpty = Items.Count == 0 && ErrorMessage is null;
            }
        }
    }
}
