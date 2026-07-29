namespace Hapay.Drawables;

/// Мікрографік історії ціни для картки стрічки (S33) — 64×20, без осей і підписів.
///
/// Це НЕ зменшений PriceHistoryDrawable. Той малює провенанс: точки вимірів, розриви
/// на добах без даних, лінію 30-денної бази. На 64×20 кожна з цих деталей стала б
/// сірою кашею, тому тут лише ФОРМА, а твердження лишається на картці товару.
///
/// Що збережено з тієї логіки й ЧОМУ:
///   · сходинки, а не інтерполяція — пряма між двома вимірами вигадує ціни, яких не
///     існувало (T12);
///   · вісь X за РЕАЛЬНИМИ зсувами діб — прогалина у вимірах лишається прогалиною,
///     а не стискається в рівний крок.
///
/// Формат точки — [зсув доби від початку вікна, копійки], рівно як віддає сервер
/// у полі `spark`. Той самий контракт, що й у sparkMini() на сайті: одне джерело,
/// два клієнти, жодного перерахунку по дорозі.
public sealed class SparkDrawable : IDrawable
{
    public IReadOnlyList<IReadOnlyList<long>> Points { get; set; } = Array.Empty<long[]>();

    /// Ширина вікна в добах (сервер віддає 30). Потрібна саме вона, а не діапазон
    /// самих точок: інакше графік із трьох діб розтягнувся б на всю ширину й читався
    /// б як місяць спостережень.
    public int Days { get; set; } = 30;

    public Color LineColor { get; set; } = Color.FromArgb("#868D97");

    public void Draw(ICanvas canvas, RectF rect)
    {
        var pts = Points;
        if (pts.Count < 3) return;                 // менше трьох діб — це не лінія, а відрізок

        const float pad = 2f;
        float w = rect.Width - 2 * pad;
        float h = rect.Height - 2 * pad;
        if (w <= 0 || h <= 0) return;

        long lo = long.MaxValue, hi = long.MinValue;
        foreach (var p in pts) { lo = Math.Min(lo, p[1]); hi = Math.Max(hi, p[1]); }
        double range = Math.Max(hi - lo, 1);
        double span = Math.Max(Days - 1, 1);

        float X(long d) => pad + (float)(Math.Clamp(d, 0, span) / span * w);
        // Ціна не змінювалась → рівна лінія посередині, а не притиснута до краю:
        // притиснута читалась би як «на мінімумі», тобто як твердження, якого нема.
        float Y(long v) => hi == lo ? rect.Height / 2f
                                    : pad + (float)((1 - (v - lo) / range) * h);

        var path = new PathF();
        path.MoveTo(X(pts[0][0]), Y(pts[0][1]));
        for (int i = 1; i < pts.Count; i++)
        {
            path.LineTo(X(pts[i][0]), Y(pts[i - 1][1]));   // тримаємо стару ціну до дня зміни
            path.LineTo(X(pts[i][0]), Y(pts[i][1]));       // і лише тоді ступінь
        }

        canvas.StrokeColor = LineColor;
        canvas.StrokeSize = 1.4f;
        canvas.StrokeLineJoin = LineJoin.Round;
        canvas.StrokeLineCap = LineCap.Round;
        canvas.DrawPath(path);
    }
}
