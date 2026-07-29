using Hapay.ViewModels;

namespace Hapay.Views;

public partial class HowPage : ContentPage
{
    private readonly HowViewModel _vm;

    public HowPage(HowViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();
        _ = _vm.LoadAsync();
    }
}
