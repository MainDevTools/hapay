import 'dart:async';
import 'package:flutter/material.dart';
import '../api.dart';
import '../models.dart';
import '../widgets/discount_card.dart';
import 'detail_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _api = Api();
  final _scroll = ScrollController();
  final _searchCtrl = TextEditingController();
  Timer? _debounce;

  List<Category> _cats = [];
  final List<Discount> _items = [];
  String? _cat;
  String _sort = 'discount'; // T14: за замовч. «за заявленою знижкою»
  String _q = '';
  int _page = 0;
  bool _loading = false;
  bool _more = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadCategories();
    _reload();
    _scroll.addListener(() {
      if (_scroll.position.pixels > _scroll.position.maxScrollExtent - 400) _loadMore();
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    _searchCtrl.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  Future<void> _loadCategories() async {
    try {
      final c = await _api.categories();
      if (mounted) setState(() => _cats = c);
    } catch (_) {/* категорії необовʼязкові */}
  }

  Future<void> _reload() async {
    setState(() {
      _page = 0;
      _more = true;
      _error = null;
      _items.clear();
    });
    await _loadMore();
  }

  Future<void> _loadMore() async {
    if (_loading || !_more) return;
    setState(() => _loading = true);
    try {
      final batch = await _api.discounts(category: _cat, q: _q, sort: _sort, page: _page);
      if (!mounted) return;
      setState(() {
        _items.addAll(batch);
        _more = batch.length >= 50;
        _page++;
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _onSearch(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () {
      _q = v;
      _reload();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 16,
        title: const Text('Хапай', style: TextStyle(fontWeight: FontWeight.w800)),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(104),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
            child: Column(
              children: [
                TextField(
                  controller: _searchCtrl,
                  onChanged: _onSearch,
                  textInputAction: TextInputAction.search,
                  decoration: const InputDecoration(
                    hintText: 'Пошук за назвою…',
                    prefixIcon: Icon(Icons.search),
                  ),
                ),
                const SizedBox(height: 8),
                Row(children: [
                  Expanded(child: _categoryDropdown()),
                  const SizedBox(width: 8),
                  Expanded(child: _sortDropdown()),
                ]),
              ],
            ),
          ),
        ),
      ),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: _buildBody(),
      ),
    );
  }

  Widget _categoryDropdown() => DropdownButtonFormField<String?>(
        value: _cat,
        isExpanded: true,
        decoration: const InputDecoration(contentPadding: EdgeInsets.symmetric(horizontal: 12)),
        items: [
          const DropdownMenuItem(value: null, child: Text('Усі категорії')),
          ..._cats.map((c) => DropdownMenuItem(value: c.slug, child: Text('${c.name} (${c.n})'))),
        ],
        onChanged: (v) {
          _cat = v;
          _reload();
        },
      );

  Widget _sortDropdown() => DropdownButtonFormField<String>(
        value: _sort,
        isExpanded: true,
        decoration: const InputDecoration(contentPadding: EdgeInsets.symmetric(horizontal: 12)),
        items: const [
          DropdownMenuItem(value: 'discount', child: Text('За знижкою')),
          DropdownMenuItem(value: 'new', child: Text('Найновіші')),
          DropdownMenuItem(value: 'verified', child: Text('За нашим мінімумом')),
        ],
        onChanged: (v) {
          if (v == null) return;
          _sort = v;
          _reload();
        },
      );

  Widget _buildBody() {
    if (_items.isEmpty && _loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_items.isEmpty && _error != null) {
      return _message(Icons.cloud_off, 'Не вдалося завантажити', _error!, retry: true);
    }
    if (_items.isEmpty) {
      return _message(Icons.search_off, 'Нічого не знайдено', 'Спробуй іншу категорію чи запит');
    }
    return ListView.builder(
      controller: _scroll,
      itemCount: _items.length + 1,
      itemBuilder: (ctx, i) {
        if (i == _items.length) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Center(
              child: _more
                  ? const CircularProgressIndicator()
                  : Text('Це все', style: TextStyle(color: Theme.of(ctx).hintColor)),
            ),
          );
        }
        final d = _items[i];
        return DiscountCard(
          d: d,
          onTap: () => Navigator.push(
              ctx, MaterialPageRoute(builder: (_) => DetailScreen(d: d, api: _api))),
        );
      },
    );
  }

  Widget _message(IconData icon, String title, String sub, {bool retry = false}) => ListView(
        children: [
          const SizedBox(height: 120),
          Icon(icon, size: 48, color: Theme.of(context).hintColor),
          const SizedBox(height: 12),
          Center(child: Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16))),
          const SizedBox(height: 4),
          Center(
              child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(sub, textAlign: TextAlign.center, style: TextStyle(color: Theme.of(context).hintColor)),
          )),
          if (retry) ...[
            const SizedBox(height: 16),
            Center(child: FilledButton.tonal(onPressed: _reload, child: const Text('Спробувати ще'))),
          ],
        ],
      );
}
