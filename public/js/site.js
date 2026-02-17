/* crew-bus public site JS */

// Analytics — self-hosted Plausible (privacy-friendly, no cookies)
// Set window.CREW_BUS_ANALYTICS_HOST to your Plausible instance URL
(function() {
    var host = window.CREW_BUS_ANALYTICS_HOST || '';
    if (!host) return; // Skip if not configured
    var s = document.createElement('script');
    s.defer = true;
    s.setAttribute('data-domain', window.location.hostname);
    s.src = host.replace(/\/$/, '') + '/js/script.js';
    document.head.appendChild(s);
})();

// Mobile nav toggle
(function() {
    var toggle = document.getElementById('navToggle');
    var links = document.getElementById('navLinks');
    if (toggle && links) {
        toggle.addEventListener('click', function() {
            links.classList.toggle('open');
        });
        // Close on link click
        links.querySelectorAll('a').forEach(function(a) {
            a.addEventListener('click', function() {
                links.classList.remove('open');
            });
        });
    }
})();

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
    anchor.addEventListener('click', function(e) {
        var target = document.querySelector(this.getAttribute('href'));
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// Nav background on scroll
(function() {
    var nav = document.getElementById('nav');
    if (!nav) return;
    window.addEventListener('scroll', function() {
        if (window.scrollY > 20) {
            nav.style.background = 'rgba(26, 26, 46, 0.98)';
        } else {
            nav.style.background = 'rgba(26, 26, 46, 0.95)';
        }
    });
})();

// Cookie consent banner (EU compliance)
(function() {
    if (localStorage.getItem('cookie_consent')) return;
    var banner = document.createElement('div');
    banner.className = 'cookie-banner';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-label', 'Cookie consent');
    banner.innerHTML = '<p>crew-bus uses no tracking cookies. We only use essential cookies for authentication. <a href="/privacy">Privacy Policy</a></p>'
        + '<div class="cookie-actions">'
        + '<button class="btn btn-sm btn-primary" id="cookieAccept">OK</button>'
        + '</div>';
    document.body.appendChild(banner);
    document.getElementById('cookieAccept').addEventListener('click', function() {
        localStorage.setItem('cookie_consent', '1');
        banner.remove();
    });
})();

// Hero demo typing animation
(function() {
    var typing = document.getElementById('hdTyping');
    var bubble = document.getElementById('hdBubble');
    var input = document.getElementById('hdInput');
    if (!typing || !bubble) return;
    var msg = "Hey! I\u2019m right here with you \uD83D\uDE0A What\u2019s on your mind today?";
    setTimeout(function() { typing.style.opacity = '1'; typing.style.transition = 'opacity 0.3s'; }, 9000);
    setTimeout(function() {
        typing.style.opacity = '0';
        bubble.style.opacity = '1'; bubble.style.transition = 'opacity 0.3s';
        var i = 0;
        var iv = setInterval(function() {
            if (i < msg.length) { bubble.textContent = msg.substring(0, i + 1); i++; }
            else clearInterval(iv);
        }, 55);
    }, 10500);
    setTimeout(function() {
        if (!input) return;
        input.innerHTML = '<span style="color:var(--text-dim);">|</span>';
        setInterval(function() {
            var c = input.querySelector('span');
            if (c) c.style.opacity = c.style.opacity === '0' ? '1' : '0';
        }, 530);
    }, 13500);
})();

// Toast helper
window.showToast = function(msg, type) {
    var t = document.createElement('div');
    t.className = 'toast toast-' + (type || 'success');
    t.textContent = msg;
    t.setAttribute('role', 'alert');
    document.body.appendChild(t);
    setTimeout(function() { t.remove(); }, 3000);
};
