using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

// IQueryAttributable (а не [QueryProperty]) — надійно застосовується Shell до BindingContext-VM.
public partial class DetailViewModel : ObservableObject, IQueryAttributable
{
    private readonly ApiService _api;

    [ObservableProperty] private Discount? _item;
    [ObservableProperty] private bool _loadingHistory;
    [ObservableProperty] private string? _historyNote;

    /// Точки для графіка — свій IDrawable читає цю колекцію (сходинки+розриви, T12).
    public ObservableCollection<HistoryPoint> History { get; } = new();

    public DetailViewModel(ApiService api) => _api = api;

    public void ApplyQueryAttributes(IDictionary<string, object> query)
    {
        if (query.TryGetValue("Discount", out var value) && value is Discount d)
            Item = d;   // setter → OnItemChanged → тягне історію
    }

    // прийшов товар через Shell-навігацію → тягнемо історію
    partial void OnItemChanged(Discount? value)
    {
        if (value is not null) _ = LoadHistory(value.StoreProductId);
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
