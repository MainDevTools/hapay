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
    public IReadOnlyList<SortOption> SortOptions { get; } = new List<SortOption>
    {
        // підписи короткі: пікери тепер по третині ширини (компактна панель фільтрів)
        new("За знижкою", "discount"),
        new("Де дешевше", "cheaper"),   // той самий товар дешевший в іншій крамниці
        new("Дешевші", "cheap"),
        new("Дорожчі", "expensive"),
        new("Найновіші", "new"),
    };
    public IReadOnlyList<PriceOption> PriceOptions { get; } = new List<PriceOption>
    {
        new("Будь-яка", null, null),   // «ціна» зайве — пікер і так підписаний; довше різалось
        new("до 500 ₴", null, 50_000),
        new("500–2 000 ₴", 50_000, 200_000),
        new("2 000–10 000 ₴", 200_000, 1_000_000),
        new("10 000–30 000 ₴", 1_000_000, 3_000_000),
        new("від 30 000 ₴", 3_000_000, null),
    };

    [ObservableProperty] private Category? _selectedCategory;
    [ObservableProperty] private SortOption? _selectedSort;
    [ObservableProperty] private PriceOption? _selectedPrice;
    [ObservableProperty] private string _searchText = "";
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

        // пуш із каталогу → обрати ту категорію; інакше «Усі»
        _selectedCategory = string.IsNullOrEmpty(_pendingCategory)
            ? Categories[0]
            : Categories.FirstOrDefault(c => c.Slug == _pendingCategory) ?? Categories[0];
        if (!string.IsNullOrEmpty(_pendingQuery))
            _searchText = _pendingQuery;         // backing-поле: не тригерити debounce-reload тут
        _selectedSort = SortOptions[0];
        _selectedPrice = PriceOptions[0];    // «Будь-яка ціна»
        OnPropertyChanged(nameof(SelectedCategory));
        OnPropertyChanged(nameof(SelectedSort));
        OnPropertyChanged(nameof(SelectedPrice));
        OnPropertyChanged(nameof(SearchText));

        await ReloadAsync();
        _ready = true;
    }

    // property-changed від пікерів → перезавантаження (після ініціалізації)
    partial void OnSelectedCategoryChanged(Category? value) { if (_ready) _ = ReloadAsync(); }
    partial void OnSelectedSortChanged(SortOption? value) { if (_ready) _ = ReloadAsync(); }
    partial void OnSelectedPriceChanged(PriceOption? value) { if (_ready) _ = ReloadAsync(); }

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
                    SearchNote = $"У «{SelectedCategory?.Name}» нічого — показуємо з усіх категорій";
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
                    : $"У «{SelectedCategory?.Name}» ціни в крамницях однакові — дешевшого поруч нема";

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
