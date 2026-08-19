# app.py - Awwalu Devs Learning Management System
# Complete backend with all features in one file

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
# DATABASE CONFIGURATION
# ============================================================================

# Check if the app is running on Render
if os.environ.get('RENDER'):
    # PostgreSQL on Render
    database_url = os.environ.get('DATABASE_URL')
    if database_url and 'sslmode' not in database_url:
        database_url += '?sslmode=require'
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
else:
    # SQLite locally
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///../database/awwaludevs.db')

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
# DATABASE MODELS
# ============================================================================

# Association Tables
admin_course = db.Table('admin_course',
    db.Column('admin_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'))
)

student_course = db.Table('student_course',
    db.Column('student_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'))
)

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='student')
    is_approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    dark_mode = db.Column(db.Boolean, default=False)
    
    managed_courses = db.relationship('Course', secondary=admin_course, backref='admins')
    enrolled_courses = db.relationship('Course', secondary=student_course, backref='students')
    notes_read = db.relationship('StudentProgress', backref='student', lazy=True)
    quiz_answers = db.relationship('QuizAnswer', backref='student', lazy=True)
    submissions = db.relationship('AssignmentSubmission', backref='student', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_courses(self):
        if self.role == 'super_admin':
            return Course.query.all()
        elif self.role == 'admin':
            return self.managed_courses
        else:
            return self.enrolled_courses
    
    def is_admin(self):
        return self.role in ['admin', 'super_admin']
    
    def is_super_admin(self):
        return self.role == 'super_admin'

class Announcement(db.Model):
    __tablename__ = 'announcement'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    author = db.relationship('User', backref='announcements')

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

class Tag(db.Model):
    __tablename__ = 'tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    notes = db.relationship('Note', backref='tag', lazy=True)

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
    
    def is_new(self):
        return (datetime.utcnow() - self.created_at).days <= 7

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
    )

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
    )

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

class RejectionMessage(db.Model):
    __tablename__ = 'rejection_message'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('User', backref='rejections')
    course = db.relationship('Course', backref='rejections')

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
    except Exception as e:
        print(f"⚠️ Error creating admin: {e}")

# ============================================================================
# USER LOADER
# ============================================================================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============================================================================
# CONTEXT PROCESSORS
# ============================================================================

@app.context_processor
def inject_user():
    return {
        'current_user': current_user,
        'now': datetime.utcnow(),
        'get_courses': lambda: current_user.get_courses() if current_user.is_authenticated else []
    }

# ============================================================================
# ROUTES - AUTHENTICATION
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if not user.is_approved and user.role == 'student':
                flash('Your account is pending approval. Please wait for an admin to approve your account.', 'warning')
                return render_template('login.html')
            
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            
            if user.is_admin():
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('student_dashboard'))
        else:
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
        
        for course_id in selected_courses:
            course = Course.query.get(course_id)
            if course:
                student.enrolled_courses.append(course)
        
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
    return redirect(url_for('student_dashboard'))

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    courses = current_user.enrolled_courses
    progress_data = []
    for course in courses:
        progress_data.append({
            'course': course,
            'progress': course.get_progress_for_student(current_user.id)
        })
    
    quiz_results = []
    quiz_answers = QuizAnswer.query.filter_by(student_id=current_user.id).all()
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
    
    announcements = Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).limit(5).all()
    
    return render_template('student_dashboard.html', 
                         courses=courses, 
                         progress_data=progress_data,
                         quiz_results=quiz_results[:5],
                         announcements=announcements)

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    total_students = User.query.filter_by(role='student').count()
    pending_approvals = User.query.filter_by(role='student', is_approved=False).count()
    pending = User.query.filter_by(role='student', is_approved=False).all()
    
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
    
    recent_notes = Note.query.order_by(Note.created_at.desc()).limit(5).all()
    recent_quizzes = QuizGroup.query.order_by(QuizGroup.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_students=total_students,
                         pending_approvals=pending_approvals,
                         pending=pending,
                         total_courses=total_courses,
                         total_notes=total_notes,
                         total_quizzes=total_quizzes,
                         total_assignments=total_assignments,
                         courses=courses,
                         recent_notes=recent_notes,
                         recent_quizzes=recent_quizzes,
                         admin_count=admin_count,
                         tag_count=tag_count)

