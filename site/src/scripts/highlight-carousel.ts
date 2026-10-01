const carousel = document.querySelector<HTMLElement>('[data-highlight-carousel]');
if (carousel) {
  const slides = Array.from(carousel.querySelectorAll<HTMLElement>('[data-highlight-slide]'));
  const pages = Array.from(carousel.querySelectorAll<HTMLButtonElement>('[data-carousel-page]'));
  const play = carousel.querySelector<HTMLButtonElement>('.carousel-play');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  let current = 0;
  let paused = motion.matches;
  let hovered = false;
  let focused = false;
  let timer: ReturnType<typeof setInterval> | undefined;
  let transition = 0;
  function show(index: number, announce = false) {
    if (!slides.length) return;
    const next = (index + slides.length) % slides.length;
    if (next === current) return;
    const previous = current;
    const direction = index < current ? -1 : 1;
    const run = ++transition;
    slides.forEach((slide, i) => {
      slide.getAnimations({ subtree: true }).forEach(animation => animation.cancel());
      slide.hidden = i !== previous && i !== next;
      slide.inert = i !== next;
      slide.setAttribute('aria-hidden', String(i !== next));
    });
    current = next;
    const outgoing = slides[previous];
    const incoming = slides[next];
    if (motion.matches) {
      outgoing.hidden = true;
    } else {
      const exit = outgoing.animate([
        { opacity: 1, transform: 'translateX(0)', filter: 'blur(0)' },
        { opacity: 0, transform: `translateX(${-direction * 28}px)`, filter: 'blur(3px)' },
      ], { duration: 220, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
      exit.finished.then(() => { if (transition === run) outgoing.hidden = true; }).catch(() => {});
      Array.from(incoming.children).forEach((child, i) => {
        child.animate([
          { opacity: 0, transform: `translate(${direction * 42}px, 10px)`, filter: 'blur(4px)' },
          { opacity: 1, transform: 'translate(0, 0)', filter: 'blur(0)' },
        ], { duration: 620, delay: 120 + i * 75, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'both' });
      });
      const mark = document.querySelector('.opening-mark');
      mark?.animate([
        { transform: 'translateY(0) scale(1)' },
        { transform: 'translateY(-4px) scale(1.025)', offset: .4 },
        { transform: 'translateY(0) scale(1)' },
      ], { duration: 850, easing: 'cubic-bezier(.22,1,.36,1)' });
    }
    pages.forEach((page, i) => page.setAttribute('aria-pressed', String(i === current)));
    const status = carousel!.querySelector<HTMLElement>('.carousel-status');
    if (status) { status.setAttribute('aria-live', announce ? 'polite' : 'off'); status.textContent = `${current + 1} / ${slides.length}`; }
  }
  function schedule() {
    clearInterval(timer);
    if (play) { play.textContent = paused ? '播放' : '暂停'; play.setAttribute('aria-label', paused ? '开始自动轮播' : '暂停自动轮播'); }
    if (slides.length > 1 && !paused && !hovered && !focused && !document.hidden) timer = setInterval(() => show(current + 1), 8000);
  }
  function select(index: number) { paused = true; show(index, true); schedule(); }
  carousel.querySelector('[data-carousel-prev]')?.addEventListener('click', () => select(current - 1));
  carousel.querySelector('[data-carousel-next]')?.addEventListener('click', () => select(current + 1));
  pages.forEach((page, i) => page.addEventListener('click', () => select(i)));
  play?.addEventListener('click', () => { paused = !paused; schedule(); });
  carousel.addEventListener('mouseenter', () => { hovered = true; schedule(); });
  carousel.addEventListener('mouseleave', () => { hovered = false; schedule(); });
  carousel.addEventListener('focusin', () => { focused = true; schedule(); });
  carousel.addEventListener('focusout', event => { focused = carousel.contains(event.relatedTarget as Node | null); schedule(); });
  carousel.addEventListener('keydown', event => {
    if (event.target instanceof HTMLInputElement) return;
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); select(current + (event.key === 'ArrowRight' ? 1 : -1)); }
  });
  document.addEventListener('visibilitychange', schedule);
  motion.addEventListener('change', () => { if (motion.matches) paused = true; schedule(); });
  schedule();
}
