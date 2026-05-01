import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

const String kBaseUrl = 'http://10.0.2.2:8000';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(statusBarColor: Colors.transparent),
  );
  await DBHelper.init();
  runApp(const MyApp());
}

/* ══════════════════════════════════════════════════════════════
    DESIGN TOKENS
══════════════════════════════════════════════════════════════ */

abstract class _K {
  // Core palette
  static const green      = Color(0xFF00E676);
  static const teal       = Color(0xFF1DE9B6);
  static const blue       = Color(0xFF448AFF);
  static const orange     = Color(0xFFFFAB40);
  static const pink       = Color(0xFFFF6090);
  static const bgDark     = Color(0xFF07090F);
  static const cardDark   = Color(0xFF10172A);
  static const glass      = Color(0x12FFFFFF);
  static const glassBord  = Color(0x26FFFFFF);

  // Gradients
  static const greenGrad = LinearGradient(
    colors: [Color(0xFF00E676), Color(0xFF1DE9B6)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
  static const blueGrad = LinearGradient(
    colors: [Color(0xFF448AFF), Color(0xFF7C5CFC)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
  static const bgGrad = LinearGradient(
    colors: [Color(0xFF07090F), Color(0xFF0D1530)],
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
  );
}

/* ══════════════════════════════════════════════════════════════
    DATA MODELS  (unchanged)
══════════════════════════════════════════════════════════════ */

class FoodItem {
  final int? foodId;
  String name;
  final double confidence;
  final double baseServingSizeG;
  final double unitCalories;
  final double unitProtein;
  final double unitCarbs;
  final double unitFat;

  double portionRatio;
  double calories;
  double proteinG;
  double carbsG;
  double fatG;

  FoodItem({
    this.foodId,
    required this.name,
    required this.confidence,
    required this.portionRatio,
    required this.baseServingSizeG,
    required this.unitCalories,
    required this.unitProtein,
    required this.unitCarbs,
    required this.unitFat,
    required this.calories,
    required this.proteinG,
    required this.carbsG,
    required this.fatG,
  });

  Map<String, dynamic> toJson() => {
    'food_id': foodId,
    'name': name,
    'confidence': confidence,
    'portion_ratio': portionRatio,
    'base_serving_size_g': baseServingSizeG,
    'calories': calories,
    'protein_g': proteinG,
    'carbs_g': carbsG,
    'fat_g': fatG,
  };

  factory FoodItem.fromJson(Map<String, dynamic> j) {
    double ratio = (j['portion_ratio'] as num).toDouble();
    return FoodItem(
      foodId: j['food_id'],
      name: j['name'],
      confidence: (j['confidence'] as num).toDouble(),
      portionRatio: ratio,
      baseServingSizeG: (j['base_serving_size_g'] as num).toDouble(),
      unitCalories: (j['calories'] as num).toDouble() / ratio,
      unitProtein: (j['protein_g'] as num).toDouble() / ratio,
      unitCarbs: (j['carbs_g'] as num).toDouble() / ratio,
      unitFat: (j['fat_g'] as num).toDouble() / ratio,
      calories: (j['calories'] as num).toDouble(),
      proteinG: (j['protein_g'] as num).toDouble(),
      carbsG: (j['carbs_g'] as num).toDouble(),
      fatG: (j['fat_g'] as num).toDouble(),
    );
  }

  void updateRatio(double newRatio) {
    portionRatio = newRatio.clamp(0.1, 5.0);
    calories = unitCalories * portionRatio;
    proteinG = unitProtein * portionRatio;
    carbsG = unitCarbs * portionRatio;
    fatG = unitFat * portionRatio;
  }
}

class AnalyzeResponse {
  final List<FoodItem> items;
  double get totalCalories => items.fold(0, (s, e) => s + e.calories);
  double get totalProtein  => items.fold(0, (s, e) => s + e.proteinG);
  double get totalCarbs    => items.fold(0, (s, e) => s + e.carbsG);
  double get totalFat      => items.fold(0, (s, e) => s + e.fatG);
  AnalyzeResponse({required this.items});
  factory AnalyzeResponse.fromJson(Map<String, dynamic> j) => AnalyzeResponse(
    items: (j['items'] as List).map((e) => FoodItem.fromJson(e)).toList(),
  );
}

/* ══════════════════════════════════════════════════════════════
    SQLITE HELPER  (unchanged)
══════════════════════════════════════════════════════════════ */

class DBHelper {
  static Database? _db;

  static Future<void> init() async {
    _db = await openDatabase(
      p.join(await getDatabasesPath(), 'dietary_v5.db'),
      version: 1,
      onCreate: (db, v) async {
        await db.execute('''
          CREATE TABLE meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT, timestamp TEXT, items_json TEXT,
            total_calories REAL, total_protein REAL,
            total_carbs REAL,   total_fat REAL
          )
        ''');
      },
    );
  }

  static Future<void> saveMeal(AnalyzeResponse res, {int? id}) async {
    final label = res.items.map((e) => e.name).join(', ');
    final data = {
      'label': label.isEmpty ? 'Unknown' : label,
      'timestamp': DateTime.now().toIso8601String(),
      'items_json': jsonEncode(res.items.map((e) => e.toJson()).toList()),
      'total_calories': res.totalCalories,
      'total_protein': res.totalProtein,
      'total_carbs': res.totalCarbs,
      'total_fat': res.totalFat,
    };
    id == null
        ? await _db!.insert('meals', data)
        : await _db!.update('meals', data, where: 'id = ?', whereArgs: [id]);
  }

  static Future<List<Map<String, dynamic>>> getMeals() async =>
      _db!.query('meals', orderBy: 'timestamp DESC');

  static Future<void> deleteMeal(int id) async =>
      _db!.delete('meals', where: 'id = ?', whereArgs: [id]);
}

/* ══════════════════════════════════════════════════════════════
    SHARED UI PRIMITIVES
══════════════════════════════════════════════════════════════ */

/// Frosted-glass container — wraps any child with blur + translucent border
class GlassBox extends StatelessWidget {
  final Widget child;
  final EdgeInsets padding;
  final double radius;

  const GlassBox({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(20),
    this.radius = 22,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          padding: padding,
          decoration: BoxDecoration(
            color: isDark ? _K.glass : Colors.white.withOpacity(0.65),
            borderRadius: BorderRadius.circular(radius),
            border: Border.all(
              color: isDark ? _K.glassBord : Colors.white.withOpacity(0.55),
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// Custom painter for the sweep-gradient macro ring
class _RingPainter extends CustomPainter {
  final double progress;
  final Color color;
  _RingPainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 6;
    const stroke = 6.0;

    // Track
    canvas.drawCircle(
      center,
      radius,
      Paint()
        ..color = color.withOpacity(0.12)
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke,
    );

    if (progress > 0) {
      // Arc with sweep gradient
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        -math.pi / 2,
        2 * math.pi * progress,
        false,
        Paint()
          ..shader = SweepGradient(
            startAngle: -math.pi / 2,
            endAngle: -math.pi / 2 + 2 * math.pi,
            colors: [color.withOpacity(0.5), color],
          ).createShader(Rect.fromCircle(center: center, radius: radius))
          ..style = PaintingStyle.stroke
          ..strokeWidth = stroke
          ..strokeCap = StrokeCap.round,
      );
    }
  }

  @override
  bool shouldRepaint(_RingPainter o) => o.progress != progress;
}

/// Animated circular macro ring widget
class MacroRing extends StatelessWidget {
  final String label;
  final double value, max;
  final Color color;

  const MacroRing({
    super.key,
    required this.label,
    required this.value,
    required this.max,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      TweenAnimationBuilder<double>(
        duration: const Duration(milliseconds: 1100),
        curve: Curves.easeOutCubic,
        tween: Tween(begin: 0.0, end: (value / max).clamp(0.0, 1.0)),
        builder: (_, v, __) => SizedBox(
          width: 68,
          height: 68,
          child: CustomPaint(
            painter: _RingPainter(progress: v, color: color),
            child: Center(
              child: Text(
                '${value.round()}',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w900,
                  color: color,
                ),
              ),
            ),
          ),
        ),
      ),
      const SizedBox(height: 8),
      Text(label,
          style: const TextStyle(
              fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 1.5)),
      Text('/ ${max.round()} g',
          style: TextStyle(fontSize: 9, color: Colors.grey.shade500)),
    ]);
  }
}

/// Animated gradient progress bar
class MacroBar extends StatelessWidget {
  final String label;
  final double value, max;
  final Color color;

  const MacroBar({
    super.key,
    required this.label,
    required this.value,
    required this.max,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label,
            style: const TextStyle(
                fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.3)),
        Text('${value.toStringAsFixed(1)} g',
            style: TextStyle(
                fontSize: 12, fontWeight: FontWeight.bold, color: color)),
      ]),
      const SizedBox(height: 8),
      ClipRRect(
        borderRadius: BorderRadius.circular(10),
        child: TweenAnimationBuilder<double>(
          duration: const Duration(milliseconds: 1100),
          curve: Curves.easeOutCubic,
          tween: Tween(begin: 0.0, end: (value / max).clamp(0.0, 1.0)),
          builder: (_, v, __) => Stack(children: [
            Container(
                height: 8,
                decoration: BoxDecoration(
                  color: color.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(10),
                )),
            FractionallySizedBox(
              widthFactor: v,
              child: Container(
                height: 8,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                      colors: [color.withOpacity(0.6), color]),
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
            ),
          ]),
        ),
      ),
    ]);
  }
}

/// Macro pill chip (used in history cards)
class _MacroChip extends StatelessWidget {
  final String abbr, value;
  final Color color;
  const _MacroChip(this.abbr, this.value, this.color);

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(
      color: color.withOpacity(0.12),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Text(abbr,
          style: TextStyle(
              fontSize: 9, fontWeight: FontWeight.w900, color: color)),
      const SizedBox(width: 3),
      Text(value,
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.bold, color: color)),
    ]),
  );
}

