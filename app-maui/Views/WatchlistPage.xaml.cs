using Hapay.ViewModels;

namespace Hapay.Views;

public partial class WatchlistPage : ContentPage
{
    private readonly WatchlistViewModel _vm;

    public WatchlistPage(WatchlistViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    // без guard-прапорця: список має оновлюватись при кожному поверненні на екран
    // (ціни змінюються, і сенс екрана саме в тому, щоб показувати свіже)
    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.InitializeAsync();
    }
}
