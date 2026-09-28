/* SkillSprint AI — Client-side utilities (Phase 4) */

"use strict";

// ── Auto-dismiss alerts ──
document.querySelectorAll('.alert.auto-dismiss').forEach(el => {
  setTimeout(() => el.classList.add('d-none'), 5000);
});

// ── Animate elements on scroll ──
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(
    entries => entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('animate-fade'); }),
    { threshold: 0.1 }
  );
  document.querySelectorAll('.stat-card, .card').forEach(el => observer.observe(el));
}

// ── Progress bar animation trigger ──
document.querySelectorAll('.progress-bar').forEach(bar => {
  const target = bar.style.width;
  bar.style.width = '0%';
  requestAnimationFrame(() => {
    setTimeout(() => { bar.style.width = target; }, 100);
  });
});

// ── Tab memory (persist active tab in sessionStorage) ──
document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tab => {
  const key = `tab:${location.pathname}`;
  tab.addEventListener('shown.bs.tab', () => sessionStorage.setItem(key, tab.getAttribute('data-bs-target')));
  const saved = sessionStorage.getItem(key);
  if (saved && tab.getAttribute('data-bs-target') === saved) {
    new bootstrap.Tab(tab).show();
  }
});

// ── Report export link updater ──
function updateExportLinks(type) {
  ['csv', 'pdf', 'excel'].forEach(fmt => {
    const el = document.getElementById(`export-${fmt}-btn`);
    if (el) el.href = `/reports/export/${fmt}?type=${type}`;
  });
}

// ── Search form: update URL without page reload ──
const searchForm = document.getElementById('search-form');
if (searchForm) {
  searchForm.addEventListener('submit', e => {
    e.preventDefault();
    const q = document.getElementById('search-query')?.value.trim();
    if (!q) return;
    window.location.href = `/search?q=${encodeURIComponent(q)}&entity=${document.getElementById('search-entity')?.value || ''}&department=${document.getElementById('search-department')?.value || ''}`;
  });
}

// ── Confirm before destructive actions ──
document.querySelectorAll('[data-confirm]').forEach(el => {
  el.addEventListener('click', e => {
    if (!confirm(el.dataset.confirm)) e.preventDefault();
  });
});
