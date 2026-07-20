using System.Globalization;
using System.Text.Json.Serialization;

namespace Hapay.Models;

// Гроші — копійки (int) з API; формат у грн лише на показ (інв. A: гроші = BIGINT копійки).
public static class Money
{
    // Український формат НЕЗАЛЕЖНО від локалі пристрою: «17 099 ₴», «1 761,20 ₴»
    // (інакше en-US емулятор показує «17,099.00 ₴»). Тисячі — нерозривний пробіл.
    private static readonly NumberFormatInfo _uk = new()
    {
        NumberGroupSeparator = " ",
        NumberDecimalSeparator = ",",
    };

    public static string Grn(int? kop)
    {
        if (kop is null) return "—";
        var uah = kop.Value / 100m;
        // цілі гривні — без «,00» (компактніше в картці); з копійками — 2 знаки
        var s = kop.Value % 100 == 0 ? uah.ToString("N0", _uk) : uah.ToString("N2", _uk);
        return s + " ₴";
    }
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
    [JsonPropertyName("offers_n")] public int OffersN { get; set; } = 1;   // розмір MPN-групи (T15)
    [JsonPropertyName("promo_until")] public string? PromoUntil { get; set; }   // дата кінця акції (крамниця)

    // --- похідні для XAML-байндингу ---
    [JsonIgnore] public bool HasMultiStores => OffersN > 1;
    [JsonIgnore] public bool ShowStoreLine => OffersN <= 1;              // одна крамниця → її й показуємо
    [JsonIgnore] public string StoresText => $"Наявно в {OffersN} крамницях";
    // для групи — «від {найдешевша}» (агрегатор, §17); для однієї крамниці — просто ціна
    [JsonIgnore] public string PriceText => HasMultiStores ? $"від {CurrentGrn}" : CurrentGrn;
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

    // «Акція діє до DD.MM» — лише коли крамниця дала реальну дату (сервер уже відсіяв генеричні)
    [JsonIgnore] public bool HasPromo => !string.IsNullOrEmpty(PromoUntil);
    [JsonIgnore] public string PromoText =>
        DateTime.TryParse(PromoUntil, out var d) ? $"Акція діє до {d:dd.MM}" : "";
}

/// Категорія з /api/categories.
public class Category
{
    [JsonPropertyName("slug")] public string Slug { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("n")] public int N { get; set; }
    [JsonPropertyName("section")] public string Section { get; set; } = "";   // розділ сітки-каталогу
    [JsonPropertyName("icon")] public string Icon { get; set; } = "";         // емодзі-іконка плитки

    // синтетичний запис «Усі категорії» має порожній slug і N=0 → без «(0)»;
    // реальні категорії з /api/categories завжди мають n≥1
    [JsonIgnore] public string Display => string.IsNullOrEmpty(Slug) ? Name : $"{Name} ({N})";
    [JsonIgnore] public string CountText => $"{N} товарів";
}

/// Розділ сітки-каталогу (E-Katalog, §17): заголовок + категорії розділу.
public class CategoryGroup : List<Category>
{
    public string Title { get; }
    public CategoryGroup(string title, IEnumerable<Category> items) : base(items) => Title = title;
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

/// Відповідь /api/auth/register|login (S11).
public class AuthResult
{
    [JsonPropertyName("token")] public string Token { get; set; } = "";
    [JsonPropertyName("role")] public string Role { get; set; } = "user";
    [JsonPropertyName("email")] public string Email { get; set; } = "";
}

/// Профіль із /api/me.
public class UserProfile
{
    [JsonPropertyName("user_id")] public int UserId { get; set; }
    [JsonPropertyName("email")] public string Email { get; set; } = "";
    [JsonPropertyName("role")] public string Role { get; set; } = "user";
}

/// Оффер із /api/product/{id}/offers — той самий товар (mpn) в одній із крамниць (T15).
public class Offer
{
    [JsonPropertyName("store_product_id")] public int StoreProductId { get; set; }
    [JsonPropertyName("store")] public string Store { get; set; } = "";
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("current_kop")] public int CurrentKop { get; set; }
    [JsonPropertyName("old_declared_kop")] public int? OldDeclaredKop { get; set; }
    [JsonPropertyName("in_stock")] public bool InStock { get; set; } = true;
    [JsonPropertyName("seen_day")] public string? SeenDay { get; set; }

    [JsonIgnore] public string CurrentGrn => Money.Grn(CurrentKop);
    [JsonIgnore] public double Opacity => InStock ? 1.0 : 0.45;   // «немає» — приглушено

    // ціна крамниці — як згори картки: поточна + перекреслена стара + −% (якщо є знижка)
    [JsonIgnore] public string OldGrn => Money.Grn(OldDeclaredKop);
    [JsonIgnore] public bool HasOld => OldDeclaredKop is int old && old > CurrentKop;
    [JsonIgnore]
    public int? Pct => (OldDeclaredKop is int old && old > CurrentKop)
        ? (int)Math.Round((1 - (double)CurrentKop / old) * 100)
        : null;
    [JsonIgnore] public bool HasPct => Pct is not null;
    [JsonIgnore] public string PctText => Pct is int p ? $"−{p}%" : "";
}

/// Задача з черги-оренди /api/collect/lease (T16): одна сторінка однієї крамниці.
public class LeaseTask
{
    [JsonPropertyName("task_id")] public int TaskId { get; set; }
    [JsonPropertyName("source")] public string Source { get; set; } = "";
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("kind")] public string Kind { get; set; } = "page";
    [JsonPropertyName("mode")] public string Mode { get; set; } = "fetch";   // fetch | render (WebView)
}

public class LeaseResponse
{
    [JsonPropertyName("tasks")] public List<LeaseTask> Tasks { get; set; } = new();
}

/// Ціль збору з /api/collect/plan — ЩО тягнути. Сервер вирішує (застосунок = «тупий фетчер»).
public class CollectTarget
{
    [JsonPropertyName("source")] public string Source { get; set; } = "";
    [JsonPropertyName("url")] public string Url { get; set; } = "";
    [JsonPropertyName("kind")] public string Kind { get; set; } = "page";   // hub | page
    [JsonPropertyName("mode")] public string Mode { get; set; } = "fetch";  // fetch | render (WebView)
}

/// Відповідь /api/collect/plan.
public class CollectPlan
{
    [JsonPropertyName("targets")] public List<CollectTarget> Targets { get; set; } = new();
}

/// Відповідь /api/ingest/html. Для hub — discovered-лендинги (сервер їх знайшов); для page — accepted.
public class IngestHtmlResult
{
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";        // hub | page
    [JsonPropertyName("accepted")] public int Accepted { get; set; }
    [JsonPropertyName("rejected")] public int Rejected { get; set; }
    [JsonPropertyName("discovered")] public List<string>? Discovered { get; set; }
}
