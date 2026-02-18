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

// Hero demo — infinite looping animation
(function() {
    var scene = document.querySelector('.hd-scene');
    if (!scene) return;
    var typing = document.getElementById('hdTyping');
    var bubble = document.getElementById('hdBubble');
    var input = document.getElementById('hdInput');
    if (!typing || !bubble) return;

    var messages = [
        "Hey! I\u2019m right here with you \uD83D\uDE0A What\u2019s on your mind today?",
        "Your family calendar is all set for this week \uD83D\uDCC5",
        "Time for a creative break! Want to sketch or write? \uD83C\uDFA8",
        "You\u2019ve been going strong \u2014 maybe a 5-min breather? \uD83D\uDCAA",
        "I found 3 great ideas for your project \u2728 Want to see them?"
    ];
    var msgIdx = 0;
    var inputPlaceholder = 'Type a message...';
    var cursorIv = null;

    function resetDemo() {
        // Kill any cursor blink interval
        if (cursorIv) { clearInterval(cursorIv); cursorIv = null; }
        // Reset all animated children by re-triggering CSS animations
        var animated = scene.querySelectorAll('.hd-ambient, .hd-line, .hd-boss, .hd-agent, .hd-chat, .hd-send-btn, .hd-brand, .hd-progress');
        animated.forEach(function(el) {
            el.style.animation = 'none';
            el.offsetHeight; // force reflow
        });
        // Reset text content
        typing.style.opacity = '0';
        typing.style.transition = 'none';
        bubble.style.opacity = '0';
        bubble.textContent = '';
        if (input) input.textContent = inputPlaceholder;
        // Restore animations after reflow
        requestAnimationFrame(function() {
            animated.forEach(function(el) {
                el.style.animation = '';
            });
        });
    }

    function playTyping() {
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

    // Initial play
    playTyping();

    // Loop every 17s (15s demo + 2s pause)
    setInterval(function() {
        resetDemo();
        setTimeout(playTyping, 50);
    }, 17000);
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
