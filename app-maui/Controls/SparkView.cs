using Hapay.Drawables;

namespace Hapay.Controls;

/// GraphicsView, який уміє байндитись у DataTemplate.
///
/// Навіщо власний контрол: `Drawable` — звичайна властивість, і задати її з байндингу
/// на елемент колекції означало б тримати по одному drawable на кожну картку в
/// ресурсах. Тут drawable один на екземпляр view, а дані приходять байндингом і
/// самі перемальовують полотно.
public sealed class SparkView : GraphicsView
{
    readonly SparkDrawable _d = new();

    public static readonly BindableProperty PointsProperty = BindableProperty.Create(
        nameof(Points), typeof(List<List<long>>), typeof(SparkView), null,
        propertyChanged: (b, _, v) =>
        {
            var s = (SparkView)b;
            s._d.Points = (v as List<List<long>>)?.ConvertAll(p => (IReadOnlyList<long>)p)
                          ?? (IReadOnlyList<IReadOnlyList<long>>)Array.Empty<long[]>();
            s.Invalidate();
        });

    public static readonly BindableProperty DaysProperty = BindableProperty.Create(
        nameof(Days), typeof(int), typeof(SparkView), 30,
        propertyChanged: (b, _, v) => { var s = (SparkView)b; s._d.Days = (int)v; s.Invalidate(); });

    public static readonly BindableProperty LineColorProperty = BindableProperty.Create(
        nameof(LineColor), typeof(Color), typeof(SparkView), null,
        propertyChanged: (b, _, v) =>
        {
            var s = (SparkView)b;
            if (v is Color c) { s._d.LineColor = c; s.Invalidate(); }
        });

    public List<List<long>>? Points
    {
        get => (List<List<long>>?)GetValue(PointsProperty);
        set => SetValue(PointsProperty, value);
    }

    public int Days
    {
        get => (int)GetValue(DaysProperty);
        set => SetValue(DaysProperty, value);
    }

    public Color? LineColor
    {
        get => (Color?)GetValue(LineColorProperty);
        set => SetValue(LineColorProperty, value);
    }

    public SparkView() => Drawable = _d;
}

/// Плитка товару без фото: гліф розділу замість порожнього квадрата.
public sealed class GlyphView : GraphicsView
{
    readonly CategoryGlyphDrawable _d = new();

    public static readonly BindableProperty GlyphKeyProperty = BindableProperty.Create(
        nameof(GlyphKey), typeof(string), typeof(GlyphView), "box",
        propertyChanged: (b, _, v) =>
        {
            var g = (GlyphView)b;
            // null з сервера — законний випадок (стара відповідь із кешу), не помилка
            g._d.Key = string.IsNullOrEmpty(v as string) ? "box" : (string)v;
            g.Invalidate();
        });

    public static readonly BindableProperty GlyphColorProperty = BindableProperty.Create(
        nameof(GlyphColor), typeof(Color), typeof(GlyphView), null,
        propertyChanged: (b, _, v) =>
        {
            var g = (GlyphView)b;
            if (v is Color c) { g._d.Color = c; g.Invalidate(); }
        });

    public string? GlyphKey
    {
        get => (string?)GetValue(GlyphKeyProperty);
        set => SetValue(GlyphKeyProperty, value);
    }

    public Color? GlyphColor
    {
        get => (Color?)GetValue(GlyphColorProperty);
        set => SetValue(GlyphColorProperty, value);
    }

    public GlyphView() => Drawable = _d;
}