/* ══════════════════════════════════════════════════════════════
    NAV HELPER  — silky slide transition
══════════════════════════════════════════════════════════════ */

PageRouteBuilder<T> _slide<T>(Widget page) => PageRouteBuilder<T>(
  pageBuilder: (_, anim, __) => page,
  transitionsBuilder: (_, anim, __, child) => SlideTransition(
    position: Tween<Offset>(
            begin: const Offset(1, 0), end: Offset.zero)
        .animate(CurvedAnimation(parent: anim, curve: Curves.easeOutCubic)),
    child: child,
  ),
  transitionDuration: const Duration(milliseconds: 380),
);

/* ══════════════════════════════════════════════════════════════
    APP ROOT
══════════════════════════════════════════════════════════════ */

class MyApp extends StatefulWidget {
  const MyApp({super.key});
  @override
  State<MyApp> createState() => _MyAppState();
  static _MyAppState of(BuildContext context) =>
      context.findAncestorStateOfType<_MyAppState>()!;
}

class _MyAppState extends State<MyApp> {
  ThemeMode _tm = ThemeMode.dark;
  void toggle() => setState(
      () => _tm = _tm == ThemeMode.light ? ThemeMode.dark : ThemeMode.light);

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    themeMode: _tm,
    theme: ThemeData(
    useMaterial3: true,
    colorSchemeSeed: const Color(0xFF00E676),
    brightness: Brightness.light,
    scaffoldBackgroundColor: const Color(0xFFF3F6FA),
    cardTheme: CardThemeData(                          // ← changed
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(22)),
      elevation: 0,
    ),
  ),
  darkTheme: ThemeData(
    useMaterial3: true,
    colorSchemeSeed: const Color(0xFF00E676),
    brightness: Brightness.dark,
    scaffoldBackgroundColor: _K.bgDark,
    cardTheme: CardThemeData(                          // ← changed
      color: _K.cardDark,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(22)),
      elevation: 0,
    ),
  ),
    home: const HomeScreen(),
  );
}

