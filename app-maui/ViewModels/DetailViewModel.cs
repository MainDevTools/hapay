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
    [ObservableProperty] private bool _isWatched;      // вже у відстеженні
    private int? _watchlistId;                         // потрібен, щоб зняти зі стеження

    /// Напис на кнопці залежить від стану — інакше після натискання екран виглядає так,
    /// ніби нічого не сталося, і людина тисне вдруге.
    public string WatchButtonText => IsWatched ? "Ви стежите — прибрати" : "Стежити за ціною";

    partial void OnIsWatchedChanged(bool value) => OnPropertyChanged(nameof(WatchButtonText));
    [ObservableProperty] private bool _loadingHistory;
    [ObservableProperty] private string? _historyNote;
    [ObservableProperty] private bool _hasOffers;   // ≥2 крамниці — тоді блок «Де купити» видно

    /// Точки для графіка — свій IDrawable читає цю колекцію (сходинки+розриви, T12).
    public ObservableCollection<HistoryPoint> History { get; } = new();

    /// «Де купити» (T15): той самий товар (mpn) у крамницях, від найдешевшої.
    public ObservableCollection<Offer> Offers { get; } = new();

    private readonly IPriceWatchScheduler _watchScheduler;

    public DetailViewModel(ApiService api, AuthService auth, IPriceWatchScheduler watchScheduler)
    {
        _api = api;
        _auth = auth;
        _watchScheduler = watchScheduler;
    }

    /// Стежити може лише залогінений — інакше нема кому належати списку.
    public bool CanWatch => _auth.IsLoggedIn;

    /// Чи цей товар уже у відстеженні — щоб кнопка показувала стан, а не питання.
    private async Task LoadWatchStateAsync(int storeProductId)
    {
        if (!_auth.IsLoggedIn) return;
        try
        {
            var wl = await _api.WatchlistAsync();
            var mine = wl.FirstOrDefault(w => w.Kind == "store_product" && w.RefId == storeProductId);
            _watchlistId = mine?.WatchlistId;
            IsWatched = mine is not null;
        }
        catch { /* стан кнопки — не привід ламати картку */ }
    }

    [RelayCommand]
    private async Task Watch()
    {
        if (Item is null || WatchBusy) return;
        WatchBusy = true;
        WatchNote = null;
        try
        {
            if (IsWatched)                       // повторний тап = зняти зі стеження
            {
                if (_watchlistId is int id) await _api.UnwatchAsync(id);
                IsWatched = false;
                _watchlistId = null;
                WatchNote = "Прибрано зі стеження";
                return;
            }
            await _api.WatchAsync(Item.StoreProductId);
            IsWatched = true;
            await LoadWatchStateAsync(Item.StoreProductId);   // дістати watchlist_id для зняття
            // дозвіл питаємо САМЕ тут — у момент, коли користувач попросив стежити,
            // а не на старті застосунку «про всяк випадок»
            var granted = await Permissions.RequestAsync<Permissions.PostNotifications>();
            _watchScheduler.Enable();     // перевірка працює і без дозволу — просто мовчки
            WatchNote = granted == PermissionStatus.Granted
                ? "Стежимо — сповістимо, коли подешевшає"
                : "Стежимо. Сповіщення вимкнені — дивись у профілі";
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
            _ = LoadWatchStateAsync(value.StoreProductId);
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
            // Уцінене з діапазону ВИКЛЮЧАЄМО: діапазон описує ринок нового товару, і
            // ціна відкритої коробки занижувала б його нижню межу. Якщо ЧИСТИХ немає
            // взагалі — беремо всі, бо тоді інших цін на цей товар у нас просто нема.
            var src = Offers.Where(o => !o.IsUsed).ToList();
            if (src.Count == 0) src = Offers.ToList();
            if (src.Count >= 1)
            {
                var min = src.Min(o => o.CurrentKop);
                var max = src.Max(o => o.CurrentKop);
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

    /// Графік має сенс лише коли є ЩО малювати: від двох точок І з реальним рухом ціни.
    ///
    /// Спершу тут була сама лише умова «≥2 точки». На живому кадрі вийшло гірше за
    /// порожнечу: при незмінній ціні графік малював самотню червону риску над кнопкою —
    /// схоже на артефакт розмітки, а не на дані. Причому підпис поруч уже казав те саме
    /// словами («Ціна не змінювалась з 20.07»), тобто риска не додавала нічого.
    [ObservableProperty] private bool _hasChart;

    /// Чи всі виміри однакові (ціна не рухалась) — тоді малювати нема чого.
    private bool HistoryIsFlat() =>
        History.Count > 0
        && History.All(p => p.MinKop == History[0].MinKop && p.MaxKop == History[0].MinKop);

    /// Підпис під графіком. Кажемо те, що ЗНАЄМО, а не вибачаємось загальним «замало
    /// вимірів»: якщо ціна два дні поспіль однакова — це вже корисний факт. І навпаки,
    /// на одному вимірі стверджувати «не змінювалась» не можна (§7.5) — нема з чим порівняти.
    private string? DescribeHistory()
    {
        if (History.Count == 0) return "Історія ще порожня — перший вимір попереду";
        if (History.Count == 1) return $"Поки один вимір — {History[0].Date:dd.MM}";
        // мінялась — графік сам скаже; не мінялась — скаже цей рядок, і графік зайвий
        return HistoryIsFlat() ? $"Ціна не змінювалась з {History[0].Date:dd.MM}" : null;
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
            HistoryNote = DescribeHistory();
            HasChart = History.Count >= 2 && !HistoryIsFlat();
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
