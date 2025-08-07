// script.js

document.addEventListener('DOMContentLoaded', function() {

  // Smooth scrolling for internal anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      e.preventDefault();
      const targetElement = document.querySelector(this.getAttribute('href'));
      if (targetElement) {
        targetElement.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });

  // Collapse navbar menu on small screens when link clicked
  const navLinks = document.querySelectorAll('.navbar-collapse .nav-link');
  const navbarCollapse = document.querySelector('.navbar-collapse');
  navLinks.forEach(link => {
    link.addEventListener('click', function () {
      if (navbarCollapse.classList.contains('show')) {
        // Bootstrap 5 uses collapse instance; trigger collapse programmatically
        const bsCollapse = bootstrap.Collapse.getInstance(navbarCollapse);
        if (bsCollapse) {
          bsCollapse.hide();
        }
      }
    });
  });

  // Optional: Back to top button
  const backToTopBtn = document.createElement('button');
  backToTopBtn.id = 'back-to-top';
  backToTopBtn.textContent = '↑';
  Object.assign(backToTopBtn.style, {
    position: 'fixed',
    bottom: '30px',
    right: '30px',
    padding: '0.5rem 0.8rem',
    fontSize: '1.5rem',
    borderRadius: '50%',
    border: 'none',
    background: '#0d6efd',
    color: '#fff',
    cursor: 'pointer',
    display: 'none',
    zIndex: 1000,
  });
  document.body.appendChild(backToTopBtn);

  backToTopBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  window.addEventListener('scroll', () => {
    if (window.scrollY > 400) {
      backToTopBtn.style.display = 'block';
    } else {
      backToTopBtn.style.display = 'none';
    }
  });

});
