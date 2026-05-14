print("REAL SEED FILE EXECUTED")
from database import SessionLocal, Food, init_db


def seed_food_data():
    init_db()
    db = SessionLocal()

    if db.query(Food).count() > 0:
        db.close()
        return

    foods = [
        Food(
            name="burger",
            category="fast_food",
            serving_size=150,
            calories=393,
            protein_g=23,
            carbs_g=32,
            fat_g=19,
            source="USDA",
        ),
        Food(
            name="pizza",
            category="fast_food",
            serving_size=200,
            calories=532,
            protein_g=22,
            carbs_g=66,
            fat_g=20,
            source="USDA",
        ),
        Food(
            name="fries",
            category="fast_food",
            serving_size=50,
            calories=156,
            protein_g=1.6,
            carbs_g=20.4,
            fat_g=7.5,
            source="USDA",
        ),
        Food(
            name="soft_drinks",
            category="fast_food",
            serving_size=350,
            calories=144,
            protein_g=0,
            carbs_g=38,
            fat_g=0,
            source="USDA",
        ),
        Food(
            name="donut",
            category="fast_food",
            serving_size=52,
            calories=200,
            protein_g=2,
            carbs_g=22,
            fat_g=11,
            source="USDA",
        ),
        Food(
            name="fried_chicken",
            category="fast_food",
            serving_size=83,
            calories=205,
            protein_g=19,
            carbs_g=4,
            fat_g=12.2,
            source="USDA",
        ),
    ]

    db.add_all(foods)
    db.commit()
    db.close()
    print("Database seeded successfully.")