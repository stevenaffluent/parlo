// Line icons on a 24px grid, drawn for this app. Use <span data-icon="name"></span>.
const ICONS = {
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
  home: '<path d="M3.5 10.5 12 4l8.5 6.5"/><path d="M5.5 9v11h13V9"/><path d="M10 20v-5.5h4V20"/>',
  note: '<path d="M6 3h8.5L19 7.5V21H6z"/><path d="M14 3v5h5M9 12.5h7M9 16.5h5"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  speaker: '<path d="M4 9.5v5h3.5L12 18V6L7.5 9.5z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2.5"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/>',
  sliders: '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
  trash: '<path d="M4.5 7h15M10 11v6M14 11v6M6.5 7l1 13h9l1-13M9.5 7V4.5h5V7"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  download: '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
  upload: '<path d="M12 15.5V4.5M7.5 9 12 4.5 16.5 9M5 19.5h14"/>',
  export: '<path d="M12 14V4M8 8l4-4 4 4"/><path d="M5 12.5V20h14v-7.5"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  checksq: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="m8 12 3 3 5-6"/>',
  list: '<path d="M9.5 6.5H20M9.5 12H20M9.5 17.5H20"/><circle cx="5" cy="6.5" r="1"/><circle cx="5" cy="12" r="1"/><circle cx="5" cy="17.5" r="1"/>',
  listnum: '<path d="M10 6.5h10M10 12h10M10 17.5h10M4 5h1.5v4M4 9h3M4 14.5c0-1 .7-1.5 1.5-1.5S7 13.5 7 14.3c0 1.2-3 1.7-3 3.7h3"/>',
  quote: '<path d="M6 17c2-1 3-3 3-5V7H5v5h4M15 17c2-1 3-3 3-5V7h-4v5h4"/>',
  eraser: '<path d="m8.5 19.5-4-4a1.5 1.5 0 0 1 0-2.1L13.4 4.5a1.5 1.5 0 0 1 2.1 0l4 4a1.5 1.5 0 0 1 0 2.1l-9 8.9zM8.5 19.5H20M9 9l6 6"/>',
  pilcrow: '<path d="M13 4v16M17 4v16M19 4h-9.5a4 4 0 0 0 0 8H13"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8v.4"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.6 2.6 2.6 14.4 0 17M12 3.5c-2.6 2.6-2.6 14.4 0 17"/>',
  bolt: '<path d="M13 3 5.5 13.5H11L10 21l8-10.5h-5.5z"/>',
  target: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r=".8"/>',
  keyboard: '<rect x="3" y="6" width="18" height="12" rx="2.5"/><path d="M7 10h.01M10.5 10h.01M14 10h.01M17.5 10h.01M7.5 14h9"/>',
  replace: '<path d="M4 8h12l-3-3M20 16H8l3 3"/>',
  palette: '<path d="M12 3.5a8.5 8.5 0 0 0 0 17c1.4 0 2-1 1.5-2.2-.6-1.4.3-2.3 1.6-2.3h2a3.4 3.4 0 0 0 3.4-3.6A8.7 8.7 0 0 0 12 3.5z"/><circle cx="7.8" cy="11" r="1"/><circle cx="10.5" cy="7.5" r="1"/><circle cx="15" cy="8" r="1"/>',
  type: '<path d="M5 7V5h14v2M12 5v14M9 19h6"/>',
  sigma: '<path d="M17.5 6V4.5h-11l6 7.5-6 7.5h11V18"/>',
  layers: '<path d="m12 4 8.5 4.5L12 13 3.5 8.5z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5"/>',
  memory: '<rect x="3.5" y="7" width="17" height="10" rx="1.5"/><path d="M7 7v10M11 7v10M15 7v10M6 20v-3M18 20v-3"/>',
  file: '<path d="M6 3h8.5L19 7.5V21H6z"/><path d="M14 3v5h5"/>',
  sparkles: '<path d="M11 4.5 12.6 9a2 2 0 0 0 1.2 1.2l4.5 1.6-4.5 1.6a2 2 0 0 0-1.2 1.2L11 19l-1.6-4.4a2 2 0 0 0-1.2-1.2L3.7 11.8l4.5-1.6A2 2 0 0 0 9.4 9z"/><path d="M18.5 3v3.5M16.75 4.75h3.5"/>',
  mail: '<rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4 7 8 6 8-6"/>',
  briefcase: '<rect x="3.5" y="7.5" width="17" height="12" rx="2"/><path d="M9 7.5V5.5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5.5v2M3.5 13h17"/>',
  folder: '<path d="M3.5 7.5A1.5 1.5 0 0 1 5 6h4l2 2h8a1.5 1.5 0 0 1 1.5 1.5v8.5A1.5 1.5 0 0 1 19 19.5H5A1.5 1.5 0 0 1 3.5 18z"/>',
  sync: '<path d="M19.5 9A7.5 7.5 0 0 0 6 6.6L4.5 8M4.5 4v4h4M4.5 15A7.5 7.5 0 0 0 18 17.4l1.5-1.4M19.5 20v-4h-4"/>',
  key: '<circle cx="8" cy="15" r="3.5"/><path d="m10.5 12.5 8-8M16 7l2.5 2.5M14 9l2 2"/>',
  pill: '<rect x="3" y="9" width="18" height="6" rx="3"/>',
};
function icon(name, cls = "") {
  return `<svg class="i ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    if (!el.dataset.done) { el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon)); el.dataset.done = "1"; }
  });
}
