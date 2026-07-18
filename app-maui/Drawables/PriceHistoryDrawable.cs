using Hapay.Models;

namespace Hapay.Drawables;

/// Графік історії ціни на GraphicsView. Малює рівно виміряне: сходинки (не інтерполяція)
/// + РОЗРИВ на добах без вимірів — не вигадуємо суцільну лінію (T12/§5.4.2).
public class PriceHistoryDrawable : IDrawable
{
    public IReadOnlyList<HistoryPoint> Points { get; set; } = new List<HistoryPoint>();
    public Color LineColor { get; set; } = Color.FromArgb("#E23B3B");

    public void Draw(ICanvas canvas, RectF rect)
    {
        var pts = Points;
        if (pts.Count < 2) return;

        const float pad = 8f;
        float w = rect.Width - 2 * pad;
        float h = rect.Height - 2 * pad;
        if (w <= 0 || h <= 0) return;

        double minY = double.MaxValue, maxY = double.MinValue;
        foreach (var p in pts) { minY = Math.Min(minY, p.MinKop); maxY = Math.Max(maxY, p.MinKop); }
        double t0 = pts[0].Date.Ticks;
        double span = Math.Max(pts[^1].Date.Ticks - t0, TimeSpan.TicksPerDay);
        double range = Math.Max(maxY - minY, 1);

        float X(int i) => pad + (float)((pts[i].Date.Ticks - t0) / span * w);
        float Y(int i) => pad + (float)((1 - (pts[i].MinKop - minY) / range) * h);
        double DayOf(int i) => (double)pts[i].Date.Ticks / TimeSpan.TicksPerDay;

        canvas.StrokeColor = LineColor;
        canvas.StrokeSize = 2.4f;
        canvas.StrokeLineJoin = LineJoin.Round;

        var path = new PathF();
        path.MoveTo(X(0), Y(0));
        for (int i = 1; i < pts.Count; i++)
        {
            if (DayOf(i) - DayOf(i - 1) > 1.5)
            {
                path.MoveTo(X(i), Y(i));       // прогалина ≥2 діб → розрив, новий сегмент
            }
            else
            {
                path.LineTo(X(i), Y(i - 1));    // горизонталь на рівні попереднього виміру
                path.LineTo(X(i), Y(i));        // вертикаль до нового (сходинка між суміжними днями)
            }
        }
        canvas.DrawPath(path);

        // маркери вимірів — щоб видно було, що це точки, а не намальована крива
        canvas.FillColor = LineColor;
        float r = pts.Count <= 20 ? 3f : 1.6f;
        for (int i = 0; i < pts.Count; i++)
            canvas.FillCircle(X(i), Y(i), r);
    }
}
