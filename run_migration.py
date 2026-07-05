from database import init_db, seed_sms_templates, seed_tractates, seed_questions

def run():
    print("Starting database migration...")
    init_db()
    print("Database schema updated.")
    
    print("Seeding templates...")
    seed_sms_templates()
    
    print("Seeding tractates...")
    seed_tractates()
    
    print("Migrating questions to include classification...")
    seed_questions()
    
    print("✅ Migration completed successfully.")

if __name__ == "__main__":
    run()
