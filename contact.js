// The contact address is in the page only encoded, in the button's
// `data-contact` (`.eleventy.js`'s `contactCode` filter), so a crawler
// collecting addresses for spam does not find it. It is decoded and turned
// into a link only when a visitor asks for it. The button is hidden in the
// markup, so a page without this script shows its <noscript> line instead
// of a button that does nothing.
for (const button of document.querySelectorAll('[data-contact]')) {
  button.hidden = false;
  button.addEventListener(
    'click',
    () => {
      const address = atob(button.dataset.contact);
      const link = document.createElement('a');
      link.href = `mailto:${address}`;
      link.textContent = address;
      button.replaceWith(link);
      link.focus();
    },
    { once: true },
  );
}
