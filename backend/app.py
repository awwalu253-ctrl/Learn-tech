# app.py - Awwalu Devs Learning Management System
# Complete backend with all features in one file
import json
import os
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import logging

# ============================================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================================

# Load .env from root directory
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# ============================================================================
# APP CONFIGURATION
# ============================================================================

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# Security - Secret key for session encryption
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'awwaludevs-secret-key-change-in-production')

# ============================================================================
# DATABASE CONFIGURATION - UPDATED FOR SUPABASE
# ============================================================================

# Get database URL from environment
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Check if it's Supabase
    if 'supabase.co' in database_url or 'pooler.supabase.com' in database_url:
        print("🔗 Connecting to Supabase PostgreSQL...")
        # Ensure SSL is enabled for Supabase
        if 'sslmode' not in database_url:
            database_url += '?sslmode=require'
        print("✅ Supabase connection configured")
    elif os.environ.get('RENDER'):
        # PostgreSQL on Render
        if 'sslmode' not in database_url:
            database_url += '?sslmode=require'
        print("🔗 Connecting to Render PostgreSQL...")
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    
    # Connection pool settings for production
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'connect_args': {
            'connect_timeout': 10  # Prevent timeout issues
        }
    }
else:
    # Fallback to SQLite for local development
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../database/awwaludevs.db'
    print("⚠️ Using SQLite (local development)")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ============================================================================
# UPLOAD CONFIGURATION
# ============================================================================

if os.environ.get('RENDER'):
    app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
else:
    app.config['UPLOAD_FOLDER'] = '../static/uploads'

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'txt', 'zip'}

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
if not os.environ.get('RENDER'):
    os.makedirs(os.path.join(os.path.dirname(__file__), '../database'), exist_ok=True)

# ============================================================================
# LOGGING
# ============================================================================

