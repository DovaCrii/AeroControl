// R2.5: the status dropdown on the flight permission detail page posts to a
// different URL per choice (approve/deny/complete), but one <form> only has
// one action. The form's static action attribute already points at the
// first option (works with no JS at all); this only overwrites it right
// before submit to match whatever the user actually picked.
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('permission-status-form');
    var select = document.getElementById('permission-status-action');
    if (!form || !select) return;
    form.addEventListener('submit', function () {
      form.action = select.value;
    });
  });
})();
