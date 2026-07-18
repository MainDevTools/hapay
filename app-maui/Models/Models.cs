using System.Text.Json.Serialization;

namespace Hapay.Models;

// Гроші — копійки (int) з API; формат у грн лише на показ (інв. A: гроші = BIGINT копійки).
public static class Money
{
    public static string Grn(int? kop) =>
        kop is null ? "—" : (kop.Value / 100m).ToString("N2") + " ₴";
}

/// Одна знижкова подія з /api/discounts.
public class Discount
{
    [JsonPropertyName("discount_event_id")] public int DiscountEventId { get; set; }
    [JsonPropertyName("store_product_id")] public int StoreProductId { get; set; }
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("image_url")] public string? ImageUrl { get; set; }
    [JsonPropertyName("variant_note")] public string? VariantNote { get; set; }
    [JsonPropertyName("store")] public string Store { get; set; } = "";
    [JsonPropertyName("current_kop")] public int CurrentKop { get; set; }
    [JsonPropertyName("old_declared_kop")] public int? OldDeclaredKop { get; set; }
    [JsonPropertyName("reference_kop")] public int? ReferenceKop { get; set; }
    [JsonPropertyName("declared_pct")] public int? DeclaredPct { get; set; }
    [JsonPropertyName("verified_pct")] public int? VerifiedPct { get; set; }
    [JsonPropertyName("badge_state")] public string BadgeState { get; set; } = "declared";

    // --- похідні для XAML-байндингу ---
    [JsonIgnore] public string CurrentGrn => Money.Grn(CurrentKop);
    [JsonIgnore] public string OldGrn => Money.Grn(OldDeclaredKop);
    [JsonIgnore] public bool HasOld => OldDeclaredKop is not null && OldDeclaredKop > CurrentKop;
    [JsonIgnore] public string SubTitle => VariantNote is null ? Store : $"{Store} · {VariantNote}";

    /// Відсоток знижки від заявленої старої ціни; null якщо не знижка.
    [JsonIgnore]
    public int? Pct => (OldDeclaredKop is int old && old > CurrentKop)
        ? (int)Math.Round((1 - (double)CurrentKop / old) * 100)
        : null;

    [JsonIgnore] public bool HasPct => Pct is not null;
    [JsonIgnore] public string PctText => Pct is int p ? $"−{p}%" : "";
}

/// Категорія з /api/categories.
public class Category
{
    [JsonPropertyName("slug")] public string Slug { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("n")] public int N { get; set; }

    [JsonIgnore] public string Display => $"{Name} ({N})";
}

/// Точка історії ціни з /api/product/{id}/history.
public class HistoryPoint
{
    [JsonPropertyName("day")] public string Day { get; set; } = "";
    [JsonPropertyName("min_kop")] public int MinKop { get; set; }
    [JsonPropertyName("max_kop")] public int MaxKop { get; set; }
    [JsonPropertyName("n")] public int N { get; set; }

    [JsonIgnore] public DateTime Date => DateTime.Parse(Day);
}
