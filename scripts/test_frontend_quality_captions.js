const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('web/public/app.js', 'utf8');

// Mock DOM & window
global.window = {
  location: { hash: '', origin: 'http://127.0.0.1:8000' },
  addEventListener: () => {}
};
global.elements = {};
global.document = {
  getElementById: (id) => {
    if (!global.elements[id]) {
      global.elements[id] = {
        innerHTML: '',
        classList: {
          classes: new Set(),
          add(c) { this.classes.add(c); },
          remove(c) { this.classes.delete(c); },
          contains(c) { return this.classes.has(c); },
          toggle(c) { if (this.classes.has(c)) this.classes.delete(c); else this.classes.add(c); }
        }
      };
    }
    return global.elements[id];
  },
  addEventListener: () => {}
};

// Evaluate in global context
vm.runInThisContext(code);

console.log('=== 1. TEST QUALITY EXAMPLE A (720p, 480p, 360p) ===');
global.elements['quality-options-list'] = { innerHTML: '' };
renderQualityMenu(['hd720', 'large', 'medium']);
let htmlA = global.elements['quality-options-list'].innerHTML;
console.log('HTML A:\n' + htmlA);
if (htmlA.includes('4K') || htmlA.includes('2K') || htmlA.includes('1080p')) {
  throw new Error('Failed A: contains fake qualities!');
}
if (!htmlA.includes('720p') || !htmlA.includes('480p') || !htmlA.includes('360p')) {
  throw new Error('Failed A: missing supported qualities!');
}

console.log('\n=== 2. TEST QUALITY EXAMPLE B (2160p, 1440p, 1080p, 720p) ===');
global.elements['quality-options-list'] = { innerHTML: '' };
renderQualityMenu(['hd2160', 'hd1440', 'hd1080', 'hd720']);
let htmlB = global.elements['quality-options-list'].innerHTML;
console.log('HTML B:\n' + htmlB);
if (!htmlB.includes('2160p') || !htmlB.includes('1440p') || !htmlB.includes('1080p') || !htmlB.includes('720p')) {
  throw new Error('Failed B: missing 4K/2K/1080p/720p!');
}

console.log('\n=== 3. TEST QUALITY EXAMPLE C (EMPTY / NONE) ===');
global.elements['quality-options-list'] = { innerHTML: '' };
renderQualityMenu([]);
let htmlC = global.elements['quality-options-list'].innerHTML;
console.log('HTML C:\n' + htmlC);
if (!htmlC.includes('Auto (Adaptive Bitrate)') || htmlC.includes('2160p') || htmlC.includes('720p')) {
  throw new Error('Failed C: should only be auto!');
}

console.log('\n=== 4. TEST CAPTIONS (NO TRACKS) ===');
State.ytPlayer = { getOption: () => [] };
State.isPlayerReady = true;
let ccBtn = document.getElementById('btn-captions');
ccBtn.classList.add('hidden');
detectCaptionTracks();
if (!ccBtn.classList.contains('hidden')) throw new Error('CC button should be hidden when tracklist is empty');
if (State.hasCaptions !== false) throw new Error('State.hasCaptions should be false');
console.log('Captions correctly hidden.');

console.log('\n=== 5. TEST CAPTIONS (GENUINE TRACKS) ===');
State.ytPlayer = {
  getOption: () => [
    { languageCode: 'en', displayName: 'English' },
    { languageCode: 'hi', displayName: 'Hindi' }
  ]
};
detectCaptionTracks();
if (ccBtn.classList.contains('hidden')) throw new Error('CC button should be visible when tracks exist');
if (State.hasCaptions !== true) throw new Error('State.hasCaptions should be true');
let capHtml = document.getElementById('captions-options-list').innerHTML;
console.log('Captions HTML:\n' + capHtml);
if (!capHtml.includes('English') || !capHtml.includes('Hindi')) {
  throw new Error('Missing English/Hindi tracks in captions menu');
}

console.log('\nALL FRONTEND QUALITY AND CAPTION TESTS PASSED (100%)!');
