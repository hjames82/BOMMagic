/**
 * BOMMagic - Main JavaScript functionality
 */

// Global configuration
const CONFIG = {
    POLLING_INTERVAL: 3000, // 3 seconds
    MAX_FILE_SIZE: 25 * 1024 * 1024, // 25MB  
    ALLOWED_TYPES: ['application/pdf', 'image/png', 'image/jpeg', 'image/tiff'],
    ALLOWED_EXTENSIONS: /\.(pdf|png|jpe?g|tiff?)$/i
};

// Global state
let pollingController = null; // AbortController for fetch polling
let uploadInProgress = false;

/**
 * Initialize the application
 */
document.addEventListener('DOMContentLoaded', function() {
    initializeFeatherIcons();
    initializeTooltips();
    initializeAlerts();
    initializeFileUpload();
    initializeJobPolling();
    initializeTableSorting();
    
    // Initialize page-specific functionality
    initializePageSpecific();
});

/**
 * Initialize Feather icons
 */
function initializeFeatherIcons() {
    if (typeof feather !== 'undefined') {
        feather.replace();
    }
}

/**
 * Initialize Bootstrap tooltips
 */
function initializeTooltips() {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => 
        new bootstrap.Tooltip(tooltipTriggerEl)
    );
}

/**
 * Initialize alert auto-dismiss
 */
function initializeAlerts() {
    // Auto-dismiss alerts after 5 seconds
    document.querySelectorAll('.alert:not(.alert-permanent)').forEach(alert => {
        if (!alert.querySelector('.btn-close')) {
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 5000);
        }
    });
}

/**
 * Initialize file upload functionality
 */
function initializeFileUpload() {
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');
    
    if (!uploadZone || !fileInput || !browseBtn) return;
    
    // Click handlers
    browseBtn.addEventListener('click', () => fileInput.click());
    uploadZone.addEventListener('click', (e) => {
        if (!uploadInProgress && (e.target === uploadZone || e.target.closest('#upload-content'))) {
            fileInput.click();
        }
    });
    
    // Drag and drop handlers
    uploadZone.addEventListener('dragover', handleDragOver);
    uploadZone.addEventListener('dragleave', handleDragLeave);
    uploadZone.addEventListener('drop', handleDrop);
    
    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });
}

/**
 * Handle drag over event
 */
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    
    if (!uploadInProgress) {
        e.currentTarget.classList.add('dragover');
    }
}

/**
 * Handle drag leave event
 */
function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    
    e.currentTarget.classList.remove('dragover');
}

/**
 * Handle drop event
 */
function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    
    const uploadZone = e.currentTarget;
    uploadZone.classList.remove('dragover');
    
    if (uploadInProgress) return;
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload(files[0]);
    }
}

/**
 * Handle file upload
 */
function handleFileUpload(file) {
    // Prevent duplicate uploads
    if (uploadInProgress) {
        console.log('Upload already in progress');
        return;
    }
    
    // Validate file
    const validation = validateFile(file);
    if (!validation.valid) {
        showAlert(validation.message, 'danger');
        return;
    }
    
    uploadInProgress = true;
    
    // Disable all upload triggers
    const browseBtn = document.getElementById('browse-btn');
    const fileInput = document.getElementById('file-input');
    if (browseBtn) browseBtn.disabled = true;
    if (fileInput) fileInput.disabled = true;
    
    // Show upload progress
    showUploadProgress();
    
    // Create form data
    const formData = new FormData();
    formData.append('file', file);
    
    // Upload file
    fetch('/api/upload', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || `HTTP ${response.status}`);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.job_id) {
            showAlert('Document uploaded successfully! Processing started.', 'success');
            // Navigate to job page, do NOT call /v1/analyze
            setTimeout(() => {
                window.location.href = `/jobs/${data.job_id}`;
            }, 1000);
        } else {
            throw new Error(data.error || 'Upload failed');
        }
    })
    .catch(error => {
        console.error('Upload error:', error);
        showAlert(error.message || 'Upload failed', 'danger');
    })
    .finally(() => {
        hideUploadProgress();
        resetFileInput();
        uploadInProgress = false;
        
        // Re-enable upload triggers
        if (browseBtn) browseBtn.disabled = false;
        if (fileInput) fileInput.disabled = false;
    });
}

