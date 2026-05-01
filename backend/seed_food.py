from database import SessionLocal, Food

db = SessionLocal()

missing = [
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
        name="fried_chicken",   # model label "fried chicken" → normalized to this
        category="Fast Food",
        serving_size=140.0,
        calories=400.0,
        protein_g=30.0,
        carbs_g=15.0,
        fat_g=24.0,
        source="USDA / FoodData Central",
    ),
    Food(
        name="soft_drinks",     # model label "soft drinks" → normalized to this
        category="Beverage",
        serving_size=330.0,
        calories=140.0,
        protein_g=0.0,
        carbs_g=35.0,
        fat_g=0.0,
        source="USDA / FoodData Central",
    ),
]

for f in missing:
    exists = db.query(Food).filter(Food.name == f.name).first()
    if not exists:
        db.add(f)
        print(f"✅ Added: {f.name}")
    else:
        print(f"⏭️ Already exists: {f.name}")

db.commit()
db.close()