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

    public bool IsEmpty => !IsBusy && Items.Count == 0;

    partial void OnWindowIndexChanged(int value) => _ = Load();
    partial void OnOrderIndexChanged(int value) => _ = Load();

    [RelayCommand]
    public async Task Load()
    {
        if (IsBusy) return;
        IsBusy = true; ErrorMessage = null;
        try
        {
            var days = _days[Math.Clamp(WindowIndex, 0, _days.Length - 1)];
            var ord = _orderKeys[Math.Clamp(OrderIndex, 0, _orderKeys.Length - 1)];
            var r = await _api.MeasuredDropsAsync(days, ord);
            Items.Clear();
            foreach (var d in r?.Items ?? new()) Items.Add(d);

            // Подорожчання показуємо НАВМИСНО: без нього екран читався б як «усе
            // дешевшає», хоча підвищень зазвичай більше. Інакше це була б наша власна
            // накачана знижка — рівно те, що ми ловимо в крамниць.
            var s = r?.Summary;
            SummaryText = s is null || s.Compared == 0
                ? ""
                : $"Порівняли два виміри для {s.Compared} товарів: {s.Down} подешевшали, "
                  + $"{s.Up} подорожчали.";
        }
        catch (Exception e)
        {
            ErrorMessage = $"Не вдалося завантажити: {e.Message}";
        }
        finally
        {
            IsBusy = false; IsRefreshing = false;
            OnPropertyChanged(nameof(IsEmpty));
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
