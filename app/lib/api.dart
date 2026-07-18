import 'dart:convert';
import 'package:http/http.dart' as http;
import 'models.dart';

/// Клієнт read-API «Хапай». Один base-URL — легко змінити хост, не чіпаючи екрани.
class Api {
  /// Прод. Локально можна: --dart-define=HAPAY_API=http://10.0.2.2:8080 (емулятор Android → хост).
  static const base = String.fromEnvironment('HAPAY_API', defaultValue: 'https://hapay.today');

  final http.Client _c = http.Client();

  Future<List<Discount>> discounts({
    String? category,
    String? q,
    String sort = 'discount', // T14: агрегатор → за замовч. «за заявленою знижкою»
    int page = 0,
  }) async {
    final qp = <String, String>{'sort': sort, 'page': '$page'};
    if (category != null && category.isNotEmpty) qp['category'] = category;
    if (q != null && q.trim().isNotEmpty) qp['q'] = q.trim();
    final uri = Uri.parse('$base/api/discounts').replace(queryParameters: qp);
    final r = await _c.get(uri).timeout(const Duration(seconds: 20));
    if (r.statusCode != 200) {
      throw Exception('discounts ${r.statusCode}');
    }
    final list = jsonDecode(utf8.decode(r.bodyBytes)) as List;
    return list.map((e) => Discount.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Category>> categories() async {
    final r = await _c.get(Uri.parse('$base/api/categories')).timeout(const Duration(seconds: 20));
    if (r.statusCode != 200) throw Exception('categories ${r.statusCode}');
    final list = jsonDecode(utf8.decode(r.bodyBytes)) as List;
    return list.map((e) => Category.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<HistoryPoint>> history(int storeProductId) async {
    final uri = Uri.parse('$base/api/product/$storeProductId/history');
    final r = await _c.get(uri).timeout(const Duration(seconds: 20));
    if (r.statusCode != 200) throw Exception('history ${r.statusCode}');
    final list = jsonDecode(utf8.decode(r.bodyBytes)) as List;
    return list.map((e) => HistoryPoint.fromJson(e as Map<String, dynamic>)).toList();
  }
}