/* ══════════════════════════════════════════════════════════════
    HOME SCREEN
══════════════════════════════════════════════════════════════ */

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  Future<void> _pick(BuildContext context, ImageSource src) async {
    final pick =
        await ImagePicker().pickImage(source: src, imageQuality: 85);
    if (pick != null && context.mounted) {
      Navigator.push(context, _slide(LoadingScreen(file: File(pick.path))));
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            icon: Icon(
              isDark ? Icons.wb_sunny_rounded : Icons.nights_stay_rounded,
              color: _K.green,
            ),
            onPressed: MyApp.of(context).toggle,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Stack(children: [
        // Dark gradient background
        if (isDark)
          Container(
              decoration: const BoxDecoration(gradient: _K.bgGrad)),

        // Ambient glow orbs
        if (isDark) ...[
          Positioned(
            top: -100,
            left: -60,
            child: Container(
              width: 320,
              height: 320,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(colors: [
                  _K.green.withOpacity(0.14),
                  Colors.transparent
                ]),
              ),
            ),
          ),
          Positioned(
            bottom: 100,
            right: -80,
            child: Container(
              width: 240,
              height: 240,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(colors: [
                  _K.blue.withOpacity(0.10),
                  Colors.transparent
                ]),
              ),
            ),
          ),
        ],

        SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 36),
                // App icon badge with glow
                Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                        colors: [_K.green, _K.teal]),
                    borderRadius: BorderRadius.circular(18),
                    boxShadow: [
                      BoxShadow(
                        color: _K.green.withOpacity(0.45),
                        blurRadius: 24,
                        offset: const Offset(0, 8),
                      )
                    ],
                  ),
                  child:
                      const Icon(Icons.eco_rounded, color: Colors.black, size: 30),
                ),
                const SizedBox(height: 28),
                Text(
                  'AI\nNutrition',
                  style: Theme.of(context)
                      .textTheme
                      .displaySmall
                      ?.copyWith(
                        fontWeight: FontWeight.w900,
                        letterSpacing: -1.5,
                        height: 1.05,
                      ),
                ),
                const SizedBox(height: 14),
                Text(
                  'Snap a photo. Get instant\nmacros and calories.',
                  style: TextStyle(
                      fontSize: 15,
                      color: Colors.grey.shade500,
                      height: 1.55),
                ),
                const Spacer(),
                // Camera button
                _GradientButton(
                  label: 'Take Photo',
                  sub: 'Use your camera',
                  icon: Icons.camera_alt_rounded,
                  gradient: const LinearGradient(
                      colors: [_K.green, _K.teal]),
                  onTap: () => _pick(context, ImageSource.camera),
                ),
                const SizedBox(height: 16),
                // Gallery button
                _GradientButton(
                  label: 'Photo Library',
                  sub: 'Choose from gallery',
                  icon: Icons.photo_library_rounded,
                  gradient: _K.blueGrad,
                  onTap: () => _pick(context, ImageSource.gallery),
                ),
                const SizedBox(height: 28),
                Center(
                  child: TextButton.icon(
                    onPressed: () => Navigator.push(
                        context, _slide(const MealHistoryScreen())),
                    icon: const Icon(Icons.history_rounded, size: 18),
                    label: const Text('View Meal History'),
                    style: TextButton.styleFrom(
                      foregroundColor: _K.green,
                      textStyle: const TextStyle(
                          fontWeight: FontWeight.w600, fontSize: 14),
                    ),
                  ),
                ),
                const SizedBox(height: 36),
              ],
            ),
          ),
        ),
      ]),
    );
  }
}

