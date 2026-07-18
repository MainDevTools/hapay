import 'package:cached_network_image/cached_network_image.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../api.dart';
import '../models.dart';
import '../theme.dart';

/// Картка товару: ціни + графік історії + кнопка «відкрити в крамниці».
class DetailScreen extends StatefulWidget {
  final Discount d;
  final Api api;
  const DetailScreen({super.key, required this.d, required this.api});
  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  late Future<List<HistoryPoint>> _hist;

  @override
  void initState() {
    super.initState();
    _hist = widget.api.history(widget.d.storeProductId);
  }

  Future<void> _openStore() async {
    final uri = Uri.tryParse(widget.d.url);
    if (uri != null && await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = widget.d;
    final t = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(d.store)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (d.imageUrl != null)
            Center(
              child: CachedNetworkImage(
                imageUrl: d.imageUrl!,
                height: 200,
                fit: BoxFit.contain,
                errorWidget: (_, __, ___) => const Icon(Icons.broken_image_outlined, size: 80),
              ),
            ),
          const SizedBox(height: 16),
          Text(d.title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, height: 1.3)),
          if (d.variantNote != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(d.variantNote!, style: TextStyle(color: t.hintColor)),
            ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(formatKop(d.currentKop),
                  style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w800)),
              const SizedBox(width: 10),
              if (d.oldDeclaredKop != null)
                Text(formatKop(d.oldDeclaredKop),
                    style: TextStyle(
                        fontSize: 15, color: t.hintColor, decoration: TextDecoration.lineThrough)),
              const Spacer(),
              if (d.pct != null) DiscountTag(d.pct!),
            ],
          ),
          const SizedBox(height: 24),
          Text('Історія ціни', style: TextStyle(fontWeight: FontWeight.w700, color: t.hintColor)),
          const SizedBox(height: 12),
          SizedBox(height: 180, child: _chart(t)),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: _openStore,
            icon: const Icon(Icons.open_in_new),
            label: const Text('Відкрити в крамниці'),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
          ),
        ],
      ),
    );
  }

  Widget _chart(ThemeData t) => FutureBuilder<List<HistoryPoint>>(
        future: _hist,
        builder: (ctx, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          final pts = snap.data ?? [];
          if (pts.length < 2) {
            return Center(
              child: Text('Замало вимірів — історія ще накопичується',
                  textAlign: TextAlign.center, style: TextStyle(color: t.hintColor)),
            );
          }
          // сходинки, не інтерполяція, І РОЗРИВ на добах без вимірів: між ними ціна могла бути
          // іншою — не вигадуємо суцільну лінію (T12/§5.4.2; бекенд пропускає порожні доби навмисно).
          final x0 = pts.first.day.millisecondsSinceEpoch.toDouble();
          double xOf(int i) => (pts[i].day.millisecondsSinceEpoch.toDouble() - x0) / 86400000.0;
          final spots = <FlSpot>[FlSpot(xOf(0), pts[0].minKop / 100.0)];
          for (var i = 1; i < pts.length; i++) {
            final x = xOf(i);
            final y = pts[i].minKop / 100.0;
            if (x - xOf(i - 1) > 1.5) {
              spots.add(FlSpot.nullSpot); // прогалина ≥2 діб → розрив лінії, не горизонталь
            } else {
              spots.add(FlSpot(x, pts[i - 1].minKop / 100.0)); // сходинка лише між суміжними днями
            }
            spots.add(FlSpot(x, y));
          }
          return LineChart(LineChartData(
            gridData: const FlGridData(show: false),
            titlesData: const FlTitlesData(show: false),
            borderData: FlBorderData(show: false),
            lineBarsData: [
              LineChartBarData(
                spots: spots,
                isCurved: false,
                color: t.colorScheme.primary,
                barWidth: 2.4,
                dotData: FlDotData(show: pts.length <= 20),
                belowBarData: BarAreaData(
                    show: true, color: t.colorScheme.primary.withOpacity(0.12)),
              ),
            ],
          ));
        },
      );
}
