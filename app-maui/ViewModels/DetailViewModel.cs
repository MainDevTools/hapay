using System.Collections.ObjectModel;
using System.Linq;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

// IQueryAttributable (а не [QueryProperty]) — надійно застосовується Shell до BindingContext-VM.
public partial class DetailViewModel : ObservableObject, IQueryAttributable
{
    private readonly ApiService _api;
    private readonly AuthService _auth;

    [ObservableProperty] private Discount? _item;
    [ObservableProperty] private bool _watchBusy;
    [ObservableProperty] private string? _watchNote;   // результат дії — коротко, у картці
    [ObservableProperty] private bool _loadingHistory;
    [ObservableProperty] private string? _historyNote;
    [ObservableProperty] private bool _hasOffers;   // ≥2 крамниці — тоді блок «Де купити» видно

    /// Точки для графіка — свій IDrawable читає цю колекцію (сходинки+розриви, T12).
    public ObservableCollection<HistoryPoint> History { get; } = new();

    /// «Де купити» (T15): той самий товар (mpn) у крамницях, від найдешевшої.
    public ObservableCollection<Offer> Offers { get; } = new();

    public DetailViewModel(ApiService api, AuthService auth)
    {
        _api = api;
        _auth = auth;
    }

    /// Стежити може лише залогінений — інакше нема кому належати списку.
    public bool CanWatch => _auth.IsLoggedIn;

    [RelayCommand]
    private async Task Watch()
    {
        if (Item is null || WatchBusy) return;
        WatchBusy = true;
        WatchNote = null;
        try
        {
            await _api.WatchAsync(Item.StoreProductId);
            WatchNote = "Стежимо за ціною — дивись у профілі";
        }
        catch (UnauthorizedException)
        {
            WatchNote = "Треба увійти в акаунт";
        }
        catch (Exception e)
        {
            WatchNote = $"Не вдалося: {e.Message}";
        }
        finally
        {
            WatchBusy = false;
        }
    }

    public void ApplyQueryAttributes(IDictionary<string, object> query)
    {
        if (query.TryGetValue("Discount", out var value) && value is Discount d)
            Item = d;   // setter → OnItemChanged → тягне історію
    }

    // прийшов товар через Shell-навігацію → тягнемо історію + офери
    partial void OnItemChanged(Discount? value)
    {
        if (value is not null)
        {
            _ = LoadHistory(value.StoreProductId);
            _ = LoadOffers(value.StoreProductId);
        }
        // до завантаження оферів — фолбек на ціну самого товару
        OnPropertyChanged(nameof(PriceRangeText));
        OnPropertyChanged(nameof(ShowSingleDiscount));
        OnPropertyChanged(nameof(PageTitle));
    }

    /// «Наявно в N крамницях» — під ціною, щоб було видно без скролу до «Де купити».
    public string OffersLine => $"Наявно в {Offers.Count} крамницях";

    /// Діапазон цін по крамницях (згори картки, §17): «5 999 – 6 499 ₴» або одна ціна.
    /// З тих самих оферів, що й «Де купити» → узгоджено. Показує, що навіть без «знижки»
    /// в іншій крамниці може бути дешевше (навіщо тоді знижка).
    public string PriceRangeText
    {
        get
        {
            if (Offers.Count >= 1)
            {
                var min = Offers.Min(o => o.CurrentKop);
                var max = Offers.Max(o => o.CurrentKop);
                return min == max ? Money.Grn(min) : $"{Money.Grn(min)} – {Money.Grn(max)}";
            }
            return Item?.CurrentGrn ?? "—";
        }
    }

    /// Класичний блок «стара ціна + −%» — лише для однієї крамниці (без діапазону).
    public bool ShowSingleDiscount => !HasOffers && (Item?.HasPct ?? false);

    /// Заголовок сторінки. Для ГРУПИ назва однієї крамниці ввела б в оману (товар у кількох) —
    /// там показуємо суть сторінки; для однієї крамниці її назва доречна.
    public string PageTitle => HasOffers ? "Порівняння цін" : (Item?.Store ?? "Товар");

    private async Task LoadOffers(int storeProductId)
    {
        try
        {
            var offers = await _api.OffersAsync(storeProductId);
            Offers.Clear();
            foreach (var o in offers) Offers.Add(o);
            HasOffers = Offers.Count > 1;   // група з 1 = сам товар, блок не потрібен
            OnPropertyChanged(nameof(OffersLine));
            OnPropertyChanged(nameof(PriceRangeText));       // діапазон рахується з оферів
            OnPropertyChanged(nameof(ShowSingleDiscount));
            OnPropertyChanged(nameof(PageTitle));            // група → «Порівняння цін»
        }
        catch
        {
            HasOffers = false;              // офери — бонус; збій мережі не ламає картку
            OnPropertyChanged(nameof(PriceRangeText));       // фолбек на ціну товару
            OnPropertyChanged(nameof(ShowSingleDiscount));
            OnPropertyChanged(nameof(PageTitle));
        }
    }

    [RelayCommand]
    private async Task OpenOffer(Offer? o)
    {
        if (o?.Url is string url && Uri.TryCreate(url, UriKind.Absolute, out var uri))
            await Launcher.Default.OpenAsync(uri);
    }

    private async Task LoadHistory(int storeProductId)
    {
        LoadingHistory = true;
        HistoryNote = null;
        try
        {
            var pts = await _api.HistoryAsync(storeProductId);
            History.Clear();
            foreach (var p in pts) History.Add(p);
            if (History.Count < 2)
                HistoryNote = "Замало вимірів — історія ще накопичується";
        }
        catch (Exception e)
        {
            HistoryNote = $"Не вдалося завантажити історію: {e.Message}";
        }
        finally
        {
            LoadingHistory = false;
        }
    }

    [RelayCommand]
    private async Task OpenStore()
    {
        if (Item?.Url is string url && Uri.TryCreate(url, UriKind.Absolute, out var uri))
            await Launcher.Default.OpenAsync(uri);
    }
}
