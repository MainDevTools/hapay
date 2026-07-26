using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

// Дашборд метрик (S16 П1): дані · детекція · збір по крамницях · акаунти.
// До S16 панель знала лише про акаунти — здоров'я самого продукту (скільки зібрано,
// що показала перевірка знижок, які крамниці мовчать) не було видно ніде.
public partial class AdminMetricsViewModel : ObservableObject
{
    private readonly ApiService _api;

    public ObservableCollection<BadgeRow> Badges { get; } = new();
    public ObservableCollection<StoreRow> Stores { get; } = new();

    [ObservableProperty] private bool _isLoading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private AdminMetrics? _metrics;

    public AdminMetricsViewModel(ApiService api) => _api = api;

    public async Task LoadAsync()
    {
        IsLoading = true;
        Error = null;
        try
        {
            var m = await _api.AdminMetricsAsync();
            Metrics = m;
            Badges.Clear();
            Stores.Clear();
            if (m is null) return;
            // порядок із сервера зберігаємо: нульові бейджі теж показуємо (тихий нуль —
            // визнаний дефект показників: verified=0 при 29 pumped це сигнал, не порожнеча)
            foreach (var b in m.Detection.Badges) Badges.Add(b);
            // мовчазні крамниці — нагору: саме вони потребують дії
            foreach (var s in m.Collect.Stores.OrderByDescending(x => x.OkMin ?? int.MaxValue))
                Stores.Add(s);
        }
        catch (UnauthorizedException) { Error = "Сесія завершилась — увійди знову."; }
        catch (Exception e) { Error = e.Message; }
        finally { IsLoading = false; }
    }

    [RelayCommand]
    private Task Refresh() => LoadAsync();
}
