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
    /// Скелетон на місці 🏆/«Де купити», поки офери в дорозі (блоки «вистрибували»
    /// зі зсувом лейауту — частина скарги на затримки 2026-07-24).
    [ObservableProperty] private bool _loadingOffers;

    /// Точки для графіка — свій IDrawable читає цю колекцію (сходинки+розриви, T12).
    public ObservableCollection<HistoryPoint> History { get; } = new();

    /// «Де купити» (T15): той самий товар (mpn) у крамницях, від найдешевшої.
    public ObservableCollection<Offer> Offers { get; } = new();

    // ── «Наш вибір» (S9-E2): прозорий скор зі складниками ─────────────────────────
    [ObservableProperty] private ChoiceResult? _choice;
    [ObservableProperty] private bool _isChoiceExpanded;   // tap розкриває складники

    public bool HasChoice => Choice is not null;
    public string ChoiceLine => Choice is null ? "" : $"🏆 Наш вибір: {Choice.OurChoice}";
    /// Рядок економії — лише коли вона Є: «економите 0 грн» звучало б як глум.
    public bool ShowSavings => (Choice?.SavingsKop ?? 0) > 0;
    public string ChoiceSavingsText => Choice is null ? "" :
        $"Ви економите {Money.Grn(Choice.SavingsKop)} у порівнянні з найдорожчим варіантом";

    partial void OnChoiceChanged(ChoiceResult? value)
    {
        OnPropertyChanged(nameof(HasChoice));
        OnPropertyChanged(nameof(ChoiceLine));
        OnPropertyChanged(nameof(ShowSavings));
        OnPropertyChanged(nameof(ChoiceSavingsText));
    }

    [RelayCommand]
    private void ToggleChoice() => IsChoiceExpanded = !IsChoiceExpanded;

    /// «Як ми рахуємо?» — формула з живими вагами, окремий toggle усередині блока.
    [ObservableProperty] private bool _isFormulaExpanded;

    [RelayCommand]
    private void ToggleFormula() => IsFormulaExpanded = !IsFormulaExpanded;

    /// ── Характеристики (S12): пари назва-значення з картки крамниці ───────────────
    [ObservableProperty] private SpecsResult? _specs;
    [ObservableProperty] private bool _isSpecsExpanded;    // згорнуто → перші 6 рядків

    public bool HasSpecs => Specs is not null && Specs.Attrs.Count > 0;
    /// Згорнуто — перші 6 пар; розгорнуто — всі. Кнопка лише коли є що розгортати.
    public List<SpecAttr> VisibleSpecs =>
        Specs is null ? new() : (IsSpecsExpanded ? Specs.Attrs : Specs.Attrs.Take(6).ToList());
    public bool ShowSpecsToggle => (Specs?.Attrs.Count ?? 0) > 6;
    public string SpecsToggleText => IsSpecsExpanded
        ? "Згорнути" : $"Показати всі ({Specs?.Attrs.Count ?? 0})";
    public string SpecsProvenance => Specs?.Provenance ?? "";

    partial void OnSpecsChanged(SpecsResult? value)
    {
        OnPropertyChanged(nameof(HasSpecs));
        OnPropertyChanged(nameof(VisibleSpecs));
        OnPropertyChanged(nameof(ShowSpecsToggle));
        OnPropertyChanged(nameof(SpecsToggleText));
        OnPropertyChanged(nameof(SpecsProvenance));
    }

    partial void OnIsSpecsExpandedChanged(bool value)
    {
        OnPropertyChanged(nameof(VisibleSpecs));
        OnPropertyChanged(nameof(SpecsToggleText));
    }

    [RelayCommand]
    private void ToggleSpecs() => IsSpecsExpanded = !IsSpecsExpanded;

    private async Task LoadSpecs(Task<SpecsResult?> specsTask)
    {
        try { Specs = await specsTask; }
        catch { Specs = null; }    // характеристики — бонус; збій не ламає картку
    }

    /// HTTP-запит вибору стартує РАЗОМ з оферами (послідовність давала подвійну
    /// затримку — скарга 2026-07-24); тут лише чекаємо результат і накладаємо на
    /// вже завантажені офери: переможцю 🏆, крамницям — бейдж перевірки знижок,
    /// і перебудовуємо колекцію, щоб BindableLayout перечитав обчислювані властивості.
    private async Task LoadChoice(Task<ChoiceResult?> choiceTask)
    {
        try
        {
            Choice = await choiceTask;
            if (Choice is null) return;
            var byStore = Choice.Candidates.ToDictionary(c => c.Store, c => c);
            var snapshot = Offers.ToList();
            foreach (var o in snapshot)
            {
                o.IsOurChoice = o.Store == Choice.OurChoice;
                // фактологічний бейдж перевірки знижок замість «чесність N%»
                // (юр-рішення 2026-07-24: без оцінок крамниці, лише наші перевірки)
                o.HonestyNote = byStore.TryGetValue(o.Store, out var c) ? c.DiscountBadge : null;
            }
            Offers.Clear();
            foreach (var o in snapshot) Offers.Add(o);
        }
        catch { Choice = null; }   // вибір — бонус; збій мережі не ламає картку
    }

    private readonly IPriceWatchScheduler _watchScheduler;
    private readonly RecentProducts _recent;

    public DetailViewModel(ApiService api, AuthService auth, IPriceWatchScheduler watchScheduler,
                           RecentProducts recent)
    {
        _api = api;
        _auth = auth;
        _watchScheduler = watchScheduler;
        _recent = recent;
    }

    // ── «Найнижча за 30 днів» (UX-пакет 2026-07-24): пряма Omnibus-цінність ─────────
    // Рахуємо з /history, ЧЕСНО до глибини даних: поки історії менш як 30 днів,
    // формулювання каже «з {дата}», не «за 30 днів» — не обіцяємо вікно, якого нема.
    [ObservableProperty] private string? _min30Text;
    [ObservableProperty] private bool _isAtMin30;
    [ObservableProperty] private string? _min30Badge;

    private void ComputeMin30()
    {
        Min30Text = null; IsAtMin30 = false; Min30Badge = null;
        if (Item is null || History.Count == 0) return;
        var cutoff = DateTime.Today.AddDays(-30);
        var window = History.Where(p => p.Date >= cutoff).ToList();
        if (window.Count == 0) return;
        var min = window.MinBy(p => p.MinKop)!;
        var full30 = window[0].Date <= cutoff.AddDays(3);   // історія покриває ~все вікно
        var span = full30 ? "за 30 днів" : $"з {window[0].Date:dd.MM}";
        Min30Text = $"Найнижча ціна {span}: {Money.Grn(min.MinKop)} ({min.Date:dd.MM})";
        if (Item.CurrentKop <= min.MinKop)
        {
            IsAtMin30 = true;
            Min30Badge = $"Зараз найнижча ціна {span}";
        }
    }

    /// «Поділитись» — системний share sheet: назва + ціна + посилання НА НАС.
    ///
    /// ⚠ Було посилання на КРАМНИЦЮ (Item.Url), і це віддавало кожен share конкуренту:
    /// одержувач бачив картку Rozetka, а не історію цін, тобто саме те, заради чого
    /// існує «Хапай». Тепер шлемо hapay.today/product/{id} — там і графік, і 30-денна
    /// база, і кнопка в крамницю за один дотик. Сторінка віддає прев'ю (og:) сама, тож
    /// у чаті картка розкривається з назвою й ціною.
    [RelayCommand]
    private async Task ShareProduct()
    {
        if (Item is null) return;
        var text = $"{Item.Title} — {PriceRangeText}" +
                   (Item.OffersN > 1 ? $" · порівняно в {Item.OffersN} крамницях" : "") +
                   $"\nhttps://hapay.today/product/{Item.StoreProductId}";
        await Share.Default.RequestAsync(new ShareTextRequest { Text = text, Title = Item.Title });
    }

    /// «ⓘ Як ми перевіряємо знижки» — прозорість детекції (юр-плюс: формулювання
    /// фактологічні, суголосні бейджам §5.4; «чесність крамниці» не оцінюємо).
    [RelayCommand]
    private async Task ExplainBadges() => await Shell.Current.DisplayAlert(
        "Як ми перевіряємо знижки",
        "Ми щодня зберігаємо ціни крамниць і звіряємо кожну знижку з правилом " +
        "закону №3153-IX: чесна «стара ціна» — це найнижча ціна за останні 30 днів.\n\n" +
        "✓ підтверджена — заявлена стара ціна збігається з нашою історією цін\n" +
        "· заявлена — історії ще замало, щоб перевірити\n" +
        "⚠ завищена — за 30 днів такої «старої» ціни ми не бачили\n\n" +
        "🏆 Наш вибір — відкрита формула з ціни, перевірки знижок і самовивозу " +
        "(складники — в блоці вибору). Крамниці не платять за позиції.",
        "Зрозуміло");

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
        Haptic.Tap();
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
        {
            Item = d;   // setter → OnItemChanged → тягне історію
            return;
        }
        // Глибоке посилання (hapay.today/product/{id}) приносить лише число — товар
        // доводиться дотягнути. Shell віддає значення рядком, звідки й розбір.
        if (query.TryGetValue("id", out var raw)
            && int.TryParse(Convert.ToString(raw), out var id) && id > 0)
            _ = LoadByIdAsync(id);
    }

    /// Товар за id: єдиний шлях, коли екран відкрили посиланням, а не зі стрічки.
    private async Task LoadByIdAsync(int id)
    {
        try
        {
            Item = await _api.CardAsync(id);
            if (Item is null) HistoryNote = "Товар не знайдено — можливо, він зник із продажу.";
        }
        catch (Exception e)
        {
            HistoryNote = $"Не вдалося відкрити товар: {e.Message}";
        }
    }

    // прийшов товар через Shell-навігацію → тягнемо історію + офери
    partial void OnItemChanged(Discount? value)
    {
        if (value is not null)
        {
            _ = LoadHistory(value.StoreProductId);
            _ = LoadOffers(value.StoreProductId);
            _ = LoadWatchStateAsync(value.StoreProductId);
            _recent.Push(value);   // «Нещодавно переглянуті» на головній (локально)
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
        // усі три запити СТАРТУЮТЬ одразу; choice/specs лише ЧЕКАЮТЬСЯ після оферів
        // (накладання бейджів потребує завантаженої колекції, а не відповіді сервера)
        var choiceTask = _api.ChoiceAsync(storeProductId);
        var specsTask = _api.SpecsAsync(storeProductId);
        LoadingOffers = true;
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
        LoadingOffers = false;
        // choice/specs таски стартували ПАРАЛЕЛЬНО вгорі — awaited ЗАВЖДИ (обидва
        // null-safe, свій try всередині), інакше їхній HTTP-виняток лишався б
        // unobserved у гілці «1 крамниця»/збій оферів (bug-review 2026-07-25).
        await LoadChoice(choiceTask);       // S9: null для <2 крамниць — просто не рендерить
        OnPropertyChanged(nameof(ShowBuyCta));
        OnPropertyChanged(nameof(BuyCtaText));
        await LoadSpecs(specsTask);         // S12: і для груп, і соло
    }

    /// Головна CTA (UX-пакет 2026-07-24): «Купити в {переможець 🏆} — {ціна}» —
    /// одна велика кнопка замість рівноправного списку. Ціна — ФАКТИЧНА цінникова
    /// крамниці (не ефективна з доставкою): людина побачить саме її на сайті.
    private Offer? BuyOffer =>
        Choice is null ? null : Offers.FirstOrDefault(o => o.Store == Choice.OurChoice);

    public bool ShowBuyCta => BuyOffer is not null;
    public string BuyCtaText =>
        BuyOffer is Offer o ? $"Купити в {o.Store} — {o.CurrentGrn}" : "";

    [RelayCommand]
    private async Task BuyBest()
    {
        Haptic.Tap();
        await OpenOffer(BuyOffer);
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
            ComputeMin30();     // «Найнижча за 30 днів» + бейдж «зараз найнижча»
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
