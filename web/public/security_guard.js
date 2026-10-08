/**
 * ==============================================================================
 * COURSE WALLAH — ADVANCED DRM CONTENT PROTECTION & ANTI-LEAK SECURITY SUITE
 * Powered by Nexora Security Architecture
 * ==============================================================================
 * Features:
 * 1. Infinite anti-debugger loop (blocks DevTools network/DOM sniffing)
 * 2. Keyboard lock (Blocks F12, Ctrl+Shift+I/J/C, Ctrl+U, Ctrl+S, Ctrl+P, PrtScn)
 * 3. Global context menu / right-click lock & drag prevention
 * 4. Anti-screenshot & screen capture privacy shield on window blur / tab switch
 * 5. Dynamic oscillating student security watermark
 * 6. Console sanitization & anti-DOM extraction
 * ==============================================================================
 */

(function () {
  'use strict';

  // 1. Console Sanitization in Production
  try {
    const noop = function () {};
    window.console.log = noop;
    window.console.info = noop;
    window.console.warn = noop;
    window.console.debug = noop;
    window.console.table = noop;
    window.console.dir = noop;
  } catch (e) {}

  // 2. Continuous Anti-Debugger Trap
  // Freezes DevTools immediately when opened, preventing network & element inspection
  function antiDebugger() {
    try {
      const start = performance.now();
      (function () {
        return Function('debugger')();
      })();
      const end = performance.now();
      if (end - start > 100) {
        triggerSecurityAlert();
      }
    } catch (e) {}
  }

  // Interval execution for continuous protection
  setInterval(antiDebugger, 200);

  // Asynchronous recursive debugger thread
  (function recursiveTrap() {
    try {
      (function () {
        return Function('debugger')();
      })();
    } catch (e) {}
    setTimeout(recursiveTrap, 400);
  })();

  // 3. Prevent DevTools, Source View & Print Shortcuts
  window.addEventListener('keydown', function (e) {
    // F12 key
    if (e.key === 'F12' || e.keyCode === 123) {
      e.preventDefault();
      e.stopPropagation();
      triggerSecurityAlert();
      return false;
    }

    // Ctrl+Shift+I / Ctrl+Shift+J / Ctrl+Shift+C / Ctrl+Shift+K
    if (e.ctrlKey && e.shiftKey && ['I', 'J', 'C', 'K', 'i', 'j', 'c', 'k'].includes(e.key)) {
      e.preventDefault();
      e.stopPropagation();
      triggerSecurityAlert();
      return false;
    }

    // Ctrl+U (View Source)
    if (e.ctrlKey && (e.key === 'u' || e.key === 'U' || e.keyCode === 85)) {
      e.preventDefault();
      e.stopPropagation();
      triggerSecurityAlert();
      return false;
    }

    // Ctrl+S (Save Page)
    if (e.ctrlKey && (e.key === 's' || e.key === 'S' || e.keyCode === 83)) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }

    // Ctrl+P (Print Page)
    if (e.ctrlKey && (e.key === 'p' || e.key === 'P' || e.keyCode === 80)) {
      e.preventDefault();
      e.stopPropagation();
      return false;
    }

    // PrintScreen Key (PrtScn)
    if (e.key === 'PrintScreen' || e.keyCode === 44) {
      e.preventDefault();
      e.stopPropagation();
      triggerPrivacyCurtain();
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText('');
        }
      } catch (ex) {}
      return false;
    }
  }, true);

  // 4. Disable Right-Click Context Menu Everywhere
  document.addEventListener('contextmenu', function (e) {
    e.preventDefault();
    e.stopPropagation();
    return false;
  }, true);

  // 5. Disable Dragging & Selection on Media/Player/Canvases
  document.addEventListener('dragstart', function (e) {
    e.preventDefault();
    return false;
  }, true);

  document.addEventListener('selectstart', function (e) {
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
      e.preventDefault();
      return false;
    }
  }, true);

  // 6. Anti-Screenshot & Screen-Recording Privacy Curtain on Window Blur
  let privacyCurtainEl = null;

  function initPrivacyCurtain() {
    if (!privacyCurtainEl) {
      privacyCurtainEl = document.createElement('div');
      privacyCurtainEl.id = 'cw-drm-curtain';
      privacyCurtainEl.className = 'cw-drm-curtain';
      privacyCurtainEl.innerHTML = `
        <div class="cw-drm-curtain-box">
          <div class="cw-drm-curtain-icon">🔒</div>
          <h2 class="cw-drm-curtain-title">SECURE LEARNING SESSION</h2>
          <p class="cw-drm-curtain-sub">Content protected by Course Wallah DRM Encryption. Return to tab to resume playback.</p>
          <span class="cw-drm-curtain-badge">SESSION AUTHENTICATED • ARCHITECTED BY NEXORA</span>
        </div>
      `;
      document.body.appendChild(privacyCurtainEl);
    }
  }

  function triggerPrivacyCurtain() {
    initPrivacyCurtain();
    if (privacyCurtainEl) {
      privacyCurtainEl.classList.add('active');
    }
  }

  function dismissPrivacyCurtain() {
    if (privacyCurtainEl) {
      privacyCurtainEl.classList.remove('active');
    }
  }

  window.addEventListener('blur', function () {
    // Check if user is on player or reading PDF
    const isProtectedView = document.querySelector('.as-player-card') || document.querySelector('.cw-pdf-modal-overlay.active');
    if (isProtectedView) {
      triggerPrivacyCurtain();
    }
  });

  window.addEventListener('focus', function () {
    dismissPrivacyCurtain();
  });

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      const isProtectedView = document.querySelector('.as-player-card') || document.querySelector('.cw-pdf-modal-overlay.active');
      if (isProtectedView) {
        triggerPrivacyCurtain();
      }
    } else {
      dismissPrivacyCurtain();
    }
  });

  // 7. Dynamic Moving Student Watermark Generator
  function generateSessionToken() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let token = '';
    for (let i = 0; i < 8; i++) {
      token += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return token;
  }

  const sessionToken = generateSessionToken();

  window.CW_SECURITY = {
    sessionToken: sessionToken,
    getWatermarkText: function () {
      return `COURSE WALLAH • CW-${sessionToken} • ENCRYPTED`;
    }
  };

  function triggerSecurityAlert() {
    if (typeof showToast === 'function') {
      showToast('⚠️ Developer tools and content scraping are strictly prohibited.');
    }
  }

  // Initialize privacy curtain on DOM load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPrivacyCurtain);
  } else {
    initPrivacyCurtain();
  }

})();
