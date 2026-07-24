using Hapay.ViewModels;

namespace Hapay.Views;

public partial class CategoryPickerPage : ContentPage
{
    private readonly CategoryPickerViewModel _vm;

    public CategoryPickerPage(CategoryPickerViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }

    protected override async void OnAppearing()
    {
        base.OnAppearing();
        await _vm.InitializeAsync();
    }
}