class _GradientButton extends StatelessWidget {
  final String label, sub;
  final IconData icon;
  final LinearGradient gradient;
  final VoidCallback onTap;

  const _GradientButton({
    required this.label,
    required this.sub,
    required this.icon,
    required this.gradient,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: gradient,
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: gradient.colors.first.withOpacity(0.35),
            blurRadius: 28,
            offset: const Offset(0, 10),
          )
        ],
      ),
      child: Row(children: [
        Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: Colors.black.withOpacity(0.15),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Icon(icon, color: Colors.white, size: 24),
        ),
        const SizedBox(width: 16),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label,
              style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 16)),
          const SizedBox(height: 2),
          Text(sub,
              style: TextStyle(
                  color: Colors.white.withOpacity(0.65), fontSize: 12)),
        ]),
        const Spacer(),
        Icon(Icons.arrow_forward_ios_rounded,
            color: Colors.white.withOpacity(0.65), size: 16),
      ]),
    ),
  );
}

/* ══════════════════════════════════════════════════════════════
    LOADING SCREEN
══════════════════════════════════════════════════════════════ */

class LoadingScreen extends StatefulWidget {
  final File file;
  const LoadingScreen({super.key, required this.file});
  @override
  State<LoadingScreen> createState() => _LoadingScreenState();
}

