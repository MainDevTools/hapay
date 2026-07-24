using System.Collections.Specialized;
using Hapay.Drawables;
using Hapay.ViewModels;

namespace Hapay.Views;

public partial class DetailPage : ContentPage
{
    private readonly DetailViewModel _vm;
    private readonly PriceHistoryDrawable _drawable = new();

    public DetailPage(DetailViewModel vm)
    {
        InitializeComponent();
        BindingContext = _vm = vm;
        Chart.Drawable = _drawable;

        // історія вантажиться асинхронно у VM → щойно колекція оновилась, перемальовуємо графік
        _vm.History.CollectionChanged += OnHistoryChanged;
    }

    private void OnHistoryChanged(object? sender, NotifyCollectionChangedEventArgs e)
    {
        _drawable.Points = _vm.History.ToList();
        _drawable.SelectedIndex = null;      // нова історія — старий вибір недійсний
        ChartTip.IsVisible = false;
        Chart.Invalidate();
    }

    // тап/драг по графіку → найближчий вимір: маркер на графіку + «12.07 — 19 999 ₴»
    private void OnChartTouch(object? sender, TouchEventArgs e)
    {
        if (e.Touches.Length == 0 || Chart.Width <= 0) return;
        var idx = _drawable.HitIndex((float)e.Touches[0].X, (float)Chart.Width);
        if (idx is not int i || _drawable.SelectedIndex == i) return;
        _drawable.SelectedIndex = i;
        var p = _drawable.Points[i];
        ChartTip.Text = $"{p.Date:dd.MM} — {Models.Money.Grn(p.MinKop)}";
        ChartTip.IsVisible = true;
        Chart.Invalidate();
    }

    protected override void OnDisappearing()
    {
        base.OnDisappearing();
        _vm.History.CollectionChanged -= OnHistoryChanged;   // без витоку підписки
    }
}
