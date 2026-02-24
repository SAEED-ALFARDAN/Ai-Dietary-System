from database import SessionLocal, init_db, Food

init_db()

foods = [
    Food(
        food_id=1,
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
        food_id=2,
        name="fries",
        category="Fast Food",
        serving_size=100.0,
        calories=300.0,
        protein_g=3.0,
        carbs_g=40.0,
        fat_g=15.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=3,
        name="pizza",
        category="Fast Food",
        serving_size=120.0,
        calories=285.0,
        protein_g=12.0,
        carbs_g=36.0,
        fat_g=10.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=4,
        name="shawarma",
        category="Fast Food",
        serving_size=180.0,
        calories=450.0,
        protein_g=25.0,
        carbs_g=40.0,
        fat_g=20.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=5,
        name="soft_drink",
        category="Beverage",
        serving_size=330.0,
        calories=140.0,
        protein_g=0.0,
        carbs_g=35.0,
        fat_g=0.0,
        source="USDA / FoodData Central",
    ),
]

db = SessionLocal()

for f in foods:
    existing = db.query(Food).filter(Food.food_id == f.food_id).first()
    if not existing:
        db.add(f)

db.commit()
db.close()
print("Seeded Food table.")