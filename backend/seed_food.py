from database import SessionLocal, init_db, Food

init_db()

foods = [
    Food(
        food_id=1,
        name="burger",
        category="Fast Food",
        serving_size=150.0,
        calories=856.0,
        protein_g=45.0,
        carbs_g=60.0,
        fat_g=48.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=2,
        name="donut",
        category="Bakery",
        serving_size=60.0,
        calories=253.0,
        protein_g=4.0,
        carbs_g=30.0,
        fat_g=14.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=3,
        name="fried_chicken",
        category="Fast Food",
        serving_size=150.0,
        calories=405.0,
        protein_g=30.0,
        carbs_g=16.0,
        fat_g=26.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=4,
        name="fries",
        category="Fast Food",
        serving_size=100.0,
        calories=302.0,
        protein_g=3.5,
        carbs_g=38.0,
        fat_g=16.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=5,
        name="pizza",
        category="Fast Food",
        serving_size=120.0,
        calories=320.0,
        protein_g=13.0,
        carbs_g=37.0,
        fat_g=13.0,
        source="USDA / FoodData Central",
    ),
    Food(
        food_id=6,
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