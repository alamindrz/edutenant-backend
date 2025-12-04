// static/js/attendance.js
// Attendance-specific JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize attendance functionality
    
    // Auto-update attendance table with HTMX
    const dateFilter = document.querySelector('input[name="date"]');
    if (dateFilter) {
        dateFilter.addEventListener('change', function() {
            const form = this.closest('form');
            if (form) {
                form.submit();
            }
        });
    }
    
    // Teacher sign-in/out confirmation
    const signButtons = document.querySelectorAll('a[href*="signin"], a[href*="signout"]');
    signButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const action = this.href.includes('signin') ? 'sign in' : 'sign out';
            const teacherName = this.closest('tr').querySelector('strong').textContent;
            
            if (!confirm(`Are you sure you want to ${action} ${teacherName}?`)) {
                e.preventDefault();
            }
        });
    });
    
    // Real-time clock for attendance
    function updateClock() {
        const now = new Date();
        const clockElement = document.getElementById('current-time');
        if (clockElement) {
            clockElement.textContent = now.toLocaleTimeString();
        }
    }
    
    // Update clock every second
    setInterval(updateClock, 1000);
    updateClock();
    
    // Bulk attendance actions
    const markAllPresent = document.getElementById('markAllPresent');
    const markAllAbsent = document.getElementById('markAllAbsent');
    
    if (markAllPresent) {
        markAllPresent.addEventListener('click', function() {
            document.querySelectorAll('.attendance-status').forEach(select => {
                select.value = 'present';
            });
        });
    }
    
    if (markAllAbsent) {
        markAllAbsent.addEventListener('click', function() {
            document.querySelectorAll('.attendance-status').forEach(select => {
                select.value = 'absent';
            });
        });
    }
    
    // Attendance statistics calculator
    function calculateAttendanceStats() {
        const presentCount = document.querySelectorAll('.attendance-status[value="present"]').length;
        const absentCount = document.querySelectorAll('.attendance-status[value="absent"]').length;
        const totalCount = document.querySelectorAll('.attendance-status').length;
        
        const presentPercentage = totalCount > 0 ? (presentCount / totalCount * 100).toFixed(1) : 0;
        
        // Update stats display if exists
        const statsElement = document.getElementById('attendance-stats');
        if (statsElement) {
            statsElement.innerHTML = `
                <strong>Present:</strong> ${presentCount} | 
                <strong>Absent:</strong> ${absentCount} | 
                <strong>Rate:</strong> ${presentPercentage}%
            `;
        }
    }
    
    // Recalculate stats when attendance status changes
    document.querySelectorAll('.attendance-status').forEach(select => {
        select.addEventListener('change', calculateAttendanceStats);
    });
    
    calculateAttendanceStats(); // Initial calculation
});