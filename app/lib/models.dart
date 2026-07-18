import 'package:intl/intl.dart';

/// Гроші — копійки (int) з API; формат у грн лише на показ (§A: гроші = BIGINT копійки).
final _uah = NumberFormat.currency(locale: 'uk_UA', symbol: '₴', decimalDigits: 2);

String formatKop(int? kop) => kop == null ? '—' : _uah.format(kop / 100);

/// Одна знижкова подія з /api/discounts.
class Discount {
  final int discountEventId;
  final int storeProductId;
  final String title;
  final String url;
  final String? imageUrl;
  final String? variantNote;
  final String store;
  final int currentKop;
  final int? oldDeclaredKop;
  final int? referenceKop;
  final int? declaredPct;
  final int? verifiedPct;
  final String badgeState;

  Discount({
    required this.discountEventId,
    required this.storeProductId,
    required this.title,
    required this.url,
    required this.imageUrl,
    required this.variantNote,
    required this.store,
    required this.currentKop,
    required this.oldDeclaredKop,
    required this.referenceKop,
    required this.declaredPct,
    required this.verifiedPct,
    required this.badgeState,
  });

  factory Discount.fromJson(Map<String, dynamic> j) => Discount(
        discountEventId: j['discount_event_id'] as int,
        storeProductId: j['store_product_id'] as int,
        title: (j['title'] ?? '') as String,
        url: (j['url'] ?? '') as String,
        imageUrl: j['image_url'] as String?,
        variantNote: j['variant_note'] as String?,
        store: (j['store'] ?? '') as String,
        currentKop: (j['current_kop'] ?? 0) as int,
        oldDeclaredKop: j['old_declared_kop'] as int?,
        referenceKop: j['reference_kop'] as int?,
        declaredPct: j['declared_pct'] as int?,
        verifiedPct: j['verified_pct'] as int?,
        badgeState: (j['badge_state'] ?? 'declared') as String,
      );

  /// Відсоток знижки для показу (від заявленої старої ціни). null якщо не знижка.
  int? get pct {
    final old = oldDeclaredKop;
    if (old != null && old > currentKop) {
      return ((1 - currentKop / old) * 100).round();
    }
    return null;
  }
}

/// Категорія з /api/categories.
class Category {
  final String slug;
  final String name;
  final int n;
  Category({required this.slug, required this.name, required this.n});

  factory Category.fromJson(Map<String, dynamic> j) => Category(
        slug: j['slug'] as String,
        name: j['name'] as String,
        n: (j['n'] ?? 0) as int,
      );
}

/// Точка історії ціни з /api/product/{id}/history.
class HistoryPoint {
  final DateTime day;
  final int minKop;
  final int maxKop;
  final int n; // скільки вимірів за добу (провенанс §5.4)
  HistoryPoint({required this.day, required this.minKop, required this.maxKop, required this.n});

  factory HistoryPoint.fromJson(Map<String, dynamic> j) => HistoryPoint(
        day: DateTime.parse(j['day'] as String),
        minKop: (j['min_kop'] ?? 0) as int,
        maxKop: (j['max_kop'] ?? 0) as int,
        n: (j['n'] ?? 0) as int,
      );
}