# ============================================================================
# ROUTES - COURSE MANAGEMENT (Super Admin)
# ============================================================================

@app.route('/admin/courses')
@login_required
@super_admin_required
def manage_courses():
    courses = Course.query.all()
    return render_template('admin/manage_courses.html', courses=courses)

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
        return redirect(url_for('manage_courses'))
    
    return render_template('admin/create_course.html')

@app.route('/admin/courses/<int:course_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    flash(f'Course {course.name} deleted successfully.', 'success')
    return redirect(url_for('manage_courses'))

# ============================================================================
# ROUTES - ANNOUNCEMENTS
# ============================================================================

@app.route('/admin/announcements')
@login_required
@admin_required
def manage_announcements():
    announcements = Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).all()
    return render_template('admin/manage_announcements.html', announcements=announcements)

@app.route('/admin/announcements/create', methods=['GET', 'POST'])
@login_required
@admin_required
def post_announcement():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        is_pinned = request.form.get('is_pinned') == 'on'
        
        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('admin/post_announcement.html')
        
        announcement = Announcement(
            title=title,
            content=content,
            is_pinned=is_pinned,
            author_id=current_user.id
        )
        db.session.add(announcement)
        db.session.commit()
        
        flash('Announcement posted successfully!', 'success')
        return redirect(url_for('manage_announcements'))
    
    return render_template('admin/post_announcement.html')

@app.route('/admin/announcements/<int:announcement_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
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
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        is_pinned = request.form.get('is_pinned') == 'on'
        
        if not title or not content:
            flash('Title and content are required.', 'error')
            return render_template('admin/edit_announcement.html', announcement=announcement)
        
        announcement.title = title
        announcement.content = content
        announcement.is_pinned = is_pinned
        announcement.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Announcement updated successfully!', 'success')
        return redirect(url_for('manage_announcements'))
    
    return render_template('admin/edit_announcement.html', announcement=announcement)

@app.route('/student/announcements')
@login_required
def student_announcements():
    announcements = Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc()).all()
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
        courses = ', '.join([c.name for c in student.enrolled_courses])
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
# ROUTES - STUDENT MANAGEMENT (Admin)
# ============================================================================

@app.route('/admin/students')
@login_required
@admin_required
def manage_students():
    if current_user.is_super_admin():
        students = User.query.filter_by(role='student').all()
        pending = User.query.filter_by(role='student', is_approved=False).all()
    else:
        course_ids = [c.id for c in current_user.managed_courses]
        students = User.query.filter(
            User.role == 'student',
            User.enrolled_courses.any(Course.id.in_(course_ids))
        ).all()
        pending = User.query.filter(
            User.role == 'student',
            User.is_approved == False,
            User.enrolled_courses.any(Course.id.in_(course_ids))
        ).all()
    
    courses = Course.query.all()
    return render_template('admin/manage_students.html', students=students, pending=pending, courses=courses)

