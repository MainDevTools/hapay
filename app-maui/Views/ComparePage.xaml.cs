using Hapay.ViewModels;

namespace Hapay.Views;

public partial class ComparePage : ContentPage
{
    private readonly CompareViewModel _vm;

    public ComparePage(CompareViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.LoadAsync();
    }
}
