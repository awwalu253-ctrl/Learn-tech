// ============================================================================
// Awwalu Devs - Main JavaScript
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // ========================================================================
    // Navbar Toggle (Mobile)
    // ========================================================================
    
    const navbarToggle = document.getElementById('navbarToggle');
    const navbarMenu = document.getElementById('navbarMenu');
    
    if (navbarToggle && navbarMenu) {
        navbarToggle.addEventListener('click', function() {
            navbarMenu.classList.toggle('active');
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
            setTimeout(() => msg.remove(), 400);
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
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.dark_mode) {
                    document.documentElement.setAttribute('data-theme', 'dark');
                } else {
                    document.documentElement.setAttribute('data-theme', 'light');
                }
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
            const fileName = this.files[0]?.name || 'No file chosen';
            const label = this.nextElementSibling;
            if (label) {
                label.textContent = fileName;
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
                questions.forEach(q => {
                    const selected = q.querySelector('input[type="radio"]:checked');
                    if (!selected) allAnswered = false;
                });
                submitBtn.disabled = !allAnswered;
                if (allAnswered) {
                    submitBtn.textContent = 'Submit Quiz';
                    submitBtn.classList.remove('btn-disabled');
                } else {
                    submitBtn.textContent = `Answer ${questions.length - form.querySelectorAll('.quiz-question:not(:has(input:checked))').length} more question(s)`;
                    submitBtn.classList.add('btn-disabled');
                }
            };
            
            questions.forEach(q => {
                q.querySelectorAll('input[type="radio"]').forEach(radio => {
                    radio.addEventListener('change', checkAllAnswered);
                });
            });
            
            checkAllAnswered();
        }
    });
    
    // ========================================================================
    // Search / Filter
    // ========================================================================
    
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const query = this.value.toLowerCase();
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
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab-btn').forEach(b => {
                b.classList.remove('active');
            });
            document.getElementById(target)?.classList.add('active');
            this.classList.add('active');
        });
    });
});

// ============================================================================
// Utility: Copy to Clipboard
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
// Utility: Show Flash Message
// ============================================================================

function showFlash(message, type = 'info') {
    const container = document.querySelector('.flash-container');
    if (!container) return;
    
    const icons = {
        success: 'check-circle',
        error: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    
    const flash = document.createElement('div');
    flash.className = `flash-message flash-${type} animate-slide-down`;
    flash.innerHTML = `
        <i class="fas fa-${icons[type] || 'info-circle'}"></i>
        ${message}
        <button class="flash-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    
    container.appendChild(flash);
    
    setTimeout(() => {
        flash.style.opacity = '0';
        flash.style.transform = 'translateX(20px)';
        setTimeout(() => flash.remove(), 400);
    }, 4000);
}