/* Installer Dashboard — tab switching, data loading */

(function() {
    // Tab switching
    document.querySelectorAll('.dash-tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.dash-tab').forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.dash-panel').forEach(function(p) { p.classList.remove('active'); });
            tab.classList.add('active');
            document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
        });
    });

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            btn.parentElement.querySelectorAll('.filter-btn').forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');
        });
    });

    // Profile form save
    var profileForm = document.getElementById('profileForm');
    if (profileForm) {
        profileForm.addEventListener('submit', function(e) {
            e.preventDefault();
            var token = localStorage.getItem('installer_token');
            if (!token) { window.location.href = '/auth/login.html?type=installer'; return; }

            var specialties = [];
            profileForm.querySelectorAll('input[name="specialties"]:checked').forEach(function(cb) {
                specialties.push(cb.value);
            });

            fetch('/api/installers/profile', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify({
                    display_name: document.getElementById('profName').value,
                    bio: document.getElementById('profBio').value,
                    specialties: specialties.join(','),
                    postal_code: document.getElementById('profPostal').value,
                    service_radius: document.getElementById('profRadius').value,
                }),
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.ok) showToast('Profile saved');
                else showToast(data.error || 'Save failed', 'error');
            })
            .catch(function() { showToast('Network error', 'error'); });
        });
    }

    // Buy permit
    var buyBtn = document.getElementById('buyPermit');
    if (buyBtn) {
        buyBtn.addEventListener('click', function() {
            var token = localStorage.getItem('installer_token');
            if (!token) { window.location.href = '/auth/login.html?type=installer'; return; }
            buyBtn.disabled = true;
            buyBtn.textContent = 'Processing...';
            fetch('/api/installers/permits/purchase', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                buyBtn.disabled = false;
                buyBtn.textContent = 'Buy Permit ($25)';
                if (data.url) window.location.href = data.url;
                else if (data.error) showToast(data.error, 'error');
            })
            .catch(function() {
                buyBtn.disabled = false;
                buyBtn.textContent = 'Buy Permit ($25)';
                showToast('Network error', 'error');
            });
        });
    }

    // Logout
    var logoutLink = document.getElementById('logoutLink');
    if (logoutLink) {
        logoutLink.addEventListener('click', function(e) {
            e.preventDefault();
            localStorage.removeItem('installer_token');
            window.location.href = '/installer';
        });
    }

    function showToast(msg, type) {
        var t = document.createElement('div');
        t.className = 'toast toast-' + (type || 'success');
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function() { t.remove(); }, 3000);
    }
})();
