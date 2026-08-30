# migrate_db.py - Run on Render to add missing columns

import os
import sys
from app import app, db
from sqlalchemy import inspect

def migrate():
    """Add missing columns to user table"""
    with app.app_context():
        try:
            print("🔍 Checking database schema...")
            inspector = inspect(db.engine)
            
            # Check if user table exists
            if 'user' not in inspector.get_table_names():
                print("❌ User table doesn't exist. Creating tables...")
                db.create_all()
                return
            
            # Get existing columns
            columns = [col['name'] for col in inspector.get_columns('user')]
            print(f"📋 Existing columns: {', '.join(columns)}")
            
            # Add missing columns
            added = []
            
            if 'is_suspended' not in columns:
                db.session.execute('ALTER TABLE "user" ADD COLUMN is_suspended BOOLEAN DEFAULT FALSE')
                added.append('is_suspended')
                print("✅ Added is_suspended")
            
            if 'suspension_reason' not in columns:
                db.session.execute('ALTER TABLE "user" ADD COLUMN suspension_reason TEXT')
                added.append('suspension_reason')
                print("✅ Added suspension_reason")
            
            if 'suspended_at' not in columns:
                db.session.execute('ALTER TABLE "user" ADD COLUMN suspended_at TIMESTAMP')
                added.append('suspended_at')
                print("✅ Added suspended_at")
            
            if 'phone' not in columns:
                db.session.execute('ALTER TABLE "user" ADD COLUMN phone VARCHAR(20)')
                added.append('phone')
                print("✅ Added phone")
            
            if 'dob' not in columns:
                db.session.execute('ALTER TABLE "user" ADD COLUMN dob TIMESTAMP')
                added.append('dob')
                print("✅ Added dob")
            
            if 'profile_picture' not in columns:
                db.session.execute('ALTER TABLE "user" ADD COLUMN profile_picture VARCHAR(200)')
                added.append('profile_picture')
                print("✅ Added profile_picture")
            
            db.session.commit()
            
            if added:
                print(f"✅ Migration completed! Added: {', '.join(added)}")
            else:
                print("✅ All columns already exist!")
                
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Error during migration: {e}")
            sys.exit(1)

if __name__ == '__main__':
    print("🚀 Starting database migration...")
    migrate()
    print("✅ Migration script completed!")