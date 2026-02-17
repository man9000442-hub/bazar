import sqlite3

def clean_social_tables():
    print("جاري حذف جداول socialaccount المعطلة...")
    try:
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        # قائمة الجداول التي نريد حذفها لإعادة إنشائها
        tables = [
            "socialaccount_socialaccount",
            "socialaccount_socialapp",
            "socialaccount_socialapp_sites",
            "socialaccount_socialtoken",
            "socialaccount_emailconfirmation", 
            "socialaccount_emailaddress"
        ]

        for table in tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {table};")
                print(f"✅ تم حذف الجدول: {table}")
            except Exception as e:
                print(f"⚠️ تخطي {table}: {e}")

        conn.commit()
        conn.close()
        print("\n🚀 الآن قاعدة البيانات نظيفة من مخلفات socialaccount.")
        
    except Exception as e:
        print(f"❌ حدث خطأ في الاتصال: {e}")

if __name__ == "__main__":
    clean_social_tables()