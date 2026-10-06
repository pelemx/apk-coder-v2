(() => {
  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d');
  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(innerWidth * dpr);
    canvas.height = Math.floor(innerHeight * dpr);
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${innerHeight}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  addEventListener('resize', resize, { passive: true });
  addEventListener('orientationchange', resize, { passive: true });
  ['touchstart', 'touchmove', 'touchend'].forEach(type => document.addEventListener(type, e => e.preventDefault(), { passive: false }));
  resize();
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, innerWidth, innerHeight);
})();
