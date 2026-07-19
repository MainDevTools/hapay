namespace Hapay.Services;

/// Налаштування/лічильник фонового збору (Preferences — НЕ секрети, токенів тут нема).
public static class CollectPrefs
{
    private const string AutoKey = "hapay_auto_collect";
    private const string DayKey = "hapay_collect_day";
    private const string PagesKey = "hapay_collect_pages";

    public static bool AutoEnabled => Preferences.Default.Get(AutoKey, false);
    public static void SetAuto(bool on) => Preferences.Default.Set(AutoKey, on);

    private static string Today => DateTime.Now.ToString("yyyy-MM-dd");

    /// Скільки сторінок зібрано СЬОГОДНІ (для прозорості в профілі — §7.7: усе видно).
    public static int TodayCount() =>
        Preferences.Default.Get(DayKey, "") == Today ? Preferences.Default.Get(PagesKey, 0) : 0;

    public static void BumpToday(int pages)
    {
        var cur = TodayCount();
        Preferences.Default.Set(DayKey, Today);
        Preferences.Default.Set(PagesKey, cur + pages);
    }
}