@app.route('/admin/students/<int:student_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_student(student_id):
    student = User.query.get_or_404(student_id)
    
    if not current_user.is_super_admin():
        student_course_ids = [c.id for c in student.enrolled_courses]
        admin_course_ids = [c.id for c in current_user.managed_courses]
        if not any(cid in admin_course_ids for cid in student_course_ids):
            flash('You do not have permission to approve this student.', 'error')
            return redirect(url_for('manage_students'))
    
    student.is_approved = True
    db.session.commit()
    flash(f'{student.username} has been approved.', 'success')
    return redirect(url_for('manage_students'))

@app.route('/admin/students/<int:student_id>/reject', methods=['GET', 'POST'])
@login_required
@admin_required
def reject_student(student_id):
    student = User.query.get_or_404(student_id)
    courses = student.enrolled_courses
    
    if request.method == 'POST':
        course_id = request.form.get('course_id')
        message = request.form.get('message')
        
        if not course_id or not message:
            flash('Please select a course and provide a reason.', 'error')
            return render_template('admin/reject_user.html', student=student, courses=courses)
        
        course = Course.query.get(course_id)
        if course in student.enrolled_courses:
            student.enrolled_courses.remove(course)
        
        rejection = RejectionMessage(
            student_id=student.id,
            course_id=course_id,
            message=message
        )
        db.session.add(rejection)
        
        if len(student.enrolled_courses) == 0:
            student.is_approved = False
        
        db.session.commit()
        flash(f'Student {student.username} rejected from course.', 'warning')
        return redirect(url_for('manage_students'))
    
    return render_template('admin/reject_user.html', student=student, courses=courses)

@app.route('/admin/students/<int:student_id>/unreject/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def unreject_student(student_id, course_id):
    student = User.query.get_or_404(student_id)
    course = Course.query.get_or_404(course_id)
    
    if course not in student.enrolled_courses:
        student.enrolled_courses.append(course)
        student.is_approved = True
        
        RejectionMessage.query.filter_by(
            student_id=student.id,
            course_id=course_id
        ).delete()
        
        db.session.commit()
        flash(f'{student.username} has been restored to {course.name}.', 'success')
    
    return redirect(url_for('manage_students'))

@app.route('/admin/students/bulk-approve', methods=['POST'])
@login_required
@admin_required
def bulk_approve_students():
    student_ids = request.form.getlist('student_ids')
    
    if not student_ids:
        flash('No students selected.', 'warning')
        return redirect(url_for('manage_students'))
    
    for sid in student_ids:
        student = User.query.get(sid)
        if student:
            student.is_approved = True
    
    db.session.commit()
    flash(f'{len(student_ids)} students approved successfully.', 'success')
    return redirect(url_for('manage_students'))

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
        
        flash(f'Note "{title}" posted successfully!', 'success')
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
        flash(f'Note "{title}" updated successfully!', 'success')
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
    if current_user.is_super_admin():
        assignments = Assignment.query.all()
    else:
        course_ids = [c.id for c in current_user.managed_courses]
        assignments = Assignment.query.filter(Assignment.course_id.in_(course_ids)).all()
    
    return render_template('admin/manage_assignments.html', assignments=assignments)

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
        
        flash(f'Assignment "{title}" created successfully!', 'success')
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
# ROUTES - STUDENT COURSE VIEWING
# ============================================================================

@app.route('/student/courses')
@login_required
def student_courses():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    courses = current_user.enrolled_courses
    available_courses = Course.query.filter(~Course.id.in_([c.id for c in courses])).all()
    
    return render_template('student_courses.html', courses=courses, available_courses=available_courses)

@app.route('/student/courses/<int:course_id>')
@login_required
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    if course not in current_user.enrolled_courses:
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
    
    if course in current_user.enrolled_courses:
        flash('You are already enrolled in this course.', 'info')
        return redirect(url_for('student_courses'))
    
    rejection = RejectionMessage.query.filter_by(
        student_id=current_user.id,
        course_id=course_id
    ).first()
    
    if rejection:
        flash(f'Your request for this course was previously rejected. Please contact admin.', 'error')
        return redirect(url_for('student_courses'))
    
    current_user.enrolled_courses.append(course)
    current_user.is_approved = False
    db.session.commit()
    
    flash(f'Request sent for {course.name}. Waiting for admin approval.', 'success')
    return redirect(url_for('student_courses'))

@app.route('/note/<int:note_id>')
@login_required
def view_note(note_id):
    note = Note.query.get_or_404(note_id)
    
    if not current_user.is_admin():
        if note.course not in current_user.enrolled_courses:
            flash('You do not have access to this note.', 'error')
            return redirect(url_for('student_dashboard'))
    
    return render_template('view_note.html', note=note)

@app.route('/student/notes/<int:note_id>/toggle-read', methods=['POST'])
@login_required
def toggle_note_read(note_id):
    note = Note.query.get_or_404(note_id)
    
    if current_user.is_admin():
        return jsonify({'error': 'Admins cannot track progress'}), 403
    
    if note.course not in current_user.enrolled_courses:
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
# ROUTES - STUDENT QUIZZES
# ============================================================================

@app.route('/student/quizzes')
@login_required
def student_quizzes():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    course_ids = [c.id for c in current_user.enrolled_courses]
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
    
    if quiz.course not in current_user.enrolled_courses:
        flash('You are not enrolled in this course.', 'error')
        return redirect(url_for('student_quizzes'))
    
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
    
    if quiz.course not in current_user.enrolled_courses:
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
# ROUTES - STUDENT ASSIGNMENTS
# ============================================================================

@app.route('/student/assignments')
@login_required
def student_assignments():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    course_ids = [c.id for c in current_user.enrolled_courses]
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
    
    if assignment.course not in current_user.enrolled_courses:
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
# ROUTES - LEADERBOARD
# ============================================================================

@app.route('/leaderboard')
@login_required
def leaderboard():
    if current_user.is_admin():
        flash('Leaderboard is for students.', 'info')
        return redirect(url_for('admin_dashboard'))
    
    students = User.query.filter_by(role='student', is_approved=True).all()
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
            'course_count': len(student.enrolled_courses)
        })
    
    student_scores.sort(key=lambda x: x['score'], reverse=True)
    
    return render_template('leaderboard.html', student_scores=student_scores)

