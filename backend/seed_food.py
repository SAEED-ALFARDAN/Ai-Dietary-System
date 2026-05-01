from database import SessionLocal, Food

db = SessionLocal()

all_foods = [
    Food(
        name="burger",
        category="Fast Food",
        serving_size=150.0,
        calories=600.0,
        protein_g=25.0,
        carbs_g=50.0,
        fat_g=30.0,
        source="USDA / FoodData Central",
    ),
    Food(
        name="donut",
        category="Fast Food",
        serving_size=60.0,
        calories=250.0,
        protein_g=4.0,
        carbs_g=32.0,
        fat_g=12.0,
        source="USDA / FoodData Central",
    ),
    Food(
        name="fried_chicken",
        category="Fast Food",
        serving_size=140.0,
        calories=400.0,
        protein_g=30.0,
        carbs_g=15.0,
        fat_g=24.0,
        source="USDA / FoodData Central",
    ),
    Food(
        name="fries",
        category="Fast Food",
        serving_size=100.0,
        calories=312.0,
        protein_g=3.4,
        carbs_g=41.0,
        fat_g=15.0,
        source="USDA / FoodData Central",
    ),
    Food(
        name="pizza",
        category="Fast Food",
        serving_size=107.0,
        calories=285.0,
        protein_g=12.0,
        carbs_g=36.0,
        fat_g=10.0,
        source="USDA / FoodData Central",
    ),
    Food(
        name="soft_drinks",
        category="Beverage",
        serving_size=330.0,
        calories=140.0,
        protein_g=0.0,
        carbs_g=35.0,
        fat_g=0.0,
        source="USDA / FoodData Central",
    ),
]

for f in all_foods:
    exists = db.query(Food).filter(Food.name == f.name).first()
    if not exists:
        db.add(f)
        print(f"✅ Added: {f.name}")
    else:
        # Update existing entry with correct values
        exists.category     = f.category
        exists.serving_size = f.serving_size
        exists.calories     = f.calories
        exists.protein_g    = f.protein_g
        exists.carbs_g      = f.carbs_g
        exists.fat_g        = f.fat_g
        exists.source       = f.source
        print(f"🔄 Updated: {f.name}")

db.commit()
db.close()
print("\n✅ All 6 foods seeded successfully!")