using System.Collections.ObjectModel;
using System.Linq;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

// Повний екран пошуку (2026-07-25, замість лайт-чіпів на головній): одне поле,
// під ним НАЖИВО — збіги категорій + перші товари; порожнє поле — історія запитів.
// Тап по товару → картка; по категорії → стрічка; «Всі результати» → стрічка з q.
public partial class SearchViewModel : ObservableObject
{
    private readonly ApiService _api;
    private readonly SearchHistory _history;

    public ObservableCollection<Category> CategoryMatches { get; } = new();
    public ObservableCollection<Discount> Results { get; } = new();
    public ObservableCollection<string> History { get; } = new();

    [ObservableProperty] private string _searchText = "";
    [ObservableProperty] private bool _hasCategoryMatches;
    [ObservableProperty] private bool _hasResults;
    [ObservableProperty] private bool _hasMore;       // результатів ≥10 → «Всі результати»
    [ObservableProperty] private bool _showHistory;
    [ObservableProperty] private bool _isSearching;

    private readonly List<Category> _allCats = new();
    private int _gen;
    private CancellationTokenSource? _cts;

    public SearchViewModel(ApiService api, SearchHistory history)
    {
        _api = api;
        _history = history;
    }

    public async Task InitializeAsync()
    {
        RefreshHistory();
        try
        {
            _allCats.Clear();
            _allCats.AddRange((await _api.CategoriesAsync())
                              .Where(c => !string.IsNullOrEmpty(c.Slug)));
        }
        catch { /* категорійні підказки — бонус */ }
    }

    private void RefreshHistory()
    {
        History.Clear();
        foreach (var q in _history.Load()) History.Add(q);
        ShowHistory = History.Count > 0 && string.IsNullOrWhiteSpace(SearchText);
    }

    partial void OnSearchTextChanged(string value)
    {
        ShowHistory = History.Count > 0 && string.IsNullOrWhiteSpace(value);
        _cts?.Cancel();
        var cts = new CancellationTokenSource();
        _cts = cts;
        _ = DebouncedSearch(cts.Token);
    }

    private async Task DebouncedSearch(CancellationToken token)
    {
        try { await Task.Delay(300, token); }
        catch (TaskCanceledException) { return; }
        if (!token.IsCancellationRequested)
            await MainThread.InvokeOnMainThreadAsync(RunLiveSearch);
    }

    private async Task RunLiveSearch()
    {
        var gen = ++_gen;
        var q = SearchText?.Trim();
        if (string.IsNullOrEmpty(q) || q.Length < 2)
        {
            CategoryMatches.Clear();
            Results.Clear();
            HasCategoryMatches = HasResults = HasMore = false;
            return;
        }

        // категорії — миттєво, з кешованого списку
        CategoryMatches.Clear();
        foreach (var c in _allCats.Where(c =>
                     c.Name.Contains(q, StringComparison.CurrentCultureIgnoreCase)).Take(6))
            CategoryMatches.Add(c);
        HasCategoryMatches = CategoryMatches.Count > 0;

        IsSearching = true;
        try
        {
            var found = await _api.ProductsAsync(q: q, onlyDiscounts: false);
            if (gen != _gen) return;                 // текст уже змінився
            Results.Clear();
            foreach (var d in found.Take(10)) Results.Add(d);
            HasResults = Results.Count > 0;
            HasMore = found.Count >= 10;
        }
        catch { if (gen == _gen) { HasResults = Results.Count > 0; } }
        finally { if (gen == _gen) IsSearching = false; }
    }

    [RelayCommand]
    private async Task OpenProduct(Discount? d)
    {
        if (d is null) return;
        _history.Push(SearchText);                   // запит виявився корисним
        await Shell.Current.GoToAsync(nameof(DetailPage),
            new Dictionary<string, object> { ["Discount"] = d });
    }

    [RelayCommand]
    private async Task OpenCategory(Category? c)
    {
        if (c is null) return;
        await Shell.Current.GoToAsync($"../{nameof(HomePage)}",
            new Dictionary<string, object> { ["Category"] = c.Slug, ["Title"] = c.Name });
    }

    /// «Всі результати» / Enter — стрічка з цим запитом.
    [RelayCommand]
    private async Task RunFull()
    {
        var q = SearchText?.Trim();
        if (string.IsNullOrEmpty(q)) return;
        _history.Push(q);
        await Shell.Current.GoToAsync($"../{nameof(HomePage)}",
            new Dictionary<string, object> { ["Query"] = q, ["Title"] = $"Пошук: {q}" });
    }

    [RelayCommand]
    private void PickHistory(string? q)
    {
        if (!string.IsNullOrEmpty(q)) SearchText = q;   // debounce підхопить
    }

    [RelayCommand]
    private void DeleteHistory(string? q)
    {
        if (string.IsNullOrEmpty(q)) return;
        _history.Remove(q!);
        RefreshHistory();
    }
}
