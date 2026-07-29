using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

/// «Що подешевшало» — ВИМІРЯНІ зниження цін (S28).
///
/// Наш єдиний актив, який неможливо підробити: знижку оголошує крамниця (її можна
/// намалювати), а зниження ціни міряємо ми. До 28.07 воно існувало лише персонально
/// (watchlist), тобто вимагало реєстрації й ручного додавання товару.
public partial class DropsViewModel : ObservableObject
{
    private readonly ApiService _api;

    public DropsViewModel(ApiService api) => _api = api;

    public ObservableCollection<MeasuredDrop> Items { get; } = new();

    /// Проміжок порівняння. Ширший проміжок — не «більше знижок», а інша база: ми
    /// беремо останній вимір ДО нього.
    public List<string> Windows { get; } = new() { "За добу", "За 3 дні", "За тиждень" };
    private static readonly int[] _days = { 1, 3, 7 };

    /// ⚠ «Щойно виміряні» — саме ЗА ЗАМОВЧУВАННЯМ, і це не смак. Сортування за
    /// відсотком підіймає артефакти за побудовою: будь-який шум вимірювання виглядає
    /// як величезне зниження. Заміряно 28.07 — перша видача очолювалась «−86%» на
    /// кормі, що виявилось зміною фасування на сторінці крамниці, а не ціною.
    public List<string> Orders { get; } = new() { "Щойно виміряні", "Найбільші зниження" };
    private static readonly string[] _orderKeys = { "fresh", "deep" };

    [ObservableProperty] private int _windowIndex;
    [ObservableProperty] private int _orderIndex;
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private bool _isRefreshing;
    [ObservableProperty] private string? _errorMessage;
    [ObservableProperty] private string _summaryText = "";

    /* ── дозавантаження (S35) ──────────────────────────────────────────────────
       Заміряно 2026-07-29: сервер віддає сторінки (`/api/drops?page=1` → ще 50),
       а екран просив лише нульову — і не мав ні кнопки «показати ще», ні
       нескінченної стрічки. Тобто «Що подешевшало» показувало рівно перші 50
       позицій і крапку, назавжди.

       ⚠ З семи екранів, які я спершу перелічив як «без дозавантаження», решті
       шести воно НЕ потрібне: у крамницях 30 записів, картка крамниці віддає
       статистику, стеження — власний список людини, каталог зібраний із каруселей,
       а пошук навмисно показує 10 підказок і має вихід «Всі результати» у стрічку,
       де нескінченне гортання вже є. Заміряно, а не припущено. */
    private int _page;
    private bool _endReached;

    public bool IsEmpty => !IsBusy && Items.Count == 0;
    public bool CanLoadMore => !IsBusy && !_endReached && Items.Count > 0;

    partial void OnWindowIndexChanged(int value) => _ = Load();
    partial void OnOrderIndexChanged(int value) => _ = Load();

    [RelayCommand]
    public async Task Load()
    {
        if (IsBusy) return;
        IsBusy = true; ErrorMessage = null;
        _page = 0; _endReached = false;
        try
        {
            var days = _days[Math.Clamp(WindowIndex, 0, _days.Length - 1)];
            var ord = _orderKeys[Math.Clamp(OrderIndex, 0, _orderKeys.Length - 1)];
            var r = await _api.MeasuredDropsAsync(days, ord, 0);
            Items.Clear();
            var got = r?.Items ?? new();
            foreach (var d in got) Items.Add(d);
            _endReached = got.Count < PageSize;

            // Подорожчання показуємо НАВМИСНО: без нього екран читався б як «усе
            // дешевшає», хоча підвищень зазвичай більше. Інакше це була б наша власна
            // накачана знижка — рівно те, що ми ловимо в крамниць.
            var s = r?.Summary;
            SummaryText = s is null || s.Compared == 0
                ? ""
                // Money.N, не сира інтерполяція: «16868» замість «16 868» — те саме,
                // що сьогодні вже ловили на ринковому зрізі.
                : $"Порівняли два виміри для {Money.N(s.Compared)} товарів: "
                  + $"{Money.N(s.Down)} подешевшали, {Money.N(s.Up)} подорожчали.";
        }
        catch (Exception e)
        {
            ErrorMessage = $"Не вдалося завантажити: {e.Message}";
        }
        finally
        {
            IsBusy = false; IsRefreshing = false;
            OnPropertyChanged(nameof(IsEmpty));
            OnPropertyChanged(nameof(CanLoadMore));
        }
    }

    /// Розмір сторінки задає СЕРВЕР (limit=50 у /api/drops). Тримаємо константу тут
    /// лише щоб зрозуміти «прийшло менше — далі нічого немає»; змінювати її наосліп
    /// не можна: тоді кінець списку визначався б хибно.
    private const int PageSize = 50;

    /// Дозавантаження наступної сторінки. Мовчазне: помилку на ДОвантаженні не
    /// показуємо смугою — уже показаний список важливіший за повідомлення про те,
    /// чого людина ще не бачила. Наступна спроба гортання спробує знову.
    [RelayCommand]
    private async Task LoadMore()
    {
        if (IsBusy || _endReached || Items.Count == 0) return;
        IsBusy = true;
        try
        {
            var days = _days[Math.Clamp(WindowIndex, 0, _days.Length - 1)];
            var ord = _orderKeys[Math.Clamp(OrderIndex, 0, _orderKeys.Length - 1)];
            var r = await _api.MeasuredDropsAsync(days, ord, _page + 1);
            var got = r?.Items ?? new();
            foreach (var d in got) Items.Add(d);
            _page++;
            _endReached = got.Count < PageSize;
        }
        catch { _endReached = true; }
        finally
        {
            IsBusy = false;
            OnPropertyChanged(nameof(CanLoadMore));
        }
    }

    [RelayCommand]
    private async Task Refresh() { IsRefreshing = true; await Load(); }

    /// Відкриваємо СТОРІНКУ товару: там історія ціни й провенанс, тобто те, що робить
    /// зниження перевірюваним. Екран деталей уміє тягнути товар за самим id (S25).
    [RelayCommand]
    private async Task OpenDrop(MeasuredDrop? d)
    {
        if (d is null) return;
        await Shell.Current.GoToAsync(nameof(Views.DetailPage),
            new Dictionary<string, object> { ["id"] = d.StoreProductId });
    }
}
