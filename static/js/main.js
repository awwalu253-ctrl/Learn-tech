// ============================================================================
// Awwalu Devs - Main JavaScript
// ============================================================================

// ============================================================================
// API CONFIGURATION - Everything on Render (relative paths)
// ============================================================================

// No need for absolute URL - everything is served from the same domain on Render
const API_BASE_URL = '';

// Helper function for API calls
async function apiCall(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const defaultOptions = {
        credentials: 'include',  // Important for cookies/sessions
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, mergedOptions);
        return response;
    } catch (error) {
        console.error('API Error:', error);
        showFlash('Network error. Please try again.', 'error');
        throw error;
    }
}

// ============================================================================
// DOM READY
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    
    // ========================================================================
    // Navbar Toggle (Mobile)
    // ========================================================================
    
    const navbarToggle = document.getElementById('navbarToggle');
    const navbarMenu = document.getElementById('navbarMenu');
    
    if (navbarToggle && navbarMenu) {
        navbarToggle.addEventListener('click', function() {
            navbarMenu.classList.toggle('open');
            const icon = navbarToggle.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-bars');
                icon.classList.toggle('fa-times');
            }
        });
        
        // Close menu when clicking a link (mobile)
        navbarMenu.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                navbarMenu.classList.remove('open');
                const icon = navbarToggle.querySelector('i');
                if (icon) {
                    icon.classList.add('fa-bars');
                    icon.classList.remove('fa-times');
                }
            });
        });
    }
    
    // ========================================================================
    // Navbar Scroll Effect
    // ========================================================================
    
    const navbar = document.getElementById('navbar');
    if (navbar) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 10) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });
    }
    
    // ========================================================================
    // Flash Messages Auto-Dismiss
    // ========================================================================
    
    const flashMessages = document.querySelectorAll('.flash-message');
    flashMessages.forEach((msg, index) => {
        setTimeout(() => {
            msg.style.opacity = '0';
            msg.style.transform = 'translateX(20px)';
            setTimeout(() => {
                if (msg.parentElement) msg.remove();
            }, 400);
        }, 4000 + (index * 300));
    });
    
    // ========================================================================
    // Dark Mode Toggle
    // ========================================================================
    
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', function() {
            fetch('/profile/toggle-dark-mode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include'
            })
            .then(response => response.json())
            .then(data => {
                if (data.dark_mode) {
                    document.documentElement.setAttribute('data-theme', 'dark');
                } else {
                    document.documentElement.setAttribute('data-theme', 'light');
                }
            })
            .catch(error => {
                console.error('Error toggling dark mode:', error);
            });
        });
    }
    
    // ========================================================================
    // Confirm Delete
    // ========================================================================
    
    document.querySelectorAll('.confirm-delete').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            if (confirm('Are you sure you want to delete this item? This action cannot be undone.')) {
                this.closest('form').submit();
            }
        });
    });
    
    // ========================================================================
    // File Input Preview
    // ========================================================================
    
    document.querySelectorAll('input[type="file"]').forEach(input => {
        input.addEventListener('change', function() {
            const fileInput = this;
            const fileName = fileInput.files[0]?.name || 'No file chosen';
            
            // Find the label associated with this input
            const label = document.querySelector(`label[for="${fileInput.id}"]`);
            if (label) {
                const fileNameSpan = label.querySelector('.file-name');
                if (fileNameSpan) {
                    fileNameSpan.textContent = fileName;
                } else {
                    // Update the label text
                    const textNode = label.childNodes[0];
                    if (textNode) {
                        label.innerHTML = label.innerHTML.replace(/Choose a file.*/, 'Choose a file');
                        const span = document.createElement('span');
                        span.className = 'file-name';
                        span.textContent = fileName;
                        label.appendChild(span);
                    }
                }
            }
        });
    });
    
    // ========================================================================
    // Quiz Form - Auto Submit Check
    // ========================================================================
    
    const quizForms = document.querySelectorAll('.quiz-form');
    quizForms.forEach(form => {
        const questions = form.querySelectorAll('.quiz-question');
        const submitBtn = form.querySelector('.btn-submit-quiz');
        
        if (questions.length > 0 && submitBtn) {
            const checkAllAnswered = () => {
                let allAnswered = true;
                let answeredCount = 0;
                
                questions.forEach(q => {
                    const selected = q.querySelector('input[type="radio"]:checked');
                    if (selected) {
                        answeredCount++;
                    } else {
                        allAnswered = false;
                    }
                });
                
                const remaining = questions.length - answeredCount;
                
                if (allAnswered) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = '✅ Submit Quiz';
                    submitBtn.classList.remove('btn-disabled');
                } else {
                    submitBtn.disabled = true;
                    submitBtn.textContent = `📝 ${remaining} question(s) remaining`;
                    submitBtn.classList.add('btn-disabled');
                }
            };
            
            questions.forEach(q => {
                q.querySelectorAll('input[type="radio"]').forEach(radio => {
                    radio.addEventListener('change', checkAllAnswered);
                });
            });
            
            // Initial check
            checkAllAnswered();
        }
    });
    
    // ========================================================================
    // Search / Filter
    // ========================================================================
    
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.toLowerCase().trim();
            const items = document.querySelectorAll('.searchable-item');
            
            items.forEach(item => {
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(query) ? '' : 'none';
            });
        });
    }
    
    // ========================================================================
    // Tab Switching
    // ========================================================================
    
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const target = this.dataset.target;
            
            // Remove active from all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab-btn').forEach(b => {
                b.classList.remove('active');
            });
            
            // Activate the selected tab
            const targetElement = document.getElementById(target);
            if (targetElement) {
                targetElement.classList.add('active');
            }
            this.classList.add('active');
        });
    });
    
    // ========================================================================
    // Course Progress Animation
    // ========================================================================
    
    const progressBars = document.querySelectorAll('.progress-track .fill');
    progressBars.forEach(bar => {
        const targetWidth = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.width = targetWidth;
        }, 300);
    });
    
    // ========================================================================
    // Notification Bell (if present)
    // ========================================================================
    
    const notificationBtn = document.getElementById('notificationBtn');
    const notificationDropdown = document.getElementById('notificationDropdown');
    
    if (notificationBtn && notificationDropdown) {
        // Load notifications on click
        notificationBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            
            // Toggle dropdown
            notificationDropdown.classList.toggle('open');
            
            // Load notifications if not loaded
            if (notificationDropdown.classList.contains('open')) {
                loadNotifications();
            }
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!notificationBtn.contains(e.target) && !notificationDropdown.contains(e.target)) {
                notificationDropdown.classList.remove('open');
            }
        });
    }
    
    // ========================================================================
    // Load Notifications from API
    // ========================================================================
    
    async function loadNotifications() {
        try {
            const response = await apiCall('/api/notifications');
            if (response.ok) {
                const notifications = await response.json();
                renderNotifications(notifications);
            }
        } catch (error) {
            console.error('Error loading notifications:', error);
        }
    }
    
    function renderNotifications(notifications) {
        const dropdown = document.getElementById('notificationDropdown');
        if (!dropdown) return;
        
        const list = dropdown.querySelector('.notification-list');
        if (!list) return;
        
        if (!notifications || notifications.length === 0) {
            list.innerHTML = `
                <div class="notification-empty">
                    <i class="fas fa-bell-slash"></i>
                    <p>No notifications</p>
                </div>
            `;
            return;
        }
        
        list.innerHTML = notifications.map(notif => `
            <div class="notification-item unread">
                <div class="notif-icon ${notif.icon_color || 'blue'}">
                    <i class="fas ${notif.icon || 'fa-bell'}"></i>
                </div>
                <div class="notif-content">
                    <div class="notif-title">${notif.title}</div>
                    <div class="notif-meta">
                        <span>${notif.message}</span>
                        <span class="notif-badge unread-badge">New</span>
                    </div>
                </div>
                <div class="notif-time">${formatTime(notif.created_at)}</div>
            </div>
        `).join('');
    }
    
    function formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;
        
        if (diff < 60000) return 'Just now';
        if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
        if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
        return date.toLocaleDateString();
    }
    
    // ========================================================================
    // Login Form Handler
    // ========================================================================
    
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const username = document.getElementById('username')?.value;
            const password = document.getElementById('password')?.value;
            
            if (!username || !password) {
                showFlash('Please fill in all fields.', 'error');
                return;
            }
            
            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    credentials: 'include',
                    body: JSON.stringify({ username, password })
                });
                
                if (response.redirected) {
                    window.location.href = response.url;
                } else {
                    const data = await response.json();
                    if (data.error) {
                        showFlash(data.error, 'error');
                    } else if (data.redirect) {
                        window.location.href = data.redirect;
                    } else {
                        // If login successful but no redirect, reload page
                        window.location.reload();
                    }
                }
            } catch (error) {
                console.error('Login error:', error);
                showFlash('Login failed. Please try again.', 'error');
            }
        });
    }
    
    // ========================================================================
    // Signup Form Handler
    // ========================================================================
    
    const signupForm = document.getElementById('signupForm');
    if (signupForm) {
        signupForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const username = document.getElementById('username')?.value;
            const email = document.getElementById('email')?.value;
            const password = document.getElementById('password')?.value;
            const confirmPassword = document.getElementById('confirm_password')?.value;
            
            if (!username || !email || !password || !confirmPassword) {
                showFlash('Please fill in all fields.', 'error');
                return;
            }
            
            if (password !== confirmPassword) {
                showFlash('Passwords do not match.', 'error');
                return;
            }
            
            if (password.length < 6) {
                showFlash('Password must be at least 6 characters.', 'error');
                return;
            }
            
            try {
                const response = await fetch('/signup', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    credentials: 'include',
                    body: JSON.stringify({ 
                        username, 
                        email, 
                        password, 
                        confirm_password: confirmPassword 
                    })
                });
                
                if (response.redirected) {
                    window.location.href = response.url;
                } else {
                    const data = await response.json();
                    if (data.error) {
                        showFlash(data.error, 'error');
                    } else if (data.success) {
                        showFlash(data.message, 'success');
                        window.location.href = '/login';
                    }
                }
            } catch (error) {
                console.error('Signup error:', error);
                showFlash('Signup failed. Please try again.', 'error');
            }
        });
    }
    
    // ========================================================================
    // Logout Handler
    // ========================================================================
    
    const logoutBtn = document.querySelector('.btn-logout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (confirm('Are you sure you want to logout?')) {
                window.location.href = '/logout';
            }
        });
    }
});

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// ============================================================================
// Copy to Clipboard
// ============================================================================

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showFlash('Copied to clipboard!', 'success');
    }).catch(() => {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showFlash('Copied to clipboard!', 'success');
    });
}

