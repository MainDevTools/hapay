using System.Collections.ObjectModel;
using System.Linq;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

/// «Мої відстеження»: товари, за ціною яких стежить користувач.
/// Показуємо рух ціни від моменту додавання — сервер зафіксував ту ціну сам,
/// тож це виміряний факт, а не наш підрахунок (§7.5).
public partial class WatchlistViewModel : ObservableObject
{
    private readonly ApiService _api;

    public ObservableCollection<WatchItem> Items { get; } = new();

    [ObservableProperty] private bool _isRefreshing;
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private bool _showEmpty;

    public WatchlistViewModel(ApiService api) => _api = api;

    public async Task InitializeAsync() => await LoadAsync();

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
            var all = await _api.WatchlistAsync();
            Items.Clear();
            // поки показуємо лише товари: стеження за категорією/запитом є в API,
            // але без сповіщень воно нічого не додає користувачеві
            foreach (var w in all.Where(w => w.Kind == "store_product"))
                Items.Add(w);
            ShowEmpty = Items.Count == 0;
        }
        catch (UnauthorizedException)
        {
            ErrorMessage = "Сесія застаріла — увійди ще раз";
            ShowEmpty = false;
        }
        catch (Exception e)
        {
            ErrorMessage = e.Message;
            ShowEmpty = false;
        }
    }

    [RelayCommand]
    private async Task Open(WatchItem? w)
    {
        if (w?.Url is string url && Uri.TryCreate(url, UriKind.Absolute, out var uri))
            await Launcher.Default.OpenAsync(uri);
    }

    [RelayCommand]
    private async Task Remove(WatchItem? w)
    {
        if (w is null) return;
        try
        {
            await _api.UnwatchAsync(w.WatchlistId);
            Items.Remove(w);
            ShowEmpty = Items.Count == 0;
        }
        catch (Exception e)
        {
            ErrorMessage = e.Message;
        }
    }
}
