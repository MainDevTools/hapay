using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

/// Одна крамниця: ФАКТИ спостережень і її найбільші категорії.
///
/// ⚠ Свідомо БЕЗ частки «накачаних» знижок і без будь-якої оцінки продавця. Це не
/// сором'язливість: мітка стосується ОКРЕМОЇ знижки, а «без мітки» означає лише те,
/// що історії ще замало. Історія почалась 18.07, тож у великої крамниці зараз буває
/// 1758 знижок і одна перевірена — без пояснення поруч такий екран читався б як
/// звинувачення, хоча каже протилежне.
public partial class StoreViewModel : ObservableObject, IQueryAttributable
{
    private readonly ApiService _api;

    public StoreViewModel(ApiService api) => _api = api;

    [ObservableProperty] private Store? _store;
    [ObservableProperty] private bool _isBusy;
    [ObservableProperty] private string? _errorMessage;

    public string Title => Store?.Name ?? "Крамниця";
    public bool HasStore => Store is not null;

    partial void OnStoreChanged(Store? value)
    {
        OnPropertyChanged(nameof(Title));
        OnPropertyChanged(nameof(HasStore));
    }

    public void ApplyQueryAttributes(IDictionary<string, object> query)
    {
        if (query.TryGetValue("slug", out var raw))
        {
            var slug = Convert.ToString(raw) ?? "";
            if (!string.IsNullOrWhiteSpace(slug)) _ = Load(slug);
        }
    }

    private async Task Load(string slug)
    {
        IsBusy = true; ErrorMessage = null;
        try
        {
            Store = await _api.StoreAsync(slug);
            if (Store is null) ErrorMessage = "Такої крамниці ми не відстежуємо.";
        }
        catch (Exception e)
        {
            ErrorMessage = $"Не вдалося відкрити крамницю: {e.Message}";
        }
        finally { IsBusy = false; }
    }

    /// Категорія крамниці веде в ЗАГАЛЬНУ стрічку цієї категорії — так само, як на
    /// сайті. Окремої «стрічки крамниці» немає навмисно: сервер фільтрує за категорією,
    /// а не за джерелом, і вигадувати клієнтський фільтр означало б показувати не те,
    /// що людина побачить, повернувшись через каталог.
    [RelayCommand]
    private async Task OpenCategory(Category? c)
    {
        if (c is null) return;
        // Ключі словника — ті самі, що в CatalogViewModel.OpenCategory: HomeViewModel
        // читає саме "Category" і "Title". Підглянув у сусідній файл, а не згадав.
        await Shell.Current.GoToAsync(nameof(Views.HomePage),
            new Dictionary<string, object> { ["Category"] = c.Slug, ["Title"] = c.Name });
    }

    [RelayCommand]
    private async Task OpenSite()
    {
        if (Store is null || string.IsNullOrWhiteSpace(Store.BaseUrl)) return;
        try { await Browser.Default.OpenAsync(Store.BaseUrl, BrowserLaunchMode.SystemPreferred); }
        catch (Exception e) { ErrorMessage = e.Message; }
    }
}
