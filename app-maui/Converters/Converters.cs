using System.Globalization;

namespace Hapay.Converters;

/// string → bool: true якщо не порожній. Для IsVisible (напр. блок помилки).
public class StringNotEmptyConverter : IValueConverter
{
    public object Convert(object? value, Type t, object? p, CultureInfo c) =>
        !string.IsNullOrWhiteSpace(value as string);

    public object ConvertBack(object? value, Type t, object? p, CultureInfo c) =>
        throw new NotSupportedException();
}

/// bool → !bool. Для IsVisible від інвертованої умови (напр. «Немає в наявності»).
public class InvertBoolConverter : IValueConverter
{
    public object Convert(object? value, Type t, object? p, CultureInfo c) =>
        value is not true;

    public object ConvertBack(object? value, Type t, object? p, CultureInfo c) =>
        value is not true;
}
