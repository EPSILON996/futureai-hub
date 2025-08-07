// script.js

// Utility debounce function
function debounce(func, wait = 250) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

// Display toast notification (Bootstrap 5)
// Accept type: 'success', 'danger', 'warning', 'info'
// Replace flash messages from server with nicer toasts
function showToast(message, type = 'info', duration = 3500) {
  const containerId = 'toast-container';
  let container = document.getElementById(containerId);
  if (!container) {
    container = document.createElement('div');
    container.id = containerId;
    container.style.position = 'fixed';
    container.style.top = '1rem';
    container.style.right = '1rem';
    container.style.zIndex = 1080; // above navbar etc
    document.body.appendChild(container);
  }

  // Create toast element
  const toastEl = document.createElement('div');
  toastEl.className = `toast align-items-center text-bg-${type} border-0`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');
  toastEl.setAttribute('aria-atomic', 'true');

  const toastBody = document.createElement('div');
  toastBody.className = 'd-flex';
  const messageDiv = document.createElement('div');
  messageDiv.className = 'toast-body';
  messageDiv.textContent = message;

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'btn-close btn-close-white me-2 m-auto';
  closeButton.setAttribute('data-bs-dismiss', 'toast');
  closeButton.setAttribute('aria-label', 'Close');

  toastBody.appendChild(messageDiv);
  toastBody.appendChild(closeButton);
  toastEl.appendChild(toastBody);
  container.appendChild(toastEl);

  const bsToast = new bootstrap.Toast(toastEl, { delay: duration });
  bsToast.show();

  // Remove from DOM after hidden
  toastEl.addEventListener('hidden.bs.toast', () => {
    toastEl.remove();
  });
}

// Smooth scrolling for internal anchor links (#id)
function enableSmoothScrolling() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', event => {
      // Only local anchors, and element exists
      const targetId = anchor.getAttribute('href').substring(1);
      const targetElem = document.getElementById(targetId);
      if (targetElem) {
        event.preventDefault();
        targetElem.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });
}

// Navbar auto-collapse on small screen when nav-link clicked
function setupNavbarAutoCollapse() {
  const navbarCollapse = document.getElementById('nvb');
  if (!navbarCollapse) return;

  const bsCollapse = new bootstrap.Collapse(navbarCollapse, { toggle: false });

  navbarCollapse.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth < 992) { // Bootstrap lg breakpoint
        bsCollapse.hide();
      }
    });
  });
}

// Newsletter subscription form AJAX handler with enhanced feedback
function setupSubscribeForm() {
  const form = document.getElementById('subscribe-form');
  const messageDiv = document.getElementById('subscribe-message');
  if (!form || !messageDiv) return;

  form.addEventListener('submit', e => {
    e.preventDefault();

    const emailInput = form.querySelector('input[name="email"]');
    const email = emailInput.value.trim();
    messageDiv.style.color = ''; // reset

    // Simple email validation (regex)
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      messageDiv.style.color = 'red';
      messageDiv.textContent = 'Please enter a valid email address.';
      emailInput.focus();
      return;
    }

    // Disable inputs/buttons during request
    form.querySelectorAll('input, button').forEach(el => el.disabled = true);
    messageDiv.textContent = 'Subscribing…';

    fetch('/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ email })
    })
      .then(resp => resp.json())
      .then(data => {
        if (data.status === 'success') {
          messageDiv.style.color = 'green';
          form.reset();
          showToast(data.message, 'success');
        } else {
          messageDiv.style.color = 'red';
          showToast(data.message || 'Subscription failed.', 'danger');
        }
        messageDiv.textContent = data.message || '';
      })
      .catch(() => {
        messageDiv.style.color = 'red';
        messageDiv.textContent = 'An error occurred. Please try again.';
        showToast('Error subscribing to newsletter. Please try again later.', 'danger');
      })
      .finally(() => {
        form.querySelectorAll('input, button').forEach(el => el.disabled = false);
      });
  });
}

// Optional debounced search suggestions (example)
function setupSearchSuggestions() {
  const searchInput = document.querySelector('input[name="q"]');
  if (!searchInput) return;

  // You'll want to augment your Flask backend to support suggestion API for this
  const suggestionBox = document.createElement('div');
  suggestionBox.style.position = 'absolute';
  suggestionBox.style.background = '#fff';
  suggestionBox.style.border = '1px solid #ddd';
  suggestionBox.style.borderRadius = '0.25rem';
  suggestionBox.style.width = searchInput.offsetWidth + 'px';
  suggestionBox.style.maxHeight = '200px';
  suggestionBox.style.overflowY = 'auto';
  suggestionBox.style.zIndex = 1100;
  suggestionBox.style.display = 'none';
  searchInput.parentNode.appendChild(suggestionBox);

  const fetchSuggestions = debounce(query => {
    if (!query.trim()) {
      suggestionBox.style.display = 'none';
      return;
    }

    fetch(`/search_suggestions?q=${encodeURIComponent(query)}`)
      .then(res => res.json())
      .then(suggestions => {
        if (!suggestions.length) {
          suggestionBox.style.display = 'none';
          return;
        }
        suggestionBox.innerHTML = '';
        suggestions.forEach(item => {
          const div = document.createElement('div');
          div.textContent = item.title;
          div.style.padding = '0.25rem 0.75rem';
          div.style.cursor = 'pointer';
          div.addEventListener('click', () => {
            window.location.href = `/post/${item.id}`;
          });
          suggestionBox.appendChild(div);
        });
        suggestionBox.style.display = 'block';
      })
      .catch(() => {
        suggestionBox.style.display = 'none';
      });
  }, 300);

  searchInput.addEventListener('input', e => {
    fetchSuggestions(e.target.value);
  });

  document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !suggestionBox.contains(e.target)) {
      suggestionBox.style.display = 'none';
    }
  });
}

// Initialize all frontend scripts
document.addEventListener('DOMContentLoaded', () => {
  enableSmoothScrolling();
  setupNavbarAutoCollapse();
  setupSubscribeForm();

  // Optional: Uncomment to enable search suggestions and implement backend
  // setupSearchSuggestions();

  // Replace inline alerts with toasts for flash messages if needed
  // If your server sends flash messages as Bootstrap alerts, you can enhance them here if desired.
});

