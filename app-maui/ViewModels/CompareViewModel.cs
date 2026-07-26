using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;
using Hapay.Views;

namespace Hapay.ViewModels;

// Порівняння товарів side-by-side (S14). Ids приходять із HomeViewModel через
// query-атрибут; тягне /api/compare і будує колонки + таблицю характеристик.
public partial class CompareViewModel : ObservableObject, IQueryAttributable
{
    private readonly ApiService _api;

    public ObservableCollection<CompareProduct> Products { get; } = new();
    public ObservableCollection<SpecRow> SpecRows { get; } = new();

    [ObservableProperty] private bool _isLoading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private bool _hasSpecs;
    [ObservableProperty] private bool _showSpecsPending;   // характеристики ще не зібрані (S12)

    private string _ids = "";

    public CompareViewModel(ApiService api) => _api = api;

    public void ApplyQueryAttributes(IDictionary<string, object> query)
    {
        if (query.TryGetValue("Ids", out var v) && v is string s) _ids = s;
    }

    public async Task LoadAsync()
    {
        if (string.IsNullOrEmpty(_ids)) return;
        IsLoading = true;
        Error = null;
        try
        {
            var ids = _ids.Split(',').Select(int.Parse);
            var res = await _api.CompareAsync(ids);
            Products.Clear();
            SpecRows.Clear();
            if (res is not null)
            {
                foreach (var p in res.Products) Products.Add(p);
                foreach (var r in res.SpecRows) SpecRows.Add(r);
            }
            HasSpecs = SpecRows.Count > 0;
            // характеристики частково покриті (S12 у вільних слотах) — чесний плейсхолдер
            ShowSpecsPending = !HasSpecs && Products.Count > 0;
        }
        catch (Exception e) { Error = e.Message; }
        finally { IsLoading = false; }
    }

    /// Тап по колонці товару → його картка.
    [RelayCommand]
    private async Task OpenProduct(CompareProduct? p)
    {
        if (p is null) return;
        // передаємо як Discount-заглушку через store_product_id (DetailPage сам дотягне)
        await Shell.Current.GoToAsync(nameof(DetailPage),
            new Dictionary<string, object>
            { ["Discount"] = new Discount { StoreProductId = p.StoreProductId, Title = p.Title,
                                            ImageUrl = p.ImageUrl, CurrentKop = p.PriceKop ?? 0 } });
    }
}
