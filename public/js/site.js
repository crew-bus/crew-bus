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

// Magical floating particles — ambient snowflake / firefly effect
(function() {
    var container = document.getElementById('magicParticles');
    if (!container) return;

    var sizes = ['mp-sm', 'mp-sm', 'mp-sm', 'mp-md', 'mp-md', 'mp-lg'];
    var colors = ['', '', '', '', 'mp-teal', 'mp-purple', 'mp-blue', 'mp-pink', 'mp-orange', 'mp-green'];
    var PARTICLE_COUNT = 35;

    function spawnParticle() {
        var p = document.createElement('div');
        var size = sizes[Math.floor(Math.random() * sizes.length)];
        var color = colors[Math.floor(Math.random() * colors.length)];
        p.className = 'magic-particle ' + size + (color ? ' ' + color : '');
        // Random horizontal position
        p.style.left = Math.random() * 100 + '%';
        // Random drift direction
        var drift = (Math.random() - 0.5) * 120;
        p.style.setProperty('--drift', drift + 'px');
        // Random duration (slow, relaxing 12-28s)
        var dur = 12 + Math.random() * 16;
        p.style.animationDuration = dur + 's';
        // Random start delay for initial spread
        p.style.animationDelay = Math.random() * dur + 's';
        container.appendChild(p);
        return p;
    }

    // Spawn initial batch
    for (var i = 0; i < PARTICLE_COUNT; i++) {
        spawnParticle();
    }
})();

// Hero demo — infinite looping animation via DOM clone restart
(function() {
    var sceneWrap = document.querySelector('.hero-demo');
    if (!sceneWrap) return;

    var messages = [
        "Hey! I\u2019m right here with you \uD83D\uDE0A What\u2019s on your mind today?",
        "Your family calendar is all set for this week \uD83D\uDCC5",
        "Time for a creative break! Want to sketch or write? \uD83C\uDFA8",
        "You\u2019ve been going strong \u2014 maybe a 5-min breather? \uD83D\uDCAA",
        "I found 3 great ideas for your project \u2728 Want to see them?"
    ];
    var msgIdx = 0;
    // Save the original scene HTML for clean resets
    var originalScene = sceneWrap.querySelector('.hd-scene');
    var sceneHTML = originalScene.outerHTML;
    var cursorIv = null;

    function playTyping() {
        var typing = document.getElementById('hdTyping');
        var bubble = document.getElementById('hdBubble');
        var input = document.getElementById('hdInput');
        if (!typing || !bubble) return;
        var msg = messages[msgIdx % messages.length];
        msgIdx++;
        // Show typing dots at 9s
        setTimeout(function() {
            typing.style.transition = 'opacity 0.3s';
            typing.style.opacity = '1';
        }, 9000);
        // Show bubble with typewriter at 10.5s
        setTimeout(function() {
            typing.style.opacity = '0';
            bubble.style.opacity = '1';
            bubble.style.transition = 'opacity 0.3s';
            var i = 0;
            var iv = setInterval(function() {
                if (i < msg.length) { bubble.textContent = msg.substring(0, i + 1); i++; }
                else clearInterval(iv);
            }, 55);
        }, 10500);
        // Show cursor blink at 13.5s
        setTimeout(function() {
            if (!input) return;
            input.innerHTML = '<span style="color:var(--text-dim);">|</span>';
            cursorIv = setInterval(function() {
                var c = input.querySelector('span');
                if (c) c.style.opacity = c.style.opacity === '0' ? '1' : '0';
            }, 530);
        }, 13500);
    }

    function resetAndReplay() {
        // Kill cursor interval
        if (cursorIv) { clearInterval(cursorIv); cursorIv = null; }
        // Replace scene with fresh clone (resets all CSS animations)
        var oldScene = sceneWrap.querySelector('.hd-scene');
        if (oldScene) {
            var temp = document.createElement('div');
            temp.innerHTML = sceneHTML;
            var newScene = temp.firstChild;
            oldScene.parentNode.replaceChild(newScene, oldScene);
        }
        // Start typing animation on fresh DOM
        playTyping();
    }

    // Initial play
    playTyping();

    // Loop every 17s (15s demo + 2s pause)
    setInterval(resetAndReplay, 17000);
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
