/* Job Board — listing, posting, search */

(function() {
    // --- Job Listing Page ---
    var jobGrid = document.getElementById('jobGrid');
    var noJobs = document.getElementById('noJobs');
    var jobLoading = document.getElementById('jobLoading');
    var jobsInfo = document.getElementById('jobsInfo');
    var jobsCount = document.getElementById('jobsCount');

    if (jobGrid) {
        function renderJobs(jobs) {
            if (!jobs.length) {
                jobGrid.innerHTML = '';
                jobGrid.style.display = 'none';
                noJobs.style.display = 'block';
                jobsInfo.style.display = 'none';
                return;
            }
            noJobs.style.display = 'none';
            jobGrid.style.display = 'grid';
            jobsInfo.style.display = 'block';
            jobsCount.textContent = jobs.length;

            jobGrid.innerHTML = jobs.map(function(job) {
                var tags = (job.needs || '').split(',').filter(Boolean).map(function(n) {
                    return '<span class="spec-tag">' + n.trim().replace(/_/g, ' ') + '</span>';
                }).join('');
                var statusBadge = '<span class="badge badge-' +
                    (job.status === 'open' ? 'success' : job.status === 'claimed' ? 'warning' : 'info') +
                    '">' + job.status + '</span>';

                return '<div class="job-card">' +
                    '<div class="job-card-main">' +
                        '<div class="job-card-title">' + (job.title || 'Untitled Job') + ' ' + statusBadge + '</div>' +
                        '<div class="job-card-desc">' + (job.description || '').substring(0, 200) + '</div>' +
                        '<div class="job-card-tags">' + tags + '</div>' +
                        '<div class="job-card-meta">' +
                            '<span>' + (job.postal_code || '') + ' ' + (job.country || '') + '</span>' +
                            '<span>' + (job.urgency || 'standard') + '</span>' +
                            '<span>' + timeAgo(job.created_at) + '</span>' +
                        '</div>' +
                    '</div>' +
                    '<div class="job-card-side">' +
                        '<div class="job-card-budget">' + (job.budget || 'Negotiable') + '</div>' +
                        (job.status === 'open' ? '<a href="/jobs/detail.html?id=' + job.id + '" class="btn btn-sm btn-primary">View / Claim</a>' :
                         '<a href="/jobs/detail.html?id=' + job.id + '" class="btn btn-sm btn-outline">View</a>') +
                    '</div>' +
                '</div>';
            }).join('');
        }

        function searchJobs() {
            var postal = document.getElementById('jobSearch').value.trim();
            var urgency = document.getElementById('jobUrgency').value;
            var status = document.getElementById('jobStatus').value;

            jobLoading.style.display = 'block';
            noJobs.style.display = 'none';
            jobGrid.style.display = 'none';

            var params = new URLSearchParams();
            if (postal) params.set('postal_code', postal);
            if (urgency) params.set('urgency', urgency);
            if (status && status !== 'all') params.set('status', status);

            fetch('/api/jobs?' + params.toString())
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    jobLoading.style.display = 'none';
                    renderJobs(data.jobs || data || []);
                })
                .catch(function() {
                    jobLoading.style.display = 'none';
                    showToast('Failed to load jobs', 'error');
                });
        }

        var searchBtn = document.getElementById('jobSearchBtn');
        if (searchBtn) searchBtn.addEventListener('click', searchJobs);

        // Auto-load open jobs
        searchJobs();
    }

    // --- Job Post Form ---
    var jobForm = document.getElementById('jobForm');
    var jobSuccess = document.getElementById('jobSuccess');

    if (jobForm) {
        jobForm.addEventListener('submit', function(e) {
            e.preventDefault();

            var title = document.getElementById('jobTitle').value.trim();
            var desc = document.getElementById('jobDesc').value.trim();
            var postal = document.getElementById('jobPostal').value.trim();
            var country = document.getElementById('jobCountry').value;

            // Validation
            var valid = true;
            if (!title) { document.getElementById('jobTitleError').textContent = 'Required'; valid = false; }
            else document.getElementById('jobTitleError').textContent = '';
            if (!desc) { document.getElementById('jobDescError').textContent = 'Required'; valid = false; }
            else document.getElementById('jobDescError').textContent = '';
            if (!valid) return;

            if (!document.getElementById('jobTerms').checked) {
                alert('Please accept the Terms of Service.');
                return;
            }

            var needs = [];
            jobForm.querySelectorAll('input[name="needs"]:checked').forEach(function(cb) {
                needs.push(cb.value);
            });

            var payload = {
                title: title,
                description: desc,
                needs: needs.join(','),
                postal_code: postal,
                country: country,
                urgency: document.getElementById('jobUrgency') ? document.getElementById('jobUrgency').value : 'standard',
                budget: document.getElementById('jobBudget') ? document.getElementById('jobBudget').value : 'negotiable',
                contact_name: document.getElementById('jobName').value.trim(),
                contact_email: document.getElementById('jobEmail').value.trim(),
            };

            var btn = document.getElementById('postJobBtn');
            btn.disabled = true;
            btn.textContent = 'Posting...';

            fetch('/api/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.error) {
                    btn.disabled = false;
                    btn.textContent = 'Post Job';
                    alert('Error: ' + data.error);
                    return;
                }
                jobForm.style.display = 'none';
                jobSuccess.style.display = 'block';
            })
            .catch(function() {
                btn.disabled = false;
                btn.textContent = 'Post Job';
                alert('Network error. Please try again.');
            });
        });

        var postAnother = document.getElementById('postAnother');
        if (postAnother) {
            postAnother.addEventListener('click', function(e) {
                e.preventDefault();
                jobForm.reset();
                jobForm.style.display = 'block';
                jobSuccess.style.display = 'none';
                document.getElementById('postJobBtn').disabled = false;
                document.getElementById('postJobBtn').textContent = 'Post Job';
            });
        }
    }

    function timeAgo(dateStr) {
        if (!dateStr) return '';
        var now = new Date();
        var then = new Date(dateStr);
        var diff = Math.floor((now - then) / 1000);
        if (diff < 60) return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    function showToast(msg, type) {
        var t = document.createElement('div');
        t.className = 'toast toast-' + (type || 'success');
        t.textContent = msg;
        document.body.appendChild(t);
        setTimeout(function() { t.remove(); }, 3000);
    }
})();
