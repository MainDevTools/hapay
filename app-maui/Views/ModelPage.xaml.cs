using Hapay.ViewModels;

namespace Hapay.Views;

public partial class ModelPage : ContentPage
{
    private readonly ModelViewModel _vm;

    public ModelPage(ModelViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
    }
    // ModelPage вантажиться з ApplyQueryAttributes (id приходить маршрутом), тож
    // OnAppearing тут нічого не робить — інакше був би другий запит на кожен показ.
}
