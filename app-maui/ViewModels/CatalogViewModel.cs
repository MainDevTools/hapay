using System.Collections.ObjectModel;
using System.Linq;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

// Головна = сітка-каталог (E-Katalog, §17): категорії зі знижками, згруповані в розділи.
// Тап по плитці → HomePage зі стрічкою тієї категорії. Порожні категорії сервер не віддає.
public partial class CatalogViewModel : ObservableObject
{
    private readonly ApiService _api;
    private readonly AuthService _auth;

    public ObservableCollection<CategoryGroup> Groups { get; } = new();

    [ObservableProperty] private bool _isRefreshing;
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private bool _showEmpty;
    [ObservableProperty] private string _searchText = "";

    private bool _ready;

    public CatalogViewModel(ApiService api, AuthService auth)
    {
        _api = api;
        _auth = auth;
    }

    public async Task InitializeAsync()
    {
        if (_ready) return;
        await _auth.LoadAsync();   // підняти токен до першого запиту (як у HomeVM)
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
            // сервер уже сортує за розділом, тоді за к-стю → GroupBy зберігає цей порядок
            foreach (var g in cats.Where(c => !string.IsNullOrEmpty(c.Slug))
                                  .GroupBy(c => c.Section))
                Groups.Add(new CategoryGroup(g.Key, g));
            ShowEmpty = Groups.Count == 0;
        }
        catch (Exception e)
        {
            ErrorMessage = e.Message;
            ShowEmpty = Groups.Count == 0;
        }
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

    [RelayCommand]
    private async Task Account()
    {
        var route = _auth.IsLoggedIn ? nameof(ProfilePage) : nameof(LoginPage);
        await Shell.Current.GoToAsync(route);
    }
}