// ============================================================================
// Show Flash Message
// ============================================================================

function showFlash(message, type = 'info') {
    // Check if container exists
    let container = document.querySelector('.flash-container');
    
    // Create container if it doesn't exist
    if (!container) {
        container = document.createElement('div');
        container.className = 'flash-container';
        document.body.prepend(container);
    }
    
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };
    
    const icon = icons[type] || icons.info;
    
    const flash = document.createElement('div');
    flash.className = `flash-message flash-${type} animate-slide-down`;
    flash.innerHTML = `
        <span class="flash-icon">
            <i class="fas ${icon}"></i>
        </span>
        <span class="flash-content">${message}</span>
        <button class="flash-close" onclick="this.closest('.flash-message').remove()">&times;</button>
    `;
    
    container.appendChild(flash);
    
    // Auto-dismiss after 4 seconds
    setTimeout(() => {
        if (flash.parentElement) {
            flash.style.opacity = '0';
            flash.style.transform = 'translateX(20px)';
            setTimeout(() => {
                if (flash.parentElement) {
                    flash.remove();
                }
            }, 300);
        }
    }, 4000);
}

// ============================================================================
// API Helpers
// ============================================================================

async function apiGet(endpoint) {
    const response = await apiCall(endpoint, { method: 'GET' });
    return response;
}

async function apiPost(endpoint, data) {
    const response = await apiCall(endpoint, {
        method: 'POST',
        body: JSON.stringify(data)
    });
    return response;
}

async function apiPut(endpoint, data) {
    const response = await apiCall(endpoint, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
    return response;
}

async function apiDelete(endpoint) {
    const response = await apiCall(endpoint, { method: 'DELETE' });
    return response;
}

// ============================================================================
// Export API functions globally
// ============================================================================

window.apiCall = apiCall;
window.apiGet = apiGet;
window.apiPost = apiPost;
window.apiPut = apiPut;
window.apiDelete = apiDelete;
window.showFlash = showFlash;
window.copyToClipboard = copyToClipboard;
window.API_BASE_URL = API_BASE_URL;

// ============================================================================
// Console Helpers (for debugging)
// ============================================================================

console.log('🚀 Awwalu Devs LMS loaded successfully!');
console.log('📚 API_BASE_URL:', API_BASE_URL || 'Same domain (relative paths)');