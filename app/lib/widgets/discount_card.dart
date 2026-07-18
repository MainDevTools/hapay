import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import '../models.dart';
import '../theme.dart';

/// Картка знижки у стрічці. Фото — hotlink (кеш), не байти (§7.4).
class DiscountCard extends StatelessWidget {
  final Discount d;
  final VoidCallback onTap;
  const DiscountCard({super.key, required this.d, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final pct = d.pct;
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _thumb(),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(d.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w600, height: 1.25)),
                    const SizedBox(height: 3),
                    Text([d.store, if (d.variantNote != null) d.variantNote!].join(' · '),
                        style: TextStyle(fontSize: 12, color: t.hintColor)),
                    const SizedBox(height: 8),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.baseline,
                      textBaseline: TextBaseline.alphabetic,
                      children: [
                        Text(formatKop(d.currentKop),
                            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
                        const SizedBox(width: 8),
                        if (d.oldDeclaredKop != null)
                          Text(formatKop(d.oldDeclaredKop),
                              style: TextStyle(
                                  fontSize: 13,
                                  color: t.hintColor,
                                  decoration: TextDecoration.lineThrough)),
                        const Spacer(),
                        if (pct != null) DiscountTag(pct),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _thumb() {
    const size = 74.0;
    if (d.imageUrl == null) {
      return Container(
        width: size,
        height: size,
        color: Colors.black12,
        child: const Icon(Icons.image_not_supported_outlined, color: Colors.black26),
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: CachedNetworkImage(
        imageUrl: d.imageUrl!,
        width: size,
        height: size,
        fit: BoxFit.contain,
        placeholder: (_, __) => Container(width: size, height: size, color: Colors.black12),
        errorWidget: (_, __, ___) => Container(
            width: size,
            height: size,
            color: Colors.black12,
            child: const Icon(Icons.broken_image_outlined, color: Colors.black26)),
      ),
    );
  }
}
