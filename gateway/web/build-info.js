'use strict';

(async function showBuildVersion() {
  const label = document.querySelector('#gateway-version');
  if (!label) return;
  try {
    const response = await fetch('/build-info.json', {cache: 'no-store'});
    if (!response.ok) throw new Error('Build metadata unavailable');
    const info = await response.json();
    if (!/^dev\.[a-f0-9]{12}$/.test(info.version) ||
        !/^[a-f0-9]{64}$/.test(info.source_sha256) ||
        info.version !== 'dev.' + info.source_sha256.slice(0, 12)) {
      throw new Error('Invalid build metadata');
    }
    label.textContent = '版本 ' + info.version;
    label.title = '应用源码 SHA-256：' + info.source_sha256;
  } catch {
    label.textContent = '版本信息不可用';
  }
})();
