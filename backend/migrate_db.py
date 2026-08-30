# migrate_db.py - Complete migration script

import os
import sys
from sqlalchemy import text
from app import app, db

def run_migration():
    """Add missing columns to all tables"""
    with app.app_context():
        try:
            print("🚀 Starting database migration...")
            
            with db.engine.connect() as conn:
                # ==========================================
                # USER TABLE
                # ==========================================
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'user'
                """))
                user_columns = [row[0] for row in result]
                print(f"📋 User columns: {', '.join(user_columns)}")
                
                user_added = []
                
                if 'is_suspended' not in user_columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN is_suspended BOOLEAN DEFAULT FALSE'))
                    user_added.append('is_suspended')
                    print("✅ Added is_suspended to user")
                
                if 'suspension_reason' not in user_columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN suspension_reason TEXT'))
                    user_added.append('suspension_reason')
                    print("✅ Added suspension_reason to user")
                
                if 'suspended_at' not in user_columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN suspended_at TIMESTAMP'))
                    user_added.append('suspended_at')
                    print("✅ Added suspended_at to user")
                
                if 'phone' not in user_columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN phone VARCHAR(20)'))
                    user_added.append('phone')
                    print("✅ Added phone to user")
                
                if 'dob' not in user_columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN dob TIMESTAMP'))
                    user_added.append('dob')
                    print("✅ Added dob to user")
                
                if 'profile_picture' not in user_columns:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN profile_picture VARCHAR(200)'))
                    user_added.append('profile_picture')
                    print("✅ Added profile_picture to user")
                
                # ==========================================
                # ANNOUNCEMENT TABLE
                # ==========================================
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'announcement'
                """))
                ann_columns = [row[0] for row in result]
                print(f"📋 Announcement columns: {', '.join(ann_columns)}")
                
                ann_added = []
                
                if 'course_id' not in ann_columns:
                    conn.execute(text('ALTER TABLE "announcement" ADD COLUMN course_id INTEGER REFERENCES course(id)'))
                    ann_added.append('course_id')
                    print("✅ Added course_id to announcement")
                
                conn.commit()
                
                if user_added or ann_added:
                    print(f"✅ Migration completed!")
                    if user_added:
                        print(f"   User: {', '.join(user_added)}")
                    if ann_added:
                        print(f"   Announcement: {', '.join(ann_added)}")
                else:
                    print("✅ All columns already exist!")
                
        except Exception as e:
            print(f"⚠️ Error during migration: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == '__main__':
    run_migration()