class _LoadingScreenState extends State<LoadingScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _pulse;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1400))
      ..repeat(reverse: true);
    _pulse =
        Tween<double>(begin: 0.88, end: 1.12).animate(
            CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
    _run();
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _run() async {
    try {
      final req =
          http.MultipartRequest('POST', Uri.parse('$kBaseUrl/analyze'));
      req.files.add(await http.MultipartFile.fromPath(
          'image', widget.file.path,
          contentType: MediaType('image', 'jpeg')));
      final res = await http.Response.fromStream(await req.send());
      if (res.statusCode == 200 && mounted) {
        Navigator.pushReplacement(
          context,
          _slide(MealAnalysisScreen(
            result: AnalyzeResponse.fromJson(jsonDecode(res.body)),
            imageFile: widget.file,
          )),
        );
      } else {
        throw 'Error ${res.statusCode}';
      }
    } catch (_) {
      if (mounted) Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(children: [
        // Blurred background of the food image
        Positioned.fill(
            child: Image.file(widget.file, fit: BoxFit.cover)),
        Positioned.fill(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 22, sigmaY: 22),
            child: Container(color: Colors.black.withOpacity(0.55)),
          ),
        ),
        Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            ScaleTransition(
              scale: _pulse,
              child: Container(
                width: 84,
                height: 84,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: const LinearGradient(
                      colors: [_K.green, _K.teal]),
                  boxShadow: [
                    BoxShadow(
                        color: _K.green.withOpacity(0.55),
                        blurRadius: 36)
                  ],
                ),
                child: const Icon(Icons.analytics_rounded,
                    color: Colors.black, size: 38),
              ),
            ),
            const SizedBox(height: 36),
            const Text('Analyzing your meal…',
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 19,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5)),
            const SizedBox(height: 10),
            Text('AI is identifying ingredients',
                style: TextStyle(
                    color: Colors.white.withOpacity(0.5), fontSize: 14)),
            const SizedBox(height: 36),
            SizedBox(
              width: 180,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  backgroundColor: Colors.white.withOpacity(0.1),
                  valueColor: const AlwaysStoppedAnimation(_K.green),
                  minHeight: 3,
                ),
              ),
            ),
          ]),
        ),
      ]),
    );
  }
}

/* ══════════════════════════════════════════════════════════════
    MEAL ANALYSIS SCREEN
══════════════════════════════════════════════════════════════ */

class MealAnalysisScreen extends StatefulWidget {
  final AnalyzeResponse result;
  final File? imageFile;
  final int? mealId;
  const MealAnalysisScreen(
      {super.key, required this.result, this.imageFile, this.mealId});
  @override
  State<MealAnalysisScreen> createState() => _MealAnalysisScreenState();
}

