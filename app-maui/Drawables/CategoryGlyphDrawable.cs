namespace Hapay.Drawables;

/// Гліф розділу на плитці товару БЕЗ фото (S33).
///
/// KTC (2405 з 2405) і Eldorado (923 з 923) не віддають фото взагалі — тобто на
/// третині стрічки застосунок показував **порожній сірий квадрат**. Сайт це вже
/// полагодив у S32; тут та сама правка, з тим самим ключем від сервера
/// (`taxonomy.glyph_key`), щоб дві поверхні не вигадували свої розділи.
///
/// ⚠ Емодзі тут не годяться, і це не смак: вони малюються по-різному на кожній
/// платформі, а плитку видно на третині стрічки. Той самий аргумент, з якого на
/// сайті живе вектор.
///
/// Гліфи навмисно примітивні: 26px на екрані, і будь-яка деталь дрібніша за штрих
/// перетворюється на пляму. Впізнаваність тут дає силует, а не малюнок.
public sealed class CategoryGlyphDrawable : IDrawable
{
    public string Key { get; set; } = "box";
    public Color Color { get; set; } = Microsoft.Maui.Graphics.Color.FromArgb("#B9BFC7");

    public void Draw(ICanvas canvas, RectF rect)
    {
        // Малюємо в умовній сітці 24×24 й масштабуємо — координати нижче збігаються
        // з тими самими шляхами в GLYPHS (web/app.js), тож правити треба обидва місця.
        float s = Math.Min(rect.Width, rect.Height) / 24f;
        float ox = rect.X + (rect.Width - 24 * s) / 2f;
        float oy = rect.Y + (rect.Height - 24 * s) / 2f;
        float Px(float x) => ox + x * s;
        float Py(float y) => oy + y * s;

        canvas.StrokeColor = Color;
        canvas.StrokeSize = Math.Max(1.2f, 1.6f * s);
        canvas.StrokeLineJoin = LineJoin.Round;
        canvas.StrokeLineCap = LineCap.Round;

        void Rect(float x, float y, float w, float h, float r)
            => canvas.DrawRoundedRectangle(Px(x), Py(y), w * s, h * s, r * s);
        void Circle(float cx, float cy, float r)
            => canvas.DrawEllipse(Px(cx - r), Py(cy - r), 2 * r * s, 2 * r * s);
        void Line(float x1, float y1, float x2, float y2)
            => canvas.DrawLine(Px(x1), Py(y1), Px(x2), Py(y2));

        switch (Key)
        {
            case "device":                                   // монітор на ніжці
                Rect(3, 5, 18, 12, 2); Line(12, 17, 12, 21); Line(8, 21, 16, 21);
                break;
            case "camera":
                Rect(3, 6, 18, 12, 2); Circle(12, 12, 3.2f); Line(9, 6, 10.5f, 4); Line(15, 6, 13.5f, 4);
                break;
            case "appliance":                                // пралка: барабан у корпусі
                Rect(5, 3, 14, 18, 2); Circle(12, 14, 4); Line(8, 6.5f, 10, 6.5f);
                break;
            case "tool":                                     // ключ по діагоналі
                Circle(16, 8, 3.4f); Line(13.6f, 10.4f, 4.5f, 19.5f); Line(6, 17, 8, 19);
                break;
            case "car":
                Line(3, 16, 21, 16); Line(3, 16, 3, 12.8f); Line(21, 16, 21, 12.8f);
                Line(3.2f, 12.6f, 6, 8); Line(20.8f, 12.6f, 18, 8); Line(6, 8, 18, 8);
                Circle(7.5f, 16, 1.4f); Circle(16.5f, 16, 1.4f);
                break;
            case "pet":                                      // лапа
                Circle(8, 8, 1.8f); Circle(12, 6.5f, 1.8f); Circle(16, 8, 1.8f);
                Circle(12, 15, 4.2f);
                break;
            case "health":                                   // аптечка
                Rect(3, 7, 18, 12, 2.5f); Line(12, 10.5f, 12, 15.5f); Line(9.5f, 13, 14.5f, 13);
                break;
            case "toy":                                      // ведмежа: голова + вуха
                Circle(7.5f, 7, 2.2f); Circle(16.5f, 7, 2.2f); Circle(12, 13.5f, 5.6f);
                break;
            case "sport":                                    // мʼяч
                Circle(12, 12, 8.5f); Line(3.5f, 12, 20.5f, 12); Line(12, 3.5f, 12, 20.5f);
                break;
            case "watch":
                Circle(12, 12, 4.8f); Line(9.5f, 7.4f, 9.5f, 3.5f); Line(14.5f, 7.4f, 14.5f, 3.5f);
                Line(9.5f, 16.6f, 9.5f, 20.5f); Line(14.5f, 16.6f, 14.5f, 20.5f);
                Line(9.5f, 3.5f, 14.5f, 3.5f); Line(9.5f, 20.5f, 14.5f, 20.5f);
                break;
            default:                                          // коробка
                Line(12, 3, 3.5f, 7.5f); Line(3.5f, 7.5f, 3.5f, 16.5f); Line(3.5f, 16.5f, 12, 21);
                Line(12, 21, 20.5f, 16.5f); Line(20.5f, 16.5f, 20.5f, 7.5f); Line(20.5f, 7.5f, 12, 3);
                Line(3.5f, 7.5f, 12, 12); Line(12, 12, 20.5f, 7.5f); Line(12, 12, 12, 21);
                break;
        }
    }
}
