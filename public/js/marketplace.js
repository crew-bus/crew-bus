/* Installer Marketplace — search & results */

(function() {
    var grid = document.getElementById('installerGrid');
    var noResults = document.getElementById('noResults');
    var loading = document.getElementById('loading');
    var resultsInfo = document.getElementById('resultsInfo');
    var resultsCount = document.getElementById('resultsCount');

    if (!grid) return;

    function showToast(msg, type) {
        var t = document.createElement('div');
        t.className = 'toast toast-' + (type || 'success');
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function() { t.remove(); }, 3000);
    }

    function renderInstallers(installers) {
        if (!installers.length) {
            grid.innerHTML = '';
            grid.style.display = 'none';
            noResults.style.display = 'block';
            resultsInfo.style.display = 'none';
            return;
        }
        noResults.style.display = 'none';
        grid.style.display = 'grid';
        resultsInfo.style.display = 'block';
        resultsCount.textContent = installers.length;

        grid.innerHTML = installers.map(function(inst) {
            var stars = '';
            for (var i = 0; i < 5; i++) {
                stars += i < Math.round(inst.rating_avg || 0) ? '&#9733;' : '&#9734;';
            }
            var specs = (inst.specialties || '').split(',').filter(Boolean).map(function(s) {
                return '<span class="spec-tag">' + s.trim().replace(/_/g, ' ') + '</span>';
            }).join('');

            return '<div class="installer-card">' +
                '<div class="installer-card-header">' +
                    '<div class="installer-card-avatar">&#9673;</div>' +
                    '<div>' +
                        '<div class="installer-card-name">' + (inst.display_name || 'Installer') + '</div>' +
                        '<div class="installer-card-meta">' +
                            '<span class="badge badge-success">&#10003; Verified</span>' +
                            '<span class="installer-card-stars">' + stars + ' ' + (inst.rating_avg || '0.0') + '</span>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
                '<div class="installer-card-specs">' + specs + '</div>' +
                '<div class="installer-card-footer">' +
                    '<span class="installer-card-location">' + (inst.postal_code || '') + ' ' + (inst.country || '') + '</span>' +
                    '<div>' +
                        '<a href="/installer/profile.html?id=' + inst.techie_id + '" class="btn btn-sm btn-outline">View Profile</a> ' +
                        '<a href="/installer/meet.html?id=' + inst.techie_id + '" class="btn btn-sm btn-primary">Meet & Greet</a>' +
                    '</div>' +
                '</div>' +
            '</div>';
        }).join('');
    }

    function searchInstallers() {
        var postal = document.getElementById('searchPostal').value.trim();
        var country = document.getElementById('searchCountry').value;
        var specialty = document.getElementById('filterSpecialty').value;
        var minRating = document.getElementById('filterRating').value;

        loading.style.display = 'block';
        noResults.style.display = 'none';
        grid.style.display = 'none';

        var params = new URLSearchParams();
        if (postal) params.set('postal_code', postal);
        if (country) params.set('country', country);
        if (specialty) params.set('specialty', specialty);
        if (minRating) params.set('min_rating', minRating);

        fetch('/api/installers?' + params.toString())
            .then(function(r) { return r.json(); })
            .then(function(data) {
                loading.style.display = 'none';
                renderInstallers(data.installers || data);
            })
            .catch(function() {
                loading.style.display = 'none';
                showToast('Failed to search installers', 'error');
            });
    }

    document.getElementById('searchBtn').addEventListener('click', searchInstallers);
    document.getElementById('browseAll').addEventListener('click', function() {
        document.getElementById('searchPostal').value = '';
        searchInstallers();
    });

    document.getElementById('searchPostal').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') searchInstallers();
    });
})();