class _MealAnalysisScreenState extends State<MealAnalysisScreen> {
  late AnalyzeResponse data;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    data = widget.result;
  }

  void _onSave() async {
    setState(() => _saving = true);
    await DBHelper.saveMeal(data, id: widget.mealId);
    if (!mounted) return;
    setState(() => _saving = false);
    Navigator.pop(context, true);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Row(children: [
        const Icon(Icons.check_circle_rounded, color: Colors.white),
        const SizedBox(width: 10),
        Text(widget.mealId != null ? 'Meal Updated!' : 'Meal Logged!'),
      ]),
      backgroundColor: _K.green.withOpacity(0.92),
      behavior: SnackBarBehavior.floating,
      shape:
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ));
  }

  void _onDelete() async {
    if (widget.mealId == null) return;
    await DBHelper.deleteMeal(widget.mealId!);
    if (!mounted) return;
    Navigator.pop(context, true);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: const Row(children: [
        Icon(Icons.delete_rounded, color: Colors.white),
        SizedBox(width: 10),
        Text('Meal Deleted'),
      ]),
      backgroundColor: Colors.redAccent.withOpacity(0.92),
      behavior: SnackBarBehavior.floating,
      shape:
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bool isEditing = widget.mealId != null;
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          // ── Collapsible hero image ──────────────────────────
          SliverAppBar(
            expandedHeight: 290,
            pinned: true,
            backgroundColor:
                isDark ? _K.bgDark : Theme.of(context).scaffoldBackgroundColor,
            flexibleSpace: FlexibleSpaceBar(
              background: Stack(fit: StackFit.expand, children: [
                widget.imageFile != null
                    ? Image.file(widget.imageFile!, fit: BoxFit.cover)
                    : Container(
                        decoration:
                            const BoxDecoration(gradient: _K.greenGrad),
                        child: const Icon(Icons.fastfood_rounded,
                            size: 90, color: Colors.black26),
                      ),
                // Fade-to-background overlay
                Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.transparent,
                        (isDark ? _K.bgDark : Theme.of(context).scaffoldBackgroundColor)
                            .withOpacity(0.95),
                      ],
                      stops: const [0.35, 1.0],
                    ),
                  ),
                ),
              ]),
            ),
            actions: isEditing
                ? [
                    IconButton(
                      icon: Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.red.withOpacity(0.15),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.delete_rounded,
                            color: Colors.redAccent, size: 20),
                      ),
                      onPressed: _onDelete,
                    ),
                    const SizedBox(width: 8),
                  ]
                : null,
          ),

          // ── Scrollable content ──────────────────────────────
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(18, 0, 18, 60),
              child: Column(children: [
                // ── Calories + macro rings card ────────────
                GlassBox(
                  child: Column(children: [
                    const Text('TOTAL CALORIES',
                        style: TextStyle(
                          fontSize: 11,
                          letterSpacing: 2,
                          fontWeight: FontWeight.w700,
                          color: Colors.grey,
                        )),
                    const SizedBox(height: 6),
                    // Animated gradient calorie number
                    TweenAnimationBuilder<double>(
                      duration: const Duration(milliseconds: 1200),
                      curve: Curves.easeOutCubic,
                      tween: Tween(begin: 0, end: data.totalCalories),
                      builder: (_, v, __) => ShaderMask(
                        blendMode: BlendMode.srcIn,
                        shaderCallback: (b) =>
                            const LinearGradient(colors: [_K.green, _K.teal])
                                .createShader(b),
                        child: Text(
                          v.toStringAsFixed(0),
                          style: const TextStyle(
                            fontSize: 66,
                            fontWeight: FontWeight.w900,
                            letterSpacing: -2,
                          ),
                        ),
                      ),
                    ),
                    Text('kilocalories',
                        style: TextStyle(
                            fontSize: 13, color: Colors.grey.shade500)),
                    const SizedBox(height: 28),
                    // Macro rings
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                      children: [
                        MacroRing(
                            label: 'PROTEIN',
                            value: data.totalProtein,
                            max: 100,
                            color: _K.orange),
                        MacroRing(
                            label: 'CARBS',
                            value: data.totalCarbs,
                            max: 200,
                            color: _K.blue),
                        MacroRing(
                            label: 'FAT',
                            value: data.totalFat,
                            max: 80,
                            color: _K.pink),
                      ],
                    ),
                    const SizedBox(height: 24),
                    Divider(color: Colors.grey.withOpacity(0.15)),
                    const SizedBox(height: 20),
                    MacroBar(
                        label: 'PROTEIN',
                        value: data.totalProtein,
                        max: 100,
                        color: _K.orange),
                    const SizedBox(height: 16),
                    MacroBar(
                        label: 'CARBS',
                        value: data.totalCarbs,
                        max: 200,
                        color: _K.blue),
                    const SizedBox(height: 16),
                    MacroBar(
                        label: 'FAT',
                        value: data.totalFat,
                        max: 80,
                        color: _K.pink),
                  ]),
                ),

                const SizedBox(height: 30),

                // ── Detected items section label ───────────
                Row(children: [
                  const Text('DETECTED ITEMS',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 2,
                        color: Colors.grey,
                      )),
                  const SizedBox(width: 10),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                    decoration: BoxDecoration(
                      color: _K.green.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text('${data.items.length}',
                        style: const TextStyle(
                            color: _K.green,
                            fontSize: 11,
                            fontWeight: FontWeight.bold)),
                  ),
                ]),
                const SizedBox(height: 14),

                // ── Food item cards ───────────────────────
                ...data.items.map((item) => _FoodItemCard(
                      item: item,
                      onUpdate: () => setState(() {}),
                    )),

                const SizedBox(height: 30),

                // ── Save / Update button ──────────────────
                GestureDetector(
                  onTap: _saving ? null : _onSave,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    height: 62,
                    decoration: BoxDecoration(
                      gradient: _saving
                          ? null
                          : const LinearGradient(
                              colors: [_K.green, _K.teal]),
                      color: _saving
                          ? Colors.grey.withOpacity(0.15)
                          : null,
                      borderRadius: BorderRadius.circular(22),
                      boxShadow: _saving
                          ? []
                          : [
                              BoxShadow(
                                color: _K.green.withOpacity(0.40),
                                blurRadius: 24,
                                offset: const Offset(0, 10),
                              )
                            ],
                    ),
                    child: Center(
                      child: _saving
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2.5,
                                  color: Colors.white))
                          : Row(mainAxisSize: MainAxisSize.min, children: [
                              const Icon(Icons.bookmark_added_rounded,
                                  color: Colors.black, size: 20),
                              const SizedBox(width: 10),
                              Text(
                                isEditing ? 'Update Entry' : 'Log Meal',
                                style: const TextStyle(
                                  color: Colors.black,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 16,
                                  letterSpacing: 0.3,
                                ),
                              ),
                            ]),
                    ),
                  ),
                ),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

