using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

public record SortOption(string Label, string Key);
public record PriceOption(string Label, int? MinKop, int? MaxKop);   // межі — копійки (інв. A), null = без межі

public partial class HomeViewModel : ObservableObject
{
    private readonly ApiService _api;
    private readonly AuthService _auth;

    public ObservableCollection<Discount> Items { get; } = new();
    public ObservableCollection<Category> Categories { get; } = new();
    public IReadOnlyList<SortOption> SortOptions { get; } = new List<SortOption>
    {
        new("За знижкою", "discount"),     // T14 (агрегатор): дефолт — за заявленою знижкою
        new("Найновіші", "new"),
        new("Наш мінімум", "verified"),    // коротко — вміщається на пів-ширини поряд із ціною
    };
    public IReadOnlyList<PriceOption> PriceOptions { get; } = new List<PriceOption>
    {
        new("Будь-яка ціна", null, null),
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

        _selectedCategory = Categories[0];   // завжди є принаймні «Усі категорії»
        _selectedSort = SortOptions[0];
        _selectedPrice = PriceOptions[0];    // «Будь-яка ціна»
        OnPropertyChanged(nameof(SelectedCategory));
        OnPropertyChanged(nameof(SelectedSort));
        OnPropertyChanged(nameof(SelectedPrice));

        await ReloadAsync();
        _ready = true;
    }

    // property-changed від пікерів → перезавантаження (після ініціалізації)
    partial void OnSelectedCategoryChanged(Category? value) { if (_ready) _ = ReloadAsync(); }
    partial void OnSelectedSortChanged(SortOption? value) { if (_ready) _ = ReloadAsync(); }
    partial void OnSelectedPriceChanged(PriceOption? value) { if (_ready) _ = ReloadAsync(); }

    partial void OnSearchTextChanged(string value)
    {
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
        ErrorMessage = null;
        Items.Clear();
        IsLoading = true;
        await FetchAsync(gen);         // НЕ через LoadMore: свіжий reload не блокується IsLoading
    }

    private async Task FetchAsync(int gen)
    {
        try
        {
            var batch = await _api.DiscountsAsync(
                category: string.IsNullOrEmpty(SelectedCategory?.Slug) ? null : SelectedCategory!.Slug,
                q: SearchText,
                sort: SelectedSort?.Key ?? "discount",
                page: _page,
                priceMinKop: SelectedPrice?.MinKop,
                priceMaxKop: SelectedPrice?.MaxKop);
            if (gen != _gen) return;   // фільтр змінився під час запиту → відповідь застаріла
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
