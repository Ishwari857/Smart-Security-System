// WebSocket Connection
const socket = io();

socket.on('connect', function() {
    console.log('Connected to security system');
    updateConnectionStatus(true);
});

socket.on('disconnect', function() {
    console.log('Disconnected from security system');
    updateConnectionStatus(false);
});

socket.on('new_alert', function(alert) {
    showToast(`New Alert: ${alert.type} - ${alert.description}`);
    updateAlertsList(alert);
    playAlertSound();
    updateStats();
});

function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('system-status');
    if (statusEl) {
        if (connected) {
            statusEl.className = 'status-badge online';
            statusEl.innerHTML = '<i class="fas fa-circle"></i> System Online';
        } else {
            statusEl.className = 'status-badge pending';
            statusEl.innerHTML = '<i class="fas fa-circle"></i> Reconnecting...';
        }
    }
}

function showToast(message) {
    const toast = document.getElementById('alert-toast');
    const toastMessage = document.getElementById('toast-message');
    
    if (toast && toastMessage) {
        toastMessage.textContent = message;
        toast.classList.remove('hidden');
        
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 5000);
    }
}

function updateAlertsList(alert) {
    const alertsList = document.getElementById('alerts-list');
    if (!alertsList) return;
    
    const alertItem = document.createElement('div');
    alertItem.className = 'alert-item unread';
    alertItem.innerHTML = `
        <div class="alert-icon">
            <i class="fas fa-exclamation"></i>
        </div>
        <div class="alert-content">
            <h4>${alert.type}</h4>
            <p>${alert.description}</p>
            <small>${new Date(alert.timestamp).toLocaleString()}</small>
        </div>
    `;
    
    alertsList.insertBefore(alertItem, alertsList.firstChild);
    
    // Keep only last 10 alerts in the list
    while (alertsList.children.length > 10) {
        alertsList.removeChild(alertsList.lastChild);
    }
}

function playAlertSound() {
    const audio = new Audio('/static/alert.mp3');
    audio.play().catch(e => console.log('Audio play prevented'));
}

async function updateStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('total-alerts').textContent = stats.total || 0;
        document.getElementById('pending-alerts').textContent = stats.pending || 0;
        document.getElementById('intrusions').textContent = stats.intrusions || 0;
        document.getElementById('unknown-faces').textContent = stats.unknown_faces || 0;
    } catch (error) {
        console.error('Failed to update stats:', error);
    }
}

// Load initial alerts
async function loadRecentAlerts() {
    const alertsList = document.getElementById('alerts-list');
    if (!alertsList) return;
    
    try {
        const response = await fetch('/api/alerts?limit=10');
        const alerts = await response.json();
        
        alertsList.innerHTML = '';
        
        if (alerts.length === 0) {
            alertsList.innerHTML = '<p class="no-alerts">No recent alerts</p>';
            return;
        }
        
        alerts.forEach(alert => {
            const alertItem = document.createElement('div');
            alertItem.className = `alert-item ${!alert.is_acknowledged ? 'unread' : ''}`;
            alertItem.innerHTML = `
                <div class="alert-icon">
                    <i class="fas fa-exclamation"></i>
                </div>
                <div class="alert-content">
                    <h4>${alert.alert_type}</h4>
                    <p>${alert.description}</p>
                    <small>${new Date(alert.timestamp).toLocaleString()}</small>
                </div>
            `;
            alertsList.appendChild(alertItem);
        });
    } catch (error) {
        console.error('Failed to load alerts:', error);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadRecentAlerts();
    
    // Update stats every 30 seconds
    setInterval(updateStats, 30000);
});