/**
 * Validate uploaded file
 */
function validateFile(file) {
    // Check file type
    const isValidType = CONFIG.ALLOWED_TYPES.includes(file.type) || 
                       CONFIG.ALLOWED_EXTENSIONS.test(file.name);
    
    if (!isValidType) {
        return {
            valid: false,
            message: 'Please select a valid file type (PDF, PNG, JPG, TIFF)'
        };
    }
    
    // Check file size
    if (file.size > CONFIG.MAX_FILE_SIZE) {
        return {
            valid: false,
            message: 'File size must be less than 25MB'
        };
    }
    
    return { valid: true };
}

/**
 * Show upload progress
 */
function showUploadProgress() {
    const uploadContent = document.getElementById('upload-content');
    const uploadProgress = document.getElementById('upload-progress');
    
    if (uploadContent && uploadProgress) {
        uploadContent.classList.add('d-none');
        uploadProgress.classList.remove('d-none');
        
        // Animate progress bar
        const progressBar = uploadProgress.querySelector('.progress-bar');
        if (progressBar) {
            let width = 0;
            const interval = setInterval(() => {
                width += Math.random() * 10;
                if (width >= 90) {
                    clearInterval(interval);
                    width = 90;
                }
                progressBar.style.width = width + '%';
            }, 200);
        }
    }
}

/**
 * Hide upload progress
 */
function hideUploadProgress() {
    const uploadContent = document.getElementById('upload-content');
    const uploadProgress = document.getElementById('upload-progress');
    
    if (uploadContent && uploadProgress) {
        uploadContent.classList.remove('d-none');
        uploadProgress.classList.add('d-none');
        
        // Reset progress bar
        const progressBar = uploadProgress.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.style.width = '0%';
        }
    }
}

/**
 * Reset file input
 */
function resetFileInput() {
    const fileInput = document.getElementById('file-input');
    if (fileInput) {
        fileInput.value = '';
    }
}

/**
 * Initialize job status polling
 */
function initializeJobPolling() {
    // Check if we're on job detail page
    const jobIdMatch = window.location.pathname.match(/\/jobs\/([a-f0-9-]+)/);
    if (jobIdMatch) {
        const jobId = jobIdMatch[1];
        const statusBadge = document.querySelector('.badge.bg-primary, .badge.bg-secondary');
        if (statusBadge) {
            startJobPolling(jobId);
        }
        return;
    }
    
    // Check if we're on dashboard with processing jobs
    const processingJobs = document.querySelectorAll('.badge.bg-primary, .badge.bg-secondary');
    if (processingJobs.length > 0) {
        startDashboardPolling();
    }
}

/**
 * Start polling for a specific job
 */
function startJobPolling(jobId) {
    stopPolling(); // Stop any existing polling
    
    // Create new AbortController
    pollingController = new AbortController();
    
    const poll = async () => {
        try {
            const response = await fetch(`/api/jobs/${jobId}/status`, {
                signal: pollingController.signal
            });
            
            if (!response.ok) throw new Error('Failed to fetch status');
            
            const data = await response.json();
            updateJobStatus(data);
            
            // Continue polling if still processing
            if (data.status === 'processing' || data.status === 'pending') {
                setTimeout(() => {
                    if (pollingController && !pollingController.signal.aborted) {
                        poll();
                    }
                }, CONFIG.POLLING_INTERVAL);
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Polling error:', error);
            }
        }
    };
    
    poll();
}

/**
 * Start polling for dashboard updates
 */
