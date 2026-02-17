/* Installer Signup — multi-step form with KYC hashing */

(function() {
    var form = document.getElementById('signupForm');
    var success = document.getElementById('signupSuccess');
    if (!form) return;

    var currentStep = 1;
    var idHash = null;

    function showStep(n) {
        currentStep = n;
        document.querySelectorAll('.form-step').forEach(function(s) {
            s.classList.toggle('active', parseInt(s.dataset.step) === n);
        });
        document.querySelectorAll('.step-dot').forEach(function(d) {
            var step = parseInt(d.dataset.step);
            d.classList.toggle('active', step === n);
            d.classList.toggle('done', step < n);
        });
    }

    function validateStep(n) {
        var step = form.querySelector('.form-step[data-step="' + n + '"]');
        var valid = true;
        step.querySelectorAll('[required]').forEach(function(input) {
            var error = document.getElementById(input.id + 'Error');
            if (!input.value.trim()) {
                input.classList.add('error');
                if (error) error.textContent = 'This field is required';
                valid = false;
            } else {
                input.classList.remove('error');
                if (error) error.textContent = '';
            }
        });
        // Email format check
        var email = step.querySelector('#email');
        if (email && email.value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
            email.classList.add('error');
            var err = document.getElementById('emailError');
            if (err) err.textContent = 'Invalid email address';
            valid = false;
        }
        return valid;
    }

    // Navigation buttons
    form.addEventListener('click', function(e) {
        if (e.target.classList.contains('next-step')) {
            if (validateStep(currentStep)) {
                showStep(currentStep + 1);
            }
        }
        if (e.target.classList.contains('prev-step')) {
            showStep(currentStep - 1);
        }
    });

    // File upload + SHA-256 hashing
    var uploadArea = document.getElementById('uploadArea');
    var uploadInput = document.getElementById('idUpload');
    var uploadPreview = document.getElementById('uploadPreview');
    var uploadFileName = document.getElementById('uploadFileName');
    var uploadHashEl = document.getElementById('uploadHash');
    var removeBtn = document.getElementById('removeUpload');

    if (uploadArea) {
        uploadArea.addEventListener('click', function() { uploadInput.click(); });
        uploadArea.addEventListener('dragover', function(e) { e.preventDefault(); uploadArea.style.borderColor = 'var(--info)'; });
        uploadArea.addEventListener('dragleave', function() { uploadArea.style.borderColor = ''; });
        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            uploadArea.style.borderColor = '';
            if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
        });
    }

    if (uploadInput) {
        uploadInput.addEventListener('change', function() {
            if (this.files.length) handleFile(this.files[0]);
        });
    }

    if (removeBtn) {
        removeBtn.addEventListener('click', function() {
            idHash = null;
            uploadInput.value = '';
            uploadArea.style.display = 'block';
            uploadPreview.style.display = 'none';
        });
    }

    function handleFile(file) {
        if (file.size > 10 * 1024 * 1024) {
            alert('File too large. Max 10MB.');
            return;
        }
        uploadFileName.textContent = file.name;

        // SHA-256 hash client-side
        var reader = new FileReader();
        reader.onload = function(e) {
            crypto.subtle.digest('SHA-256', e.target.result).then(function(hash) {
                var hex = Array.from(new Uint8Array(hash)).map(function(b) {
                    return b.toString(16).padStart(2, '0');
                }).join('');
                idHash = hex;
                uploadHashEl.textContent = 'SHA-256: ' + hex.substring(0, 16) + '...';
                uploadArea.style.display = 'none';
                uploadPreview.style.display = 'flex';
            });
        };
        reader.readAsArrayBuffer(file);
    }

    // Form submission
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        if (!document.getElementById('termsAccept').checked) {
            alert('Please accept the Terms of Service and Privacy Policy.');
            return;
        }
        if (!idHash) {
            alert('Please upload your ID for verification.');
            return;
        }

        var specialties = [];
        form.querySelectorAll('input[name="specialties"]:checked').forEach(function(cb) {
            specialties.push(cb.value);
        });

        var payload = {
            display_name: document.getElementById('displayName').value.trim(),
            email: document.getElementById('email').value.trim(),
            phone: document.getElementById('phone').value.trim(),
            bio: document.getElementById('bio').value.trim(),
            specialties: specialties.join(','),
            country: document.getElementById('country').value,
            postal_code: document.getElementById('postalCode').value.trim(),
            service_radius: document.getElementById('serviceRadius').value,
            service_type: form.querySelector('input[name="service_type"]:checked').value,
            id_type: document.getElementById('idType').value,
            id_hash: idHash,
        };

        var btn = document.getElementById('submitBtn');
        btn.disabled = true;
        btn.textContent = 'Submitting...';

        fetch('/api/installers/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) {
                btn.disabled = false;
                btn.textContent = 'Submit Application';
                alert('Error: ' + data.error);
                return;
            }
            form.style.display = 'none';
            document.querySelector('.step-indicator').style.display = 'none';
            document.getElementById('successEmail').textContent = payload.email;
            success.style.display = 'block';
        })
        .catch(function() {
            btn.disabled = false;
            btn.textContent = 'Submit Application';
            alert('Network error. Please try again.');
        });
    });
})();
