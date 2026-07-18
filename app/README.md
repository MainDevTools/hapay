# Хапай — мобільний застосунок (Flutter)

Нативний застосунок під **Android + iOS** з одного коду. Клієнт read-API `hapay.today`.
Рішення власника (2026-07-18): «фінальний проект» — нативний у стори, не Mini App/PWA.

## ⚠ Windows → iOS не збереться локально

Flutter-код один на обидві платформи, але **збірка iOS потребує macOS+Xcode**
(обмеження Apple). На Windows: **Android — так**, iOS — через Mac або хмарний Mac-CI
(напр. Codemagic збирає Flutter-iOS без свого Mac).

## Що вже є (MVP)

- `lib/api.dart` — клієнт (discounts / categories / history);
- `lib/models.dart` — Discount / Category / HistoryPoint, формат грн;
- `lib/screens/home_screen.dart` — стрічка + категорії + пошук + пагінація + pull-to-refresh;
- `lib/screens/detail_screen.dart` — товар + графік історії (сходинки, §5.4.2) + «відкрити в крамниці»;
- `lib/widgets/discount_card.dart`, `lib/theme.dart` (M3, світла/темна).

## Запуск (Android, на Windows)

Один раз — інструменти:
1. Постав **Flutter SDK** (docs.flutter.dev) + **Android Studio** (Android SDK, емулятор).
2. `flutter doctor` — усе зелене.

У цій папці:
```
flutter create .           # згенерує android/ (платформні файли; код у lib/ не чіпає)
flutter pub get
flutter run                # на емуляторі/пристрої
```

Локальний бекенд замість прода (емулятор Android → хост):
```
flutter run --dart-define=HAPAY_API=http://10.0.2.2:8080
```

## Перед релізом у стори (не зараз)

- App Store: Apple Developer **$99/рік** + Mac/Codemagic; Google Play: **$25** одноразово.
- **ФОП** — щоб отримувати кошти (консультація бухгалтера).
- **Юр-сторінки** на hapay.today: privacy policy + support URL (стори вимагають).
- Іконка, скріншоти, опис, вікові рейтинги, privacy nutrition labels (Apple).

## Далі (беклог MVP)

- watchlist/сповіщення про падіння ціни (push — потребує FCM/APNs, §9.3);
- перевдягти під T14 остаточно (зараз уже агрегатор-орієнтований);
- офлайн-кеш стрічки; шаринг товару.
