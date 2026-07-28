using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

/// Перелік крамниць, за якими ми стежимо (S28). На сайті це `/stores` — застосунок
/// довго не мав нічого схожого, тобто людина не могла подивитись «а що взагалі є в
/// Comfy» чи «за ким ви стежите».
///
/// ⚠ Порядок — за нашим ПОКРИТТЯМ (скільки знижок бачимо), як і на сайті. Сортування
/// за часткою «накачаних» перетворило б перелік на рейтинг чесності, якого ми свідомо
/// не даємо: видимий шар не оцінює продавця (T12).
public partial class StoresViewModel : ObservableObject
{
    private readonly ApiService _api;

    public StoresViewModel(ApiService api) => _api = api;

    public ObservableCollection<Store> Items { get; } = new();

    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private bool _isRefreshing;
    [ObservableProperty] private string? _errorMessage;

    public bool IsEmpty => !IsBusy && Items.Count == 0;

    [RelayCommand]
    public async Task Load()
    {
        if (IsBusy) return;
        IsBusy = true; ErrorMessage = null;
        try
        {
            var rows = await _api.StoresAsync();
            Items.Clear();
            // крамниці без жодного товару ховаємо: порожній рядок нічого не каже
            foreach (var s in rows.Where(s => s.Products > 0)) Items.Add(s);
        }
        catch (Exception e)
        {
            ErrorMessage = $"Не вдалося завантажити перелік: {e.Message}";
        }
        finally
        {
            IsBusy = false; IsRefreshing = false;
            OnPropertyChanged(nameof(IsEmpty));
        }
    }

    [RelayCommand]
    private async Task Refresh() { IsRefreshing = true; await Load(); }

    [RelayCommand]
    private async Task OpenStore(Store? s)
    {
        if (s is null) return;
        await Shell.Current.GoToAsync($"{nameof(Views.StorePage)}?slug={s.Slug}");
    }
}