function startDashboardPolling() {
    stopPolling(); // Stop any existing polling
    
    // Get all job IDs that need polling
    const jobRows = document.querySelectorAll('tr[data-job-id]');
    if (jobRows.length === 0) return;
    
    pollingController = new AbortController();
    
    const poll = async () => {
        try {
            // Poll each job status
            const updates = [];
            for (const row of jobRows) {
                const jobId = row.dataset.jobId;
                const badge = row.querySelector('.badge');
                if (badge && (badge.classList.contains('bg-primary') || badge.classList.contains('bg-secondary'))) {
                    const response = await fetch(`/api/jobs/${jobId}/status`, {
                        signal: pollingController.signal
                    });
                    if (response.ok) {
                        const data = await response.json();
                        updates.push({ jobId, data, row });
                    }
                }
            }
            
            // Update UI
            updates.forEach(({ data, row }) => {
                updateJobRowStatus(row, data);
            });
            
            // Continue polling if there are still processing jobs
            const stillProcessing = document.querySelector('.badge.bg-primary, .badge.bg-secondary');
            if (stillProcessing) {
                setTimeout(() => {
                    if (pollingController && !pollingController.signal.aborted) {
                        poll();
                    }
                }, CONFIG.POLLING_INTERVAL);
            }
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Polling error:', error);
            }
        }
    };
    
    poll();
}

/**
 * Stop polling
 */
function stopPolling() {
    if (pollingController) {
        pollingController.abort();
        pollingController = null;
    }
}

/**
 * Update job status in UI
 */
function updateJobStatus(data) {
    // Update status badge
    const badge = document.querySelector('.badge.fs-6');
    if (badge && data.status) {
        badge.className = 'badge fs-6';
        badge.textContent = getStatusLabel(data.status);
        badge.classList.add(getStatusBadgeClass(data.status));
    }
    
    // Update timeline if needed
    if (data.status === 'completed' || data.status === 'failed') {
        // Refresh the timeline section
        const timelineSection = document.querySelector('.status-timeline');
        if (timelineSection) {
            // Could update timeline items here
            // For now, we'll reload BOM preview if completed
            if (data.status === 'completed' && typeof loadBOMPreview === 'function') {
                loadBOMPreview();
            }
        }
    }
}

/**
 * Update job row status in dashboard
 */
function updateJobRowStatus(row, data) {
    const badge = row.querySelector('.badge');
    if (badge && data.status) {
        badge.className = 'badge';
        badge.textContent = getStatusLabel(data.status);
        badge.classList.add(getStatusBadgeClass(data.status));
    }
    
    // Update confidence if available
    const confidenceCell = row.querySelector('[data-confidence]');
    if (confidenceCell && data.confidence_score !== undefined) {
        confidenceCell.textContent = data.confidence_score ? 
            `${Math.round(data.confidence_score * 100)}%` : '-';
    }
}

/**
 * Get status label
 */
function getStatusLabel(status) {
    const labels = {
        'completed': 'Completed',
        'processing': 'Processing',
        'pending': 'Pending',
        'requires_review': 'Needs Review',
        'failed': 'Failed',
        'reviewed': 'Reviewed'
    };
    return labels[status] || status;
}

/**
 * Get status badge class
 */
function getStatusBadgeClass(status) {
    const classes = {
        'completed': 'bg-success',
        'processing': 'bg-primary',
        'pending': 'bg-secondary',
        'requires_review': 'bg-warning text-dark',
        'failed': 'bg-danger',
        'reviewed': 'bg-info'
    };
    return classes[status] || 'bg-secondary';
}

/**
 * Initialize table sorting
 */
function initializeTableSorting() {
    const sortableHeaders = document.querySelectorAll('[data-sortable]');
    
    sortableHeaders.forEach(header => {
        header.style.cursor = 'pointer';
        header.addEventListener('click', () => {
            sortTable(header);
        });
    });
}

/**
 * Sort table by column
 */
