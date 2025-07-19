// Main JavaScript for Mentor Connect

// Handle flash message close buttons
document.addEventListener('DOMContentLoaded', function() {
    // Close flash messages when clicking the close button
    const closeButtons = document.querySelectorAll('.flash-message .close-btn');
    
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            this.parentElement.style.opacity = '0';
            setTimeout(() => {
                this.parentElement.style.display = 'none';
            }, 300);
        });
    });
    
    // Auto-hide flash messages after 5 seconds
    setTimeout(() => {
        document.querySelectorAll('.flash-message').forEach(message => {
            message.style.opacity = '0';
            setTimeout(() => {
                message.style.display = 'none';
            }, 300);
        });
    }, 5000);
});