if os.environ.get('RENDER'):
    logging.basicConfig(level=logging.INFO)
    app.logger.setLevel(logging.INFO)

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_upload_path(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    unique_name = f"{uuid.uuid4().hex[:12]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return f"{unique_name}.{ext}" if ext else unique_name

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['admin', 'super_admin']:
            flash('Admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'super_admin':
            flash('Super admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# NOTIFICATION HELPER FUNCTIONS
# ============================================================================

def create_notification(user_id, title, message, type='info', link=None, icon='fa-bell', icon_color='gold'):
    """Create a notification for a user"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        link=link,
        icon=icon,
        icon_color=icon_color
    )
    db.session.add(notification)
    db.session.commit()
    return notification

def notify_student_approved(student_id):
    """Notify student when their account is approved"""
    user = User.query.get(student_id)
    if user:
        create_notification(
            user_id=student_id,
            title='Account Approved! 🎉',
            message=f'Your account has been approved. You can now log in and access courses.',
            type='success',
            link=url_for('student_dashboard'),
            icon='fa-check-circle',
            icon_color='green'
        )

def notify_student_rejected(student_id, course_name, reason):
    """Notify student when they are rejected from a course"""
    create_notification(
        user_id=student_id,
        title='Course Request Rejected ❌',
        message=f'Your request for "{course_name}" has been rejected. Reason: {reason}',
        type='error',
        link=url_for('student_courses'),
        icon='fa-times-circle',
        icon_color='red'
    )

def notify_course_approved(student_id, course_name):
    """Notify student when they are approved for a course"""
    course = Course.query.filter_by(name=course_name).first()
    create_notification(
        user_id=student_id,
        title='Course Approved! ✅',
        message=f'You have been approved for "{course_name}". Start learning now!',
        type='success',
        link=url_for('view_course', course_id=course.id) if course else None,
        icon='fa-check-circle',
        icon_color='green'
    )

def notify_course_request(student_id, course_name):
    """Notify student when they request a course"""
    create_notification(
        user_id=student_id,
        title='Course Requested 📚',
        message=f'Your request for "{course_name}" has been sent. Waiting for admin approval.',
        type='info',
        link=url_for('student_courses'),
        icon='fa-clock',
        icon_color='gold'
    )

def notify_admin_course_request(admin_id, student_name, course_name):
    """Notify admin when a student requests a course"""
    create_notification(
        user_id=admin_id,
        title='New Course Request 📋',
        message=f'{student_name} has requested access to "{course_name}". Please review.',
        type='warning',
        link=url_for('manage_students'),
        icon='fa-users',
        icon_color='orange'
    )

def notify_student_suspended(student_id, reason):
    """Notify student when they are suspended"""
    create_notification(
        user_id=student_id,
        title='Account Suspended ⛔',
        message=f'Your account has been suspended. Reason: {reason}',
        type='error',
        link=None,
        icon='fa-ban',
        icon_color='red'
    )

def notify_student_unsuspended(student_id):
    """Notify student when they are unsuspended"""
    create_notification(
        user_id=student_id,
        title='Account Restored ✅',
        message='Your account has been unsuspended. You can now log in and access courses.',
        type='success',
        link=url_for('login'),
        icon='fa-check-circle',
        icon_color='green'
    )

# ============================================================================
# DATABASE MODELS - CORRECT ORDER
# ============================================================================

# 1. Association Tables
admin_course = db.Table('admin_course',
    db.Column('admin_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'))
)

student_course = db.Table('student_course',
    db.Column('student_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'))
)

# 2. CourseEnrollment MUST be defined BEFORE User
class CourseEnrollment(db.Model):
    __tablename__ = 'course_enrollment'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)
    rejected_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    
    # Relationships - will be resolved after User and Course are defined
    student = db.relationship('User', backref='enrollments', foreign_keys=[student_id])
    course = db.relationship('Course', backref='enrollments')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='unique_student_course_enrollment'),
        db.Index('idx_enrollment_student_course', 'student_id', 'course_id'),
        db.Index('idx_enrollment_status', 'status'),
    )

# 3. User model
class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='student')
    is_approved = db.Column(db.Boolean, default=False)
    is_suspended = db.Column(db.Boolean, default=False)
    suspension_reason = db.Column(db.Text, nullable=True)
    suspended_at = db.Column(db.DateTime, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    dob = db.Column(db.DateTime, nullable=True)
    profile_picture = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    dark_mode = db.Column(db.Boolean, default=False)
    
    # Admin can manage multiple courses
    managed_courses = db.relationship('Course', secondary=admin_course, backref='admins')
    
    # Student enrollments - CourseEnrollment is now defined
    # enrollments relationship is defined via CourseEnrollment.student
    
    notes_read = db.relationship('StudentProgress', backref='student', lazy=True)
    quiz_answers = db.relationship('QuizAnswer', backref='student', lazy=True)
    submissions = db.relationship('AssignmentSubmission', backref='student', lazy=True)
    
    __table_args__ = (
        db.Index('idx_user_role_status', 'role', 'is_approved'),
        db.Index('idx_user_created', 'created_at'),
        db.Index('idx_user_username', 'username'),
        db.Index('idx_user_email', 'email'),
    )
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_courses(self):
        """Get all courses the user has access to"""
        if self.role == 'super_admin':
            return Course.query.all()
        elif self.role == 'admin':
            return self.managed_courses
        else:
            return self.get_enrolled_courses()
    
    def is_admin(self):
        return self.role in ['admin', 'super_admin']
    
    def is_super_admin(self):
        return self.role == 'super_admin'
    
    def is_active(self):
        """Check if user account is active (not suspended)"""
        return not self.is_suspended
    
    def get_unread_notifications_count(self):
        """Get count of unread notifications"""
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()
    
    def get_recent_notifications(self, limit=10):
        """Get recent notifications"""
        return Notification.query.filter_by(user_id=self.id).order_by(
            Notification.created_at.desc()
        ).limit(limit).all()
    
    # ==========================================
    # COURSE ENROLLMENT METHODS
    # ==========================================
    
    def is_enrolled_in_course(self, course_id):
        """Check if student is approved for a specific course"""
        from sqlalchemy import and_
        enrollment = CourseEnrollment.query.filter(
            and_(
                CourseEnrollment.student_id == self.id,
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.status == 'approved'
            )
        ).first()
        return enrollment is not None
    
    def has_pending_request_for_course(self, course_id):
        """Check if student has a pending request for a course"""
        from sqlalchemy import and_
        enrollment = CourseEnrollment.query.filter(
            and_(
                CourseEnrollment.student_id == self.id,
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.status == 'pending'
            )
        ).first()
        return enrollment is not None
    
    def get_course_status(self, course_id):
        """Get the status of a specific course enrollment"""
        enrollment = CourseEnrollment.query.filter_by(
            student_id=self.id,
            course_id=course_id
        ).first()
        return enrollment.status if enrollment else None
    
    def get_enrolled_courses(self):
        """Get all courses where student is approved"""
        enrollments = CourseEnrollment.query.filter_by(
            student_id=self.id,
            status='approved'
        ).all()
        return [e.course for e in enrollments]
    
    def get_pending_courses(self):
        """Get all courses where student has pending requests"""
        enrollments = CourseEnrollment.query.filter_by(
            student_id=self.id,
            status='pending'
        ).all()
        return [e.course for e in enrollments]
    
    def get_rejected_courses(self):
        """Get all courses where student was rejected"""
        enrollments = CourseEnrollment.query.filter_by(
            student_id=self.id,
            status='rejected'
        ).all()
        return [e.course for e in enrollments]
    
    def __repr__(self):
        return f'<User {self.username}>'

# 4. Course model
class Course(db.Model):
    __tablename__ = 'course'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    code = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    notes = db.relationship('Note', backref='course', lazy=True, cascade='all, delete-orphan')
    quiz_groups = db.relationship('QuizGroup', backref='course', lazy=True, cascade='all, delete-orphan')
    assignments = db.relationship('Assignment', backref='course', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        db.Index('idx_course_code', 'code'),
        db.Index('idx_course_name', 'name'),
    )
    
    def get_progress_for_student(self, student_id):
        total_notes = Note.query.filter_by(course_id=self.id).count()
        if total_notes == 0:
            return 0
        read_count = StudentProgress.query.filter_by(
            student_id=student_id, 
            course_id=self.id,
            is_read=True
        ).count()
        return int((read_count / total_notes) * 100)

# 5. Tag model
class Tag(db.Model):
    __tablename__ = 'tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    notes = db.relationship('Note', backref='tag', lazy=True)
    
    __table_args__ = (
        db.Index('idx_tag_name', 'name'),
    )

# 6. Note model
class Note(db.Model):
    __tablename__ = 'note'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.String(200))
    file_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tag.id'))
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    author = db.relationship('User', backref='notes')
    progress = db.relationship('StudentProgress', backref='note', lazy=True)
    
    __table_args__ = (
        db.Index('idx_note_course', 'course_id'),
        db.Index('idx_note_tag', 'tag_id'),
        db.Index('idx_note_created', 'created_at'),
    )
    
    def is_new(self):
        return (datetime.utcnow() - self.created_at).days <= 7

# 7. StudentProgress model
class StudentProgress(db.Model):
    __tablename__ = 'student_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    note_id = db.Column(db.Integer, db.ForeignKey('note.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'note_id', name='unique_student_note'),
        db.Index('idx_progress_student', 'student_id'),
        db.Index('idx_progress_course', 'course_id'),
    )

# 8. QuizGroup model
class QuizGroup(db.Model):
    __tablename__ = 'quiz_group'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    time_limit = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    author = db.relationship('User', backref='created_quizzes')
    questions = db.relationship('QuizQuestion', backref='quiz_group', lazy=True, cascade='all, delete-orphan')
    answers = db.relationship('QuizAnswer', backref='quiz_group', lazy=True)
    
    __table_args__ = (
        db.Index('idx_quiz_course', 'course_id'),
        db.Index('idx_quiz_created', 'created_at'),
    )
    
    def get_total_questions(self):
        return len(self.questions)
    
    def get_student_score(self, student_id):
        answers = QuizAnswer.query.filter_by(
            quiz_group_id=self.id,
            student_id=student_id
        ).all()
        if not answers:
            return None
        correct = sum(1 for a in answers if a.is_correct)
        return {'correct': correct, 'total': len(answers), 'score': int((correct / len(answers)) * 100) if answers else 0}

# 9. QuizQuestion model
class QuizQuestion(db.Model):
    __tablename__ = 'quiz_question'
    
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    quiz_group_id = db.Column(db.Integer, db.ForeignKey('quiz_group.id'), nullable=False)
    
    __table_args__ = (
        db.Index('idx_question_quiz', 'quiz_group_id'),
        db.Index('idx_question_order', 'order'),
    )

# 10. QuizAnswer model
class QuizAnswer(db.Model):
    __tablename__ = 'quiz_answer'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    quiz_group_id = db.Column(db.Integer, db.ForeignKey('quiz_group.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_question.id'), nullable=False)
    selected_option = db.Column(db.String(1), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    question = db.relationship('QuizQuestion', backref='answers')
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'question_id', name='unique_student_question'),
        db.Index('idx_answer_student', 'student_id'),
        db.Index('idx_answer_quiz', 'quiz_group_id'),
    )

# 11. Assignment model
class Assignment(db.Model):
    __tablename__ = 'assignment'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    max_score = db.Column(db.Float, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    author = db.relationship('User', backref='created_assignments')
    submissions = db.relationship('AssignmentSubmission', backref='assignment', lazy=True, cascade='all, delete-orphan')
    
    def is_past_due(self):
        return datetime.utcnow() > self.due_date
    
    def get_submission_for_student(self, student_id):
        return AssignmentSubmission.query.filter_by(
            assignment_id=self.id,
            student_id=student_id
        ).first()
    
    def get_submissions_count(self):
        return AssignmentSubmission.query.filter_by(assignment_id=self.id).count()

# 12. AssignmentSubmission model
class AssignmentSubmission(db.Model):
    __tablename__ = 'assignment_submission'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    content = db.Column(db.Text)
    file_path = db.Column(db.String(200))
    file_name = db.Column(db.String(100))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_graded = db.Column(db.Boolean, default=False)
    score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    
    __table_args__ = (
        db.Index('idx_submission_student', 'student_id'),
        db.Index('idx_submission_assignment', 'assignment_id'),
        db.Index('idx_submission_graded', 'is_graded'),
    )

# 13. RejectionMessage model
class RejectionMessage(db.Model):
    __tablename__ = 'rejection_message'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('User', backref='rejections')
    course = db.relationship('Course', backref='rejections')
    
    __table_args__ = (
        db.Index('idx_rejection_student', 'student_id'),
        db.Index('idx_rejection_course', 'course_id'),
    )

# 14. Announcement model
class Announcement(db.Model):
    __tablename__ = 'announcement'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    author = db.relationship('User', backref='announcements')
    course = db.relationship('Course', backref='announcements')
    
    __table_args__ = (
        db.Index('idx_announcement_course', 'course_id'),
        db.Index('idx_announcement_pinned', 'is_pinned'),
        db.Index('idx_announcement_created', 'created_at'),
    )

# 15. Notification model
class Notification(db.Model):
    __tablename__ = 'notification'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')  # info, success, warning, error, approval, rejection
    link = db.Column(db.String(500), nullable=True)
    icon = db.Column(db.String(50), default='fa-bell')
    icon_color = db.Column(db.String(20), default='gold')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')
    
    __table_args__ = (
        db.Index('idx_notification_user', 'user_id'),
        db.Index('idx_notification_user_read', 'user_id', 'is_read'),
        db.Index('idx_notification_created', 'created_at'),
    )
    
    def __repr__(self):
        return f'<Notification {self.id} - {self.user_id}>'

# ============================================================================
# BACKUP MODELS
# ============================================================================

class Backup(db.Model):
    __tablename__ = 'backup'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    backup_date = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text)
    size = db.Column(db.String(50))
    record_count = db.Column(db.Integer, default=0)
    created_by = db.Column(db.String(80))
    
    __table_args__ = (
        db.Index('idx_backup_date', 'backup_date'),
    )
    
    def __repr__(self):
        return f'<Backup {self.filename}>'

# ============================================================================
# EMAIL TEMPLATE MODEL
# ============================================================================

class EmailTemplate(db.Model):
    __tablename__ = 'email_template'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_email_template_name', 'name'),
    )
    
    def __repr__(self):
        return f'<EmailTemplate {self.name}>'

# ============================================================================
# SYSTEM SETTINGS MODEL
# ============================================================================

class SystemSetting(db.Model):
    __tablename__ = 'system_setting'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    setting_type = db.Column(db.String(50), default='string')  # string, boolean, integer, json
    description = db.Column(db.Text)
    category = db.Column(db.String(50), default='general')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.Index('idx_setting_key', 'key'),
        db.Index('idx_setting_category', 'category'),
    )
    
    def __repr__(self):
        return f'<SystemSetting {self.key}={self.value}>'

# ============================================================================
# SYSTEM SETTINGS HELPER FUNCTIONS
# ============================================================================

def save_setting(key, value, setting_type='string', description='', category='general'):
    """Save or update a system setting"""
    try:
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value) if value is not None else ''
            setting.setting_type = setting_type
            setting.description = description
            setting.category = category
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSetting(
                key=key,
                value=str(value) if value is not None else '',
                setting_type=setting_type,
                description=description,
                category=category
            )
            db.session.add(setting)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error saving setting {key}: {e}')
        return False

def get_setting(key, default=None):
    """Get a system setting by key"""
    try:
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            value = setting.value
            if value.lower() == 'true':
                return True
            elif value.lower() == 'false':
                return False
            try:
                if value.isdigit():
                    return int(value)
            except:
                pass
            return value
        return default
    except Exception as e:
        app.logger.error(f'Error getting setting {key}: {e}')
        return default

def get_all_settings():
    """Get all system settings as a dictionary"""
    settings = {}
    try:
        all_settings = SystemSetting.query.all()
        for setting in all_settings:
            value = setting.value
            if value.lower() == 'true':
                settings[setting.key] = True
            elif value.lower() == 'false':
                settings[setting.key] = False
            else:
                try:
                    if value.isdigit():
                        settings[setting.key] = int(value)
                    else:
                        settings[setting.key] = value
                except:
                    settings[setting.key] = value
        return settings
    except Exception as e:
        app.logger.error(f'Error getting all settings: {e}')
        return {}

def get_bool_setting(key, default=False):
    """Get boolean setting"""
    value = get_setting(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == 'true'
    return bool(value)

def get_int_setting(key, default=0):
    """Get integer setting"""
    value = get_setting(key, default)
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def get_str_setting(key, default=''):
    """Get string setting"""
    value = get_setting(key, default)
    return str(value) if value is not None else ''

def get_site_name():
    """Get the site name from settings"""
    return get_setting('site_name', 'A-Portal LMS')

def get_site_description():
    """Get the site description from settings"""
    return get_setting('site_description', 'Learning Management System')

def init_default_settings():
    """Initialize default system settings if they don't exist"""
    defaults = {
        'site_name': 'A-Portal LMS',
        'site_description': 'Learning Management System',
        'default_language': 'en',
        'maintenance_mode': 'False',
        'timezone': 'UTC',
        'auto_approve_students': 'False',
        'max_courses_per_student': '10',
        'allow_reapplications': 'True',
        'require_phone_number': 'True',
        'student_registration_enabled': 'True',
        'session_timeout': '60',
        'require_email_verification': 'False',
        'max_login_attempts': '5',
        'lockout_duration': '30',
        'force_ssl': 'True',
        'max_file_upload_size': '16',
        'allowed_file_types': 'pdf,png,jpg,jpeg,gif,doc,docx,txt,zip',
        'enable_comments': 'False',
        'enable_ratings': 'True',
        'email_notifications': 'True',
        'push_notifications': 'True',
        'assignment_reminders': 'True',
        'reminder_days_before': '3',
    }
    
    for key, value in defaults.items():
        existing = SystemSetting.query.filter_by(key=key).first()
        if not existing:
            setting = SystemSetting(key=key, value=value)
            db.session.add(setting)
    
    db.session.commit()
    app.logger.info('✅ Default system settings initialized')

# ============================================================================
# ADMIN DASHBOARD HELPER FUNCTIONS - ENHANCED
# ============================================================================

def get_admin_upcoming_deadlines(admin_user):
    """Get upcoming deadlines for all courses the admin manages"""
    from sqlalchemy import and_
    
    # Get course IDs based on admin role
    if admin_user.is_super_admin():
        course_ids = [c.id for c in Course.query.all()]
    else:
        course_ids = [c.id for c in admin_user.managed_courses]
    
    # Get assignments with due dates in the future or recent past
    now = datetime.utcnow()
    upcoming = Assignment.query.filter(
        and_(
            Assignment.course_id.in_(course_ids),
            Assignment.due_date >= (now - timedelta(days=7))
        )
    ).order_by(Assignment.due_date.asc()).limit(10).all()
    
    # Format deadlines with status
    deadlines = []
    for assignment in upcoming:
        days_until = (assignment.due_date - now).days
        if days_until < 0:
            status = 'overdue'
            status_text = f'Overdue by {abs(days_until)}d'
        elif days_until == 0:
            status = 'today'
            status_text = 'Today'
        elif days_until <= 3:
            status = 'soon'
            status_text = f'{days_until}d left'
        else:
            status = 'upcoming'
            status_text = f'{days_until}d left'
        
        # Get submission count
        submissions_count = AssignmentSubmission.query.filter_by(
            assignment_id=assignment.id
        ).count()
        
        total_students = CourseEnrollment.query.filter_by(
            course_id=assignment.course_id,
            status='approved'
        ).count()
        
        deadlines.append({
            'id': assignment.id,
            'title': assignment.title,
            'course_name': assignment.course.name,
            'due_date': assignment.due_date,
            'days_until': days_until,
            'status': status,
            'status_text': status_text,
            'submissions_count': submissions_count,
            'total_students': total_students
        })
    
    return deadlines

def get_admin_quiz_results(admin_user):
    """Get recent quiz results for all courses the admin manages"""
    # Get course IDs
    if admin_user.is_super_admin():
        course_ids = [c.id for c in Course.query.all()]
    else:
        course_ids = [c.id for c in admin_user.managed_courses]
    
    # Get all quiz groups in these courses
    quiz_groups = QuizGroup.query.filter(QuizGroup.course_id.in_(course_ids)).all()
    
    results = []
    for quiz in quiz_groups:
        # Get all answers for this quiz
        answers = QuizAnswer.query.filter_by(quiz_group_id=quiz.id).all()
        
        if answers:
            # Group by student
            student_scores = {}
            for answer in answers:
                if answer.student_id not in student_scores:
                    student_scores[answer.student_id] = {'correct': 0, 'total': 0}
                student_scores[answer.student_id]['total'] += 1
                if answer.is_correct:
                    student_scores[answer.student_id]['correct'] += 1
            
            # Calculate average score
            if student_scores:
                total_score = 0
                for s in student_scores.values():
                    total_score += (s['correct'] / s['total']) * 100 if s['total'] > 0 else 0
                avg_score = total_score / len(student_scores)
            else:
                avg_score = 0
            
            # Get latest submission
            latest = QuizAnswer.query.filter_by(
                quiz_group_id=quiz.id
            ).order_by(QuizAnswer.answered_at.desc()).first()
            
            results.append({
                'quiz_id': quiz.id,
                'title': quiz.title,
                'course_name': quiz.course.name,
                'avg_score': round(avg_score, 1),
                'total_students': len(student_scores),
                'latest_submission': latest.answered_at if latest else None,
                'color_class': 'high' if avg_score >= 70 else 'medium' if avg_score >= 50 else 'low'
            })
        else:
            results.append({
                'quiz_id': quiz.id,
                'title': quiz.title,
                'course_name': quiz.course.name,
                'avg_score': 0,
                'total_students': 0,
                'latest_submission': None,
                'color_class': 'low'
            })
    
    # Sort by latest submission (most recent first)
    results.sort(key=lambda x: x['latest_submission'] or datetime(1970, 1, 1), reverse=True)
    return results[:10]

def get_admin_announcements_with_pins(admin_user):
    """Get announcements with pinned badges for admin"""
    if admin_user.is_super_admin():
        announcements = Announcement.query.order_by(
            Announcement.is_pinned.desc(),
            Announcement.created_at.desc()
        ).limit(6).all()
    else:
        course_ids = [c.id for c in admin_user.managed_courses]
        announcements = Announcement.query.filter(
            db.or_(
                Announcement.course_id.in_(course_ids),
                Announcement.course_id.is_(None)
            )
        ).order_by(
            Announcement.is_pinned.desc(),
            Announcement.created_at.desc()
        ).limit(6).all()
    
    result = []
    for ann in announcements:
        result.append({
            'id': ann.id,
            'title': ann.title,
            'content': ann.content,
            'is_pinned': ann.is_pinned,
            'course_name': ann.course.name if ann.course else 'Global',
            'created_at': ann.created_at,
            'author': ann.author.username if ann.author else 'System'
        })
    
    return result

def get_admin_notices_with_ctas(admin_user):
    """Get enhanced notices/alerts with CTAs for admin"""
    notices = []
    
    # 1. Pending student approvals
    pending_students = User.query.filter_by(role='student', is_approved=False).count()
    if pending_students > 0:
        notices.append({
            'type': 'warning',
            'icon': 'fa-user-clock',
            'icon_color': 'orange',
            'title': f'{pending_students} Student(s) Pending Approval',
            'message': f'{pending_students} students are waiting for account approval.',
            'cta_text': 'Review Students',
            'cta_url': url_for('manage_students'),
            'priority': 'high',
            'dismissible': False
        })
    
    # 2. Pending course requests
    pending_enrollments = CourseEnrollment.query.filter_by(status='pending').count()
    if pending_enrollments > 0:
        notices.append({
            'type': 'info',
            'icon': 'fa-book-open',
            'icon_color': 'gold',
            'title': f'{pending_enrollments} Pending Course Request(s)',
            'message': 'Students are waiting for course approval.',
            'cta_text': 'Review Requests',
            'cta_url': url_for('manage_students'),
            'priority': 'medium',
            'dismissible': True
        })
    
    # 3. Assignments due soon
    if admin_user.is_super_admin():
        all_courses = Course.query.all()
    else:
        all_courses = admin_user.managed_courses
    
    course_ids = [c.id for c in all_courses]
    now = datetime.utcnow()
    due_soon = Assignment.query.filter(
        Assignment.course_id.in_(course_ids),
        Assignment.due_date >= now,
        Assignment.due_date <= (now + timedelta(days=3))
    ).count()
    
    if due_soon > 0:
        notices.append({
            'type': 'info',
            'icon': 'fa-clock',
            'icon_color': 'gold',
            'title': f'{due_soon} Assignment(s) Due Soon',
            'message': 'Assignments are due within the next 3 days.',
            'cta_text': 'View Assignments',
            'cta_url': url_for('manage_assignments'),
            'priority': 'medium',
            'dismissible': True
        })
    
    # 4. Overdue assignments
    overdue = Assignment.query.filter(
        Assignment.course_id.in_(course_ids),
        Assignment.due_date < now
    ).count()
    
    if overdue > 0:
        notices.append({
            'type': 'error',
            'icon': 'fa-exclamation-triangle',
            'icon_color': 'red',
            'title': f'{overdue} Overdue Assignment(s)',
            'message': 'Some assignments are past their due date.',
            'cta_text': 'View Overdue',
            'cta_url': url_for('manage_assignments'),
            'priority': 'high',
            'dismissible': False
        })
    
    # 5. New quizzes
    new_quizzes = QuizGroup.query.filter(
        QuizGroup.course_id.in_(course_ids),
        QuizGroup.created_at >= (now - timedelta(days=7))
    ).count()
    
    if new_quizzes > 0:
        notices.append({
            'type': 'success',
            'icon': 'fa-puzzle-piece',
            'icon_color': 'green',
            'title': f'{new_quizzes} New Quiz(zes) Available',
            'message': 'New quizzes have been added recently.',
            'cta_text': 'View Quizzes',
            'cta_url': url_for('manage_quizzes'),
            'priority': 'low',
            'dismissible': True
        })
    
    # Sort by priority
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    notices.sort(key=lambda x: priority_order.get(x['priority'], 3))
    
    return notices

def get_admin_enhanced_activity(admin_user, limit=15):
    """Get enhanced recent activity feed with icons and colors"""
    activities = []
    
    # Get course IDs
    if admin_user.is_super_admin():
        course_ids = [c.id for c in Course.query.all()]
    else:
        course_ids = [c.id for c in admin_user.managed_courses]
    
    # 1. New notes (last 30 days)
    notes = Note.query.filter(
        Note.course_id.in_(course_ids),
        Note.created_at >= (datetime.utcnow() - timedelta(days=30))
    ).order_by(Note.created_at.desc()).limit(10).all()
    
    for note in notes:
        activities.append({
            'type': 'note',
            'icon': 'fa-file-alt',
            'color': 'blue',
            'title': f'📝 New Note: "{note.title}"',
            'description': f'Posted in {note.course.name}',
            'time': note.created_at,
            'user': note.author.username if note.author else 'System',
            'url': url_for('edit_note', note_id=note.id) if note.id else None,
            'badge': 'New' if note.is_new() else None,
            'badge_color': 'green'
        })
    
    # 2. New quiz results (last 30 days)
    quiz_answers = QuizAnswer.query.filter(
        QuizAnswer.answered_at >= (datetime.utcnow() - timedelta(days=30))
    ).order_by(QuizAnswer.answered_at.desc()).limit(10).all()
    
    for answer in quiz_answers:
        if answer.quiz_group and answer.quiz_group.course_id in course_ids:
            student = User.query.get(answer.student_id)
            activities.append({
                'type': 'quiz',
                'icon': 'fa-puzzle-piece',
                'color': 'gold',
                'title': f'🎯 Quiz Completed: "{answer.quiz_group.title}"',
                'description': f'{student.username if student else "Student"} scored {"✓" if answer.is_correct else "✗"}',
                'time': answer.answered_at,
                'user': student.username if student else 'Unknown',
                'url': url_for('edit_quiz_group', quiz_id=answer.quiz_group.id) if answer.quiz_group.id else None,
                'badge': 'New' if (datetime.utcnow() - answer.answered_at).days <= 1 else None,
                'badge_color': 'gold'
            })
    
    # 3. New assignment submissions (last 30 days)
    submissions = AssignmentSubmission.query.filter(
        AssignmentSubmission.submitted_at >= (datetime.utcnow() - timedelta(days=30))
    ).order_by(AssignmentSubmission.submitted_at.desc()).limit(10).all()
    
    for sub in submissions:
        if sub.assignment and sub.assignment.course_id in course_ids:
            student = User.query.get(sub.student_id)
            activities.append({
                'type': 'submission',
                'icon': 'fa-tasks',
                'color': 'green',
                'title': f'📋 Assignment Submitted: "{sub.assignment.title}"',
                'description': f'{student.username if student else "Student"} submitted work',
                'time': sub.submitted_at,
                'user': student.username if student else 'Unknown',
                'url': url_for('view_submissions', assignment_id=sub.assignment.id) if sub.assignment.id else None,
                'badge': 'Needs Grading' if not sub.is_graded else None,
                'badge_color': 'orange'
            })
    
    # 4. New students (last 30 days)
    new_students = User.query.filter(
        User.role == 'student',
        User.created_at >= (datetime.utcnow() - timedelta(days=30))
    ).order_by(User.created_at.desc()).limit(5).all()
    
    for student in new_students:
        activities.append({
            'type': 'student',
            'icon': 'fa-user-plus',
            'color': 'purple',
            'title': f'👤 New Student Registered',
            'description': f'{student.username} ({student.email})',
            'time': student.created_at,
            'user': student.username,
            'url': url_for('edit_student', student_id=student.id) if student.id else None,
            'badge': 'Pending' if not student.is_approved else 'Approved',
            'badge_color': 'orange' if not student.is_approved else 'green'
        })
    
    # 5. New announcements (last 30 days)
    anns = Announcement.query.filter(
        Announcement.created_at >= (datetime.utcnow() - timedelta(days=30))
    ).order_by(Announcement.created_at.desc()).limit(5).all()
    
    for ann in anns:
        if admin_user.is_super_admin() or (ann.course_id and ann.course_id in course_ids) or ann.course_id is None:
            activities.append({
                'type': 'announcement',
                'icon': 'fa-bullhorn',
                'color': 'gold',
                'title': f'📢 New Announcement: "{ann.title}"',
                'description': f'By {ann.author.username if ann.author else "System"}',
                'time': ann.created_at,
                'user': ann.author.username if ann.author else 'System',
                'url': url_for('edit_announcement', announcement_id=ann.id) if ann.id else None,
                'badge': 'Pinned' if ann.is_pinned else None,
                'badge_color': 'gold'
            })
    
    # Sort by time (newest first) and remove duplicates
    activities.sort(key=lambda x: x['time'], reverse=True)
    
    # Remove duplicates based on title and time (keep unique)
    seen = set()
    unique_activities = []
    for act in activities:
        key = (act['title'], act['time'].strftime('%Y-%m-%d %H:%M'))
        if key not in seen:
            seen.add(key)
            unique_activities.append(act)
    
    return unique_activities[:limit]

def get_student_progress_visualization(admin_user):
    """Get student progress data for visualization"""
    # Get course IDs
    if admin_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = admin_user.managed_courses
    
    visualization_data = []
    for course in courses:
        # Get approved enrollments
        enrollments = CourseEnrollment.query.filter_by(
            course_id=course.id,
            status='approved'
        ).all()
        
        if enrollments:
            # Calculate progress for each student
            progress_values = []
            students = []
            for enrollment in enrollments:
                student = User.query.get(enrollment.student_id)
                if student:
                    progress = course.get_progress_for_student(student.id)
                    progress_values.append(progress)
                    students.append({
                        'name': student.username,
                        'progress': progress
                    })
            
            # Calculate statistics
            if progress_values:
                avg_progress = sum(progress_values) / len(progress_values)
                max_progress = max(progress_values)
                min_progress = min(progress_values)
                completed_count = sum(1 for p in progress_values if p >= 100)
            else:
                avg_progress = max_progress = min_progress = completed_count = 0
            
            visualization_data.append({
                'course_id': course.id,
                'course_name': course.name,
                'course_code': course.code,
                'total_students': len(students),
                'avg_progress': round(avg_progress, 1),
                'max_progress': max_progress,
                'min_progress': min_progress,
                'completed_count': completed_count,
                'students': students,
                'progress_distribution': {
                    '0-25': sum(1 for p in progress_values if 0 <= p < 25),
                    '25-50': sum(1 for p in progress_values if 25 <= p < 50),
                    '50-75': sum(1 for p in progress_values if 50 <= p < 75),
                    '75-100': sum(1 for p in progress_values if 75 <= p < 100),
                    '100': sum(1 for p in progress_values if p >= 100)
                }
            })
        else:
            # No students enrolled
            visualization_data.append({
                'course_id': course.id,
                'course_name': course.name,
                'course_code': course.code,
                'total_students': 0,
                'avg_progress': 0,
                'max_progress': 0,
                'min_progress': 0,
                'completed_count': 0,
                'students': [],
                'progress_distribution': {
                    '0-25': 0,
                    '25-50': 0,
                    '50-75': 0,
                    '75-100': 0,
                    '100': 0
                }
            })
    
    return visualization_data

# ============================================================================
# AUTO-MIGRATE ON STARTUP
# ============================================================================

def ensure_columns():
    """Ensure all required columns exist - runs on startup"""
    from sqlalchemy import text, inspect
    from sqlalchemy.exc import ProgrammingError
    
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            
            # ==========================================
            # 1. USER TABLE COLUMNS
            # ==========================================
            if 'user' in inspector.get_table_names():
                columns = [col['name'] for col in inspector.get_columns('user')]
                print(f"📋 Existing user columns: {', '.join(columns)}")
                
                added = []
                
                if 'is_suspended' not in columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN DEFAULT FALSE'))
                    added.append('is_suspended')
                    print("✅ Added is_suspended to user")
                
                if 'suspension_reason' not in columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS suspension_reason TEXT'))
                    added.append('suspension_reason')
                    print("✅ Added suspension_reason to user")
                
                if 'suspended_at' not in columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMP'))
                    added.append('suspended_at')
                    print("✅ Added suspended_at to user")
                
                if 'phone' not in columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
                    added.append('phone')
                    print("✅ Added phone to user")
                
                if 'dob' not in columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS dob TIMESTAMP'))
                    added.append('dob')
                    print("✅ Added dob to user")
                
                if 'profile_picture' not in columns:
                    db.session.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(200)'))
                    added.append('profile_picture')
                    print("✅ Added profile_picture to user")
                
                if added:
                    db.session.commit()
                    print(f"✅ Added to user: {', '.join(added)}")
            
            # ==========================================
            # 2. ANNOUNCEMENT TABLE COLUMNS
            # ==========================================
            if 'announcement' in inspector.get_table_names():
                ann_columns = [col['name'] for col in inspector.get_columns('announcement')]
                print(f"📋 Existing announcement columns: {', '.join(ann_columns)}")
                
                ann_added = []
                
                if 'course_id' not in ann_columns:
                    db.session.execute(text('ALTER TABLE "announcement" ADD COLUMN IF NOT EXISTS course_id INTEGER REFERENCES course(id)'))
                    ann_added.append('course_id')
                    print("✅ Added course_id to announcement")
                
                if ann_added:
                    db.session.commit()
                    print(f"✅ Added to announcement: {', '.join(ann_added)}")
            
            if not added and not ann_added:
                print("✅ All columns already exist!")
                
        except ProgrammingError as e:
            db.session.rollback()
            print(f"⚠️ Programming error during migration: {e}")
            # Try retry with direct connection
            try:
                print("🔄 Retrying migration with direct SQL...")
                with db.engine.connect() as conn:
                    # User table columns
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN DEFAULT FALSE'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS suspension_reason TEXT'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMP'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS phone VARCHAR(20)'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS dob TIMESTAMP'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(200)'))
                    # Announcement table columns
                    conn.execute(text('ALTER TABLE "announcement" ADD COLUMN IF NOT EXISTS course_id INTEGER REFERENCES course(id)'))
                    conn.commit()
                    print("✅ Migration retry succeeded!")
            except Exception as retry_error:
                print(f"⚠️ Retry also failed: {retry_error}")
                
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Auto-migration warning: {e}")

# ============================================================================
# CREATE ADMIN USER
# ============================================================================

def create_initial_admin():
    try:
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@awwaludevs.com',
                role='super_admin',
                is_approved=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin created: admin / admin123")
        else:
            print("✅ Admin user already exists")
            # Force reset password
            admin.set_password('admin123')
            admin.is_approved = True
            admin.role = 'super_admin'
            db.session.commit()
            print("✅ Password reset to: admin123")
    except Exception as e:
        print(f"⚠️ Error: {e}")

# ============================================================================
# USER LOADER
# ============================================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============================================================================
# CONTEXT PROCESSOR - COMPLETE WITH DYNAMIC SETTINGS
# ============================================================================

@app.context_processor
def inject_user():
    """Inject variables into all templates"""
    
    # Get site settings
    site_name = get_setting('site_name', 'A-Portal LMS')
    site_description = get_setting('site_description', 'Learning Management System')
    site_language = get_setting('default_language', 'en')
    site_timezone = get_setting('timezone', 'UTC')
    
    # Get counts for stats
    total_students = User.query.filter_by(role='student').count()
    total_courses = Course.query.count()
    total_notes = Note.query.count()
    total_quizzes = QuizGroup.query.count()
    total_assignments = Assignment.query.count()
    
    return {
        'current_user': current_user,
        'now': datetime.utcnow(),
        'get_courses': lambda: current_user.get_courses() if current_user.is_authenticated else [],
        'is_approved': lambda: current_user.is_approved if current_user.is_authenticated else False,
        
        # ============================================
        # DYNAMIC SYSTEM SETTINGS
        # ============================================
        'site_name': site_name,
        'site_description': site_description,
        'site_language': site_language,
        'site_timezone': site_timezone,
        'get_setting': get_setting,
        
        # ============================================
        # STATISTICS FOR HOME PAGE
        # ============================================
        'total_students': total_students,
        'total_courses': total_courses,
        'total_notes': total_notes,
        'total_quizzes': total_quizzes,
        'total_assignments': total_assignments,
        
        # ============================================
        # ADDITIONAL HELPER FUNCTIONS
        # ============================================
        'get_bool_setting': get_bool_setting,
        'get_int_setting': get_int_setting,
        'get_str_setting': get_str_setting,
    }

# ============================================================================
# CUSTOM JINJA2 FILTERS
# ============================================================================

@app.template_filter('zfill')
def zfill_filter(value, width):
    """Pad a string with zeros to the specified width"""
    return str(value).zfill(width)

# ============================================================================
# ROUTES - AUTHENTICATION
# ============================================================================

@app.route('/')
def index():
    """Home page with dynamic stats"""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json
        
        if user and user.check_password(password):
            # Check if account is suspended
            if user.is_suspended:
                if is_ajax:
                    return jsonify({'error': f'Account suspended. Reason: {user.suspension_reason or "No reason provided."}'}), 403
                flash(f'Account suspended. Reason: {user.suspension_reason or "No reason provided."}', 'error')
                return render_template('login.html')
            
            if not user.is_approved and user.role == 'student':
                if is_ajax:
                    return jsonify({'error': 'Your account is pending approval.'}), 403
                flash('Your account is pending approval.', 'warning')
                return render_template('login.html')
            
            login_user(user)
            
            if is_ajax:
                if user.is_admin():
                    return jsonify({'redirect': url_for('admin_dashboard')})
                return jsonify({'redirect': url_for('student_dashboard')})
            
            if user.is_admin():
                return redirect(url_for('admin_dashboard'))
            
            if not user.is_approved:
                return redirect(url_for('student_pending_approval'))
            
            return redirect(url_for('student_dashboard'))
        else:
            if is_ajax:
                return jsonify({'error': 'Invalid username or password.'}), 401
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    courses = Course.query.all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        selected_courses = request.form.getlist('courses')
        
        if not username or not email or not password:
            flash('Please fill in all required fields.', 'error')
            return render_template('signup.html', courses=courses)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('signup.html', courses=courses)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('signup.html', courses=courses)
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('signup.html', courses=courses)
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('signup.html', courses=courses)
        
        student = User(
            username=username,
            email=email,
            role='student',
            is_approved=False
        )
        student.set_password(password)
        db.session.add(student)
        db.session.flush()
        
        # Create CourseEnrollment records for each selected course
        for course_id in selected_courses:
            course = Course.query.get(course_id)
            if course:
                enrollment = CourseEnrollment(
                    student_id=student.id,
                    course_id=course_id,
                    status='pending'
                )
                db.session.add(enrollment)
        
        db.session.commit()
        
        flash('Account created! Please wait for admin approval.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html', courses=courses)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

# ============================================================================
# ROUTES - DASHBOARDS
# ============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Check if student is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    return redirect(url_for('student_dashboard'))

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Check if account is suspended
    if current_user.is_suspended:
        flash(f'Your account has been suspended. Reason: {current_user.suspension_reason or "No reason provided."}', 'error')
        logout_user()
        return redirect(url_for('login'))
    
    # Check if student account is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Get ONLY approved courses (where enrollment status is 'approved')
    approved_courses = current_user.get_enrolled_courses()
    
    # Get pending courses (where enrollment status is 'pending')
    pending_courses = current_user.get_pending_courses()
    
    # If student has no approved courses but has pending ones
    if not approved_courses and pending_courses:
        flash('Your account is approved, but you are waiting for course access. Please contact an admin.', 'info')
    
    # If student has no courses at all (approved or pending)
    if not approved_courses and not pending_courses:
        flash('You are not enrolled in any courses. Browse available courses to request access.', 'info')
    
    # Calculate progress for approved courses only
    progress_data = []
    for course in approved_courses:
        progress_data.append({
            'course': course,
            'progress': course.get_progress_for_student(current_user.id)
        })
    
    # Get quiz results from approved courses only
    quiz_results = []
    if approved_courses:
        approved_course_ids = [c.id for c in approved_courses]
        quiz_answers = QuizAnswer.query.filter(
            QuizAnswer.student_id == current_user.id,
            QuizAnswer.quiz_group_id.in_(
                db.session.query(QuizGroup.id).filter(QuizGroup.course_id.in_(approved_course_ids))
            )
        ).all()
        
        quiz_groups_taken = set()
        for ans in quiz_answers:
            if ans.quiz_group_id not in quiz_groups_taken:
                quiz_groups_taken.add(ans.quiz_group_id)
                score = ans.quiz_group.get_student_score(current_user.id)
                if score:
                    quiz_results.append({
                        'title': ans.quiz_group.title,
                        'score': score
                    })
    
    # Get announcements
    announcements = Announcement.query.order_by(
        Announcement.is_pinned.desc(), 
        Announcement.created_at.desc()
    ).limit(5).all()
    
    # Get pending course count for badge/notification
    pending_count = len(pending_courses)
    
    # Calculate average progress
    avg_progress = 0
    if progress_data:
        total_progress = sum(data['progress'] for data in progress_data)
        avg_progress = total_progress // len(progress_data)
    
    return render_template('student_dashboard.html', 
                         approved_courses=approved_courses,
                         pending_courses=pending_courses,
                         pending_count=pending_count,
                         progress_data=progress_data,
                         quiz_results=quiz_results[:5],
                         announcements=announcements,
                         has_approved_courses=bool(approved_courses),
                         has_pending_courses=bool(pending_courses),
                         avg_progress=avg_progress)

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """Enhanced admin dashboard with all features"""
    # Existing data
    total_students = User.query.filter_by(role='student').count()
    
    # Count students with pending course enrollments
    pending_students = db.session.query(CourseEnrollment.student_id).filter(
        CourseEnrollment.status == 'pending'
    ).distinct().all()
    pending_student_ids = [p[0] for p in pending_students]
    pending_approvals = len(pending_student_ids)
    
    # Get the actual pending students with their enrollments
    pending = User.query.filter(User.id.in_(pending_student_ids)).all() if pending_student_ids else []
    
    # For regular admins, count pending students in their courses
    pending_students_count = 0
    if not current_user.is_super_admin():
        admin_course_ids = [c.id for c in current_user.managed_courses]
        pending_in_admin_courses = CourseEnrollment.query.filter(
            CourseEnrollment.status == 'pending',
            CourseEnrollment.course_id.in_(admin_course_ids)
        ).distinct().count()
        pending_students_count = pending_in_admin_courses
    
    # Get pending course enrollments (students waiting for course approval)
    pending_enrollments = CourseEnrollment.query.filter_by(status='pending').all()
    
    # Group pending enrollments by student for display
    pending_course_requests = {}
    for enrollment in pending_enrollments:
        if enrollment.student_id not in pending_course_requests:
            pending_course_requests[enrollment.student_id] = {
                'student': enrollment.student,
                'courses': []
            }
        pending_course_requests[enrollment.student_id]['courses'].append(enrollment.course)
    
    # Convert to list for template
    pending_course_requests_list = list(pending_course_requests.values())
    
    # Get announcements count for badge
    announcements_count = Announcement.query.count()
    
    if current_user.is_super_admin():
        courses = Course.query.all()
        total_courses = Course.query.count()
        total_notes = Note.query.count()
        total_quizzes = QuizGroup.query.count()
        total_assignments = Assignment.query.count()
        admin_count = User.query.filter_by(role='admin').count()
        tag_count = Tag.query.count()
    else:
        courses = current_user.managed_courses
        total_courses = len(courses)
        total_notes = Note.query.filter(Note.course_id.in_([c.id for c in courses])).count()
        total_quizzes = QuizGroup.query.filter(QuizGroup.course_id.in_([c.id for c in courses])).count()
        total_assignments = Assignment.query.filter(Assignment.course_id.in_([c.id for c in courses])).count()
        admin_count = 0
        tag_count = Tag.query.count()
    
    # --- NEW DATA FOR ENHANCED FEATURES ---
    upcoming_deadlines = get_admin_upcoming_deadlines(current_user)
    quiz_results = get_admin_quiz_results(current_user)
    announcements_with_pins = get_admin_announcements_with_pins(current_user)
    notices = get_admin_notices_with_ctas(current_user)
    enhanced_activity = get_admin_enhanced_activity(current_user)
    progress_visualization = get_student_progress_visualization(current_user)
    
    # Existing recent data for backward compatibility
    recent_notes = Note.query.order_by(Note.created_at.desc()).limit(5).all()
    recent_quizzes = QuizGroup.query.order_by(QuizGroup.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         # Existing data
                         total_students=total_students,
                         pending_approvals=pending_approvals,
                         pending=pending,
                         pending_students_count=pending_students_count,
                         pending_course_requests=pending_course_requests_list,
                         pending_course_requests_count=len(pending_course_requests_list),
                         total_courses=total_courses,
                         total_notes=total_notes,
                         total_quizzes=total_quizzes,
                         total_assignments=total_assignments,
                         courses=courses,
                         recent_notes=recent_notes,
                         recent_quizzes=recent_quizzes,
                         admin_count=admin_count,
                         tag_count=tag_count,
                         announcements_count=announcements_count,
                         
                         # NEW DATA
                         upcoming_deadlines=upcoming_deadlines,
                         quiz_results=quiz_results,
                         announcements_with_pins=announcements_with_pins,
                         notices=notices,
                         enhanced_activity=enhanced_activity,
                         progress_visualization=progress_visualization)

# ============================================================================
# ROUTES - STUDENT PENDING APPROVAL
# ============================================================================

@app.route('/student/pending-approval')
@login_required
def student_pending_approval():
    """Show pending approval page for students waiting for admin approval"""
    # If user is admin, redirect to admin dashboard
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Check if account is suspended
    if current_user.is_suspended:
        flash(f'Your account has been suspended. Reason: {current_user.suspension_reason or "No reason provided."}', 'error')
        logout_user()
        return redirect(url_for('login'))
    
    # If student is already approved, redirect to student dashboard
    if current_user.is_approved:
        return redirect(url_for('student_dashboard'))
    
    # Get pending courses count and details
    pending_courses = current_user.get_pending_courses()
    
    # Get rejected courses if any
    rejected_courses = current_user.get_rejected_courses()
    
    # Get total pending count
    pending_count = len(pending_courses)
    
    # Check if student has any approved courses (should not happen if is_approved is False)
    approved_courses = current_user.get_enrolled_courses()
    
    return render_template('student/pending_approval.html', 
                         pending_courses=pending_courses,
                         pending_count=pending_count,
                         rejected_courses=rejected_courses,
                         approved_courses=approved_courses,
                         username=current_user.username)

# ============================================================================
# ROUTES - STUDENT PROFILE
# ============================================================================

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

@app.route('/student/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_student_profile():
    """Edit student profile - Only for students"""
    # Check if user is a student (not admin)
    if current_user.is_admin():
        flash('Admins cannot edit student profiles here. Please use the admin panel.', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    # Check if account is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. You cannot edit your profile until approved.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Check if account is suspended
    if current_user.is_suspended:
        flash('Your account is suspended. Please contact an admin.', 'error')
        logout_user()
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        dob = request.form.get('dob')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate
        if not username or not email:
            flash('Username and email are required.', 'error')
            return render_template('student/edit_profile.html')
        
        # Check for duplicate username
        existing_user = User.query.filter(User.username == username, User.id != current_user.id).first()
        if existing_user:
            flash('Username already taken.', 'error')
            return render_template('student/edit_profile.html')
        
        # Check for duplicate email
        existing_email = User.query.filter(User.email == email, User.id != current_user.id).first()
        if existing_email:
            flash('Email already registered.', 'error')
            return render_template('student/edit_profile.html')
        
        # Update basic info
        current_user.username = username
        current_user.email = email
        current_user.phone = phone if phone else None
        if dob:
            try:
                current_user.dob = datetime.strptime(dob, '%Y-%m-%d')
            except ValueError:
                flash('Invalid date format.', 'error')
                return render_template('student/edit_profile.html')
        
        # Handle profile picture upload
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename:
                if allowed_file(file.filename):
                    # Delete old profile picture if exists
                    if current_user.profile_picture:
                        old_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.profile_picture)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    # Save new profile picture
                    filename = secure_filename(file.filename)
                    unique_filename = f"profile_{current_user.id}_{uuid.uuid4().hex[:8]}{os.path.splitext(filename)[1]}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    current_user.profile_picture = unique_filename
                    flash('Profile picture updated successfully!', 'success')
                else:
                    flash('Invalid file format. Please upload JPG, PNG, or GIF.', 'error')
        
        # Handle password change
        if new_password:
            if not current_password:
                flash('Please enter your current password to change your password.', 'error')
                return render_template('student/edit_profile.html')
            
            if not current_user.check_password(current_password):
                flash('Current password is incorrect.', 'error')
                return render_template('student/edit_profile.html')
            
            if len(new_password) < 6:
                flash('New password must be at least 6 characters.', 'error')
                return render_template('student/edit_profile.html')
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return render_template('student/edit_profile.html')
            
            current_user.set_password(new_password)
            flash('Password changed successfully!', 'success')
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('student/edit_profile.html')

@app.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'error')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('change_password.html')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('change_password.html')
        
        current_user.set_password(new_password)
        db.session.commit()
        flash('Password changed successfully!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('change_password.html')

@app.route('/profile/toggle-dark-mode', methods=['POST'])
@login_required
def toggle_dark_mode():
    current_user.dark_mode = not current_user.dark_mode
    db.session.commit()
    return jsonify({'dark_mode': current_user.dark_mode})

# ============================================================================
# ROUTES - STUDENT MANAGEMENT (Admin) - Full CRUD
# ============================================================================

@app.route('/admin/students/<int:student_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_student(student_id):
    """Edit student profile"""
    student = User.query.get_or_404(student_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin():
        student_course_ids = [e.course_id for e in CourseEnrollment.query.filter_by(student_id=student.id).all()]
        admin_course_ids = [c.id for c in current_user.managed_courses]
        if not any(cid in admin_course_ids for cid in student_course_ids):
            flash('You do not have permission to edit this student.', 'error')
            return redirect(url_for('manage_students'))
    
    courses = Course.query.all()
    
    # Get current enrollments
    enrollments = CourseEnrollment.query.filter_by(student_id=student.id).all()
    enrolled_course_ids = [e.course_id for e in enrollments]
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        role = request.form.get('role')
        is_approved = request.form.get('is_approved') == 'on'
        selected_courses = request.form.getlist('courses')
        
        # Validate
        if not username or not email:
            flash('Username and email are required.', 'error')
            return render_template('admin/edit_student.html', 
                                 student=student, 
                                 courses=courses,
                                 enrolled_course_ids=enrolled_course_ids)
        
        # Check for duplicate username
        existing_user = User.query.filter(User.username == username, User.id != student.id).first()
        if existing_user:
            flash('Username already taken.', 'error')
            return render_template('admin/edit_student.html', 
                                 student=student, 
                                 courses=courses,
                                 enrolled_course_ids=enrolled_course_ids)
        
        # Check for duplicate email
        existing_email = User.query.filter(User.email == email, User.id != student.id).first()
        if existing_email:
            flash('Email already registered.', 'error')
            return render_template('admin/edit_student.html', 
                                 student=student, 
                                 courses=courses,
                                 enrolled_course_ids=enrolled_course_ids)
        
        # Update student
        student.username = username
        student.email = email
        
        # Only super admin can change role
        if current_user.is_super_admin():
            student.role = role
        
        student.is_approved = is_approved
        
        # Update password if provided
        new_password = request.form.get('new_password')
        if new_password:
            if len(new_password) < 6:
                flash('Password must be at least 6 characters.', 'error')
                return render_template('admin/edit_student.html', 
                                     student=student, 
                                     courses=courses,
                                     enrolled_course_ids=enrolled_course_ids)
            student.set_password(new_password)
        
        # Update course enrollments
        if current_user.is_super_admin():
            # Get current enrollments
            current_enrollments = CourseEnrollment.query.filter_by(student_id=student.id).all()
            current_course_ids = [e.course_id for e in current_enrollments]
            
            # Add new enrollments
            selected_course_ids = [int(c) for c in selected_courses]
            for course_id in selected_course_ids:
                if course_id not in current_course_ids:
                    enrollment = CourseEnrollment(
                        student_id=student.id,
                        course_id=course_id,
                        status='pending'
                    )
                    db.session.add(enrollment)
            
            # Remove unselected enrollments
            for enrollment in current_enrollments:
                if enrollment.course_id not in selected_course_ids:
                    db.session.delete(enrollment)
        else:
            # Regular admin can only manage their courses
            admin_course_ids = [c.id for c in current_user.managed_courses]
            for course_id in selected_courses:
                course_id_int = int(course_id)
                if course_id_int in admin_course_ids:
                    existing = CourseEnrollment.query.filter_by(
                        student_id=student.id,
                        course_id=course_id_int
                    ).first()
                    if not existing:
                        enrollment = CourseEnrollment(
                            student_id=student.id,
                            course_id=course_id_int,
                            status='pending'
                        )
                        db.session.add(enrollment)
        
        db.session.commit()
        flash(f'Student {student.username} updated successfully!', 'success')
        return redirect(url_for('manage_students'))
    
    return render_template('admin/edit_student.html', 
                         student=student, 
                         courses=courses,
                         enrolled_course_ids=enrolled_course_ids)

@app.route('/admin/students/<int:student_id>/suspend', methods=['GET', 'POST'])
@login_required
@admin_required
def suspend_student(student_id):
    """Suspend a student account"""
    student = User.query.get_or_404(student_id)
    
    # Prevent suspending admins
    if student.is_admin():
        flash('Cannot suspend admin accounts.', 'error')
        return redirect(url_for('manage_students'))
    
    # Check if admin has permission
    if not current_user.is_super_admin():
        student_course_ids = [e.course_id for e in CourseEnrollment.query.filter_by(student_id=student.id).all()]
        admin_course_ids = [c.id for c in current_user.managed_courses]
        if not any(cid in admin_course_ids for cid in student_course_ids):
            flash('You do not have permission to suspend this student.', 'error')
            return redirect(url_for('manage_students'))
    
    if request.method == 'POST':
        reason = request.form.get('reason', 'No reason provided.')
        
        student.is_suspended = True
        student.suspension_reason = reason
        student.suspended_at = datetime.utcnow()
        student.is_approved = False  # Remove approval when suspended
        
        db.session.commit()
        
        # Notify student
        notify_student_suspended(student.id, reason)
        
        flash(f'{student.username} has been suspended. Reason: {reason}', 'warning')
        return redirect(url_for('manage_students'))
    
    return render_template('admin/suspend_student.html', student=student)

@app.route('/admin/students/<int:student_id>/unsuspend', methods=['POST'])
@login_required
@admin_required
def unsuspend_student(student_id):
    """Unsuspend a student account"""
    student = User.query.get_or_404(student_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin():
        student_course_ids = [e.course_id for e in CourseEnrollment.query.filter_by(student_id=student.id).all()]
        admin_course_ids = [c.id for c in current_user.managed_courses]
        if not any(cid in admin_course_ids for cid in student_course_ids):
            flash('You do not have permission to unsuspend this student.', 'error')
            return redirect(url_for('manage_students'))
    
    student.is_suspended = False
    student.suspension_reason = None
    student.suspended_at = None
    # Student needs to be re-approved after unsuspension
    student.is_approved = False
    
    db.session.commit()
    
    # Notify student
    notify_student_unsuspended(student.id)
    
    flash(f'{student.username} has been unsuspended. They need to be re-approved to access courses.', 'success')
    return redirect(url_for('manage_students'))

@app.route('/admin/students/<int:student_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_student(student_id):
    """Permanently delete a student account"""
    from sqlalchemy import text
    
    student = User.query.get_or_404(student_id)
    
    # Prevent deleting admins
    if student.is_admin():
        flash('Cannot delete admin accounts.', 'error')
        return redirect(url_for('manage_students'))
    
    # Check if admin has permission
    if not current_user.is_super_admin():
        student_course_ids = [e.course_id for e in CourseEnrollment.query.filter_by(student_id=student.id).all()]
        admin_course_ids = [c.id for c in current_user.managed_courses]
        if not any(cid in admin_course_ids for cid in student_course_ids):
            flash('You do not have permission to delete this student.', 'error')
            return redirect(url_for('manage_students'))
    
    try:
        # Delete notifications FIRST (they have foreign key to user)
        Notification.query.filter_by(user_id=student.id).delete()
        
        # Delete related records using ORM
        CourseEnrollment.query.filter_by(student_id=student.id).delete()
        RejectionMessage.query.filter_by(student_id=student.id).delete()
        QuizAnswer.query.filter_by(student_id=student.id).delete()
        StudentProgress.query.filter_by(student_id=student.id).delete()
        AssignmentSubmission.query.filter_by(student_id=student.id).delete()
        
        # For many-to-many tables, use text() - these are association tables
        db.session.execute(
            text('DELETE FROM student_course WHERE student_id = :student_id'),
            {'student_id': student.id}
        )
        db.session.execute(
            text('DELETE FROM admin_course WHERE admin_id = :student_id'),
            {'student_id': student.id}
        )
        
        # Delete the user
        db.session.delete(student)
        db.session.commit()
        
        flash(f'Student {student.username} has been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'error')
        app.logger.error(f'Delete student error: {e}')
    
    return redirect(url_for('manage_students'))

@app.route('/admin/students/<int:student_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_student_password(student_id):
    """Reset student password to a random value"""
    student = User.query.get_or_404(student_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin():
        student_course_ids = [e.course_id for e in CourseEnrollment.query.filter_by(student_id=student.id).all()]
        admin_course_ids = [c.id for c in current_user.managed_courses]
        if not any(cid in admin_course_ids for cid in student_course_ids):
            flash('You do not have permission to reset this student\'s password.', 'error')
            return redirect(url_for('manage_students'))
    
    import random
    import string
    
    # Generate random password
    new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    student.set_password(new_password)
    db.session.commit()
    
    flash(f'Password for {student.username} has been reset to: {new_password}', 'info')
    return redirect(url_for('manage_students'))

@app.route('/admin/students/<int:student_id>/unapprove', methods=['POST'])
@login_required
@admin_required
def unapprove_student(student_id):
    """Unapprove a student - remove all course enrollments"""
    student = User.query.get_or_404(student_id)
    
    # Check if admin has permission for this student's courses
    if not current_user.is_super_admin():
        student_course_ids = [e.course_id for e in CourseEnrollment.query.filter_by(student_id=student.id, status='approved').all()]
        admin_course_ids = [c.id for c in current_user.managed_courses]
        if not any(cid in admin_course_ids for cid in student_course_ids):
            flash('You do not have permission to unapprove this student.', 'error')
            return redirect(url_for('manage_students'))
    
    # Remove all approved enrollments - change back to pending
    approved_enrollments = CourseEnrollment.query.filter_by(
        student_id=student.id,
        status='approved'
    ).all()
    
    for enrollment in approved_enrollments:
        enrollment.status = 'pending'  # Change back to pending
        enrollment.approved_at = None
    
    # Also mark student as not approved
    student.is_approved = False
    
    db.session.commit()
    
    flash(f'{student.username} has been unapproved. They will need to be re-approved to access courses.', 'warning')
    return redirect(url_for('manage_students'))

@app.route('/admin/students/<int:student_id>/unapprove-course/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def unapprove_course(student_id, course_id):
    """Unapprove a student from a specific course"""
    student = User.query.get_or_404(student_id)
    course = Course.query.get_or_404(course_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin() and course not in current_user.managed_courses:
        flash('You do not have permission to unapprove this course.', 'error')
        return redirect(url_for('manage_students'))
    
    # Find the enrollment
    enrollment = CourseEnrollment.query.filter_by(
        student_id=student.id,
        course_id=course.id,
        status='approved'
    ).first()
    
    if enrollment:
        enrollment.status = 'pending'
        enrollment.approved_at = None
        db.session.commit()
        flash(f'{student.username} unapproved from {course.name}.', 'warning')
    else:
        flash('Student is not approved for this course.', 'error')
    
    return redirect(url_for('manage_students'))

# ============================================================================
# UPDATED: STUDENT APPROVAL - Regular admins can only approve if they manage the student's courses
# ============================================================================

@app.route('/admin/students/<int:student_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_student(student_id):
    """Approve a student account. Super Admin: approve anyone. Regular Admin: only if they manage at least one of the student's courses."""
    student = User.query.get_or_404(student_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin():
        # Get ALL enrollments for this student
        student_enrollments = CourseEnrollment.query.filter_by(student_id=student.id).all()
        admin_course_ids = [c.id for c in current_user.managed_courses]
        
        # Check if this admin manages at least ONE course this student is enrolled in
        has_permission = any(e.course_id in admin_course_ids for e in student_enrollments)
        
        if not has_permission:
            flash('You do not have permission to approve this student. You do not manage any of their courses.', 'error')
            return redirect(url_for('manage_students'))
    
    # ONLY approve the student account - NOT the courses
    student.is_approved = True
    
    # Keep all enrollments as 'pending' - admin must approve each course separately
    # Do NOT change enrollment statuses here
    
    db.session.commit()
    
    # Notify student
    notify_student_approved(student.id)
    
    # Get pending courses count for the message
    pending_courses = CourseEnrollment.query.filter_by(
        student_id=student.id,
        status='pending'
    ).count()
    
    flash(f'{student.username} has been approved. They can now log in. ({pending_courses} course(s) pending approval)', 'success')
    return redirect(url_for('manage_students'))

# ============================================================================
# UPDATED: COURSE APPROVAL - Regular admins can only approve courses they manage
# ============================================================================

@app.route('/admin/students/<int:student_id>/approve-course/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def approve_course(student_id, course_id):
    """Approve a student for a specific course. Super Admin: approve any. Regular Admin: only if they manage the course."""
    student = User.query.get_or_404(student_id)
    course = Course.query.get_or_404(course_id)
    
    # Check if admin has permission - only super admin or admin who manages this course
    if not current_user.is_super_admin() and course not in current_user.managed_courses:
        flash('You do not have permission to approve this course.', 'error')
        return redirect(url_for('manage_students'))
    
    # Find the enrollment
    enrollment = CourseEnrollment.query.filter_by(
        student_id=student.id,
        course_id=course.id,
        status='pending'
    ).first()
    
    if enrollment:
        enrollment.status = 'approved'
        enrollment.approved_at = datetime.utcnow()
        db.session.commit()
        
        # Notify student
        notify_course_approved(student.id, course.name)
        
        flash(f'{student.username} approved for {course.name}.', 'success')
    else:
        flash('No pending enrollment found for this student and course.', 'error')
    
    return redirect(url_for('manage_students'))

# ============================================================================
# UPDATED: APPROVE ALL COURSES - Super Admin only
# ============================================================================

@app.route('/admin/students/<int:student_id>/approve-all-courses', methods=['POST'])
@login_required
@admin_required
def approve_all_courses(student_id):
    """Approve all pending course enrollments for a student. SUPER ADMIN ONLY."""
    # ONLY super admin can approve all courses
    if not current_user.is_super_admin():
        flash('Only Super Admin can approve all courses at once.', 'error')
        return redirect(url_for('manage_students'))
    
    student = User.query.get_or_404(student_id)
    
    # Get all pending enrollments
    pending_enrollments = CourseEnrollment.query.filter_by(
        student_id=student.id,
        status='pending'
    ).all()
    
    # Approve all pending enrollments
    for enrollment in pending_enrollments:
        enrollment.status = 'approved'
        enrollment.approved_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'All {len(pending_enrollments)} course(s) approved for {student.username}.', 'success')
    return redirect(url_for('manage_students'))

@app.route('/admin/students/<int:student_id>/reject', methods=['GET', 'POST'])
@login_required
@admin_required
def reject_student(student_id):
    student = User.query.get_or_404(student_id)
    
    # Get pending enrollments
    pending_enrollments = CourseEnrollment.query.filter_by(
        student_id=student.id,
        status='pending'
    ).all()
    
    if request.method == 'POST':
        course_id = request.form.get('course_id')
        message = request.form.get('message')
        
        if not course_id or not message:
            flash('Please select a course and provide a reason.', 'error')
            return render_template('admin/reject_user.html', student=student, enrollments=pending_enrollments)
        
        # Find the enrollment
        enrollment = CourseEnrollment.query.filter_by(
            student_id=student.id,
            course_id=course_id,
            status='pending'
        ).first()
        
        course_name = enrollment.course.name if enrollment else 'Unknown'
        
        if enrollment:
            enrollment.status = 'rejected'
            enrollment.rejected_at = datetime.utcnow()
            enrollment.rejection_reason = message
        
        # Save rejection message
        rejection = RejectionMessage(
            student_id=student.id,
            course_id=course_id,
            message=message
        )
        db.session.add(rejection)
        
        # Check if student has any pending enrollments left
        remaining_pending = CourseEnrollment.query.filter_by(
            student_id=student.id,
            status='pending'
        ).count()
        
        # Check if student has any approved enrollments
        approved_count = CourseEnrollment.query.filter_by(
            student_id=student.id,
            status='approved'
        ).count()
        
        # If no pending and no approved courses, set student as not approved
        if remaining_pending == 0 and approved_count == 0:
            student.is_approved = False
        
        db.session.commit()
        
        # Notify student
        notify_student_rejected(student.id, course_name, message)
        
        flash(f'Student {student.username} rejected from {course_name}.', 'warning')
        return redirect(url_for('manage_students'))
    
    return render_template('admin/reject_user.html', student=student, enrollments=pending_enrollments)

@app.route('/admin/students/<int:student_id>/reject-course/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def reject_course(student_id, course_id):
    """Reject a student from a specific course"""
    student = User.query.get_or_404(student_id)
    course = Course.query.get_or_404(course_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin() and course not in current_user.managed_courses:
        flash('You do not have permission to reject this course.', 'error')
        return redirect(url_for('manage_students'))
    
    message = request.form.get('message', 'No reason provided.')
    
    # Find the enrollment
    enrollment = CourseEnrollment.query.filter_by(
        student_id=student.id,
        course_id=course.id
    ).first()
    
    if enrollment:
        enrollment.status = 'rejected'
        enrollment.rejected_at = datetime.utcnow()
        enrollment.rejection_reason = message
        
        # Save rejection message
        rejection = RejectionMessage(
            student_id=student.id,
            course_id=course_id,
            message=message
        )
        db.session.add(rejection)
        db.session.commit()
        
        # Notify student
        notify_student_rejected(student.id, course.name, message)
        
        flash(f'{student.username} rejected from {course.name}.', 'warning')
    else:
        flash('No enrollment found for this student and course.', 'error')
    
    return redirect(url_for('manage_students'))

@app.route('/admin/students/<int:student_id>/unreject/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def unreject_student(student_id, course_id):
    student = User.query.get_or_404(student_id)
    course = Course.query.get_or_404(course_id)
    
    # Check if there's a rejection record
    rejection = RejectionMessage.query.filter_by(
        student_id=student.id,
        course_id=course_id
    ).first()
    
    if rejection:
        # Remove rejection message
        db.session.delete(rejection)
    
    # Check if there's an enrollment record
    enrollment = CourseEnrollment.query.filter_by(
        student_id=student.id,
        course_id=course_id
    ).first()
    
    if enrollment:
        enrollment.status = 'pending'
        enrollment.rejected_at = None
        enrollment.rejection_reason = None
    else:
        # Create new enrollment
        enrollment = CourseEnrollment(
            student_id=student.id,
            course_id=course_id,
            status='pending'
        )
        db.session.add(enrollment)
    
    db.session.commit()
    flash(f'{student.username} has been restored to {course.name} (pending approval).', 'success')
    
    return redirect(url_for('manage_students'))

@app.route('/admin/students/bulk-approve', methods=['POST'])
@login_required
@admin_required
def bulk_approve_students():
    """Bulk approve students - for super admin use only"""
    if not current_user.is_super_admin():
        flash('Only Super Admin can bulk approve students.', 'error')
        return redirect(url_for('manage_students'))
    
    student_ids = request.form.getlist('student_ids')
    
    if not student_ids:
        flash('No students selected.', 'warning')
        return redirect(url_for('manage_students'))
    
    approved_count = 0
    for sid in student_ids:
        student = User.query.get(sid)
        if student:
            # Approve all pending enrollments
            pending_enrollments = CourseEnrollment.query.filter_by(
                student_id=student.id,
                status='pending'
            ).all()
            for enrollment in pending_enrollments:
                enrollment.status = 'approved'
                enrollment.approved_at = datetime.utcnow()
            student.is_approved = True
            approved_count += 1
    
    db.session.commit()
    flash(f'{approved_count} students approved successfully.', 'success')
    return redirect(url_for('manage_students'))

# ============================================================================
# UPDATED: MANAGE STUDENTS - Filters students based on admin role
# ============================================================================

@app.route('/admin/students')
@login_required
@admin_required
def manage_students():
    if current_user.is_super_admin():
        students = User.query.filter_by(role='student').all()
        
        # Get students with pending enrollments
        pending_student_ids = db.session.query(CourseEnrollment.student_id).filter(
            CourseEnrollment.status == 'pending'
        ).distinct().all()
        pending_student_ids = [p[0] for p in pending_student_ids]
        pending = User.query.filter(User.id.in_(pending_student_ids)).all() if pending_student_ids else []
    else:
        # Regular admin: only see students enrolled in their courses
        course_ids = [c.id for c in current_user.managed_courses]
        students = User.query.filter(
            User.role == 'student',
            User.id.in_(
                db.session.query(CourseEnrollment.student_id).filter(
                    CourseEnrollment.course_id.in_(course_ids)
                )
            )
        ).all()
        
        # Get students with pending enrollments in admin's courses
        pending_student_ids = db.session.query(CourseEnrollment.student_id).filter(
            CourseEnrollment.status == 'pending',
            CourseEnrollment.course_id.in_(course_ids)
        ).distinct().all()
        pending_student_ids = [p[0] for p in pending_student_ids]
        pending = User.query.filter(User.id.in_(pending_student_ids)).all() if pending_student_ids else []
    
    # Get enrollment details for each student
    students_with_enrollments = []
    for student in students:
        enrollments = CourseEnrollment.query.filter_by(student_id=student.id).all()
        students_with_enrollments.append({
            'student': student,
            'enrollments': enrollments,
            'approved_count': sum(1 for e in enrollments if e.status == 'approved'),
            'pending_count': sum(1 for e in enrollments if e.status == 'pending'),
            'rejected_count': sum(1 for e in enrollments if e.status == 'rejected')
        })
    
    courses = Course.query.all()
    return render_template('admin/manage_students.html', 
                         students=students_with_enrollments, 
                         pending=pending, 
                         courses=courses)

# ============================================================================
# ROUTES - COURSE MANAGEMENT (Admin & Super Admin)
# ============================================================================

@app.route('/admin/courses')
@login_required
@admin_required
def admin_course_list():
    """List all courses with their assigned admins and student counts"""
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    course_data = []
    for course in courses:
        # Get assigned admins for this course
        assigned_admins = User.query.filter(
            User.role.in_(['admin', 'super_admin']),
            User.managed_courses.contains(course)
        ).all()
        
        # Get enrolled students with their enrollment status
        enrollments = CourseEnrollment.query.filter_by(course_id=course.id).all()
        students = []
        for enrollment in enrollments:
            students.append({
                'student': enrollment.student,
                'status': enrollment.status,
                'enrolled_at': enrollment.requested_at
            })
        
        # Count approved students
        approved_count = sum(1 for e in enrollments if e.status == 'approved')
        pending_count = sum(1 for e in enrollments if e.status == 'pending')
        
        course_data.append({
            'course': course,
            'admins': assigned_admins,
            'students': students,
            'total_students': len(students),
            'approved_students': approved_count,
            'pending_students': pending_count,
            'notes_count': len(course.notes),
            'quizzes_count': len(course.quiz_groups),
            'assignments_count': len(course.assignments)
        })
    
    return render_template('admin/course_list.html', 
                         courses=course_data,
                         is_super_admin=current_user.is_super_admin())

@app.route('/admin/courses/<int:course_id>')
@login_required
@admin_required
def admin_course_detail(course_id):
    """View detailed course information including students and admins"""
    course = Course.query.get_or_404(course_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin() and course not in current_user.managed_courses:
        flash('You do not have permission to view this course.', 'error')
        return redirect(url_for('admin_course_list'))
    
    # Get assigned admins
    assigned_admins = User.query.filter(
        User.role.in_(['admin', 'super_admin']),
        User.managed_courses.contains(course)
    ).all()
    
    # Get all students with their enrollment status
    enrollments = CourseEnrollment.query.filter_by(course_id=course.id).all()
    students_data = []
    for enrollment in enrollments:
        students_data.append({
            'student': enrollment.student,
            'status': enrollment.status,
            'requested_at': enrollment.requested_at,
            'approved_at': enrollment.approved_at,
            'rejected_at': enrollment.rejected_at,
            'rejection_reason': enrollment.rejection_reason
        })
    
    # Get notes, quizzes, assignments
    notes = Note.query.filter_by(course_id=course.id).order_by(Note.created_at.desc()).all()
    quizzes = QuizGroup.query.filter_by(course_id=course.id).all()
    assignments = Assignment.query.filter_by(course_id=course.id).all()
    
    # Statistics
    total_students = len(students_data)
    approved_count = sum(1 for s in students_data if s['status'] == 'approved')
    pending_count = sum(1 for s in students_data if s['status'] == 'pending')
    rejected_count = sum(1 for s in students_data if s['status'] == 'rejected')
    
    return render_template('admin/course_detail.html',
                         course=course,
                         admins=assigned_admins,
                         students=students_data,
                         total_students=total_students,
                         approved_count=approved_count,
                         pending_count=pending_count,
                         rejected_count=rejected_count,
                         notes=notes,
                         quizzes=quizzes,
                         assignments=assignments,
                         is_super_admin=current_user.is_super_admin())

@app.route('/admin/courses/<int:course_id>/assign-admin/<int:admin_id>', methods=['POST'])
@login_required
@super_admin_required
def assign_admin_to_course(course_id, admin_id):
    """Assign an admin to manage a course"""
    course = Course.query.get_or_404(course_id)
    admin = User.query.get_or_404(admin_id)
    
    if not admin.is_admin():
        flash('User is not an admin.', 'error')
        return redirect(url_for('admin_course_detail', course_id=course_id))
    
    if admin in course.admins:
        flash(f'{admin.username} is already assigned to this course.', 'warning')
    else:
        course.admins.append(admin)
        db.session.commit()
        flash(f'{admin.username} has been assigned to {course.name}.', 'success')
    
    return redirect(url_for('admin_course_detail', course_id=course_id))

@app.route('/admin/courses/<int:course_id>/remove-admin/<int:admin_id>', methods=['POST'])
@login_required
@super_admin_required
def remove_admin_from_course(course_id, admin_id):
    """Remove an admin from a course"""
    course = Course.query.get_or_404(course_id)
    admin = User.query.get_or_404(admin_id)
    
    # Prevent removing the last admin
    if len(course.admins) <= 1:
        flash('Cannot remove the last admin from a course.', 'error')
        return redirect(url_for('admin_course_detail', course_id=course_id))
    
    if admin in course.admins:
        course.admins.remove(admin)
        db.session.commit()
        flash(f'{admin.username} has been removed from {course.name}.', 'success')
    else:
        flash(f'{admin.username} is not assigned to this course.', 'warning')
    
    return redirect(url_for('admin_course_detail', course_id=course_id))

@app.route('/admin/courses/<int:course_id>/student/<int:student_id>/view')
@login_required
@admin_required
def view_student_in_course(course_id, student_id):
    """View a student's details within a specific course"""
    course = Course.query.get_or_404(course_id)
    student = User.query.get_or_404(student_id)
    
    # Check if admin has permission
    if not current_user.is_super_admin() and course not in current_user.managed_courses:
        flash('You do not have permission to view this course.', 'error')
        return redirect(url_for('admin_course_list'))
    
    # Get enrollment status
    enrollment = CourseEnrollment.query.filter_by(
        student_id=student.id,
        course_id=course.id
    ).first()
    
    if not enrollment:
        flash('Student is not enrolled in this course.', 'error')
        return redirect(url_for('admin_course_detail', course_id=course_id))
    
    # Get student's progress in this course
    progress = course.get_progress_for_student(student.id)
    
    # Get student's quiz results for this course
    quiz_answers = QuizAnswer.query.filter_by(student_id=student.id).all()
    quiz_results = []
    for answer in quiz_answers:
        if answer.quiz_group and answer.quiz_group.course_id == course.id:
            score = answer.quiz_group.get_student_score(student.id)
            if score:
                quiz_results.append({
                    'title': answer.quiz_group.title,
                    'score': score
                })
    
    # Get student's assignment submissions for this course
    submissions = AssignmentSubmission.query.filter_by(student_id=student.id).all()
    assignment_results = []
    for sub in submissions:
        if sub.assignment and sub.assignment.course_id == course.id:
            assignment_results.append({
                'title': sub.assignment.title,
                'submitted_at': sub.submitted_at,
                'score': sub.score,
                'is_graded': sub.is_graded,
                'feedback': sub.feedback
            })
    
    return render_template('admin/student_course_detail.html',
                         course=course,
                         student=student,
                         enrollment=enrollment,
                         progress=progress,
                         quiz_results=quiz_results,
                         assignment_results=assignment_results)

# ============================================================================
# ROUTES - COURSE MANAGEMENT (Super Admin) - CREATE & DELETE
# ============================================================================

@app.route('/admin/courses/create', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_course():
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        description = request.form.get('description')
        
        if not name or not code:
            flash('Course name and code are required.', 'error')
            return render_template('admin/create_course.html')
        
        if Course.query.filter_by(code=code).first():
            flash('Course code already exists.', 'error')
            return render_template('admin/create_course.html')
        
        course = Course(name=name, code=code, description=description)
        db.session.add(course)
        db.session.commit()
        
        flash(f'Course {name} created successfully!', 'success')
        return redirect(url_for('admin_course_list'))
    
    return render_template('admin/create_course.html')

@app.route('/admin/courses/<int:course_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Delete all rejection messages related to this course first
    RejectionMessage.query.filter_by(course_id=course_id).delete()
    
    # Delete all enrollments for this course
    CourseEnrollment.query.filter_by(course_id=course_id).delete()
    
    # Now delete the course
    db.session.delete(course)
    db.session.commit()
    
    flash(f'Course {course.name} deleted successfully.', 'success')
    return redirect(url_for('admin_course_list'))

# ============================================================================
# ROUTES - ANNOUNCEMENTS
# ============================================================================

@app.route('/admin/announcements')
@login_required
@admin_required
def manage_announcements():
    # Filter announcements based on admin role
    if current_user.is_super_admin():
        announcements = Announcement.query.order_by(
            Announcement.is_pinned.desc(), 
            Announcement.created_at.desc()
        ).all()
    else:
        # Regular admin only sees announcements for their courses
        admin_course_ids = [c.id for c in current_user.managed_courses]
        announcements = Announcement.query.filter(
            db.or_(
                Announcement.course_id.in_(admin_course_ids),
                Announcement.course_id.is_(None)  # Also show global announcements
            )
        ).order_by(
            Announcement.is_pinned.desc(), 
            Announcement.created_at.desc()
        ).all()
    
    return render_template('admin/manage_announcements.html', announcements=announcements)

@app.route('/admin/announcements/create', methods=['GET', 'POST'])
@login_required
@admin_required
def post_announcement():
    # Get courses based on admin role
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        is_pinned = request.form.get('is_pinned') == 'on'
        course_id = request.form.get('course_id')
        
        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('admin/post_announcement.html', courses=courses)
        
        # Validate course access for regular admins
        if course_id:
            course = Course.query.get(course_id)
            if not current_user.is_super_admin() and course not in current_user.managed_courses:
                flash('You do not have permission to post announcements for this course.', 'error')
                return render_template('admin/post_announcement.html', courses=courses)
        else:
            course_id = None
        
        announcement = Announcement(
            title=title,
            content=content,
            is_pinned=is_pinned,
            course_id=course_id if course_id else None,
            author_id=current_user.id
        )
        db.session.add(announcement)
        db.session.commit()
        
        # Notify students enrolled in the course
        if course_id:
            course = Course.query.get(course_id)
            students = User.query.filter(
                User.id.in_(
                    db.session.query(CourseEnrollment.student_id).filter(
                        CourseEnrollment.course_id == course_id,
                        CourseEnrollment.status == 'approved'
                    )
                )
            ).all()
            
            for student in students:
                create_notification(
                    user_id=student.id,
                    title=f'New Announcement: {title}',
                    message=f'New announcement posted in {course.name}: {content[:100]}...',
                    type='info',
                    link=url_for('student_announcements'),
                    icon='fa-bullhorn',
                    icon_color='purple'
                )
        else:
            # Global announcement - send to all students
            students = User.query.filter_by(role='student', is_approved=True).all()
            for student in students:
                create_notification(
                    user_id=student.id,
                    title=f'New Announcement: {title}',
                    message=f'New global announcement: {content[:100]}...',
                    type='info',
                    link=url_for('student_announcements'),
                    icon='fa-bullhorn',
                    icon_color='purple'
                )
        
        course_name = course.name if course_id else 'All Courses'
        flash(f'Announcement posted successfully to {course_name}!', 'success')
        return redirect(url_for('manage_announcements'))
    
    return render_template('admin/post_announcement.html', courses=courses)

@app.route('/admin/announcements/<int:announcement_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    
    # Check if admin has permission to delete
    if not current_user.is_super_admin():
        if announcement.course_id and announcement.course not in current_user.managed_courses:
            flash('You do not have permission to delete this announcement.', 'error')
            return redirect(url_for('manage_announcements'))
    
    db.session.delete(announcement)
    db.session.commit()
    flash('Announcement deleted.', 'success')
    return redirect(url_for('manage_announcements'))

@app.route('/admin/announcements/<int:announcement_id>/toggle-pin', methods=['POST'])
@login_required
@admin_required
def toggle_pin_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    announcement.is_pinned = not announcement.is_pinned
    db.session.commit()
    status = 'pinned' if announcement.is_pinned else 'unpinned'
    flash(f'Announcement {status}.', 'success')
    return redirect(url_for('manage_announcements'))

@app.route('/admin/announcements/<int:announcement_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    
    # Check if admin has permission to edit
    if not current_user.is_super_admin():
        if announcement.course_id and announcement.course not in current_user.managed_courses:
            flash('You do not have permission to edit this announcement.', 'error')
            return redirect(url_for('manage_announcements'))
    
    # Get courses based on admin role
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        is_pinned = request.form.get('is_pinned') == 'on'
        course_id = request.form.get('course_id')
        
        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('admin/edit_announcement.html', announcement=announcement, courses=courses)
        
        # Validate course access for regular admins
        if course_id:
            course = Course.query.get(course_id)
            if not current_user.is_super_admin() and course not in current_user.managed_courses:
                flash('You do not have permission to assign this course.', 'error')
                return render_template('admin/edit_announcement.html', announcement=announcement, courses=courses)
        
        announcement.title = title
        announcement.content = content
        announcement.is_pinned = is_pinned
        announcement.course_id = course_id if course_id else None
        announcement.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Announcement updated successfully!', 'success')
        return redirect(url_for('manage_announcements'))
    
    return render_template('admin/edit_announcement.html', 
                         announcement=announcement, 
                         courses=courses)

@app.route('/student/announcements')
@login_required
def student_announcements():
    # Check if student is approved
    if not current_user.is_admin() and not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Get announcements for courses the student is enrolled in
    enrolled_course_ids = [c.id for c in current_user.get_enrolled_courses()]
    
    # Get global announcements and course-specific announcements
    announcements = Announcement.query.filter(
        db.or_(
            Announcement.course_id.is_(None),  # Global announcements
            Announcement.course_id.in_(enrolled_course_ids)  # Course-specific announcements
        )
    ).order_by(
        Announcement.is_pinned.desc(), 
        Announcement.created_at.desc()
    ).all()
    
    return render_template('student/announcements.html', announcements=announcements)

# ============================================================================
# ROUTES - EXPORT REPORTS
# ============================================================================

@app.route('/admin/export')
@login_required
@admin_required
def export_page():
    total_students = User.query.filter_by(role='student').count()
    total_quizzes = QuizGroup.query.count()
    total_assignments = Assignment.query.count()
    return render_template('admin/export.html', 
                         total_students=total_students,
                         total_quizzes=total_quizzes,
                         total_assignments=total_assignments)

@app.route('/admin/export/students')
@login_required
@admin_required
def export_students():
    import csv
    from io import StringIO
    
    students = User.query.filter_by(role='student').all()
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Username', 'Email', 'Enrolled Courses', 'Status', 'Joined Date'])
    
    for student in students:
        courses = ', '.join([c.name for c in student.get_enrolled_courses()])
        status = 'Approved' if student.is_approved else 'Pending'
        writer.writerow([
            student.username,
            student.email,
            courses,
            status,
            student.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=students_export.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

@app.route('/admin/export/quizzes')
@login_required
@admin_required
def export_quizzes():
    import csv
    from io import StringIO
    
    answers = QuizAnswer.query.all()
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Student', 'Quiz', 'Course', 'Question', 'Selected', 'Correct', 'Result'])
    
    for answer in answers:
        student = User.query.get(answer.student_id)
        quiz = QuizGroup.query.get(answer.quiz_group_id)
        question = QuizQuestion.query.get(answer.question_id)
        
        writer.writerow([
            student.username if student else 'Unknown',
            quiz.title if quiz else 'Unknown',
            quiz.course.name if quiz and quiz.course else 'Unknown',
            question.question_text[:50] if question else 'Unknown',
            answer.selected_option,
            question.correct_option if question else 'Unknown',
            'Correct' if answer.is_correct else 'Incorrect'
        ])
    
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=quiz_results_export.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

# ============================================================================
# ROUTES - ADMIN MANAGEMENT (Super Admin)
# ============================================================================

@app.route('/admin/admins')
@login_required
@super_admin_required
def manage_admins():
    admins = User.query.filter(User.role.in_(['admin', 'super_admin'])).all()
    courses = Course.query.all()
    return render_template('admin/manage_admins.html', admins=admins, courses=courses)

@app.route('/admin/admins/create', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_admin():
    courses = Course.query.all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        assigned_courses = request.form.getlist('courses')
        
        if not username or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('admin/create_admin.html', courses=courses)
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            return render_template('admin/create_admin.html', courses=courses)
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('admin/create_admin.html', courses=courses)
        
        admin = User(
            username=username,
            email=email,
            role='admin',
            is_approved=True
        )
        admin.set_password(password)
        db.session.add(admin)
        db.session.flush()
        
        for course_id in assigned_courses:
            course = Course.query.get(course_id)
            if course:
                admin.managed_courses.append(course)
        
        db.session.commit()
        flash(f'Admin {username} created successfully!', 'success')
        return redirect(url_for('manage_admins'))
    
    return render_template('admin/create_admin.html', courses=courses)

@app.route('/admin/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_admin(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.is_super_admin():
        flash('Cannot edit super admin.', 'error')
        return redirect(url_for('manage_admins'))
    
    courses = Course.query.all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        assigned_courses = request.form.getlist('courses')
        
        if not username or not email:
            flash('Username and email are required.', 'error')
            return render_template('admin/edit_admin.html', admin=admin, courses=courses)
        
        existing_user = User.query.filter(User.username == username, User.id != admin.id).first()
        if existing_user:
            flash('Username already taken.', 'error')
            return render_template('admin/edit_admin.html', admin=admin, courses=courses)
        
        existing_email = User.query.filter(User.email == email, User.id != admin.id).first()
        if existing_email:
            flash('Email already registered.', 'error')
            return render_template('admin/edit_admin.html', admin=admin, courses=courses)
        
        admin.username = username
        admin.email = email
        admin.managed_courses = []
        
        for course_id in assigned_courses:
            course = Course.query.get(course_id)
            if course:
                admin.managed_courses.append(course)
        
        db.session.commit()
        flash(f'Admin {username} updated successfully!', 'success')
        return redirect(url_for('manage_admins'))
    
    return render_template('admin/edit_admin.html', admin=admin, courses=courses)

@app.route('/admin/admins/<int:admin_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_admin(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.is_super_admin():
        flash('Cannot delete super admin.', 'error')
        return redirect(url_for('manage_admins'))
    
    db.session.delete(admin)
    db.session.commit()
    flash(f'Admin {admin.username} deleted.', 'success')
    return redirect(url_for('manage_admins'))

# ============================================================================
# ROUTES - NOTES (Admin)
# ============================================================================

@app.route('/admin/notes')
@login_required
@admin_required
def manage_notes():
    if current_user.is_super_admin():
        notes = Note.query.order_by(Note.created_at.desc()).all()
    else:
        course_ids = [c.id for c in current_user.managed_courses]
        notes = Note.query.filter(Note.course_id.in_(course_ids)).order_by(Note.created_at.desc()).all()
    
    courses = Course.query.all()
    tags = Tag.query.all()
    
    return render_template('admin/manage_notes.html', notes=notes, courses=courses, tags=tags)

@app.route('/admin/notes/create', methods=['GET', 'POST'])
@login_required
@admin_required
def post_note():
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    tags = Tag.query.all()
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        course_id = request.form.get('course_id')
        tag_id = request.form.get('tag_id')
        
        if not title or not content or not course_id:
            flash('Title, content, and course are required.', 'error')
            return render_template('admin/post_note.html', courses=courses, tags=tags)
        
        course = Course.query.get(course_id)
        if not current_user.is_super_admin() and course not in current_user.managed_courses:
            flash('You do not have permission for this course.', 'error')
            return render_template('admin/post_note.html', courses=courses, tags=tags)
        
        file_path = None
        file_name = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = get_upload_path(filename)
                file_path = os.path.join('uploads', unique_filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                file_path = unique_filename
                file_name = filename
        
        note = Note(
            title=title,
            content=content,
            course_id=course_id,
            tag_id=tag_id if tag_id else None,
            author_id=current_user.id,
            file_path=file_path,
            file_name=file_name
        )
        db.session.add(note)
        db.session.commit()
        
        # Send notification to all students enrolled in this course
        students = User.query.filter(
            User.id.in_(
                db.session.query(CourseEnrollment.student_id).filter(
                    CourseEnrollment.course_id == course_id,
                    CourseEnrollment.status == 'approved'
                )
            )
        ).all()
        
        for student in students:
            create_notification(
                user_id=student.id,
                title=f'📝 New Note: {title}',
                message=f'A new note "{title}" has been posted in {course.name}.',
                type='info',
                link=url_for('view_note', note_id=note.id),
                icon='fa-file-alt',
                icon_color='blue'
            )
        
        flash(f'Note "{title}" posted successfully! Notifications sent to {len(students)} students.', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/post_note.html', courses=courses, tags=tags)

@app.route('/admin/notes/<int:note_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_note(note_id):
    note = Note.query.get_or_404(note_id)
    
    if not current_user.is_super_admin() and note.course not in current_user.managed_courses:
        flash('You do not have permission to edit this note.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    tags = Tag.query.all()
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        course_id = request.form.get('course_id')
        tag_id = request.form.get('tag_id')
        
        if not title or not content or not course_id:
            flash('Title, content, and course are required.', 'error')
            return render_template('admin/edit_note.html', note=note, courses=courses, tags=tags)
        
        note.title = title
        note.content = content
        note.course_id = course_id
        note.tag_id = tag_id if tag_id else None
        note.updated_at = datetime.utcnow()
        
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                if note.file_path:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], note.file_path)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                filename = secure_filename(file.filename)
                unique_filename = get_upload_path(filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                note.file_path = unique_filename
                note.file_name = filename
        
        db.session.commit()
        
        # Send notification to all students enrolled in this course about the update
        students = User.query.filter(
            User.id.in_(
                db.session.query(CourseEnrollment.student_id).filter(
                    CourseEnrollment.course_id == course_id,
                    CourseEnrollment.status == 'approved'
                )
            )
        ).all()
        
        for student in students:
            create_notification(
                user_id=student.id,
                title=f'📝 Note Updated: {title}',
                message=f'The note "{title}" in {note.course.name} has been updated.',
                type='info',
                link=url_for('view_note', note_id=note.id),
                icon='fa-edit',
                icon_color='blue'
            )
        
        flash(f'Note "{title}" updated successfully! Notifications sent to {len(students)} students.', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/edit_note.html', note=note, courses=courses, tags=tags)

@app.route('/admin/notes/<int:note_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_note(note_id):
    note = Note.query.get_or_404(note_id)
    
    if not current_user.is_super_admin() and note.course not in current_user.managed_courses:
        flash('You do not have permission to delete this note.', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if note.file_path:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], note.file_path)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    # Delete student progress records first
    StudentProgress.query.filter_by(note_id=note.id).delete()
    
    db.session.delete(note)
    db.session.commit()
    flash('Note deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

# ============================================================================
# ROUTES - TAGS (Admin)
# ============================================================================

@app.route('/admin/tags')
@login_required
@admin_required
def manage_tags():
    tags = Tag.query.all()
    return render_template('admin/manage_tags.html', tags=tags)

@app.route('/admin/tags/create', methods=['POST'])
@login_required
@admin_required
def create_tag():
    name = request.form.get('name')
    if not name:
        flash('Tag name is required.', 'error')
        return redirect(url_for('manage_tags'))
    
    if Tag.query.filter_by(name=name).first():
        flash('Tag already exists.', 'error')
        return redirect(url_for('manage_tags'))
    
    tag = Tag(name=name)
    db.session.add(tag)
    db.session.commit()
    flash(f'Tag "{name}" created successfully!', 'success')
    return redirect(url_for('manage_tags'))

@app.route('/admin/tags/<int:tag_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_tag(tag_id):
    tag = Tag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    flash(f'Tag "{tag.name}" deleted.', 'success')
    return redirect(url_for('manage_tags'))

# ============================================================================
# ROUTES - QUIZZES (Admin)
# ============================================================================

@app.route('/admin/quizzes')
@login_required
@admin_required
def manage_quizzes():
    if current_user.is_super_admin():
        quizzes = QuizGroup.query.all()
    else:
        course_ids = [c.id for c in current_user.managed_courses]
        quizzes = QuizGroup.query.filter(QuizGroup.course_id.in_(course_ids)).all()
    
    return render_template('admin/manage_quizzes.html', quizzes=quizzes)

@app.route('/admin/quizzes/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_quiz_group():
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        course_id = request.form.get('course_id')
        time_limit = request.form.get('time_limit', 0)
        
        if not title or not course_id:
            flash('Title and course are required.', 'error')
            return render_template('admin/create_quiz_group.html', courses=courses)
        
        course = Course.query.get(course_id)
        if not current_user.is_super_admin() and course not in current_user.managed_courses:
            flash('You do not have permission for this course.', 'error')
            return render_template('admin/create_quiz_group.html', courses=courses)
        
        quiz_group = QuizGroup(
            title=title,
            description=description,
            course_id=course_id,
            author_id=current_user.id,
            time_limit=int(time_limit) if time_limit else 0
        )
        db.session.add(quiz_group)
        db.session.commit()
        
        questions = request.form.getlist('question_text')
        option_a = request.form.getlist('option_a')
        option_b = request.form.getlist('option_b')
        option_c = request.form.getlist('option_c')
        option_d = request.form.getlist('option_d')
        correct_option = request.form.getlist('correct_option')
        
        for i in range(len(questions)):
            if questions[i] and option_a[i] and option_b[i] and option_c[i] and option_d[i] and correct_option[i]:
                question = QuizQuestion(
                    question_text=questions[i],
                    option_a=option_a[i],
                    option_b=option_b[i],
                    option_c=option_c[i],
                    option_d=option_d[i],
                    correct_option=correct_option[i],
                    order=i,
                    quiz_group_id=quiz_group.id
                )
                db.session.add(question)
        
        db.session.commit()
        flash(f'Quiz "{title}" created with {len(questions)} questions!', 'success')
        return redirect(url_for('manage_quizzes'))
    
    return render_template('admin/create_quiz_group.html', courses=courses)

@app.route('/admin/quizzes/<int:quiz_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_quiz_group(quiz_id):
    quiz = QuizGroup.query.get_or_404(quiz_id)
    
    if not current_user.is_super_admin() and quiz.course not in current_user.managed_courses:
        flash('You do not have permission to edit this quiz.', 'error')
        return redirect(url_for('manage_quizzes'))
    
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        course_id = request.form.get('course_id')
        time_limit = request.form.get('time_limit', 0)
        
        quiz.title = title
        quiz.description = description
        quiz.course_id = course_id
        quiz.time_limit = int(time_limit) if time_limit else 0
        quiz.updated_at = datetime.utcnow()
        
        delete_questions = request.form.getlist('delete_questions')
        for qid in delete_questions:
            q = QuizQuestion.query.get(qid)
            if q and q.quiz_group_id == quiz.id:
                db.session.delete(q)
        
        question_ids = request.form.getlist('question_id')
        for qid in question_ids:
            if qid:
                q = QuizQuestion.query.get(qid)
                if q and q.quiz_group_id == quiz.id:
                    q.question_text = request.form.get(f'question_text_{qid}')
                    q.option_a = request.form.get(f'option_a_{qid}')
                    q.option_b = request.form.get(f'option_b_{qid}')
                    q.option_c = request.form.get(f'option_c_{qid}')
                    q.option_d = request.form.get(f'option_d_{qid}')
                    q.correct_option = request.form.get(f'correct_option_{qid}')
        
        new_questions = request.form.getlist('new_question_text')
        new_option_a = request.form.getlist('new_option_a')
        new_option_b = request.form.getlist('new_option_b')
        new_option_c = request.form.getlist('new_option_c')
        new_option_d = request.form.getlist('new_option_d')
        new_correct_option = request.form.getlist('new_correct_option')
        
        for i in range(len(new_questions)):
            if new_questions[i] and new_option_a[i] and new_option_b[i] and new_option_c[i] and new_option_d[i] and new_correct_option[i]:
                question = QuizQuestion(
                    question_text=new_questions[i],
                    option_a=new_option_a[i],
                    option_b=new_option_b[i],
                    option_c=new_option_c[i],
                    option_d=new_option_d[i],
                    correct_option=new_correct_option[i],
                    order=len(question_ids) + i,
                    quiz_group_id=quiz.id
                )
                db.session.add(question)
        
        db.session.commit()
        flash(f'Quiz "{title}" updated successfully!', 'success')
        return redirect(url_for('manage_quizzes'))
    
    return render_template('admin/edit_quiz_group.html', quiz=quiz, courses=courses)

@app.route('/admin/quizzes/<int:quiz_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_quiz_group(quiz_id):
    quiz = QuizGroup.query.get_or_404(quiz_id)
    
    if not current_user.is_super_admin() and quiz.course not in current_user.managed_courses:
        flash('You do not have permission to delete this quiz.', 'error')
        return redirect(url_for('manage_quizzes'))
    
    # Delete all answers for this quiz first
    QuizAnswer.query.filter_by(quiz_group_id=quiz.id).delete()
    
    # Delete all questions for this quiz
    QuizQuestion.query.filter_by(quiz_group_id=quiz.id).delete()
    
    # Now delete the quiz
    db.session.delete(quiz)
    db.session.commit()
    
    flash('Quiz deleted successfully.', 'success')
    return redirect(url_for('manage_quizzes'))

# ============================================================================
# ROUTES - ASSIGNMENTS (Admin)
# ============================================================================

@app.route('/admin/assignments')
@login_required
@admin_required
def manage_assignments():
    try:
        if current_user.is_super_admin():
            assignments = Assignment.query.order_by(Assignment.created_at.desc()).all()
        else:
            course_ids = [c.id for c in current_user.managed_courses]
            assignments = Assignment.query.filter(
                Assignment.course_id.in_(course_ids)
            ).order_by(Assignment.created_at.desc()).all()
        
        return render_template('admin/manage_assignments.html', assignments=assignments)
    except Exception as e:
        app.logger.error(f"Error in manage_assignments: {e}")
        flash(f'Error loading assignments: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/assignments/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_assignment():
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        course_id = request.form.get('course_id')
        due_date = request.form.get('due_date')
        max_score = request.form.get('max_score', 100)
        
        if not title or not description or not course_id or not due_date:
            flash('All fields are required.', 'error')
            return render_template('admin/create_assignment.html', courses=courses)
        
        course = Course.query.get(course_id)
        if not current_user.is_super_admin() and course not in current_user.managed_courses:
            flash('You do not have permission for this course.', 'error')
            return render_template('admin/create_assignment.html', courses=courses)
        
        try:
            due_date_obj = datetime.strptime(due_date, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format.', 'error')
            return render_template('admin/create_assignment.html', courses=courses)
        
        assignment = Assignment(
            title=title,
            description=description,
            course_id=course_id,
            author_id=current_user.id,
            due_date=due_date_obj,
            max_score=float(max_score) if max_score else 100
        )
        db.session.add(assignment)
        db.session.commit()
        
        # Send notification to all students enrolled in this course
        students = User.query.filter(
            User.id.in_(
                db.session.query(CourseEnrollment.student_id).filter(
                    CourseEnrollment.course_id == course_id,
                    CourseEnrollment.status == 'approved'
                )
            )
        ).all()
        
        for student in students:
            create_notification(
                user_id=student.id,
                title=f'📝 New Assignment: {title}',
                message=f'A new assignment "{title}" has been posted in {course.name}. Due: {due_date_obj.strftime("%b %d, %Y")}',
                type='info',
                link=url_for('student_assignments'),
                icon='fa-tasks',
                icon_color='blue'
            )
        
        flash(f'Assignment "{title}" created successfully! Notifications sent to {len(students)} students.', 'success')
        return redirect(url_for('manage_assignments'))
    
    return render_template('admin/create_assignment.html', courses=courses)

@app.route('/admin/assignments/<int:assignment_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    if not current_user.is_super_admin() and assignment.course not in current_user.managed_courses:
        flash('You do not have permission to edit this assignment.', 'error')
        return redirect(url_for('manage_assignments'))
    
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        course_id = request.form.get('course_id')
        due_date = request.form.get('due_date')
        max_score = request.form.get('max_score', 100)
        
        if not title or not description or not course_id or not due_date:
            flash('All fields are required.', 'error')
            return render_template('admin/edit_assignment.html', assignment=assignment, courses=courses)
        
        try:
            due_date_obj = datetime.strptime(due_date, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid date format.', 'error')
            return render_template('admin/edit_assignment.html', assignment=assignment, courses=courses)
        
        assignment.title = title
        assignment.description = description
        assignment.course_id = course_id
        assignment.due_date = due_date_obj
        assignment.max_score = float(max_score) if max_score else 100
        assignment.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Assignment "{title}" updated successfully!', 'success')
        return redirect(url_for('manage_assignments'))
    
    return render_template('admin/edit_assignment.html', assignment=assignment, courses=courses)

@app.route('/admin/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_assignment(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    if not current_user.is_super_admin() and assignment.course not in current_user.managed_courses:
        flash('You do not have permission to delete this assignment.', 'error')
        return redirect(url_for('manage_assignments'))
    
    db.session.delete(assignment)
    db.session.commit()
    flash('Assignment deleted successfully.', 'success')
    return redirect(url_for('manage_assignments'))

@app.route('/admin/assignments/<int:assignment_id>/submissions')
@login_required
@admin_required
def view_submissions(assignment_id):
    assignment = Assignment.query.get_or_404(assignment_id)
    
    if not current_user.is_super_admin() and assignment.course not in current_user.managed_courses:
        flash('You do not have permission to view these submissions.', 'error')
        return redirect(url_for('manage_assignments'))
    
    submissions = AssignmentSubmission.query.filter_by(assignment_id=assignment_id).all()
    return render_template('admin/view_submissions.html', assignment=assignment, submissions=submissions)

@app.route('/admin/submissions/<int:submission_id>/grade', methods=['GET', 'POST'])
@login_required
@admin_required
def grade_submission(submission_id):
    submission = AssignmentSubmission.query.get_or_404(submission_id)
    assignment = submission.assignment
    
    if not current_user.is_super_admin() and assignment.course not in current_user.managed_courses:
        flash('You do not have permission to grade this submission.', 'error')
        return redirect(url_for('manage_assignments'))
    
    if request.method == 'POST':
        score = request.form.get('score')
        feedback = request.form.get('feedback')
        
        if not score:
            flash('Score is required.', 'error')
            return render_template('admin/grade_submission.html', submission=submission)
        
        submission.score = float(score)
        submission.feedback = feedback
        submission.is_graded = True
        
        db.session.commit()
        flash(f'Submission graded with score {score}.', 'success')
        return redirect(url_for('view_submissions', assignment_id=assignment.id))
    
    return render_template('admin/grade_submission.html', submission=submission)

# ============================================================================
# ROUTES - STUDENT COURSE VIEWING (with Approval Check)
# ============================================================================

@app.route('/student/courses')
@login_required
def student_courses():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Check if account is suspended
    if current_user.is_suspended:
        flash(f'Your account has been suspended. Reason: {current_user.suspension_reason or "No reason provided."}', 'error')
        logout_user()
        return redirect(url_for('login'))
    
    # Check if student is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Get approved and pending courses
    approved_courses = current_user.get_enrolled_courses()
    pending_courses = current_user.get_pending_courses()
    
    # Get available courses (not enrolled in any way)
    enrolled_course_ids = [c.id for c in approved_courses] + [c.id for c in pending_courses]
    
    # Check for rejected courses
    rejections = RejectionMessage.query.filter_by(student_id=current_user.id).all()
    rejected_course_ids = [r.course_id for r in rejections]
    
    # Get available courses (not enrolled, not rejected)
    if enrolled_course_ids or rejected_course_ids:
        exclude_ids = enrolled_course_ids + rejected_course_ids
        available_courses = Course.query.filter(~Course.id.in_(exclude_ids)).all()
    else:
        available_courses = Course.query.all()
    
    return render_template('student_courses.html', 
                         approved_courses=approved_courses,
                         pending_courses=pending_courses,
                         available_courses=available_courses,
                         rejections=rejections)

@app.route('/student/courses/<int:course_id>')
@login_required
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Check if student is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Check if student is APPROVED for this course
    if not current_user.is_enrolled_in_course(course_id):
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('student_courses'))
    
    notes = Note.query.filter_by(course_id=course_id).order_by(Note.created_at.desc()).all()
    tags = Tag.query.all()
    progress = course.get_progress_for_student(current_user.id)
    
    return render_template('course.html', course=course, notes=notes, tags=tags, progress=progress)

@app.route('/student/courses/<int:course_id>/request', methods=['POST'])
@login_required
def request_course(course_id):
    if current_user.is_admin():
        flash('Admins cannot request courses.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    course = Course.query.get_or_404(course_id)
    
    # Check if already enrolled or pending
    existing_enrollment = CourseEnrollment.query.filter_by(
        student_id=current_user.id,
        course_id=course_id
    ).first()
    
    if existing_enrollment:
        if existing_enrollment.status == 'approved':
            flash('You are already enrolled in this course.', 'info')
        elif existing_enrollment.status == 'pending':
            flash('Your request for this course is pending approval.', 'warning')
        elif existing_enrollment.status == 'rejected':
            flash(f'Your request for this course was previously rejected.', 'error')
        return redirect(url_for('student_courses'))
    
    # Create new enrollment request
    enrollment = CourseEnrollment(
        student_id=current_user.id,
        course_id=course_id,
        status='pending'
    )
    db.session.add(enrollment)
    
    # Update user approval status
    current_user.is_approved = False
    db.session.commit()
    
    # Notify student
    notify_course_request(current_user.id, course.name)
    
    # Notify all admins assigned to this course
    admins = User.query.filter(
        User.role.in_(['admin', 'super_admin']),
        User.managed_courses.contains(course)
    ).all()
    
    for admin in admins:
        notify_admin_course_request(admin.id, current_user.username, course.name)
    
    flash(f'Request sent for {course.name}. Waiting for admin approval.', 'success')
    return redirect(url_for('student_courses'))

@app.route('/student/courses/<int:course_id>/reapply', methods=['POST'])
@login_required
def reapply_course(course_id):
    """Re-apply for a course that was previously rejected"""
    if current_user.is_admin():
        flash('Admins cannot request courses.', 'warning')
        return redirect(url_for('student_dashboard'))
    
    course = Course.query.get_or_404(course_id)
    
    # Check if there's a rejection
    enrollment = CourseEnrollment.query.filter_by(
        student_id=current_user.id,
        course_id=course_id,
        status='rejected'
    ).first()
    
    if not enrollment:
        flash('You have not been rejected from this course.', 'info')
        return redirect(url_for('student_courses'))
    
    # Update enrollment to pending
    enrollment.status = 'pending'
    enrollment.rejected_at = None
    enrollment.rejection_reason = None
    
    # Remove rejection message
    RejectionMessage.query.filter_by(
        student_id=current_user.id,
        course_id=course_id
    ).delete()
    
    current_user.is_approved = False
    db.session.commit()
    
    flash(f'You have re-applied for {course.name}. Waiting for admin approval.', 'success')
    return redirect(url_for('student_courses'))

@app.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    note = Note.query.get_or_404(note_id)
    
    if current_user.is_admin():
        # Admins can view notes directly
        return render_template('view_note.html', note=note)
    
    # Check if student is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Check if student has access to this note's course
    if not current_user.is_enrolled_in_course(note.course_id):
        flash('You do not have access to this note.', 'error')
        return redirect(url_for('student_dashboard'))
    
    # Mark as read
    progress = StudentProgress.query.filter_by(
        student_id=current_user.id,
        note_id=note.id
    ).first()
    
    if not progress:
        progress = StudentProgress(
            student_id=current_user.id,
            note_id=note.id,
            course_id=note.course_id,
            is_read=True,
            read_at=datetime.utcnow()
        )
        db.session.add(progress)
    elif not progress.is_read:
        progress.is_read = True
        progress.read_at = datetime.utcnow()
    
    db.session.commit()
    
    return render_template('view_note.html', note=note)

@app.route('/student/notes/<int:note_id>/toggle-read', methods=['POST'])
@login_required
def toggle_note_read(note_id):
    note = Note.query.get_or_404(note_id)
    
    if current_user.is_admin():
        return jsonify({'error': 'Admins cannot track progress'}), 403
    
    if not current_user.is_enrolled_in_course(note.course_id):
        return jsonify({'error': 'Not enrolled'}), 403
    
    progress = StudentProgress.query.filter_by(
        student_id=current_user.id,
        note_id=note.id
    ).first()
    
    if not progress:
        progress = StudentProgress(
            student_id=current_user.id,
            note_id=note.id,
            course_id=note.course_id,
            is_read=True,
            read_at=datetime.utcnow()
        )
        db.session.add(progress)
    else:
        progress.is_read = not progress.is_read
        if progress.is_read:
            progress.read_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True, 'is_read': progress.is_read})

# ============================================================================
# ROUTES - STUDENT QUIZZES (with Approval Check)
# ============================================================================

@app.route('/student/quizzes')
@login_required
def student_quizzes():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Check if student is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Get courses the student is approved for
    approved_courses = current_user.get_enrolled_courses()
    course_ids = [c.id for c in approved_courses]
    
    quizzes = QuizGroup.query.filter(QuizGroup.course_id.in_(course_ids)).all()
    
    quiz_data = []
    for quiz in quizzes:
        score = quiz.get_student_score(current_user.id)
        quiz_data.append({
            'quiz': quiz,
            'score': score,
            'has_attempted': score is not None
        })
    
    return render_template('student_quizzes.html', quiz_data=quiz_data)

@app.route('/student/quizzes/<int:quiz_id>/take', methods=['GET', 'POST'])
@login_required
def take_quiz(quiz_id):
    if current_user.is_admin():
        flash('Admins cannot take quizzes.', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    quiz = QuizGroup.query.get_or_404(quiz_id)
    
    if not current_user.is_enrolled_in_course(quiz.course_id):
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('student_quizzes'))
    
    # Check if already taken
    existing_answers = QuizAnswer.query.filter_by(
        student_id=current_user.id,
        quiz_group_id=quiz.id
    ).first()
    
    if existing_answers:
        flash('You have already taken this quiz.', 'info')
        return redirect(url_for('student_quizzes'))
    
    questions = quiz.questions
    
    if request.method == 'POST':
        correct_count = 0
        total = len(questions)
        
        for question in questions:
            selected = request.form.get(f'question_{question.id}')
            if selected:
                is_correct = selected == question.correct_option
                if is_correct:
                    correct_count += 1
                
                answer = QuizAnswer(
                    student_id=current_user.id,
                    quiz_group_id=quiz.id,
                    question_id=question.id,
                    selected_option=selected,
                    is_correct=is_correct
                )
                db.session.add(answer)
        
        db.session.commit()
        
        score_percentage = int((correct_count / total) * 100) if total > 0 else 0
        
        return render_template('quiz_result.html', 
                             quiz=quiz, 
                             total=total, 
                             correct=correct_count, 
                             score=score_percentage)
    
    return render_template('take_quiz_group.html', quiz=quiz, questions=questions)

@app.route('/student/quizzes/<int:quiz_id>/result')
@login_required
def quiz_result(quiz_id):
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    quiz = QuizGroup.query.get_or_404(quiz_id)
    
    if not current_user.is_enrolled_in_course(quiz.course_id):
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('student_quizzes'))
    
    answers = QuizAnswer.query.filter_by(
        student_id=current_user.id,
        quiz_group_id=quiz.id
    ).all()
    
    if not answers:
        flash('You have not taken this quiz yet.', 'info')
        return redirect(url_for('student_quizzes'))
    
    correct = sum(1 for a in answers if a.is_correct)
    total = len(answers)
    score = int((correct / total) * 100) if total > 0 else 0
    
    return render_template('quiz_result.html', 
                         quiz=quiz, 
                         total=total, 
                         correct=correct, 
                         score=score)

# ============================================================================
# ROUTES - STUDENT ASSIGNMENTS (with Approval Check)
# ============================================================================

@app.route('/student/assignments')
@login_required
def student_assignments():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Check if student is approved
    if not current_user.is_approved:
        flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
        return redirect(url_for('student_pending_approval'))
    
    # Get courses the student is approved for
    approved_courses = current_user.get_enrolled_courses()
    course_ids = [c.id for c in approved_courses]
    
    assignments = Assignment.query.filter(Assignment.course_id.in_(course_ids)).all()
    
    assignment_data = []
    for assignment in assignments:
        submission = assignment.get_submission_for_student(current_user.id)
        assignment_data.append({
            'assignment': assignment,
            'submission': submission,
            'is_submitted': submission is not None,
            'is_graded': submission and submission.is_graded,
            'is_past_due': assignment.is_past_due()
        })
    
    return render_template('student_assignments.html', assignment_data=assignment_data)

@app.route('/student/assignments/<int:assignment_id>/submit', methods=['GET', 'POST'])
@login_required
def submit_assignment(assignment_id):
    if current_user.is_admin():
        flash('Admins cannot submit assignments.', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    assignment = Assignment.query.get_or_404(assignment_id)
    
    if not current_user.is_enrolled_in_course(assignment.course_id):
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('student_assignments'))
    
    if assignment.is_past_due():
        flash('This assignment is past due.', 'error')
        return redirect(url_for('student_assignments'))
    
    existing = assignment.get_submission_for_student(current_user.id)
    if existing:
        flash('You have already submitted this assignment.', 'info')
        return redirect(url_for('student_assignments'))
    
    if request.method == 'POST':
        content = request.form.get('content')
        
        if not content:
            flash('Please provide content or upload a file.', 'error')
            return render_template('student_submit_assignment.html', assignment=assignment)
        
        file_path = None
        file_name = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = get_upload_path(filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                file_path = unique_filename
                file_name = filename
        
        submission = AssignmentSubmission(
            student_id=current_user.id,
            assignment_id=assignment.id,
            content=content,
            file_path=file_path,
            file_name=file_name
        )
        db.session.add(submission)
        db.session.commit()
        
        flash('Assignment submitted successfully!', 'success')
        return redirect(url_for('student_assignments'))
    
    return render_template('student_submit_assignment.html', assignment=assignment)

# ============================================================================
# ROUTES - LEADERBOARD (Student & Admin)
# ============================================================================

@app.route('/leaderboard')
@login_required
def leaderboard():
    if current_user.is_admin():
        flash('Leaderboard is for students.', 'info')
        return redirect(url_for('admin_dashboard'))
    
    # Get the student's enrolled courses (approved ones)
    enrolled_courses = current_user.get_enrolled_courses()
    enrolled_course_ids = [c.id for c in enrolled_courses]
    
    # Get all students who are approved and have taken quizzes
    # But only show students who share at least one course with the current user
    students = User.query.filter_by(role='student', is_approved=True).all()
    student_scores = []
    
    for student in students:
        # Get the student's enrolled courses
        student_courses = student.get_enrolled_courses()
        student_course_ids = [c.id for c in student_courses]
        
        # Check if they share any course with the current user
        shared_courses = set(enrolled_course_ids) & set(student_course_ids)
        
        # Skip if no shared courses and not the current user
        if not shared_courses and student.id != current_user.id:
            continue
        
        answers = QuizAnswer.query.filter_by(student_id=student.id).all()
        correct = sum(1 for a in answers if a.is_correct)
        total = len(answers)
        score = int((correct / total) * 100) if total > 0 else 0
        
        student_scores.append({
            'student': student,
            'score': score,
            'total_questions': total,
            'course_count': len(student_courses),
            'shared_courses': list(shared_courses)
        })
    
    # Sort by score descending
    student_scores.sort(key=lambda x: x['score'], reverse=True)
    
    # Get course list for filter dropdown (only courses the student is enrolled in)
    courses = enrolled_courses
    
    return render_template('leaderboard.html', 
                         student_scores=student_scores,
                         courses=courses,
                         current_course_id=None)

@app.route('/leaderboard/course/<int:course_id>')
@login_required
def leaderboard_by_course(course_id):
    if current_user.is_admin():
        flash('Leaderboard is for students.', 'info')
        return redirect(url_for('admin_dashboard'))
    
    # Check if the student is enrolled in this course
    if not current_user.is_enrolled_in_course(course_id):
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('leaderboard'))
    
    course = Course.query.get_or_404(course_id)
    
    # Get all students who are approved and enrolled in this course
    # Get the course's approved enrollments
    enrollments = CourseEnrollment.query.filter_by(
        course_id=course_id,
        status='approved'
    ).all()
    
    student_ids = [e.student_id for e in enrollments]
    students = User.query.filter(User.id.in_(student_ids)).all()
    
    student_scores = []
    for student in students:
        answers = QuizAnswer.query.filter_by(student_id=student.id).all()
        correct = sum(1 for a in answers if a.is_correct)
        total = len(answers)
        score = int((correct / total) * 100) if total > 0 else 0
        
        student_scores.append({
            'student': student,
            'score': score,
            'total_questions': total,
            'course_count': len(student.get_enrolled_courses())
        })
    
    # Sort by score descending
    student_scores.sort(key=lambda x: x['score'], reverse=True)
    
    # Get all courses for the filter dropdown
    courses = current_user.get_enrolled_courses()
    
    return render_template('leaderboard.html', 
                         student_scores=student_scores,
                         courses=courses,
                         current_course_id=course_id,
                         current_course=course)

@app.route('/admin/leaderboard')
@login_required
@admin_required
def admin_leaderboard():
    """Admin view of leaderboard with course filtering"""
    
    # Get all courses (or just the ones the admin manages)
    if current_user.is_super_admin():
        all_courses = Course.query.all()
    else:
        all_courses = current_user.managed_courses
    
    # Get filter parameters
    course_id = request.args.get('course_id', type=int)
    sort_by = request.args.get('sort_by', 'score')  # score, name, questions
    
    # Get students based on filter
    if course_id:
        # Filter by specific course
        course = Course.query.get_or_404(course_id)
        enrollments = CourseEnrollment.query.filter_by(
            course_id=course_id,
            status='approved'
        ).all()
        student_ids = [e.student_id for e in enrollments]
        students = User.query.filter(User.id.in_(student_ids)).all()
        selected_course = course
    else:
        # Show all students (super admin) or students in admin's courses
        if current_user.is_super_admin():
            students = User.query.filter_by(role='student', is_approved=True).all()
        else:
            # Regular admin: students in their managed courses
            admin_course_ids = [c.id for c in current_user.managed_courses]
            student_ids = db.session.query(CourseEnrollment.student_id).filter(
                CourseEnrollment.course_id.in_(admin_course_ids),
                CourseEnrollment.status == 'approved'
            ).distinct().all()
            student_ids = [s[0] for s in student_ids]
            students = User.query.filter(User.id.in_(student_ids)).all() if student_ids else []
        selected_course = None
    
    student_scores = []
    for student in students:
        answers = QuizAnswer.query.filter_by(student_id=student.id).all()
        correct = sum(1 for a in answers if a.is_correct)
        total = len(answers)
        score = int((correct / total) * 100) if total > 0 else 0
        
        # Get student's courses
        student_courses = student.get_enrolled_courses()
        
        student_scores.append({
            'student': student,
            'score': score,
            'correct': correct,
            'total': total,
            'course_count': len(student_courses),
            'courses': [c.name for c in student_courses[:3]],
            'joined': student.created_at.strftime('%b %d, %Y'),
            'status': 'Active' if student.is_approved else 'Pending',
            'course_names': ', '.join([c.name for c in student_courses[:3]]) + ('...' if len(student_courses) > 3 else '')
        })
    
    # Sort based on parameter
    if sort_by == 'name':
        student_scores.sort(key=lambda x: x['student'].username.lower())
    elif sort_by == 'questions':
        student_scores.sort(key=lambda x: x['total'], reverse=True)
    else:  # score (default)
        student_scores.sort(key=lambda x: x['score'], reverse=True)
    
    total_students = len(student_scores)
    avg_score = sum(s['score'] for s in student_scores) / total_students if total_students > 0 else 0
    top_performer = student_scores[0] if student_scores else None
    
    return render_template('admin/leaderboard.html',
                         student_scores=student_scores,
                         total_students=total_students,
                         avg_score=avg_score,
                         top_performer=top_performer,
                         courses=all_courses,
                         selected_course=selected_course,
                         current_course_id=course_id,
                         sort_by=sort_by)

@app.route('/admin/leaderboard/reset/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def reset_student_scores(student_id):
    """Reset a student's quiz scores"""
    student = User.query.get_or_404(student_id)
    
    QuizAnswer.query.filter_by(student_id=student_id).delete()
    db.session.commit()
    
    flash(f'All quiz scores for {student.username} have been reset.', 'success')
    return redirect(url_for('admin_leaderboard'))

@app.route('/admin/leaderboard/reset-all', methods=['POST'])
@login_required
@admin_required
def reset_all_scores():
    """Reset all students' quiz scores"""
    if not current_user.is_super_admin():
        flash('Only super admin can reset all scores.', 'error')
        return redirect(url_for('admin_leaderboard'))
    
    QuizAnswer.query.delete()
    db.session.commit()
    
    flash('All student quiz scores have been reset.', 'success')
    return redirect(url_for('admin_leaderboard'))

@app.route('/admin/leaderboard/export')
@login_required
@admin_required
def export_leaderboard():
    """Export leaderboard data as CSV"""
    import csv
    from io import StringIO
    
    students = User.query.filter_by(role='student', is_approved=True).all()
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['Rank', 'Student', 'Email', 'Score', 'Correct', 'Total', 'Courses', 'Joined'])
    
    rank = 1
    for student in students:
        answers = QuizAnswer.query.filter_by(student_id=student.id).all()
        correct = sum(1 for a in answers if a.is_correct)
        total = len(answers)
        score = int((correct / total) * 100) if total > 0 else 0
        
        writer.writerow([
            rank,
            student.username,
            student.email,
            f"{score}%",
            correct,
            total,
            len(student.get_enrolled_courses()),
            student.created_at.strftime('%Y-%m-%d')
        ])
        rank += 1
    
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=leaderboard_export.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

# ============================================================================
# ROUTES - FILE DOWNLOADS
# ============================================================================

@app.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ============================================================================
# ROUTES - PENDING APPROVAL PAGE
# ============================================================================

@app.route('/pending-approval')
def pending_approval():
    if current_user.is_authenticated and current_user.is_approved:
        return redirect(url_for('dashboard'))
    return render_template('pending_approval.html')

# ============================================================================
# ROUTES - RECENT ACTIVITY
# ============================================================================

@app.route('/admin/recent-activity')
@login_required
@admin_required
def recent_activity():
    """View recent activity across the platform"""
    try:
        activities = []
        
        # Get recent notes
        notes = Note.query.order_by(Note.created_at.desc()).limit(20).all()
        for note in notes:
            activities.append({
                'type': 'note',
                'action': f'Created note: "{note.title}"',
                'created_at': note.created_at,
                'author': note.author,
                'user': note.author.username if note.author else 'Unknown',
                'url': url_for('edit_note', note_id=note.id) if note.id else None
            })
        
        # Get recent quizzes
        quizzes = QuizGroup.query.order_by(QuizGroup.created_at.desc()).limit(20).all()
        for quiz in quizzes:
            activities.append({
                'type': 'quiz',
                'action': f'Created quiz: "{quiz.title}"',
                'created_at': quiz.created_at,
                'author': quiz.author,
                'user': quiz.author.username if quiz.author else 'Unknown',
                'url': url_for('edit_quiz_group', quiz_id=quiz.id) if quiz.id else None
            })
        
        # Get recent assignments
        assignments = Assignment.query.order_by(Assignment.created_at.desc()).limit(20).all()
        for assignment in assignments:
            activities.append({
                'type': 'assignment',
                'action': f'Created assignment: "{assignment.title}"',
                'created_at': assignment.created_at,
                'author': assignment.author,
                'user': assignment.author.username if assignment.author else 'Unknown',
                'url': url_for('edit_assignment', assignment_id=assignment.id) if assignment.id else None
            })
        
        # Get recent student signups (use created_at)
        students = User.query.filter_by(role='student').order_by(User.created_at.desc()).limit(10).all()
        for student in students:
            activities.append({
                'type': 'student',
                'action': f'Student registered: "{student.username}"',
                'created_at': student.created_at,
                'author': None,
                'user': student.username,
                'url': url_for('edit_student', student_id=student.id) if student.id else None
            })
        
        # Get recent announcements
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(10).all()
        for announcement in announcements:
            activities.append({
                'type': 'announcement',
                'action': f'Posted announcement: "{announcement.title}"',
                'created_at': announcement.created_at,
                'author': announcement.author,
                'user': announcement.author.username if announcement.author else 'Unknown',
                'url': url_for('edit_announcement', announcement_id=announcement.id) if announcement.id else None
            })
        
        # Sort by timestamp (newest first)
        activities.sort(key=lambda x: x['created_at'], reverse=True)
        
        return render_template('admin/recent_activity.html', activities=activities[:50])
        
    except Exception as e:
        app.logger.error(f'Recent activity error: {e}')
        flash(f'Error loading recent activity: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

# ============================================================================
# BULK DELETE NOTES
# ============================================================================

@app.route('/admin/notes/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_notes():
    note_ids = request.form.getlist('note_ids')
    
    if not note_ids:
        flash('No notes selected.', 'warning')
        return redirect(url_for('manage_notes'))
    
    deleted_count = 0
    for note_id in note_ids:
        note = Note.query.get(note_id)
        if note:
            if current_user.is_super_admin() or note.course in current_user.managed_courses:
                if note.file_path:
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], note.file_path)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                db.session.delete(note)
                deleted_count += 1
    
    db.session.commit()
    flash(f'{deleted_count} notes deleted successfully.', 'success')
    return redirect(url_for('manage_notes'))

# ============================================================================
# ROUTES - ADMIN COURSE ANALYTICS
# ============================================================================

@app.route('/admin/analytics')
@login_required
@admin_required
def admin_course_analytics():
    """Course analytics dashboard for admins"""
    # Get all courses (or just the ones the admin manages)
    if current_user.is_super_admin():
        courses = Course.query.all()
    else:
        courses = current_user.managed_courses
    
    # Get analytics data for each course
    course_data = []
    for course in courses:
        # Count students
        total_students = CourseEnrollment.query.filter_by(
            course_id=course.id,
            status='approved'
        ).count()
        
        # Count notes
        notes_count = Note.query.filter_by(course_id=course.id).count()
        
        # Count quizzes
        quizzes_count = QuizGroup.query.filter_by(course_id=course.id).count()
        
        # Count assignments
        assignments_count = Assignment.query.filter_by(course_id=course.id).count()
        
        # Count submissions
        submissions_count = AssignmentSubmission.query.filter(
            AssignmentSubmission.assignment_id.in_(
                db.session.query(Assignment.id).filter_by(course_id=course.id)
            )
        ).count()
        
        # Calculate average progress
        enrollments = CourseEnrollment.query.filter_by(
            course_id=course.id,
            status='approved'
        ).all()
        
        total_progress = 0
        if enrollments:
            for enrollment in enrollments:
                total_progress += course.get_progress_for_student(enrollment.student_id)
            avg_progress = total_progress // len(enrollments)
        else:
            avg_progress = 0
        
        course_data.append({
            'course': course,
            'total_students': total_students,
            'notes_count': notes_count,
            'quizzes_count': quizzes_count,
            'assignments_count': assignments_count,
            'submissions_count': submissions_count,
            'avg_progress': avg_progress
        })
    
    return render_template('admin/course_analytics.html', course_data=course_data)

# ============================================================================
# ROUTES - ADMIN BULK ACTIONS
# ============================================================================

@app.route('/admin/bulk-actions', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_actions():
    """Bulk actions for students"""
    if request.method == 'POST':
        action = request.form.get('action')
        student_ids = request.form.getlist('student_ids')
        
        if not student_ids:
            flash('No students selected.', 'warning')
            return redirect(url_for('bulk_actions'))
        
        if action == 'approve':
            approved_count = 0
            for sid in student_ids:
                student = User.query.get(sid)
                if student and student.role == 'student':
                    student.is_approved = True
                    approved_count += 1
            db.session.commit()
            flash(f'{approved_count} students approved successfully.', 'success')
            
        elif action == 'delete':
            # Only super admin can delete
            if not current_user.is_super_admin():
                flash('Only super admin can delete students.', 'error')
                return redirect(url_for('bulk_actions'))
            
            deleted_count = 0
            for sid in student_ids:
                student = User.query.get(sid)
                if student and student.role == 'student':
                    # Delete related records
                    CourseEnrollment.query.filter_by(student_id=student.id).delete()
                    db.session.delete(student)
                    deleted_count += 1
            db.session.commit()
            flash(f'{deleted_count} students deleted successfully.', 'success')
            
        elif action == 'suspend':
            reason = request.form.get('reason', 'No reason provided.')
            suspended_count = 0
            for sid in student_ids:
                student = User.query.get(sid)
                if student and student.role == 'student':
                    student.is_suspended = True
                    student.suspension_reason = reason
                    student.suspended_at = datetime.utcnow()
                    student.is_approved = False
                    suspended_count += 1
                    notify_student_suspended(student.id, reason)
            db.session.commit()
            flash(f'{suspended_count} students suspended successfully.', 'warning')
            
        elif action == 'unsuspend':
            unsuspended_count = 0
            for sid in student_ids:
                student = User.query.get(sid)
                if student and student.role == 'student':
                    student.is_suspended = False
                    student.suspension_reason = None
                    student.suspended_at = None
                    unsuspended_count += 1
                    notify_student_unsuspended(student.id)
            db.session.commit()
            flash(f'{unsuspended_count} students unsuspended successfully.', 'success')
            
        else:
            flash('Invalid action selected.', 'error')
        
        return redirect(url_for('bulk_actions'))
    
    # GET request - show bulk actions page
    students = User.query.filter_by(role='student').all()
    return render_template('admin/bulk_actions.html', students=students)

# ============================================================================
# ROUTES - ADMIN MESSAGES
# ============================================================================

@app.route('/admin/messages')
@login_required
@admin_required
def admin_messages():
    """Admin messages/inbox"""
    # Get all students (for sending messages)
    students = User.query.filter_by(role='student').all()
    return render_template('admin/admin_messages.html', students=students)

# ============================================================================
# ROUTES - SYSTEM SETTINGS
# ============================================================================

@app.route('/admin/system-settings', methods=['GET', 'POST'])
@login_required
@super_admin_required
def system_settings():
    """System settings configuration"""
    
    if request.method == 'POST':
        try:
            # General Settings
            save_setting('site_name', request.form.get('site_name', 'A-Portal LMS'), 'string', 'Site name displayed throughout the platform', 'general')
            save_setting('site_description', request.form.get('site_description', 'Learning Management System'), 'string', 'Meta description for SEO', 'general')
            save_setting('default_language', request.form.get('default_language', 'en'), 'string', 'Default user interface language', 'general')
            save_setting('maintenance_mode', request.form.get('maintenance_mode') == 'on', 'boolean', 'Show maintenance page to all users except admins', 'general')
            save_setting('timezone', request.form.get('timezone', 'UTC'), 'string', 'Default timezone for the system', 'general')
            
            # Student Settings
            save_setting('auto_approve_students', request.form.get('auto_approve_students') == 'on', 'boolean', 'Automatically approve new student accounts', 'student')
            save_setting('max_courses_per_student', int(request.form.get('max_courses_per_student', 10)), 'integer', 'Maximum courses a student can enroll in', 'student')
            save_setting('allow_reapplications', request.form.get('allow_reapplications') == 'on', 'boolean', 'Allow students to reapply after rejection', 'student')
            save_setting('require_phone_number', request.form.get('require_phone_number') == 'on', 'boolean', 'Require phone number during registration', 'student')
            save_setting('student_registration_enabled', request.form.get('student_registration_enabled') == 'on', 'boolean', 'Enable student self-registration', 'student')
            
            # Security Settings
            save_setting('session_timeout', int(request.form.get('session_timeout', 60)), 'integer', 'Minutes before auto-logout (0 = never)', 'security')
            save_setting('require_email_verification', request.form.get('require_email_verification') == 'on', 'boolean', 'Verify email before accessing content', 'security')
            save_setting('max_login_attempts', int(request.form.get('max_login_attempts', 5)), 'integer', 'Max login attempts before lockout', 'security')
            save_setting('lockout_duration', int(request.form.get('lockout_duration', 30)), 'integer', 'Minutes user is locked out', 'security')
            save_setting('force_ssl', request.form.get('force_ssl') == 'on', 'boolean', 'Redirect all HTTP to HTTPS', 'security')
            
            # Content Settings
            save_setting('max_file_upload_size', int(request.form.get('max_file_upload_size', 16)), 'integer', 'Maximum file upload size in MB', 'content')
            save_setting('allowed_file_types', request.form.get('allowed_file_types', 'pdf,png,jpg,jpeg,gif,doc,docx,txt,zip'), 'string', 'Comma separated allowed file extensions', 'content')
            save_setting('enable_comments', request.form.get('enable_comments') == 'on', 'boolean', 'Allow comments on notes and assignments', 'content')
            save_setting('enable_ratings', request.form.get('enable_ratings') == 'on', 'boolean', 'Allow students to rate courses', 'content')
            
            # Notification Settings
            save_setting('email_notifications', request.form.get('email_notifications') == 'on', 'boolean', 'Send email notifications for events', 'notification')
            save_setting('push_notifications', request.form.get('push_notifications') == 'on', 'boolean', 'Send in-app push notifications', 'notification')
            save_setting('assignment_reminders', request.form.get('assignment_reminders') == 'on', 'boolean', 'Send reminders before assignment due dates', 'notification')
            save_setting('reminder_days_before', int(request.form.get('reminder_days_before', 3)), 'integer', 'Days before due date to send reminder', 'notification')
            
            db.session.commit()
            flash('✅ System settings saved successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error saving settings: {str(e)}', 'error')
            app.logger.error(f'System settings error: {e}')
        
        return redirect(url_for('system_settings'))
    
    # GET request - load all settings
    settings = get_all_settings()
    
    return render_template('admin/system_settings.html', settings=settings)

# ============================================================================
# ROUTES - SYSTEM LOGS
# ============================================================================

@app.route('/admin/system-logs')
@login_required
@super_admin_required
def system_logs():
    """View system logs with filtering and pagination"""
    try:
        logs = []
        
        # Get recent notes
        notes = Note.query.order_by(Note.created_at.desc()).limit(30).all()
        for note in notes:
            logs.append({
                'timestamp': note.created_at,
                'user': note.author.username if note.author else 'System',
                'action': f'Created note: "{note.title}" in {note.course.name if note.course else "Unknown"}',
                'type': 'note',
                'details': f'Note ID: {note.id}'
            })
        
        # Get recent quizzes
        quizzes = QuizGroup.query.order_by(QuizGroup.created_at.desc()).limit(30).all()
        for quiz in quizzes:
            logs.append({
                'timestamp': quiz.created_at,
                'user': quiz.author.username if quiz.author else 'System',
                'action': f'Created quiz: "{quiz.title}" with {len(quiz.questions)} questions',
                'type': 'quiz',
                'details': f'Quiz ID: {quiz.id}'
            })
        
        # Get recent assignments
        assignments = Assignment.query.order_by(Assignment.created_at.desc()).limit(30).all()
        for assignment in assignments:
            logs.append({
                'timestamp': assignment.created_at,
                'user': assignment.author.username if assignment.author else 'System',
                'action': f'Created assignment: "{assignment.title}"',
                'type': 'assignment',
                'details': f'Assignment ID: {assignment.id}'
            })
        
        # Get recent student registrations
        students = User.query.filter_by(role='student').order_by(User.created_at.desc()).limit(20).all()
        for student in students:
            logs.append({
                'timestamp': student.created_at,
                'user': 'System',
                'action': f'Student registered: "{student.username}" ({student.email})',
                'type': 'student',
                'details': f'Student ID: {student.id}'
            })
        
        # Get recent course creations
        courses = Course.query.order_by(Course.created_at.desc()).limit(20).all()
        for course in courses:
            logs.append({
                'timestamp': course.created_at,
                'user': 'System',
                'action': f'Course created: "{course.name}" ({course.code})',
                'type': 'course',
                'details': f'Course ID: {course.id}'
            })
        
        # Get recent announcements
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(20).all()
        for announcement in announcements:
            logs.append({
                'timestamp': announcement.created_at,
                'user': announcement.author.username if announcement.author else 'System',
                'action': f'Posted announcement: "{announcement.title}"',
                'type': 'announcement',
                'details': f'Announcement ID: {announcement.id}'
            })
        
        # Get recent student approvals
        approved_students = User.query.filter_by(role='student', is_approved=True).order_by(User.created_at.desc()).limit(10).all()
        for student in approved_students:
            logs.append({
                'timestamp': student.created_at,
                'user': 'System',
                'action': f'Student approved: "{student.username}"',
                'type': 'student',
                'details': f'Student ID: {student.id}'
            })
        
        # Sort by timestamp (newest first)
        logs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return render_template('admin/system_logs.html', logs=logs[:100])
        
    except Exception as e:
        app.logger.error(f'System logs error: {e}')
        flash(f'Error loading system logs: {str(e)}', 'error')
        return redirect(url_for('admin_dashboard'))

# ============================================================================
# ROUTES - BACKUP AND RESTORE
# ============================================================================

@app.route('/admin/backup-restore')
@login_required
@super_admin_required
def backup_restore():
    """Backup and restore management page"""
    # Get all backups
    backups = Backup.query.order_by(Backup.backup_date.desc()).all()
    return render_template('admin/backup_restore.html', backups=backups)

@app.route('/admin/backup/create', methods=['POST'])
@login_required
@super_admin_required
def create_backup():
    """Create a full backup of the database"""
    try:
        # Get current timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"backup_{timestamp}.json"
        
        # Collect all data
        backup_data = {
            'backup_info': {
                'created_at': datetime.utcnow().isoformat(),
                'created_by': current_user.username,
                'version': '1.0'
            },
            'data': {
                'users': [],
                'courses': [],
                'notes': [],
                'quizzes': [],
                'assignments': [],
                'enrollments': [],
                'announcements': []
            }
        }
        
        # Get all students (exclude admins)
        students = User.query.filter_by(role='student').all()
        for student in students:
            student_data = {
                'id': student.id,
                'username': student.username,
                'email': student.email,
                'role': student.role,
                'is_approved': student.is_approved,
                'is_suspended': student.is_suspended,
                'phone': student.phone,
                'dob': student.dob.isoformat() if student.dob else None,
                'created_at': student.created_at.isoformat() if student.created_at else None,
                'profile_picture': student.profile_picture,
                'dark_mode': student.dark_mode
            }
            backup_data['data']['users'].append(student_data)
        
        # Get all courses
        courses = Course.query.all()
        for course in courses:
            course_data = {
                'id': course.id,
                'name': course.name,
                'description': course.description,
                'code': course.code,
                'created_at': course.created_at.isoformat() if course.created_at else None
            }
            backup_data['data']['courses'].append(course_data)
        
        # Get all notes
        notes = Note.query.all()
        for note in notes:
            note_data = {
                'id': note.id,
                'title': note.title,
                'content': note.content,
                'course_id': note.course_id,
                'tag_id': note.tag_id,
                'author_id': note.author_id,
                'file_path': note.file_path,
                'file_name': note.file_name,
                'created_at': note.created_at.isoformat() if note.created_at else None
            }
            backup_data['data']['notes'].append(note_data)
        
        # Get all quiz groups
        quizzes = QuizGroup.query.all()
        for quiz in quizzes:
            quiz_data = {
                'id': quiz.id,
                'title': quiz.title,
                'description': quiz.description,
                'course_id': quiz.course_id,
                'time_limit': quiz.time_limit,
                'created_at': quiz.created_at.isoformat() if quiz.created_at else None
            }
            backup_data['data']['quizzes'].append(quiz_data)
        
        # Get all assignments
        assignments = Assignment.query.all()
        for assignment in assignments:
            assignment_data = {
                'id': assignment.id,
                'title': assignment.title,
                'description': assignment.description,
                'course_id': assignment.course_id,
                'due_date': assignment.due_date.isoformat() if assignment.due_date else None,
                'max_score': assignment.max_score,
                'created_at': assignment.created_at.isoformat() if assignment.created_at else None
            }
            backup_data['data']['assignments'].append(assignment_data)
        
        # Get all enrollments
        enrollments = CourseEnrollment.query.all()
        for enrollment in enrollments:
            enrollment_data = {
                'id': enrollment.id,
                'student_id': enrollment.student_id,
                'course_id': enrollment.course_id,
                'status': enrollment.status,
                'requested_at': enrollment.requested_at.isoformat() if enrollment.requested_at else None,
                'approved_at': enrollment.approved_at.isoformat() if enrollment.approved_at else None,
                'rejected_at': enrollment.rejected_at.isoformat() if enrollment.rejected_at else None,
                'rejection_reason': enrollment.rejection_reason
            }
            backup_data['data']['enrollments'].append(enrollment_data)
        
        # Get all announcements
        announcements = Announcement.query.all()
        for announcement in announcements:
            announcement_data = {
                'id': announcement.id,
                'title': announcement.title,
                'content': announcement.content,
                'course_id': announcement.course_id,
                'is_pinned': announcement.is_pinned,
                'created_at': announcement.created_at.isoformat() if announcement.created_at else None,
                'author_id': announcement.author_id
            }
            backup_data['data']['announcements'].append(announcement_data)
        
        # Save backup to database
        backup_file = f"/tmp/{filename}"
        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)
        
        # Save backup record to database
        total_records = (
            len(backup_data['data']['users']) +
            len(backup_data['data']['courses']) +
            len(backup_data['data']['notes']) +
            len(backup_data['data']['quizzes']) +
            len(backup_data['data']['assignments']) +
            len(backup_data['data']['enrollments']) +
            len(backup_data['data']['announcements'])
        )
        
        backup = Backup(
            filename=filename,
            file_path=backup_file,
            description=f"Backup created by {current_user.username}",
            size=f"{os.path.getsize(backup_file) / 1024:.2f} KB",
            record_count=total_records,
            created_by=current_user.username
        )
        db.session.add(backup)
        db.session.commit()
        
        flash(f'✅ Backup "{filename}" created successfully! ({total_records} records)', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating backup: {str(e)}', 'error')
        app.logger.error(f'Backup error: {e}')
    
    return redirect(url_for('backup_restore'))

@app.route('/admin/backup/download/<int:backup_id>')
@login_required
@super_admin_required
def download_backup(backup_id):
    """Download a backup file"""
    backup = Backup.query.get_or_404(backup_id)
    
    try:
        if os.path.exists(backup.file_path):
            return send_from_directory(
                os.path.dirname(backup.file_path),
                os.path.basename(backup.file_path),
                as_attachment=True,
                download_name=backup.filename
            )
        else:
            flash('Backup file not found.', 'error')
    except Exception as e:
        flash(f'Error downloading backup: {str(e)}', 'error')
    
    return redirect(url_for('backup_restore'))

@app.route('/admin/backup/restore/<int:backup_id>', methods=['POST'])
@login_required
@super_admin_required
def restore_backup(backup_id):
    """Restore from a backup file"""
    backup = Backup.query.get_or_404(backup_id)
    
    try:
        if not os.path.exists(backup.file_path):
            flash('Backup file not found.', 'error')
            return redirect(url_for('backup_restore'))
        
        with open(backup.file_path, 'r') as f:
            backup_data = json.load(f)
        
        data = backup_data.get('data', {})
        
        # Delete existing student data (keep admins)
        # Delete notifications first (foreign key constraints)
        Notification.query.delete()
        
        # Delete all student-related data
        AssignmentSubmission.query.delete()
        QuizAnswer.query.delete()
        StudentProgress.query.delete()
        RejectionMessage.query.delete()
        CourseEnrollment.query.delete()
        
        # Delete all non-admin users (students)
        User.query.filter_by(role='student').delete()
        
        # Delete content
        Announcement.query.delete()
        Assignment.query.delete()
        QuizQuestion.query.delete()
        QuizGroup.query.delete()
        Note.query.delete()
        Course.query.delete()
        
        # Restore users (students)
        for user_data in data.get('users', []):
            # Check if user already exists (skip if admin)
            existing = User.query.filter_by(username=user_data['username']).first()
            if not existing:
                user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    role=user_data.get('role', 'student'),
                    is_approved=user_data.get('is_approved', False),
                    is_suspended=user_data.get('is_suspended', False),
                    phone=user_data.get('phone'),
                    profile_picture=user_data.get('profile_picture'),
                    dark_mode=user_data.get('dark_mode', False)
                )
                if user_data.get('dob'):
                    user.dob = datetime.fromisoformat(user_data['dob'])
                if user_data.get('created_at'):
                    user.created_at = datetime.fromisoformat(user_data['created_at'])
                db.session.add(user)
        
        db.session.flush()
        
        # Restore courses
        for course_data in data.get('courses', []):
            course = Course(
                name=course_data['name'],
                description=course_data.get('description'),
                code=course_data['code']
            )
            if course_data.get('created_at'):
                course.created_at = datetime.fromisoformat(course_data['created_at'])
            db.session.add(course)
        
        db.session.flush()
        
        # Restore notes
        for note_data in data.get('notes', []):
            note = Note(
                title=note_data['title'],
                content=note_data['content'],
                course_id=note_data.get('course_id'),
                tag_id=note_data.get('tag_id'),
                author_id=note_data.get('author_id'),
                file_path=note_data.get('file_path'),
                file_name=note_data.get('file_name')
            )
            if note_data.get('created_at'):
                note.created_at = datetime.fromisoformat(note_data['created_at'])
            db.session.add(note)
        
        # Restore quizzes
        for quiz_data in data.get('quizzes', []):
            quiz = QuizGroup(
                title=quiz_data['title'],
                description=quiz_data.get('description'),
                course_id=quiz_data.get('course_id'),
                time_limit=quiz_data.get('time_limit', 0)
            )
            if quiz_data.get('created_at'):
                quiz.created_at = datetime.fromisoformat(quiz_data['created_at'])
            db.session.add(quiz)
        
        # Restore assignments
        for assignment_data in data.get('assignments', []):
            assignment = Assignment(
                title=assignment_data['title'],
                description=assignment_data['description'],
                course_id=assignment_data['course_id'],
                max_score=assignment_data.get('max_score', 100)
            )
            if assignment_data.get('due_date'):
                assignment.due_date = datetime.fromisoformat(assignment_data['due_date'])
            if assignment_data.get('created_at'):
                assignment.created_at = datetime.fromisoformat(assignment_data['created_at'])
            db.session.add(assignment)
        
        # Restore enrollments
        for enrollment_data in data.get('enrollments', []):
            enrollment = CourseEnrollment(
                student_id=enrollment_data['student_id'],
                course_id=enrollment_data['course_id'],
                status=enrollment_data.get('status', 'pending'),
                rejection_reason=enrollment_data.get('rejection_reason')
            )
            if enrollment_data.get('requested_at'):
                enrollment.requested_at = datetime.fromisoformat(enrollment_data['requested_at'])
            if enrollment_data.get('approved_at'):
                enrollment.approved_at = datetime.fromisoformat(enrollment_data['approved_at'])
            if enrollment_data.get('rejected_at'):
                enrollment.rejected_at = datetime.fromisoformat(enrollment_data['rejected_at'])
            db.session.add(enrollment)
        
        # Restore announcements
        for announcement_data in data.get('announcements', []):
            announcement = Announcement(
                title=announcement_data['title'],
                content=announcement_data['content'],
                course_id=announcement_data.get('course_id'),
                is_pinned=announcement_data.get('is_pinned', False),
                author_id=announcement_data.get('author_id')
            )
            if announcement_data.get('created_at'):
                announcement.created_at = datetime.fromisoformat(announcement_data['created_at'])
            db.session.add(announcement)
        
        db.session.commit()
        
        flash(f'✅ Backup "{backup.filename}" restored successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error restoring backup: {str(e)}', 'error')
        app.logger.error(f'Restore error: {e}')
    
    return redirect(url_for('backup_restore'))

@app.route('/admin/backup/delete/<int:backup_id>', methods=['POST'])
@login_required
@super_admin_required
def delete_backup(backup_id):
    """Delete a backup file"""
    backup = Backup.query.get_or_404(backup_id)
    
    try:
        # Delete the file if it exists
        if os.path.exists(backup.file_path):
            os.remove(backup.file_path)
        
        db.session.delete(backup)
        db.session.commit()
        
        flash(f'Backup "{backup.filename}" deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting backup: {str(e)}', 'error')
    
    return redirect(url_for('backup_restore'))

# ============================================================================
# ROUTES - STUDENT DIRECTORY
# ============================================================================

@app.route('/admin/student-directory')
@login_required
@admin_required
def student_directory():
    """View all students with profile pictures and course filtering"""
    
    # Get filter parameters
    course_id = request.args.get('course_id', type=int)
    search = request.args.get('search', '')
    sort_by = request.args.get('sort_by', 'name')  # name, date, courses
    
    # Get students based on admin role
    if current_user.is_super_admin():
        # Super admin sees all students
        students = User.query.filter_by(role='student').all()
        available_courses = Course.query.all()
    else:
        # Regular admin only sees students in their courses
        course_ids = [c.id for c in current_user.managed_courses]
        
        # Get student IDs enrolled in admin's courses
        student_ids = db.session.query(CourseEnrollment.student_id).filter(
            CourseEnrollment.course_id.in_(course_ids)
        ).distinct().all()
        student_ids = [s[0] for s in student_ids]
        
        students = User.query.filter(
            User.role == 'student',
            User.id.in_(student_ids)
        ).all() if student_ids else []
        
        available_courses = current_user.managed_courses
    
    # Build student data with enrollment info
    student_data = []
    for student in students:
        # Get all enrollments for this student
        enrollments = CourseEnrollment.query.filter_by(student_id=student.id).all()
        
        # Get enrolled course names
        enrolled_courses = []
        for enrollment in enrollments:
            if enrollment.course:
                enrolled_courses.append({
                    'id': enrollment.course.id,
                    'name': enrollment.course.name,
                    'code': enrollment.course.code,
                    'status': enrollment.status
                })
        
        # Count approved courses
        approved_count = sum(1 for e in enrollments if e.status == 'approved')
        pending_count = sum(1 for e in enrollments if e.status == 'pending')
        
        # Check if student has profile picture
        has_profile_pic = bool(student.profile_picture)
        
        student_data.append({
            'student': student,
            'enrolled_courses': enrolled_courses,
            'approved_count': approved_count,
            'pending_count': pending_count,
            'total_courses': len(enrolled_courses),
            'has_profile_pic': has_profile_pic,
            'status': 'Active' if student.is_approved else 'Pending',
            'is_suspended': student.is_suspended
        })
    
    # Apply course filter
    if course_id:
        filtered_data = []
        for data in student_data:
            if any(c['id'] == course_id for c in data['enrolled_courses']):
                filtered_data.append(data)
        student_data = filtered_data
    
    # Apply search filter
    if search:
        search_lower = search.lower()
        filtered_data = []
        for data in student_data:
            student = data['student']
            if (search_lower in student.username.lower() or 
                search_lower in student.email.lower()):
                filtered_data.append(data)
        student_data = filtered_data
    
    # Apply sorting
    if sort_by == 'name':
        student_data.sort(key=lambda x: x['student'].username.lower())
    elif sort_by == 'date':
        student_data.sort(key=lambda x: x['student'].created_at, reverse=True)
    elif sort_by == 'courses':
        student_data.sort(key=lambda x: x['total_courses'], reverse=True)
    else:  # name default
        student_data.sort(key=lambda x: x['student'].username.lower())
    
    return render_template('admin/student_directory.html',
                         student_data=student_data,
                         courses=available_courses,
                         selected_course=course_id,
                         search_query=search,
                         sort_by=sort_by)

# ============================================================================
# ROUTES - EMAIL TEMPLATES
# ============================================================================

@app.route('/admin/email-templates')
@login_required
@super_admin_required
def email_templates():
    """Manage email templates"""
    templates = EmailTemplate.query.order_by(EmailTemplate.name.asc()).all()
    return render_template('admin/email_templates.html', templates=templates)

@app.route('/admin/email-templates/create', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_email_template():
    """Create a new email template"""
    if request.method == 'POST':
        name = request.form.get('name')
        subject = request.form.get('subject')
        body = request.form.get('body')
        description = request.form.get('description')
        is_active = request.form.get('is_active') == 'on'
        
        if not name or not subject or not body:
            flash('Name, subject, and body are required.', 'error')
            return render_template('admin/create_email_template.html')
        
        # Check if template name already exists
        existing = EmailTemplate.query.filter_by(name=name).first()
        if existing:
            flash(f'Template "{name}" already exists.', 'error')
            return render_template('admin/create_email_template.html')
        
        template = EmailTemplate(
            name=name,
            subject=subject,
            body=body,
            description=description,
            is_active=is_active
        )
        db.session.add(template)
        db.session.commit()
        
        flash(f'Email template "{name}" created successfully!', 'success')
        return redirect(url_for('email_templates'))
    
    return render_template('admin/create_email_template.html')

@app.route('/admin/email-templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_email_template(template_id):
    """Edit an email template"""
    template = EmailTemplate.query.get_or_404(template_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        subject = request.form.get('subject')
        body = request.form.get('body')
        description = request.form.get('description')
        is_active = request.form.get('is_active') == 'on'
        
        if not name or not subject or not body:
            flash('Name, subject, and body are required.', 'error')
            return render_template('admin/edit_email_template.html', template=template)
        
        # Check if another template has this name
        existing = EmailTemplate.query.filter(
            EmailTemplate.name == name,
            EmailTemplate.id != template.id
        ).first()
        if existing:
            flash(f'Template "{name}" already exists.', 'error')
            return render_template('admin/edit_email_template.html', template=template)
        
        template.name = name
        template.subject = subject
        template.body = body
        template.description = description
        template.is_active = is_active
        template.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Email template "{name}" updated successfully!', 'success')
        return redirect(url_for('email_templates'))
    
    return render_template('admin/edit_email_template.html', template=template)

@app.route('/admin/email-templates/<int:template_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_email_template(template_id):
    """Delete an email template"""
    template = EmailTemplate.query.get_or_404(template_id)
    
    try:
        name = template.name
        db.session.delete(template)
        db.session.commit()
        flash(f'Email template "{name}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting template: {str(e)}', 'error')
    
    return redirect(url_for('email_templates'))

@app.route('/admin/email-templates/<int:template_id>/toggle', methods=['POST'])
@login_required
@super_admin_required
def toggle_email_template(template_id):
    """Toggle template active status"""
    template = EmailTemplate.query.get_or_404(template_id)
    
    template.is_active = not template.is_active
    db.session.commit()
    
    status = 'activated' if template.is_active else 'deactivated'
    flash(f'Template "{template.name}" {status}.', 'success')
    return redirect(url_for('email_templates'))

@app.route('/admin/email-templates/<int:template_id>/preview')
@login_required
@super_admin_required
def preview_email_template(template_id):
    """Preview an email template"""
    template = EmailTemplate.query.get_or_404(template_id)
    return render_template('admin/preview_email_template.html', template=template)

# ============================================================================
# ROUTES - STUDENT PROGRESS
# ============================================================================

@app.route('/student/progress')
@login_required
def my_progress():
    """Student progress tracking"""
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Get enrolled courses
    enrolled_courses = current_user.get_enrolled_courses()
    
    # Calculate progress for each course
    course_progress = []
    total_progress = 0
    completed_notes = []
    
    for course in enrolled_courses:
        progress = course.get_progress_for_student(current_user.id)
        course_progress.append({
            'course': course,
            'progress': progress
        })
        total_progress += progress
        
        # Get completed notes for this course
        notes = Note.query.filter_by(course_id=course.id).all()
        for note in notes:
            progress_entry = StudentProgress.query.filter_by(
                student_id=current_user.id,
                note_id=note.id,
                is_read=True
            ).first()
            if progress_entry:
                completed_notes.append(note)
    
    avg_progress = (total_progress // len(enrolled_courses)) if enrolled_courses else 0
    
    return render_template('student/progress.html', 
                         enrolled_courses=enrolled_courses,
                         course_progress=course_progress,
                         avg_progress=avg_progress,
                         completed_notes=completed_notes,
                         total_notes=Note.query.count())

# ============================================================================
# ROUTES - STUDENT NOTIFICATIONS
# ============================================================================

@app.route('/student/notifications')
@login_required
def student_notifications():
    """View all notifications for student"""
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Get all notifications for the current user
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('student/notifications.html', notifications=notifications)

# ============================================================================
# ROUTES - STUDENT MESSAGES
# ============================================================================

@app.route('/student/messages')
@login_required
def student_messages():
    """Student messages/inbox"""
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    return render_template('student/messages.html')

# ============================================================================
# ROUTES - STUDENT ACHIEVEMENTS
# ============================================================================

@app.route('/student/achievements')
@login_required
def my_achievements():
    """Student achievements and badges"""
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Calculate achievements based on activity
    achievements = []
    
    # Achievement 1: First Quiz
    quiz_count = QuizAnswer.query.filter_by(student_id=current_user.id).count()
    if quiz_count > 0:
        achievements.append({
            'name': 'First Quiz',
            'icon': 'fa-puzzle-piece',
            'description': 'Completed your first quiz',
            'earned': True,
            'date': QuizAnswer.query.filter_by(student_id=current_user.id).first().answered_at if quiz_count > 0 else None
        })
    else:
        achievements.append({
            'name': 'First Quiz',
            'icon': 'fa-puzzle-piece',
            'description': 'Complete your first quiz',
            'earned': False,
            'date': None
        })
    
    # Achievement 2: Perfect Score
    answers = QuizAnswer.query.filter_by(student_id=current_user.id).all()
    if answers:
        correct = sum(1 for a in answers if a.is_correct)
        total = len(answers)
        if total > 0 and (correct / total) * 100 >= 100:
            achievements.append({
                'name': 'Perfect Score',
                'icon': 'fa-star',
                'description': 'Got 100% on a quiz',
                'earned': True,
                'date': answers[-1].answered_at
            })
        else:
            achievements.append({
                'name': 'Perfect Score',
                'icon': 'fa-star',
                'description': 'Get 100% on a quiz',
                'earned': False,
                'date': None
            })
    
    # Achievement 3: Course Master
    enrolled_courses = current_user.get_enrolled_courses()
    completed_courses = 0
    for course in enrolled_courses:
        if course.get_progress_for_student(current_user.id) >= 100:
            completed_courses += 1
    if completed_courses >= 1:
        achievements.append({
            'name': 'Course Master',
            'icon': 'fa-graduation-cap',
            'description': 'Completed a course',
            'earned': True,
            'date': None
        })
    else:
        achievements.append({
            'name': 'Course Master',
            'icon': 'fa-graduation-cap',
            'description': 'Complete all modules in a course',
            'earned': False,
            'date': None
        })
    
    # Achievement 4: Assignment Submitted
    submissions = AssignmentSubmission.query.filter_by(student_id=current_user.id).count()
    if submissions > 0:
        achievements.append({
            'name': 'Assignment Submitted',
            'icon': 'fa-tasks',
            'description': f'Submitted {submissions} assignment(s)',
            'earned': True,
            'date': AssignmentSubmission.query.filter_by(student_id=current_user.id).first().submitted_at
        })
    else:
        achievements.append({
            'name': 'Assignment Submitted',
            'icon': 'fa-tasks',
            'description': 'Submit your first assignment',
            'earned': False,
            'date': None
        })
    
    # Count earned achievements
    earned_count = sum(1 for a in achievements if a['earned'])
    
    return render_template('student/achievements.html', 
                         achievements=achievements,
                         earned_count=earned_count,
                         total_achievements=len(achievements))

# ============================================================================
# ROUTES - STUDENT CALENDAR
# ============================================================================

@app.route('/student/calendar')
@login_required
def course_calendar():
    """Course calendar with upcoming deadlines"""
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    # Get all assignments for enrolled courses
    enrolled_courses = current_user.get_enrolled_courses()
    course_ids = [c.id for c in enrolled_courses]
    
    assignments = Assignment.query.filter(
        Assignment.course_id.in_(course_ids)
    ).order_by(Assignment.due_date.asc()).all()
    
    # Get quiz deadlines (optional)
    quizzes = QuizGroup.query.filter(
        QuizGroup.course_id.in_(course_ids)
    ).all()
    
    return render_template('student/calendar.html', 
                         assignments=assignments,
                         quizzes=quizzes)

# ============================================================================
# NOTIFICATION API ENDPOINT
# ============================================================================

@app.route('/api/notifications')
@login_required
def get_notifications():
    notifications = []
    
    # Get user-specific notifications from database
    user_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(10).all()
    
    for notif in user_notifications:
        notifications.append({
            'id': notif.id,
            'type': notif.type,
            'title': notif.title,
            'message': notif.message,
            'url': notif.link or '#',
            'icon': notif.icon,
            'icon_color': notif.icon_color,
            'created_at': notif.created_at.isoformat(),
            'is_read': notif.is_read
        })
    
    # If user has no notifications, add system notifications based on status
    if not notifications:
        if current_user.is_admin():
            pending_count = User.query.filter_by(role='student', is_approved=False).count()
            if pending_count > 0:
                notifications.append({
                    'id': 'pending_approvals',
                    'type': 'approval',
                    'title': f'{pending_count} student(s) pending approval',
                    'message': 'Click to review and approve student accounts',
                    'url': url_for('manage_students'),
                    'icon': 'fa-users',
                    'icon_color': 'orange',
                    'created_at': datetime.utcnow().isoformat(),
                    'is_read': False
                })
            
            # Check for pending course requests
            pending_enrollments = CourseEnrollment.query.filter_by(status='pending').count()
            if pending_enrollments > 0:
                notifications.append({
                    'id': 'pending_course_requests',
                    'type': 'approval',
                    'title': f'{pending_enrollments} pending course request(s)',
                    'message': 'Students are waiting for course approval',
                    'url': url_for('manage_students'),
                    'icon': 'fa-book-open',
                    'icon_color': 'gold',
                    'created_at': datetime.utcnow().isoformat(),
                    'is_read': False
                })
        else:
            # Student notifications
            if not current_user.is_approved and not current_user.is_suspended:
                notifications.append({
                    'id': 'pending_approval',
                    'type': 'approval',
                    'title': 'Account Pending Approval',
                    'message': 'Your account is waiting for admin approval',
                    'url': url_for('student_pending_approval'),
                    'icon': 'fa-clock',
                    'icon_color': 'orange',
                    'created_at': datetime.utcnow().isoformat(),
                    'is_read': False
                })
            
            if current_user.is_suspended:
                notifications.append({
                    'id': 'account_suspended',
                    'type': 'suspension',
                    'title': 'Account Suspended',
                    'message': f'Your account has been suspended. Reason: {current_user.suspension_reason or "No reason provided."}',
                    'url': '#',
                    'icon': 'fa-ban',
                    'icon_color': 'red',
                    'created_at': datetime.utcnow().isoformat(),
                    'is_read': False
                })
    
    return jsonify(notifications)

@app.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_notifications_read():
    """Mark all notifications as read for the current user"""
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).all()
    
    for notif in notifications:
        notif.is_read = True
    
    db.session.commit()
    
    return jsonify({'success': True, 'count': len(notifications)})

@app.route('/api/notifications/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_single_notification_read(notification_id):
    """Mark a single notification as read"""
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    notification.is_read = True
    db.session.commit()
    
    return jsonify({'success': True})

# ============================================================================
# ADMIN DASHBOARD API ENDPOINT
# ============================================================================

@app.route('/admin/api/dashboard-data')
@login_required
@admin_required
def admin_dashboard_api():
    """API endpoint for admin dashboard data"""
    try:
        # Get all data
        data = {
            'upcoming_deadlines': get_admin_upcoming_deadlines(current_user),
            'quiz_results': get_admin_quiz_results(current_user),
            'announcements': get_admin_announcements_with_pins(current_user),
            'notices': get_admin_notices_with_ctas(current_user),
            'activity': get_admin_enhanced_activity(current_user),
            'progress_visualization': get_student_progress_visualization(current_user)
        }
        
        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        app.logger.error(f'Dashboard API error: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# HEALTH CHECK FOR RENDER
# ============================================================================

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'database': 'connected'
    })

# ============================================================================
# MAINTENANCE MODE MIDDLEWARE
# ============================================================================

@app.before_request
def check_maintenance_mode():
    """Check if maintenance mode is enabled and redirect if needed"""
    # Skip maintenance check for these endpoints
    public_endpoints = ['static', 'login', 'logout', 'health', 'maintenance']
    
    # Skip if user is admin or super_admin
    if current_user and current_user.is_authenticated and current_user.is_admin():
        return None
    
    # Skip if the request is for a public endpoint
    if request.endpoint in public_endpoints:
        return None
    
    # Check if maintenance mode is enabled
    maintenance_mode = get_bool_setting('maintenance_mode', False)
    
    if maintenance_mode:
        # If it's an API request, return JSON
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Maintenance mode is enabled',
                'status': 'maintenance',
                'message': 'The system is currently under maintenance. Please try again later.'
            }), 503
        
        # For regular requests, show maintenance page
        return render_template('maintenance.html'), 503
    
    return None

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500

# ============================================================================
# INITIALIZE DATABASE AND CREATE ADMIN
# ============================================================================

with app.app_context():
    db.create_all()
    ensure_columns()
    init_default_settings()
    create_initial_admin()

# ============================================================================
# RUN THE APPLICATION
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    print("=" * 60)
    print("🚀 Awwalu Devs - Learning Management System")
    print("=" * 60)
    print("📚 Default Admin Credentials:")
    print("   Username: admin")
    print("   Password: admin123")
    print("⚠️  Please change the default password immediately!")
    print("=" * 60)
    print(f"🔧 Running on port: {port}")
    print(f"🐛 Debug mode: {debug}")
    print("=" * 60)
    
    app.run(debug=debug, host='0.0.0.0', port=port)