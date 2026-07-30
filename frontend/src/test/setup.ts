import '@testing-library/jest-dom/vitest'

// jsdom chưa implement scrollIntoView — Chat.tsx/Dashboard.tsx dùng để auto-scroll.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}
