// Authentication helper functions
function checkAuth() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function makeAuthenticatedRequest(url, options = {}) {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/login';
        return;
    }
    
    const headers = {
        'Authorization': `Bearer ${token}`,
        ...options.headers
    };
    
    return fetch(url, { ...options, headers });
}

// Check authentication on page load for protected pages
if (window.location.pathname !== '/login' && window.location.pathname !== '/register' && window.location.pathname !== '/') {
    checkAuth();
}