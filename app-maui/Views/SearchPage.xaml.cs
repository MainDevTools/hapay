using Hapay.ViewModels;

namespace Hapay.Views;

public partial class SearchPage : ContentPage
{
    private readonly SearchViewModel _vm;

    public SearchPage(SearchViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.InitializeAsync();
        // клавіатура одразу: людина прийшла сюди друкувати
        Dispatcher.Dispatch(() => Box.Focus());
    }
}