function sortTable(header) {
    const table = header.closest('table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const column = header.cellIndex;
    const isAscending = !header.classList.contains('sort-asc');
    
    // Remove existing sort classes
    table.querySelectorAll('th').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
    });
    
    // Add sort class to current header
    header.classList.add(isAscending ? 'sort-asc' : 'sort-desc');
    
    // Sort rows
    rows.sort((a, b) => {
        const aValue = a.cells[column].textContent.trim();
        const bValue = b.cells[column].textContent.trim();
        
        // Try to parse as numbers
        const aNum = parseFloat(aValue);
        const bNum = parseFloat(bValue);
        
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAscending ? aNum - bNum : bNum - aNum;
        }
        
        // String comparison
        return isAscending ? 
            aValue.localeCompare(bValue) : 
            bValue.localeCompare(aValue);
    });
    
    // Append sorted rows
    rows.forEach(row => tbody.appendChild(row));
}

/**
 * Initialize page-specific functionality
 */
function initializePageSpecific() {
    const path = window.location.pathname;
    
    if (path.includes('/review')) {
        initializeReviewPage();
    } else if (path.includes('/jobs/')) {
        initializeJobDetailPage();
    }
}

/**
 * Initialize review page functionality
 */
function initializeReviewPage() {
    // Auto-save functionality
    let saveTimer;
    
    document.addEventListener('input', (e) => {
        if (e.target.classList.contains('editable-cell')) {
            clearTimeout(saveTimer);
            saveTimer = setTimeout(() => {
                autoSaveChanges();
            }, 2000);
        }
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.metaKey) {
            switch (e.key) {
                case 's':
                    e.preventDefault();
                    if (typeof submitReview === 'function') {
                        submitReview();
                    }
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (typeof addRow === 'function') {
                        addRow();
                    }
                    break;
            }
        }
    });
}

/**
 * Initialize job detail page functionality
 */
function initializeJobDetailPage() {
    // Auto-refresh for processing jobs
    const statusBadge = document.querySelector('.badge.bg-primary, .badge.bg-secondary');
    if (statusBadge) {
        startPolling();
    }
    
    // Initialize export buttons
    initializeExportButtons();
}

/**
 * Initialize export buttons
 */
function initializeExportButtons() {
    const exportButtons = document.querySelectorAll('[href*="/export/"]');
    
    exportButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            const originalText = button.innerHTML;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Preparing...';
            button.disabled = true;
            
            setTimeout(() => {
                button.innerHTML = originalText;
                button.disabled = false;
            }, 3000);
        });
    });
}

/**
 * Auto-save changes (for review page)
 */
function autoSaveChanges() {
    // This would implement auto-save functionality
    // For now, just show a subtle indicator that changes are saved
    showAlert('Changes auto-saved', 'info', { autoHide: true, duration: 2000 });
}

/**
 * Show alert message
 */
function showAlert(message, type = 'info', options = {}) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    
    if (options.autoHide !== false) {
        alertDiv.classList.add('alert-auto-hide');
    }
    
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Insert alert
    const target = options.target || document.querySelector('.container, .container-fluid') || document.body;
    
    if (target === document.body) {
        target.insertBefore(alertDiv, target.firstChild);
    } else {
        target.insertBefore(alertDiv, target.firstChild);
    }
    
    // Auto-dismiss
    const duration = options.duration || 5000;
    if (options.autoHide !== false) {
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, duration);
    }
    
    return alertDiv;
}

/**
 * Utility function to format file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Utility function to format date
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

/**
 * Utility function to debounce function calls
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Utility function to throttle function calls
 */
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/**
 * Export utility functions
 */
window.BOMMagic = {
    showAlert,
    formatFileSize,
    formatDate,
    debounce,
    throttle,
    startPolling,
    stopPolling
};

// Cleanup on page unload or hide
window.addEventListener('beforeunload', () => {
    stopPolling();
});

document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        stopPolling();
    } else {
        initializeJobPolling();
    }
});
