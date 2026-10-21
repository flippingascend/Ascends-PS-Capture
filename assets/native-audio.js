/* Decode ListenFree audio through Ascend's native Qt player. No downloads or account APIs. */
(function () {
  'use strict';
  if (!['listenfree.in', 'www.listenfree.in'].includes(location.hostname)) return;
  if (window.__ascendNativeAudio) return;
  const states = new Map(), elements = new Map(), pending = [];
  let counter = 0, bridge = null;
  const originalSetAttribute = Element.prototype.setAttribute;
  const originalRemoveAttribute = Element.prototype.removeAttribute;
  const originalGetAttribute = Element.prototype.getAttribute;
  function state(el) {
    let s = states.get(el);
    if (!s) {
      s = {id: String(++counter), src: '', time: 0, duration: NaN, paused: true,
           ended: false, volume: 1, muted: false, rate: 1, ready: 0,
           progress: 0, seekable: false, error: null};
      states.set(el, s); elements.set(s.id, el);
    }
    return s;
  }
  function send(el, action, value) {
    const args = [state(el).id, action, JSON.stringify(value)];
    if (bridge) bridge.command(...args); else pending.push(args);
  }
  function event(el, name) { el.dispatchEvent(new Event(name)); }
  function range(end, active) {
    return {length: active ? 1 : 0,
      start(i) { if (i !== 0 || !active) throw new DOMException('Index out of range', 'IndexSizeError'); return 0; },
      end(i) { if (i !== 0 || !active) throw new DOMException('Index out of range', 'IndexSizeError'); return end; }};
  }
  function source(el, value) {
    const s = state(el);
    let url = '';
    if (value) { try { url = new URL(String(value), document.baseURI).href; } catch (_) {} }
    if (url === s.src) return;
    s.src = url; s.time = 0; s.duration = NaN; s.ready = 0; s.ended = false; s.error = null;
    send(el, 'source', url);
    event(el, url ? 'loadstart' : 'emptied');
  }
  function update(id, raw) {
    const el = elements.get(id);
    if (!el) return;
    const s = state(el), data = JSON.parse(raw);
    switch (data.event) {
      case 'metadata': {
        const first = s.ready === 0;
        s.duration = data.duration > 0 ? data.duration : NaN;
        s.seekable = !!data.seekable; s.ready = 3;
        if (first) { event(el, 'loadedmetadata'); event(el, 'loadeddata'); }
        event(el, 'durationchange'); event(el, 'canplay'); event(el, 'canplaythrough');
        break;
      }
      case 'time': s.time = data.position; event(el, 'timeupdate'); break;
      case 'buffer': s.progress = data.progress; event(el, 'progress'); break;
      case 'playing': s.paused = false; s.ended = false; event(el, 'playing'); break;
      case 'pause':
        if (!s.paused) { s.paused = true; event(el, 'pause'); }
        break;
      case 'seeked': s.time = data.position; event(el, 'timeupdate'); event(el, 'seeked'); break;
      case 'waiting': event(el, 'waiting'); break;
      case 'ended': s.paused = true; s.ended = true; event(el, 'timeupdate'); event(el, 'ended'); break;
      case 'error': s.error = {code: 4, message: data.message}; s.paused = true; event(el, 'error'); break;
    }
  }
  const proto = HTMLAudioElement.prototype;
  const properties = {
    src: {get() { return state(this).src; }, set(v) { source(this, v); }},
    currentSrc: {get() { return state(this).src; }},
    currentTime: {get() { return state(this).time; }, set(v) {
      if (!Number.isFinite(Number(v)) || Number(v) < 0) return;
      state(this).time = Number(v); event(this, 'seeking'); send(this, 'seek', Number(v));
    }},
    duration: {get() { return state(this).duration; }},
    paused: {get() { return state(this).paused; }},
    ended: {get() { return state(this).ended; }},
    readyState: {get() { return state(this).ready; }},
    networkState: {get() { return state(this).src ? 2 : 0; }},
    error: {get() { return state(this).error; }},
    seeking: {get() { return false; }},
    buffered: {get() { const s=state(this); return range(s.duration*s.progress, s.progress>0 && Number.isFinite(s.duration)); }},
    seekable: {get() { const s=state(this); return range(s.duration, s.seekable && Number.isFinite(s.duration)); }},
    volume: {get() { return state(this).volume; }, set(v) {
      const n = Math.max(0, Math.min(1, Number(v)));
      if (!Number.isFinite(n)) return;
      state(this).volume = n; send(this, 'volume', n); event(this, 'volumechange');
    }},
    muted: {get() { return state(this).muted; }, set(v) {
      state(this).muted = !!v; send(this, 'muted', !!v); event(this, 'volumechange');
    }},
    playbackRate: {get() { return state(this).rate; }, set(v) {
      if (Number.isFinite(Number(v))) { state(this).rate = Number(v); send(this, 'rate', Number(v)); event(this, 'ratechange'); }
    }}
  };
  for (const [key, descriptor] of Object.entries(properties))
    Object.defineProperty(proto, key, {...descriptor, configurable: true});
  proto.play = function () {
    const s = state(this);
    if (!s.src) return Promise.reject(new DOMException('No audio source', 'NotSupportedError'));
    s.paused = false; s.ended = false; send(this, 'play', null); event(this, 'play');
    return Promise.resolve();
  };
  proto.pause = function () {
    const s = state(this), changed = !s.paused;
    s.paused = true; send(this, 'pause', null);
    if (changed) event(this, 'pause');
  };
  proto.load = function () {
    const s = state(this);
    send(this, 'load', null);
    if (s.src) event(this, 'loadstart');
  };
  const nativeCanPlay = HTMLMediaElement.prototype.canPlayType;
  proto.canPlayType = function (type) {
    if (/audio\/(mp4|aac|x-m4a)/i.test(type)) return 'probably';
    return nativeCanPlay.call(this, type);
  };
  Element.prototype.setAttribute = function (key, value) {
    if (this instanceof HTMLAudioElement && key.toLowerCase() === 'src') { source(this, value); return; }
    return originalSetAttribute.call(this, key, value);
  };
  Element.prototype.removeAttribute = function (key) {
    if (this instanceof HTMLAudioElement && key.toLowerCase() === 'src') { source(this, ''); return; }
    return originalRemoveAttribute.call(this, key);
  };
  Element.prototype.getAttribute = function (key) {
    if (this instanceof HTMLAudioElement && key.toLowerCase() === 'src') return state(this).src || null;
    return originalGetAttribute.call(this, key);
  };
  window.__ascendNativeAudio = {active: true, count: () => elements.size};
  new QWebChannel(qt.webChannelTransport, function (channel) {
    bridge = channel.objects.ascendAudio;
    bridge.updated.connect(update);
    for (const args of pending.splice(0)) bridge.command(...args);
    window.__ascendNativeAudio.ready = true;
  });
})();
