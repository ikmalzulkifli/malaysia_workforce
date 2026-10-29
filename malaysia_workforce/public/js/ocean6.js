(() => {
  if (window.frappe?.boot?.ocean6_branding === true || document.currentScript?.dataset.ocean6Brand === 'true') {
    document.documentElement.dataset.ocean6Brand = 'true';
  }
})();
