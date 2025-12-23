// Powerwall Controller JavaScript

// API helper
const api = {
    async get(url) {
        const response = await fetch(url);
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || 'Request failed');
        }
        return response.json();
    },

    async post(url, data = {}) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || 'Request failed');
        }
        return response.json();
    },

    async put(url, data = {}) {
        const response = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || 'Request failed');
        }
        return response.json();
    },

    async delete(url) {
        const response = await fetch(url, { method: 'DELETE' });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || 'Request failed');
        }
        return response.json();
    }
};

// Status update function
async function updateGlobalStatus() {
    try {
        const status = await api.get('/api/status');

        const dotPowerwall = document.getElementById('dot-powerwall');
        const dotMonitoring = document.getElementById('dot-monitoring');
        const dotAutomation = document.getElementById('dot-automation');

        if (dotPowerwall) {
            dotPowerwall.className = 'status-dot ' + (status.powerwall_connected ? 'connected' : 'disconnected');
        }
        if (dotMonitoring) {
            dotMonitoring.className = 'status-dot ' + (status.monitoring_running ? 'running' : 'disconnected');
        }
        if (dotAutomation) {
            dotAutomation.className = 'status-dot ' + (status.automation_running ? 'running' : 'disconnected');
        }

        return status;
    } catch (error) {
        console.error('Failed to update status:', error);
        return null;
    }
}

// Format power value
function formatPower(kw) {
    if (Math.abs(kw) >= 1) {
        return kw.toFixed(2) + ' kW';
    }
    return (kw * 1000).toFixed(0) + ' W';
}

// Format percentage
function formatPercent(value) {
    return value.toFixed(1) + '%';
}

// Format timestamp
function formatTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleTimeString();
}

function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString();
}

// Show notification
function showNotification(message, type = 'info') {
    const container = document.getElementById('notifications') || document.body;
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    alert.style.position = 'fixed';
    alert.style.top = '80px';
    alert.style.right = '20px';
    alert.style.zIndex = '1001';
    alert.style.minWidth = '300px';

    container.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

// Chart color schemes
const chartColors = {
    solar: 'rgb(255, 193, 7)',
    battery: 'rgb(40, 167, 69)',
    grid: 'rgb(108, 117, 125)',
    home: 'rgb(23, 162, 184)',
    reserve: 'rgb(220, 53, 69)',
};

// Create a real-time chart
function createRealtimeChart(ctx, datasets, options = {}) {
    const yAxisConfig = {
        display: true,
        title: { display: true, text: datasets[0].unit || 'kW' }
    };

    // Add min/max if specified
    if (options.yMin !== undefined) yAxisConfig.min = options.yMin;
    if (options.yMax !== undefined) yAxisConfig.max = options.yMax;

    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: datasets.map(ds => ({
                label: ds.label,
                data: [],
                borderColor: ds.color,
                backgroundColor: ds.color + '20',
                fill: ds.fill || false,
                tension: 0.4,
                pointRadius: 0,
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    display: true,
                    title: { display: false }
                },
                y: yAxisConfig
            },
            plugins: {
                legend: {
                    position: 'top',
                }
            }
        }
    });
}

// Update chart with new data point
function updateChart(chart, label, values, maxPoints = 60) {
    chart.data.labels.push(label);
    values.forEach((value, index) => {
        chart.data.datasets[index].data.push(value);
    });

    // Keep only last maxPoints
    if (chart.data.labels.length > maxPoints) {
        chart.data.labels.shift();
        chart.data.datasets.forEach(ds => ds.data.shift());
    }

    chart.update('none');
}

// Initialize status polling
let statusInterval;
function startStatusPolling(interval = 5000) {
    updateGlobalStatus();
    statusInterval = setInterval(updateGlobalStatus, interval);
}

function stopStatusPolling() {
    if (statusInterval) {
        clearInterval(statusInterval);
    }
}

// Start polling on page load
document.addEventListener('DOMContentLoaded', () => {
    startStatusPolling();
});

// Modal helper
function showModal(title, content, onSave = null) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-header">
            <span class="modal-title">${title}</span>
            <button class="modal-close">&times;</button>
        </div>
        <div class="modal-body">${content}</div>
        ${onSave ? `
        <div class="modal-footer">
            <button class="btn btn-secondary modal-cancel">Cancel</button>
            <button class="btn btn-primary modal-save">Save</button>
        </div>
        ` : ''}
    `;

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const close = () => overlay.remove();

    overlay.querySelector('.modal-close').addEventListener('click', close);
    overlay.querySelector('.modal-cancel')?.addEventListener('click', close);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) close();
    });

    if (onSave) {
        overlay.querySelector('.modal-save').addEventListener('click', () => {
            onSave();
            close();
        });
    }

    return { close, modal };
}
