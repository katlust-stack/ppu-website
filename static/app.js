// Archive page: filtering and search
(function () {
  'use strict';

  const searchInput = document.getElementById('search-input');
  const subspecialtySelect = document.getElementById('subspecialty-filter');
  const evidenceSelect = document.getElementById('evidence-filter');
  const resultsCount = document.getElementById('results-count');
  const articleList = document.getElementById('article-list');

  if (!searchInput || !articleList) return;

  const cards = Array.from(articleList.querySelectorAll('.article-card'));

  function applyFilters() {
    const query = searchInput.value.toLowerCase().trim();
    const subspecialty = subspecialtySelect.value;
    const evidence = evidenceSelect.value;
    let visible = 0;

    cards.forEach(function (card) {
      const title = (card.dataset.title || '').toLowerCase();
      const bottomLine = (card.dataset.bottomline || '').toLowerCase();
      const tags = card.dataset.tags || '';
      const evidenceTags = card.dataset.evidence || '';

      let show = true;

      if (query && !title.includes(query) && !bottomLine.includes(query)) {
        show = false;
      }
      if (subspecialty && !tags.includes(subspecialty)) {
        show = false;
      }
      if (evidence && !evidenceTags.includes(evidence)) {
        show = false;
      }

      card.style.display = show ? '' : 'none';
      if (show) visible++;
    });

    if (resultsCount) {
      resultsCount.textContent = visible + ' of ' + cards.length + ' articles';
    }

    var noResults = document.getElementById('no-results');
    if (noResults) {
      noResults.style.display = visible === 0 ? '' : 'none';
    }
  }

  searchInput.addEventListener('input', applyFilters);
  subspecialtySelect.addEventListener('change', applyFilters);
  evidenceSelect.addEventListener('change', applyFilters);

  // Initial count
  applyFilters();
})();

// Expand/collapse article cards
document.addEventListener('click', function (e) {
  var header = e.target.closest('.article-card-header');
  if (!header) return;
  var card = header.closest('.article-card');
  if (card) {
    card.classList.toggle('expanded');
  }
});
