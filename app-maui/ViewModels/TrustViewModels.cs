using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using System.Collections.ObjectModel;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

/// «Як ми перевіряємо знижки» — метод продукту всередині застосунку (S34).
///
/// Доти ця сторінка жила лише на сайті, і картка товару вела на неї ПОСИЛАННЯМ У
/// БРАУЗЕР. Тобто щоб дізнатись, що взагалі означає наша мітка, людина мусила вийти
/// із застосунку. Текст свідомо той самий, що на /how: два формулювання одного
/// методу розійшлися б за місяць.
public partial class HowViewModel : ObservableObject
{
    readonly ApiService _api;

    public HowViewModel(ApiService api) => _api = api;

    [ObservableProperty] bool _loading;
    [ObservableProperty] MarketIndex? _market;
    [ObservableProperty] bool _hasMarket;

    [RelayCommand]
    public async Task LoadAsync()
    {
        if (Loading) return;
        Loading = true;
        try
        {
            Market = await _api.MarketAsync();
            HasMarket = Market is not null;
        }
        // Ринковий зріз — доповнення, а не суть сторінки: метод описаний текстом і
        // без мережі. Тому мовчазне «не показуємо» тут краще за смугу помилки.
        catch { HasMarket = false; }
        finally { Loading = false; }
    }

    [RelayCommand]
    static async Task OpenVerifyAsync() =>
        await Shell.Current.GoToAsync(nameof(Views.VerifyPage));
}

/// «Чи не переписуємо ми історію» — щоденні печатки Меркла (S34).
public partial class VerifyViewModel : ObservableObject
{
    readonly ApiService _api;

    public VerifyViewModel(ApiService api) => _api = api;

    public ObservableCollection<DaySeal> Seals { get; } = new();

    [ObservableProperty] bool _loading;
    [ObservableProperty] string? _error;
    [ObservableProperty] bool _hasError;
    [ObservableProperty] bool _empty;

    [RelayCommand]
    public async Task LoadAsync()
    {
        if (Loading) return;
        Loading = true; HasError = false; Error = null;
        try
        {
            var r = await _api.VerifyChainAsync();
            Seals.Clear();
            foreach (var s in r?.Seals ?? new()) Seals.Add(s);
            // Печатка ставиться лише на ПОВНУ добу — інакше вона була б хибною за
            // побудовою. Порожній список у перший день роботи не помилка.
            Empty = Seals.Count == 0;
        }
        catch (Exception e) { HasError = true; Error = e.Message; }
        finally { Loading = false; }
    }
}

/// Канонічна модель: усі пропозиції одного артикула поруч (S34).
///
/// 16 286 моделей були доступні лише на сайті — порівняти ту саму річ між крамницями
/// в застосунку було неможливо, хоча ендпоінт існує з S30.
///
/// ⚠ Бейджі лишаються ПОСТОРІНКОВИМИ: закон говорить про мінімум за 30 днів у ЦЬОГО
/// продавця, тож «модельного» вердикту не існує і тут його не зʼявиться.
public partial class ModelViewModel : ObservableObject, IQueryAttributable
{
    readonly ApiService _api;

    public ModelViewModel(ApiService api) => _api = api;

    public ObservableCollection<ModelOffer> Offers { get; } = new();

    [ObservableProperty] int _productId;
    [ObservableProperty] ModelCard? _card;
    [ObservableProperty] bool _loading;
    [ObservableProperty] string? _error;
    [ObservableProperty] bool _hasError;
    [ObservableProperty] bool _ready;

    public void ApplyQueryAttributes(IDictionary<string, object> q)
    {
        if (q.TryGetValue("id", out var v) && int.TryParse(v?.ToString(), out var id))
        {
            ProductId = id;
            _ = LoadAsync();
        }
    }

    [RelayCommand]
    public async Task LoadAsync()
    {
        if (Loading || ProductId <= 0) return;
        Loading = true; HasError = false; Ready = false;
        try
        {
            var m = await _api.ModelAsync(ProductId);
            Card = m;
            Offers.Clear();
            var best = m?.MinKop;
            foreach (var o in m?.Offers ?? new())
            {
                // «найдешевше» позначаємо ПІСЛЯ завантаження, а не в моделі: ознака
                // стосується набору, а не самої пропозиції.
                o.IsBest = best is int b && o.CurrentKop == b;
                Offers.Add(o);
            }
            Ready = m is not null;
        }
        catch (Exception e) { HasError = true; Error = e.Message; }
        finally { Loading = false; }
    }

    [RelayCommand]
    static async Task OpenOfferAsync(ModelOffer? o)
    {
        if (o is null) return;
        await Shell.Current.GoToAsync($"{nameof(Views.DetailPage)}?id={o.StoreProductId}");
    }
}