class _FoodItemCard extends StatelessWidget {
  final FoodItem item;
  final VoidCallback onUpdate;
  const _FoodItemCard({required this.item, required this.onUpdate});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: GlassBox(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(children: [
          // Icon badge
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: _K.green.withOpacity(0.1),
              borderRadius: BorderRadius.circular(13),
              border: Border.all(color: _K.green.withOpacity(0.18)),
            ),
            child: const Icon(Icons.restaurant_rounded,
                color: _K.green, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.name,
                      style: const TextStyle(
                          fontWeight: FontWeight.bold, fontSize: 14)),
                  const SizedBox(height: 3),
                  Text(
                    '${(item.baseServingSizeG * item.portionRatio).round()} g  ·  ${item.calories.round()} kcal',
                    style: TextStyle(
                        fontSize: 12, color: Colors.grey.shade500),
                  ),
                ]),
          ),
          // Portion stepper
          Row(mainAxisSize: MainAxisSize.min, children: [
            _SmallBtn(
                icon: Icons.remove,
                onTap: () {
                  item.updateRatio(item.portionRatio - 0.2);
                  onUpdate();
                }),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: Text('${(item.portionRatio * 100).round()}%',
                  style: const TextStyle(
                      fontWeight: FontWeight.bold, fontSize: 13)),
            ),
            _SmallBtn(
                icon: Icons.add,
                onTap: () {
                  item.updateRatio(item.portionRatio + 0.2);
                  onUpdate();
                }),
          ]),
        ]),
      ),
    );
  }
}

class _SmallBtn extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _SmallBtn({required this.icon, required this.onTap});
  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      width: 32,
      height: 32,
      decoration: BoxDecoration(
        color: _K.green.withOpacity(0.1),
        shape: BoxShape.circle,
        border: Border.all(color: _K.green.withOpacity(0.2)),
      ),
      child: Icon(icon, size: 15, color: _K.green),
    ),
  );
}

/* ══════════════════════════════════════════════════════════════
    HISTORY SCREEN
══════════════════════════════════════════════════════════════ */

class MealHistoryScreen extends StatefulWidget {
  const MealHistoryScreen({super.key});
  @override
  State<MealHistoryScreen> createState() => _MealHistoryScreenState();
}

class _MealHistoryScreenState extends State<MealHistoryScreen> {
  List<Map<String, dynamic>> _meals = [];

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  void _refresh() async {
    final d = await DBHelper.getMeals();
    setState(() => _meals = d);
  }

  void _editMeal(Map<String, dynamic> row) async {
    final itemsList = jsonDecode(row['items_json']) as List;
    final res =
        AnalyzeResponse(items: itemsList.map((e) => FoodItem.fromJson(e)).toList());
    final updated = await Navigator.push(
        context,
        _slide(MealAnalysisScreen(result: res, mealId: row['id'])));
    if (updated == true) _refresh();
  }

