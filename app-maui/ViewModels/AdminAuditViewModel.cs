using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Hapay.Models;
using Hapay.Services;

namespace Hapay.ViewModels;

// Журнал адмін-дій (S16 П3). До S16 `admin_audit` була write-only: слід писався, але
// прочитати його не було чим — тобто перевірити, хто роздав права, було неможливо.
public partial class AdminAuditViewModel : ObservableObject
{
    private readonly ApiService _api;

    public ObservableCollection<AuditEntry> Entries { get; } = new();

    [ObservableProperty] private bool _isLoading;
    [ObservableProperty] private string? _error;
    [ObservableProperty] private string _actionFilter = "усі дії";

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PageText))]
    [NotifyPropertyChangedFor(nameof(HasPages))]
    private int _page;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(PageText))]
    [NotifyPropertyChangedFor(nameof(HasPages))]
    private int _pages;
    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(TotalText))]
    private int _total;

    public string TotalText => $"записів: {Total}";
    public string PageText => $"{Page + 1} / {Math.Max(Pages, 1)}";
    public bool HasPages => Pages > 1;

    public string[] ActionFilters { get; } =
        { "усі дії", "зміна ролі", "бан / розбан", "підтвердження email",
          "скидання пароля", "видалення акаунта" };

    private static readonly (string Key, string Label)[] Actions =
    {
        ("set_role", "зміна ролі"), ("set_active", "бан / розбан"),
        ("verify_email", "підтвердження email"), ("send_reset", "скидання пароля"),
        ("delete_user", "видалення акаунта"),
    };

    public AdminAuditViewModel(ApiService api) => _api = api;

    public async Task LoadAsync()
    {
        IsLoading = true;
        Error = null;
        try
        {
            var key = Actions.FirstOrDefault(a => a.Label == ActionFilter).Key;
            var r = await _api.AdminAuditAsync(key, Page);
            Entries.Clear();
            foreach (var e in r.Entries) Entries.Add(e);
            Total = r.Total;
            Pages = r.Pages;
            Page = r.Page;
        }
        catch (UnauthorizedException) { Error = "Сесія завершилась — увійди знову."; }
        catch (Exception e) { Error = e.Message; }
        finally { IsLoading = false; }
    }

    partial void OnActionFilterChanged(string value)
    {
        Page = 0;
        _ = LoadAsync();
    }

    [RelayCommand]
    private Task Refresh() => LoadAsync();

    [RelayCommand]
    private async Task PrevPage()
    {
        if (Page <= 0) return;
        Page--;
        await LoadAsync();
    }

    [RelayCommand]
    private async Task NextPage()
    {
        if (Page + 1 >= Pages) return;
        Page++;
        await LoadAsync();
    }
}