# ============================================================================
# ROUTES - PROFILE
# ============================================================================

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html')

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

@app.route('/admin/recent-activity')
@login_required
@admin_required
def recent_activity():
    recent_notes = Note.query.order_by(Note.created_at.desc()).limit(20).all()
    recent_quizzes = QuizGroup.query.order_by(QuizGroup.created_at.desc()).limit(20).all()
    recent_assignments = Assignment.query.order_by(Assignment.created_at.desc()).limit(20).all()
    
    activities = []
    
    for note in recent_notes:
        activities.append({
            'type': 'note',
            'title': note.title,
            'course': note.course.name,
            'created_at': note.created_at,
            'url': url_for('edit_note', note_id=note.id),
            'icon': 'fa-file-alt',
            'color': 'blue'
        })
    
    for quiz in recent_quizzes:
        activities.append({
            'type': 'quiz',
            'title': quiz.title,
            'course': quiz.course.name,
            'created_at': quiz.created_at,
            'url': url_for('edit_quiz_group', quiz_id=quiz.id),
            'icon': 'fa-puzzle-piece',
            'color': 'purple'
        })
    
    for assignment in recent_assignments:
        activities.append({
            'type': 'assignment',
            'title': assignment.title,
            'course': assignment.course.name,
            'created_at': assignment.created_at,
            'url': url_for('edit_assignment', assignment_id=assignment.id),
            'icon': 'fa-tasks',
            'color': 'orange'
        })
    
    activities.sort(key=lambda x: x['created_at'], reverse=True)
    
    return render_template('admin/recent_activity.html', activities=activities[:50])

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
# NOTIFICATION API ENDPOINT
# ============================================================================

@app.route('/api/notifications')
@login_required
def get_notifications():
    notifications = []
    
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
        
        recent_notes = Note.query.filter(Note.created_at > datetime.utcnow() - timedelta(days=7)).count()
        if recent_notes > 0:
            notifications.append({
                'id': 'recent_notes',
                'type': 'note',
                'title': f'{recent_notes} new note(s) added',
                'message': 'Check out the latest course notes',
                'url': url_for('manage_notes'),
                'icon': 'fa-file-alt',
                'icon_color': 'blue',
                'created_at': datetime.utcnow().isoformat(),
                'is_read': False
            })
    else:
        new_announcements = Announcement.query.filter(Announcement.created_at > datetime.utcnow() - timedelta(days=7)).count()
        if new_announcements > 0:
            notifications.append({
                'id': 'new_announcements',
                'type': 'announcement',
                'title': f'{new_announcements} new announcement(s)',
                'message': 'Check out the latest updates from your instructors',
                'url': url_for('student_announcements'),
                'icon': 'fa-bullhorn',
                'icon_color': 'purple',
                'created_at': datetime.utcnow().isoformat(),
                'is_read': False
            })
        
        enrolled_course_ids = [c.id for c in current_user.enrolled_courses]
        if enrolled_course_ids:
            unread_notes = StudentProgress.query.filter(
                StudentProgress.student_id == current_user.id,
                StudentProgress.is_read == False
            ).count()
            if unread_notes > 0:
                notifications.append({
                    'id': 'unread_notes',
                    'type': 'note',
                    'title': f'{unread_notes} unread note(s)',
                    'message': 'You have notes to catch up on',
                    'url': url_for('student_courses'),
                    'icon': 'fa-book',
                    'icon_color': 'green',
                    'created_at': datetime.utcnow().isoformat(),
                    'is_read': False
                })
    
    return jsonify(notifications)

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