  String _label(String iso) {
    final dt = DateTime.parse(iso).toLocal();
    final now = DateTime.now();
    if (dt.year == now.year &&
        dt.month == now.month &&
        dt.day == now.day) return 'Today';
    if (dt.year == now.year &&
        dt.month == now.month &&
        dt.day == now.day - 1) return 'Yesterday';
    return '${dt.day}/${dt.month}/${dt.year}';
  }

  String _time(String iso) {
    final dt = DateTime.parse(iso).toLocal();
    return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('History',
            style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: -0.5)),
        centerTitle: false,
      ),
      body: _meals.isEmpty
          ? Center(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.no_meals_rounded, size: 72, color: Colors.grey.shade700),
              const SizedBox(height: 18),
              Text('No meals logged yet',
                  style: TextStyle(
                      color: Colors.grey.shade500,
                      fontSize: 16,
                      fontWeight: FontWeight.w500)),
            ]))
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(18, 100, 18, 40),
              itemCount: _meals.length,
              itemBuilder: (_, i) {
                final m = _meals[i];
                final showHeader = i == 0 ||
                    _label(m['timestamp']) !=
                        _label(_meals[i - 1]['timestamp']);
                return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (showHeader) ...[
                        if (i != 0) const SizedBox(height: 10),
                        Padding(
                          padding:
                              const EdgeInsets.only(left: 4, bottom: 10, top: 6),
                          child: Text(
                            _label(m['timestamp']),
                            style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 1.8,
                                color: Colors.grey.shade500),
                          ),
                        ),
                      ],
                      GestureDetector(
                        onTap: () => _editMeal(m),
                        child: GlassBox(
                          padding: const EdgeInsets.all(16),
                          child: Row(children: [
                            // Left: icon + time
                            Column(
                                crossAxisAlignment: CrossAxisAlignment.center,
                                children: [
                                  Container(
                                    width: 46,
                                    height: 46,
                                    decoration: BoxDecoration(
                                      gradient: const LinearGradient(
                                          colors: [_K.green, _K.teal]),
                                      borderRadius:
                                          BorderRadius.circular(13),
                                    ),
                                    child: const Icon(
                                        Icons.restaurant_menu_rounded,
                                        color: Colors.black,
                                        size: 20),
                                  ),
                                  const SizedBox(height: 6),
                                  Text(_time(m['timestamp']),
                                      style: TextStyle(
                                          fontSize: 10,
                                          color: Colors.grey.shade500,
                                          fontWeight: FontWeight.w600)),
                                ]),
                            const SizedBox(width: 14),
                            // Center: name + macro chips
                            Expanded(
                              child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                  children: [
                                    Text(m['label'],
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            fontWeight: FontWeight.bold,
                                            fontSize: 14)),
                                    const SizedBox(height: 9),
                                    Row(children: [
                                      _MacroChip(
                                          'P',
                                          '${(m['total_protein'] as double).round()}g',
                                          _K.orange),
                                      const SizedBox(width: 6),
                                      _MacroChip(
                                          'C',
                                          '${(m['total_carbs'] as double).round()}g',
                                          _K.blue),
                                      const SizedBox(width: 6),
                                      _MacroChip(
                                          'F',
                                          '${(m['total_fat'] as double).round()}g',
                                          _K.pink),
                                    ]),
                                  ]),
                            ),
                            // Right: calorie count
                            Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  ShaderMask(
                                    blendMode: BlendMode.srcIn,
                                    shaderCallback: (b) =>
                                        const LinearGradient(
                                                colors: [_K.green, _K.teal])
                                            .createShader(b),
                                    child: Text(
                                      '${(m['total_calories'] as double).round()}',
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w900,
                                          fontSize: 24),
                                    ),
                                  ),
                                  Text('kcal',
                                      style: TextStyle(
                                          fontSize: 10,
                                          color: Colors.grey.shade500)),
                                  const SizedBox(height: 8),
                                  const Icon(Icons.chevron_right_rounded,
                                      size: 18, color: Colors.grey),
                                ]),
                          ]),
                        ),
                      ),
                      const SizedBox(height: 12),
                    ]);
              },
            ),
    );
  }
}
