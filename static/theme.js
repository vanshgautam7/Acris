// Theme toggle - persists to localStorage
(function() {
  const STORAGE_KEY = 'acris-theme';

  function getStoredTheme() {
    return localStorage.getItem(STORAGE_KEY) || 'dark';
  }

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);

    // Update all toggle icons on the page
    document.querySelectorAll('.theme-toggle').forEach(function(btn) {
      var icon = btn.querySelector('i');
      if (icon) {
        icon.className = theme === 'light' ? 'fa fa-moon-o' : 'fa fa-sun-o';
      }
    });
  }

  // Apply stored theme immediately (before paint)
  setTheme(getStoredTheme());

  // Bind toggle buttons after DOM is ready
  document.addEventListener('DOMContentLoaded', function() {
    // Set initial icon state
    var currentTheme = getStoredTheme();
    document.querySelectorAll('.theme-toggle').forEach(function(btn) {
      var icon = btn.querySelector('i');
      if (icon) {
        icon.className = currentTheme === 'light' ? 'fa fa-moon-o' : 'fa fa-sun-o';
      }

      btn.addEventListener('click', function() {
        var next = getStoredTheme() === 'dark' ? 'light' : 'dark';
        setTheme(next);
      });
    });
  });
})();
