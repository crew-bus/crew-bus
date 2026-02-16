/* ================================================================
   crew-bus Command Center - JavaScript
   ================================================================ */

// --- Toast Notifications ---
function showToast(message, type) {
    type = type || 'success';
    var existing = document.querySelector('.toast');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(function() { toast.remove(); }, 300);
    }, 3000);
}

// --- Confirm Modal ---
var pendingAction = null;

function showConfirm(title, message, callback) {
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').textContent = message;
    document.getElementById('confirmModal').classList.add('show');
    pendingAction = callback;
}

function closeModal() {
    document.getElementById('confirmModal').classList.remove('show');
    pendingAction = null;
}

function confirmAction() {
    if (pendingAction) {
        pendingAction();
    }
    closeModal();
}

// Close modal on overlay click
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay')) {
        closeModal();
    }
});

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeModal();
});

// --- Trust Score ---
function updateTrust() {
    // Try overview slider first, then settings slider
    var slider = document.getElementById('trustSlider') || document.getElementById('settingsTrust');
    if (!slider) return;
    var score = parseInt(slider.value);

    fetch('/api/trust', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({score: score})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            showToast('Trust score updated to ' + score + ' (' + data.autonomy.level + ')', 'success');
            // Update both sliders if they exist
            var s1 = document.getElementById('trustSlider');
            var s2 = document.getElementById('settingsTrust');
            if (s1) s1.value = score;
            if (s2) s2.value = score;
        } else {
            showToast(data.error || 'Failed to update', 'error');
        }
    })
    .catch(function(err) {
        showToast('Network error: ' + err, 'error');
    });
}

// --- Burnout Score ---
function updateBurnout() {
    var slider = document.getElementById('burnoutSlider') || document.getElementById('settingsBurnout');
    if (!slider) return;
    var score = parseInt(slider.value);

    fetch('/api/burnout', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({score: score})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            var level = score <= 3 ? 'low' : score <= 6 ? 'moderate' : 'high';
            showToast('Burnout score updated to ' + score + ' (' + level + ')', 'success');
        } else {
            showToast(data.error || 'Failed to update', 'error');
        }
    })
    .catch(function(err) {
        showToast('Network error: ' + err, 'error');
    });
}

// --- Agent Actions ---
function agentAction(action, agentId) {
    fetch('/api/' + action + '/' + agentId, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'}
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            showToast('Agent ' + action + 'd successfully', 'success');
            setTimeout(function() { location.reload(); }, 500);
        } else {
            showToast(data.error || 'Action failed', 'error');
        }
    })
    .catch(function(err) {
        showToast('Network error: ' + err, 'error');
    });
}

// --- Send Message (from human) ---
function sendMessage() {
    var to = document.getElementById('sendTo').value;
    var subject = document.getElementById('sendSubject').value;
    var body = document.getElementById('sendBody').value;
    var type = document.getElementById('sendType').value;
    var priority = document.getElementById('sendPriority').value;

    if (!to || !subject) {
        showToast('Recipient and subject are required', 'error');
        return;
    }

    fetch('/api/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({to: to, subject: subject, body: body, type: type, priority: priority})
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            showToast('Message sent to ' + to, 'success');
            document.getElementById('sendSubject').value = '';
            document.getElementById('sendBody').value = '';
        } else {
            showToast(data.error || 'Failed to send', 'error');
        }
    })
    .catch(function(err) {
        showToast('Network error: ' + err, 'error');
    });
}
